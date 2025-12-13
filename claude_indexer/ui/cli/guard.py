"""UI Pre-Tool Guard - Fast UI consistency checking for Claude Code.

This module provides the main UIGuard class and CLI entry point for
running UI consistency checks during pre-tool operations.

Modes:
    --fast: Tier 0 checks only (<300ms target) - for PreToolUse hooks
    --json: Output structured JSON for Claude Code consumption
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, TextIO

from ..collectors.source import SourceCollector
from ..config import UIQualityConfig, load_ui_config
from ..models import StaticComponentFingerprint, StyleFingerprint, UIAnalysisResult
from ..normalizers.component import ComponentNormalizer
from ..normalizers.style import StyleNormalizer
from ..rules.base import RuleContext
from ..rules.engine import create_rule_engine

# UI file extensions that trigger the guard
UI_EXTENSIONS = frozenset(
    [
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".jsx",
        ".tsx",
        ".vue",
        ".svelte",
        ".html",
        ".htm",
    ]
)


def is_ui_file(file_path: str | Path) -> bool:
    """Check if a file is a UI file based on extension.

    Args:
        file_path: Path to check.

    Returns:
        True if the file has a UI extension.
    """
    suffix = Path(file_path).suffix.lower()
    return suffix in UI_EXTENSIONS


class UIGuard:
    """Fast UI consistency guard for pre-tool/pre-commit checks.

    This class provides the main interface for running UI consistency
    checks on individual files or from hook input.
    """

    def __init__(
        self,
        config: UIQualityConfig | None = None,
        project_path: Path | str | None = None,
    ):
        """Initialize the UI guard.

        Args:
            config: Optional UI quality configuration. Loads defaults if not provided.
            project_path: Optional project root path.
        """
        self.project_path = Path(project_path) if project_path else Path.cwd()
        self.config = config or load_ui_config(self.project_path)
        self.engine = create_rule_engine(self.config, register_defaults=True)
        self.source_collector = SourceCollector(self.project_path)
        self.style_normalizer = StyleNormalizer()
        self.component_normalizer = ComponentNormalizer()

    def check_file(
        self,
        file_path: Path | str,
        content: str,
        fast_mode: bool = True,
    ) -> UIAnalysisResult:
        """Run UI consistency checks on a single file.

        Args:
            file_path: Path to the UI file.
            content: File content to check.
            fast_mode: If True, only run fast rules (<50ms each).

        Returns:
            UIAnalysisResult with all findings.
        """
        start = time.time()
        file_path = Path(file_path)

        # Extract components and styles from content
        extraction = self.source_collector.extract(file_path, content)

        # Create StyleFingerprints from extracted styles
        style_fingerprints: list[StyleFingerprint] = []
        for style in extraction.styles:
            if style.declarations:
                # Normalize the style to get hashes
                normalized = self.style_normalizer.normalize(style.declarations)
                # Create StyleFingerprint with the attributes rules expect
                fingerprint = StyleFingerprint(
                    declaration_set=normalized.declarations,
                    exact_hash=normalized.exact_hash,
                    near_hash=normalized.near_hash,
                    tokens_used=[],  # Populated during token resolution
                    source_refs=[style.source_ref] if style.source_ref else [],
                )
                style_fingerprints.append(fingerprint)

        # Create StaticComponentFingerprints from extracted components
        component_fingerprints: list[StaticComponentFingerprint] = []
        for component in extraction.components:
            # Normalize component structure to get hash
            normalized = self.component_normalizer.normalize(
                template=component.children_structure,
                props=component.props,
                framework=component.framework or "unknown",
            )
            # Create StaticComponentFingerprint
            fingerprint = StaticComponentFingerprint(
                structure_hash=normalized.structure_hash,
                style_refs=component.style_refs,
                prop_shape_sketch=(
                    dict.fromkeys(normalized.prop_names, "any")
                    if normalized.prop_names
                    else None
                ),
                source_ref=component.source_ref,
            )
            component_fingerprints.append(fingerprint)

        # Build rule context
        context = RuleContext(
            config=self.config,
            styles=style_fingerprints,
            components=component_fingerprints,
            token_resolver=self.config.load_tokens(self.project_path),
            file_path=file_path,
            source_files={str(file_path): content},
        )

        # Run appropriate checks
        if fast_mode:
            result = self.engine.run_fast(context)
        else:
            result = self.engine.run(context)

        result.analysis_time_ms = (time.time() - start) * 1000
        return result

    def check_from_hook_input(
        self,
        hook_input: dict[str, Any],
        fast_mode: bool = True,
    ) -> UIAnalysisResult:
        """Run checks from Claude Code hook input.

        Args:
            hook_input: Hook input dictionary with tool_name and tool_input.
            fast_mode: If True, only run fast rules.

        Returns:
            UIAnalysisResult with all findings.
        """
        tool_name = hook_input.get("tool_name", "")
        tool_input = hook_input.get("tool_input", {})

        # Extract file path and content based on tool
        file_path = tool_input.get("file_path", "")

        if tool_name == "Write":
            content = tool_input.get("content", "")
        elif tool_name == "Edit":
            content = tool_input.get("new_string", "")
        else:
            # Unsupported tool
            return UIAnalysisResult(
                findings=[],
                files_analyzed=[file_path] if file_path else [],
                analysis_time_ms=0.0,
                tier=0,
            )

        if not file_path or not content:
            return UIAnalysisResult(
                findings=[],
                files_analyzed=[file_path] if file_path else [],
                analysis_time_ms=0.0,
                tier=0,
            )

        # Skip non-UI files
        if not is_ui_file(file_path):
            return UIAnalysisResult(
                findings=[],
                files_analyzed=[file_path],
                analysis_time_ms=0.0,
                tier=0,
            )

        return self.check_file(file_path, content, fast_mode)


def run_guard(
    input_stream: TextIO = sys.stdin,
    output_stream: TextIO = sys.stdout,
    error_stream: TextIO = sys.stderr,
    fast_mode: bool = True,
    json_output: bool = True,
    project_path: Path | None = None,
) -> int:
    """Run the UI guard from stdin input.

    Args:
        input_stream: Stream to read hook input from.
        output_stream: Stream for JSON output.
        error_stream: Stream for CLI/error output.
        fast_mode: If True, only run fast rules.
        json_output: If True, output JSON; otherwise CLI format.
        project_path: Optional project root path.

    Returns:
        Exit code: 0=allow, 1=warn, 2=block
    """
    from .reporter import CLIReporter, JSONReporter

    try:
        # Read hook input
        input_text = input_stream.read()
        if not input_text.strip():
            return 0

        hook_input = json.loads(input_text)

        # Initialize guard
        guard = UIGuard(project_path=project_path)

        # Run checks
        result = guard.check_from_hook_input(hook_input, fast_mode)

        # Output results
        if json_output:
            reporter = JSONReporter(output_stream)
            reporter.report(result)
        else:
            reporter = CLIReporter(error_stream)
            reporter.report(result)

        # Determine exit code
        if result.should_block():
            return 2
        elif result.warn_count > 0:
            return 1
        return 0

    except json.JSONDecodeError:
        # Invalid JSON input - allow operation
        return 0
    except Exception as e:
        # On any error, allow operation (fail open)
        print(f"UI guard error: {e}", file=error_stream)
        return 0


def main() -> int:
    """CLI entry point for UI guard."""
    parser = argparse.ArgumentParser(
        description="UI consistency guard for Claude Code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        default=True,
        help="Run only fast rules (<50ms each). Default: True",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Run all rules including slow ones",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=True,
        help="Output JSON format. Default: True",
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="Output CLI format (color-coded)",
    )
    parser.add_argument(
        "--project",
        "-p",
        type=Path,
        help="Project root path",
    )

    args = parser.parse_args()

    fast_mode = not args.full
    json_output = not args.cli

    return run_guard(
        fast_mode=fast_mode,
        json_output=json_output,
        project_path=args.project,
    )


if __name__ == "__main__":
    sys.exit(main())
