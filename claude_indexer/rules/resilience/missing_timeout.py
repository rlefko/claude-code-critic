"""
Missing timeout detection rule.

Detects network calls and external operations that don't specify
timeout parameters, which can lead to hung processes or deadlocks.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    from ..base import Finding


class MissingTimeoutRule(BaseRule):
    """Detect network calls without timeout configuration.

    Identifies HTTP requests, API calls, and external operations
    that don't specify timeout parameters, which can cause
    applications to hang indefinitely.
    """

    # Network call patterns without timeout - multi-line aware
    # Format: (pattern, description, confidence, timeout_param)
    NETWORK_PATTERNS = {
        "python": [
            # requests library
            (
                r"requests\.(get|post|put|delete|patch|head|options)\s*\(",
                "requests.{method}() without timeout parameter",
                0.85,
                "timeout",
            ),
            # urllib
            (
                r"urllib\.request\.urlopen\s*\(",
                "urlopen() without timeout parameter",
                0.85,
                "timeout",
            ),
            # httpx
            (
                r"httpx\.(get|post|put|delete|patch|head|options)\s*\(",
                "httpx.{method}() without timeout parameter",
                0.80,
                "timeout",
            ),
            # httpx async client
            (
                r"await\s+(?:self\.)?client\.(get|post|put|delete|patch)\s*\(",
                "async HTTP call without timeout",
                0.70,
                "timeout",
            ),
            # aiohttp session
            (
                r"(?:await\s+)?session\.(get|post|put|delete|patch)\s*\(",
                "aiohttp session call without timeout",
                0.70,
                "timeout",
            ),
            # socket operations
            (
                r"socket\.(?:connect|recv|send)\s*\(",
                "socket operation without timeout",
                0.75,
                "timeout",
            ),
            # subprocess
            (
                r"subprocess\.(run|call|check_output|check_call)\s*\(",
                "subprocess call without timeout",
                0.70,
                "timeout",
            ),
        ],
        "javascript": [
            # fetch API
            (
                r"\bfetch\s*\(",
                "fetch() without AbortController/signal",
                0.75,
                "signal",
            ),
            # axios
            (
                r"axios\.(get|post|put|delete|patch|head|options)\s*\(",
                "axios.{method}() without timeout config",
                0.80,
                "timeout",
            ),
            # axios instance
            (
                r"axios\s*\(",
                "axios() without timeout config",
                0.80,
                "timeout",
            ),
            # XMLHttpRequest (legacy)
            (
                r"\.open\s*\(\s*['\"][A-Z]+['\"]",
                "XMLHttpRequest without timeout",
                0.65,
                "timeout",
            ),
            # node http/https
            (
                r"https?\.(?:get|request)\s*\(",
                "Node.js http request without timeout",
                0.70,
                "timeout",
            ),
        ],
        "typescript": [
            # Same as JavaScript
            (
                r"\bfetch\s*\(",
                "fetch() without AbortController/signal",
                0.75,
                "signal",
            ),
            (
                r"axios\.(get|post|put|delete|patch|head|options)\s*\(",
                "axios.{method}() without timeout config",
                0.80,
                "timeout",
            ),
            (
                r"axios\s*\(",
                "axios() without timeout config",
                0.80,
                "timeout",
            ),
            (
                r"https?\.(?:get|request)\s*\(",
                "Node.js http request without timeout",
                0.70,
                "timeout",
            ),
        ],
    }

    # Patterns indicating timeout is configured
    TIMEOUT_INDICATORS = [
        r"timeout\s*[=:]",
        r"timeout\s*:",
        r"\btimeout\b",
        r"signal\s*:",
        r"signal\s*=",
        r"AbortController",
        r"AbortSignal",
        r"setTimeout",
        r"with_timeout",
        r"asyncio\.wait_for",
        r"asyncio\.timeout",
    ]

    # Context indicators that suggest timeout handling elsewhere
    CONTEXT_INDICATORS = [
        r"session\s*=.*timeout",  # Session with timeout
        r"client\s*=.*timeout",  # Client with timeout
        r"@timeout",  # Timeout decorator
        r"Timeout\(",  # Timeout context manager
    ]

    @property
    def rule_id(self) -> str:
        return "RESILIENCE.MISSING_TIMEOUT"

    @property
    def name(self) -> str:
        return "Missing Timeout Detection"

    @property
    def category(self) -> str:
        return "resilience"

    @property
    def default_severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def triggers(self) -> list[Trigger]:
        return [Trigger.ON_WRITE, Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        return ["python", "javascript", "typescript"]

    @property
    def description(self) -> str:
        return (
            "Detects network calls and external operations without timeout "
            "parameters. Missing timeouts can cause applications to hang "
            "indefinitely when external services are slow or unresponsive."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def _get_call_context(
        self, lines: list[str], line_num: int, num_lines: int = 10
    ) -> str:
        """Get surrounding context for multi-line call analysis."""
        start = max(0, line_num - 2)
        end = min(len(lines), line_num + num_lines)
        return "\n".join(lines[start:end])

    def _has_timeout_param(
        self, lines: list[str], line_num: int, timeout_param: str
    ) -> bool:
        """Check if the call has a timeout parameter in the same or following lines."""
        # Get the call context (current line + following lines for multi-line calls)
        context = self._get_call_context(lines, line_num)

        # Check for timeout indicators
        for indicator in self.TIMEOUT_INDICATORS:
            if re.search(indicator, context, re.IGNORECASE):
                return True

        return False

    def _has_context_timeout(self, content: str) -> bool:
        """Check if there's context-level timeout configuration."""
        for indicator in self.CONTEXT_INDICATORS:
            if re.search(indicator, content, re.IGNORECASE):
                return True
        return False

    def _get_remediation_hint(self, language: str, timeout_param: str) -> list[str]:
        """Get language-specific remediation hints."""
        if language == "python":
            return [
                "Add timeout parameter: requests.get(url, timeout=30)",
                "Use separate connect and read timeouts: timeout=(3.05, 27)",
                "Configure session-level timeout: session.timeout = 30",
                "For async: use asyncio.wait_for(coro, timeout=30)",
            ]
        elif language in ("javascript", "typescript"):
            if timeout_param == "signal":
                return [
                    "Use AbortController: const ctrl = new AbortController();",
                    "Pass signal option: fetch(url, { signal: ctrl.signal })",
                    "Add timeout: setTimeout(() => ctrl.abort(), 5000)",
                    "Or use fetch libraries with built-in timeout support",
                ]
            return [
                "Add timeout config: axios.get(url, { timeout: 5000 })",
                "Configure axios instance: axios.create({ timeout: 5000 })",
                "Use AbortController for fetch API",
            ]
        return [f"Add {timeout_param} parameter to prevent hanging"]

    def check(self, context: RuleContext) -> list["Finding"]:
        """Check for network calls without timeout configuration.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for missing timeout parameters
        """
        findings = []
        language = context.language
        lines = context.lines
        content = context.content

        # Get patterns for this language
        patterns = self.NETWORK_PATTERNS.get(language, [])
        if not patterns:
            return findings

        # Check for context-level timeout configuration
        has_context_timeout = self._has_context_timeout(content)

        for line_num, line in enumerate(lines):
            # Skip if line not in diff
            if not context.is_line_in_diff(line_num + 1):
                continue

            # Skip comments
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            for pattern, description, base_confidence, timeout_param in patterns:
                match = re.search(pattern, line)
                if match:
                    # Check if timeout is specified
                    if self._has_timeout_param(lines, line_num, timeout_param):
                        continue

                    # Adjust confidence
                    confidence = base_confidence

                    # Lower confidence if there's context-level timeout
                    if has_context_timeout:
                        confidence *= 0.6

                    # Lower confidence in test files
                    file_path = str(context.file_path).lower()
                    if "test" in file_path or "spec" in file_path:
                        confidence *= 0.5

                    # Skip if confidence is too low
                    if confidence < 0.3:
                        continue

                    # Format description with method name if applicable
                    desc = description
                    if "{method}" in desc and match.lastindex:
                        desc = desc.replace("{method}", match.group(1))

                    # Get code snippet
                    snippet = line.strip()
                    if len(snippet) > 100:
                        snippet = snippet[:100] + "..."

                    findings.append(
                        self._create_finding(
                            summary=desc,
                            file_path=str(context.file_path),
                            line_number=line_num + 1,
                            evidence=[
                                Evidence(
                                    description=desc,
                                    line_number=line_num + 1,
                                    code_snippet=snippet,
                                    data={
                                        "pattern": pattern,
                                        "match": match.group(0),
                                        "timeout_param": timeout_param,
                                    },
                                )
                            ],
                            remediation_hints=self._get_remediation_hint(
                                language, timeout_param
                            ),
                            confidence=confidence,
                        )
                    )
                    break  # Only one finding per line

        return findings
