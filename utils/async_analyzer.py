#!/usr/bin/env python3
"""
Async Analyzer - Background Tier 3 process manager for Memory Guard.

Enables non-blocking code quality analysis by running Claude CLI in background:
- Spawns background process for Tier 3 analysis
- Writes results to guard analysis log
- Provides notification mechanism for completed analyses
- Manages process lifecycle and cleanup
"""

import json
import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


@dataclass
class AsyncAnalysisRequest:
    """A request for async Tier 3 analysis."""

    request_id: str
    file_path: str
    tool_name: str
    code_info: str
    project_root: Path
    mcp_collection: str
    created_at: float = field(default_factory=time.time)
    prompt: str = ""
    callback: Callable[[dict[str, Any]], None] | None = None


@dataclass
class AsyncAnalysisResult:
    """Result from async Tier 3 analysis."""

    request_id: str
    success: bool
    decision: str  # "approve", "block", "error"
    reason: str
    analysis: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    completed_at: float = field(default_factory=time.time)


class AsyncAnalyzerManager:
    """Manages background Tier 3 analysis processes.

    Spawns analysis as subprocess, logs results, notifies on completion.
    Thread-safe for concurrent analysis requests.
    """

    # Singleton instance
    _instance: Optional["AsyncAnalyzerManager"] = None
    _lock = threading.Lock()

    # Configuration
    MAX_CONCURRENT = 3  # Max concurrent background analyses
    ANALYSIS_TIMEOUT = 60  # Seconds before killing analysis
    LOG_RETENTION_HOURS = 24  # Hours to keep analysis logs

    def __init__(self, project_root: Path | None = None):
        """Initialize async analyzer manager.

        Args:
            project_root: Default project root for log storage
        """
        self._project_root = project_root or Path.cwd()
        self._active_processes: dict[str, subprocess.Popen] = {}
        self._results: dict[str, AsyncAnalysisResult] = {}
        self._callbacks: dict[str, Callable] = {}
        self._request_counter = 0
        self._process_lock = threading.Lock()
        self._log_path: Path | None = None

    @classmethod
    def get_instance(cls, project_root: Path | None = None) -> "AsyncAnalyzerManager":
        """Get singleton instance."""
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(project_root)
            elif project_root and cls._instance._project_root != project_root:
                # Update project root if changed
                cls._instance._project_root = project_root
            return cls._instance

    def _get_log_path(self, project_root: Path) -> Path:
        """Get path to analysis log file."""
        log_dir = project_root / "logs"
        log_dir.mkdir(exist_ok=True)
        return log_dir / "guard-analysis.log"

    def _generate_request_id(self) -> str:
        """Generate unique request ID."""
        with self._process_lock:
            self._request_counter += 1
            return f"async_{int(time.time())}_{self._request_counter}"

    def submit_analysis(
        self,
        file_path: str,
        tool_name: str,
        code_info: str,
        prompt: str,
        project_root: Path,
        mcp_collection: str,
        callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> str | None:
        """Submit code for async Tier 3 analysis.

        Args:
            file_path: File being analyzed
            tool_name: Tool operation (Write, Edit, etc.)
            code_info: Formatted code info
            prompt: Full Claude CLI prompt
            project_root: Project root path
            mcp_collection: MCP collection prefix
            callback: Optional callback on completion

        Returns:
            Request ID if submitted, None if queue full
        """
        with self._process_lock:
            # Check capacity
            if len(self._active_processes) >= self.MAX_CONCURRENT:
                self._log_event(
                    project_root,
                    "QUEUE_FULL",
                    f"Cannot submit analysis for {file_path} - queue full",
                )
                return None

            # Create request
            request_id = self._generate_request_id()
            request = AsyncAnalysisRequest(
                request_id=request_id,
                file_path=file_path,
                tool_name=tool_name,
                code_info=code_info,
                project_root=project_root,
                mcp_collection=mcp_collection,
                prompt=prompt,
                callback=callback,
            )

            # Store callback
            if callback:
                self._callbacks[request_id] = callback

            # Spawn background process
            self._spawn_analysis(request)

            return request_id

    def _spawn_analysis(self, request: AsyncAnalysisRequest) -> None:
        """Spawn background analysis subprocess."""
        try:
            # Build command
            allowed_tools = (
                f"Read,LS,Bash(ls:*),Glob,Grep,WebFetch,WebSearch,"
                f"{request.mcp_collection}search_similar,"
                f"{request.mcp_collection}read_graph,"
                f"{request.mcp_collection}get_implementation,"
                f"mcp__github__*"
            )

            cmd = [
                "claude",
                "-p",
                "--output-format",
                "json",
                "--max-turns",
                "30",
                "--model",
                "sonnet",
                "--allowedTools",
                allowed_tools,
            ]

            # Start process
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(request.project_root),
                start_new_session=True,  # Detach from parent
            )

            self._active_processes[request.request_id] = process

            # Log submission
            self._log_event(
                request.project_root,
                "SUBMITTED",
                f"Analysis {request.request_id} for {request.file_path}",
            )

            # Start monitoring thread
            monitor_thread = threading.Thread(
                target=self._monitor_process,
                args=(request, process),
                daemon=True,
            )
            monitor_thread.start()

        except Exception as e:
            self._log_event(
                request.project_root,
                "SPAWN_ERROR",
                f"Failed to spawn analysis for {request.file_path}: {e}",
            )

    def _monitor_process(
        self, request: AsyncAnalysisRequest, process: subprocess.Popen
    ) -> None:
        """Monitor a running analysis process."""
        start_time = time.time()
        result: AsyncAnalysisResult

        try:
            # Send prompt and wait for completion
            stdout, stderr = process.communicate(
                input=request.prompt, timeout=self.ANALYSIS_TIMEOUT
            )

            latency_ms = (time.time() - start_time) * 1000

            # Parse result
            if process.returncode == 0:
                try:
                    result = self._parse_claude_response(
                        request.request_id, stdout, latency_ms
                    )
                except Exception as e:
                    result = AsyncAnalysisResult(
                        request_id=request.request_id,
                        success=False,
                        decision="error",
                        reason=f"Parse error: {e}",
                        latency_ms=latency_ms,
                    )
            else:
                result = AsyncAnalysisResult(
                    request_id=request.request_id,
                    success=False,
                    decision="error",
                    reason=f"CLI failed with code {process.returncode}: {stderr[:200]}",
                    latency_ms=latency_ms,
                )

        except subprocess.TimeoutExpired:
            process.kill()
            result = AsyncAnalysisResult(
                request_id=request.request_id,
                success=False,
                decision="error",
                reason=f"Analysis timed out after {self.ANALYSIS_TIMEOUT}s",
                latency_ms=(time.time() - start_time) * 1000,
            )

        except Exception as e:
            result = AsyncAnalysisResult(
                request_id=request.request_id,
                success=False,
                decision="error",
                reason=f"Monitor error: {e}",
                latency_ms=(time.time() - start_time) * 1000,
            )

        # Store result and cleanup
        with self._process_lock:
            self._results[request.request_id] = result
            if request.request_id in self._active_processes:
                del self._active_processes[request.request_id]

        # Log result
        self._log_analysis_result(request, result)

        # Trigger callback
        if request.request_id in self._callbacks:
            try:
                callback = self._callbacks.pop(request.request_id)
                callback(
                    {
                        "request_id": result.request_id,
                        "success": result.success,
                        "decision": result.decision,
                        "reason": result.reason,
                        "latency_ms": result.latency_ms,
                    }
                )
            except Exception:
                pass  # Ignore callback errors

    def _parse_claude_response(
        self, request_id: str, stdout: str, latency_ms: float
    ) -> AsyncAnalysisResult:
        """Parse Claude CLI response."""
        stdout = stdout.strip()

        # Handle CLI wrapper format
        if stdout.startswith('{"type":"result"'):
            cli_response = json.loads(stdout)

            # Check for errors
            if (
                cli_response.get("is_error")
                or cli_response.get("subtype") == "error_max_turns"
            ):
                return AsyncAnalysisResult(
                    request_id=request_id,
                    success=False,
                    decision="error",
                    reason=f"CLI error: {cli_response}",
                    latency_ms=latency_ms,
                )

            result_content = cli_response.get("result", "")

            # Extract JSON from markdown
            if "```json" in result_content:
                json_start = result_content.find("```json\n") + 8
                json_end = result_content.find("\n```", json_start)
                inner_json = result_content[json_start:json_end]
            else:
                inner_json = result_content

            response = json.loads(inner_json)
        else:
            response = json.loads(stdout)

        # Process response
        has_issues = response.get("hasIssues", False)
        decision = "block" if has_issues else "approve"
        reason = response.get("reason", "Analysis complete")

        return AsyncAnalysisResult(
            request_id=request_id,
            success=True,
            decision=decision,
            reason=reason,
            analysis=response,
            latency_ms=latency_ms,
        )

    def _log_event(self, project_root: Path, event_type: str, message: str) -> None:
        """Log an event to the analysis log."""
        try:
            log_path = self._get_log_path(project_root)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            with open(log_path, "a") as f:
                f.write(f"[{timestamp}] {event_type}: {message}\n")

        except Exception:
            pass  # Silently fail logging

    def _log_analysis_result(
        self, request: AsyncAnalysisRequest, result: AsyncAnalysisResult
    ) -> None:
        """Log detailed analysis result."""
        try:
            log_path = self._get_log_path(request.project_root)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

            log_entry = f"""
{'=' * 60}
[{timestamp}] ASYNC ANALYSIS COMPLETE
{'=' * 60}
Request ID: {result.request_id}
File: {request.file_path}
Tool: {request.tool_name}
Decision: {result.decision.upper()}
Success: {result.success}
Latency: {result.latency_ms:.0f}ms
Reason: {result.reason}
"""

            if result.analysis:
                # Add key fields from analysis
                if result.analysis.get("dependents_count"):
                    log_entry += f"Dependents: {result.analysis['dependents_count']}\n"
                if result.analysis.get("similar_code"):
                    log_entry += f"Similar Code: {result.analysis['similar_code']}\n"
                if result.analysis.get("test_coverage"):
                    log_entry += f"Test Coverage: {result.analysis['test_coverage']}\n"
                if result.analysis.get("quality_markers"):
                    log_entry += (
                        f"Quality Markers: {result.analysis['quality_markers']}\n"
                    )

            log_entry += f"{'=' * 60}\n"

            with open(log_path, "a") as f:
                f.write(log_entry)

        except Exception:
            pass

    def get_result(self, request_id: str) -> AsyncAnalysisResult | None:
        """Get result for a completed analysis.

        Args:
            request_id: Request ID from submit_analysis

        Returns:
            AsyncAnalysisResult if complete, None if still running or not found
        """
        with self._process_lock:
            return self._results.get(request_id)

    def is_running(self, request_id: str) -> bool:
        """Check if an analysis is still running."""
        with self._process_lock:
            return request_id in self._active_processes

    def cancel(self, request_id: str) -> bool:
        """Cancel a running analysis.

        Args:
            request_id: Request ID to cancel

        Returns:
            True if cancelled, False if not found or already complete
        """
        with self._process_lock:
            if request_id not in self._active_processes:
                return False

            process = self._active_processes[request_id]
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                del self._active_processes[request_id]
                return True
            except Exception:
                return False

    def get_pending_results(
        self, since_timestamp: float | None = None
    ) -> list[AsyncAnalysisResult]:
        """Get all completed results, optionally since a timestamp.

        Args:
            since_timestamp: Only return results completed after this time

        Returns:
            List of completed analysis results
        """
        with self._process_lock:
            results = []
            for result in self._results.values():
                if since_timestamp is None or result.completed_at >= since_timestamp:
                    results.append(result)
            return results

    def get_stats(self) -> dict[str, Any]:
        """Get manager statistics."""
        with self._process_lock:
            return {
                "active_processes": len(self._active_processes),
                "completed_results": len(self._results),
                "max_concurrent": self.MAX_CONCURRENT,
                "timeout_seconds": self.ANALYSIS_TIMEOUT,
            }

    def cleanup_old_results(self, max_age_hours: float = 24.0) -> int:
        """Remove old results from memory.

        Args:
            max_age_hours: Maximum age in hours

        Returns:
            Number of results removed
        """
        cutoff = time.time() - (max_age_hours * 3600)

        with self._process_lock:
            old_keys = [
                key
                for key, result in self._results.items()
                if result.completed_at < cutoff
            ]
            for key in old_keys:
                del self._results[key]
            return len(old_keys)


def check_pending_analyses(project_root: Path) -> list[dict[str, Any]]:
    """Check for pending async analysis results.

    Convenience function to check log for recent results.

    Args:
        project_root: Project root path

    Returns:
        List of recent analysis results from log
    """
    manager = AsyncAnalyzerManager.get_instance(project_root)
    return [
        {
            "request_id": r.request_id,
            "decision": r.decision,
            "reason": r.reason,
            "latency_ms": r.latency_ms,
        }
        for r in manager.get_pending_results()
    ]
