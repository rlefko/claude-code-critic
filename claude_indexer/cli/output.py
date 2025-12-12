"""Centralized output manager for CLI with color and quiet mode support.

This module provides consistent output handling across all CLI commands,
supporting NO_COLOR environment variable, --no-color flag, quiet mode,
and accessible symbol fallbacks for colorblind users.

Following the NO_COLOR standard: https://no-color.org/
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import TextIO

import click


def should_use_color(
    explicit_flag: bool | None = None,
    stream: TextIO | None = None,
) -> bool:
    """Determine if color output should be used.

    Priority order:
    1. Explicit --no-color flag (if passed)
    2. NO_COLOR environment variable (standard convention)
    3. TTY detection (only colorize if output is a terminal)

    Args:
        explicit_flag: Explicit color preference from CLI flag.
            True = force colors, False = force no colors, None = auto-detect
        stream: Output stream to check for TTY. Defaults to stdout.

    Returns:
        True if colors should be used, False otherwise.
    """
    # Explicit flag takes precedence
    if explicit_flag is not None:
        return explicit_flag

    # NO_COLOR environment variable (standard convention)
    # Per spec, any value (including empty) means "no color"
    if "NO_COLOR" in os.environ:
        return False

    # FORCE_COLOR can override NO_COLOR for tools that support it
    if "FORCE_COLOR" in os.environ:
        return True

    # Check if output is a TTY
    if stream is None:
        stream = sys.stdout
    if hasattr(stream, "isatty") and not stream.isatty():
        return False

    return True


@dataclass
class OutputConfig:
    """Configuration for CLI output behavior.

    Attributes:
        use_color: Whether to use ANSI color codes in output.
        quiet: Suppress all output except errors.
        verbose: Enable detailed debug output.
        stream: Output stream (default: stdout).
        err_stream: Error stream (default: stderr).
    """

    use_color: bool = True
    quiet: bool = False
    verbose: bool = False
    stream: TextIO = field(default_factory=lambda: sys.stdout)
    err_stream: TextIO = field(default_factory=lambda: sys.stderr)

    @classmethod
    def from_flags(
        cls,
        verbose: bool = False,
        quiet: bool = False,
        no_color: bool = False,
    ) -> "OutputConfig":
        """Create OutputConfig from CLI flags.

        Args:
            verbose: Enable verbose output.
            quiet: Suppress non-error output.
            no_color: Disable color output.

        Returns:
            Configured OutputConfig instance.
        """
        use_color = should_use_color(explicit_flag=not no_color if no_color else None)
        return cls(use_color=use_color, quiet=quiet, verbose=verbose)


class OutputManager:
    """Centralized output handler for CLI.

    Provides consistent output formatting with:
    - Color support (respects NO_COLOR env var)
    - Quiet mode (only errors)
    - Verbose mode (debug info)
    - Accessible symbol fallbacks

    Example:
        >>> config = OutputConfig.from_flags(quiet=False, no_color=False)
        >>> output = OutputManager(config)
        >>> output.success("Operation completed")
        [OK] Operation completed
        >>> output.error("Something went wrong")
        [FAIL] Something went wrong
    """

    # ANSI color codes
    COLORS = {
        "green": "\033[92m",
        "red": "\033[91m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "cyan": "\033[96m",
        "bold": "\033[1m",
        "dim": "\033[2m",
        "reset": "\033[0m",
    }

    # Accessible symbols with color/no-color variants
    SYMBOLS = {
        "success": {"color": "\033[92m\u2713\033[0m", "plain": "[OK]"},
        "error": {"color": "\033[91m\u2717\033[0m", "plain": "[FAIL]"},
        "warning": {"color": "\033[93m\u26a0\033[0m", "plain": "[WARN]"},
        "info": {"color": "\033[94m\u2139\033[0m", "plain": "[INFO]"},
        "skip": {"color": "\033[2m\u25cb\033[0m", "plain": "[SKIP]"},
        "pending": {"color": "\033[93m\u25cb\033[0m", "plain": "[--]"},
    }

    def __init__(self, config: OutputConfig | None = None):
        """Initialize the output manager.

        Args:
            config: Output configuration. Uses defaults if None.
        """
        self.config = config or OutputConfig()

    def _get_symbol(self, symbol_type: str) -> str:
        """Get the appropriate symbol for current color mode.

        Args:
            symbol_type: Type of symbol (success, error, warning, info, skip).

        Returns:
            Symbol string appropriate for current color setting.
        """
        symbol_data = self.SYMBOLS.get(symbol_type, self.SYMBOLS["info"])
        return symbol_data["color"] if self.config.use_color else symbol_data["plain"]

    def _colorize(self, text: str, color: str) -> str:
        """Apply color to text if colors are enabled.

        Args:
            text: Text to colorize.
            color: Color name from COLORS dict.

        Returns:
            Colorized text or plain text based on config.
        """
        if not self.config.use_color:
            return text
        color_code = self.COLORS.get(color, "")
        reset = self.COLORS["reset"]
        return f"{color_code}{text}{reset}"

    def _output(
        self,
        message: str,
        symbol_type: str | None = None,
        err: bool = False,
        force: bool = False,
    ) -> None:
        """Output a message with optional symbol prefix.

        Args:
            message: Message to output.
            symbol_type: Type of symbol to prefix (or None for no symbol).
            err: Output to stderr instead of stdout.
            force: Output even in quiet mode.
        """
        if self.config.quiet and not err and not force:
            return

        stream = self.config.err_stream if err else self.config.stream

        if symbol_type:
            symbol = self._get_symbol(symbol_type)
            line = f"{symbol} {message}"
        else:
            line = message

        click.echo(line, file=stream, err=err)

    def success(self, message: str, force: bool = False) -> None:
        """Output a success message.

        Args:
            message: Success message.
            force: Output even in quiet mode.
        """
        self._output(message, symbol_type="success", force=force)

    def error(self, message: str) -> None:
        """Output an error message (always shown, even in quiet mode).

        Args:
            message: Error message.
        """
        self._output(message, symbol_type="error", err=True, force=True)

    def warning(self, message: str, force: bool = False) -> None:
        """Output a warning message.

        Args:
            message: Warning message.
            force: Output even in quiet mode.
        """
        self._output(message, symbol_type="warning", force=force)

    def info(self, message: str) -> None:
        """Output an info message (suppressed in quiet mode).

        Args:
            message: Info message.
        """
        self._output(message, symbol_type="info")

    def debug(self, message: str) -> None:
        """Output a debug message (only in verbose mode).

        Args:
            message: Debug message.
        """
        if not self.config.verbose:
            return
        dim_msg = self._colorize(message, "dim")
        self._output(f"DEBUG: {dim_msg}")

    def status_line(self, label: str, status: str, symbol_type: str = "info") -> None:
        """Output a status line with aligned label and status.

        Args:
            label: Status label (e.g., "Qdrant").
            status: Status description (e.g., "Connected").
            symbol_type: Symbol type for status indicator.
        """
        symbol = self._get_symbol(symbol_type)
        # Align labels to 12 characters
        formatted_label = f"{label}:".ljust(12)
        self._output(f"{formatted_label} {symbol} {status}")

    def header(self, title: str) -> None:
        """Output a header line (bold if colors enabled).

        Args:
            title: Header title.
        """
        if self.config.quiet:
            return
        header_text = self._colorize(title, "bold")
        self._output(header_text)
        self._output("=" * len(title))

    def newline(self) -> None:
        """Output a blank line (suppressed in quiet mode)."""
        if not self.config.quiet:
            click.echo("", file=self.config.stream)

    def plain(self, message: str, force: bool = False) -> None:
        """Output plain text without symbol prefix.

        Args:
            message: Plain text message.
            force: Output even in quiet mode.
        """
        self._output(message, force=force)

    def summary(
        self,
        total: int,
        success: int = 0,
        failed: int = 0,
        skipped: int = 0,
        duration_ms: float | None = None,
    ) -> None:
        """Output a summary line with counts.

        Args:
            total: Total items processed.
            success: Number of successful items.
            failed: Number of failed items.
            skipped: Number of skipped items.
            duration_ms: Operation duration in milliseconds.
        """
        parts = [f"{total} total"]
        if success > 0:
            parts.append(f"{success} successful")
        if failed > 0:
            parts.append(f"{failed} failed")
        if skipped > 0:
            parts.append(f"{skipped} skipped")
        if duration_ms is not None:
            if duration_ms < 1000:
                parts.append(f"{duration_ms:.0f}ms")
            else:
                parts.append(f"{duration_ms/1000:.1f}s")

        summary_text = " | ".join(parts)

        # Force output even in quiet mode for summary
        if failed > 0:
            self._output(summary_text, symbol_type="error", force=True)
        elif skipped > 0:
            self._output(summary_text, symbol_type="warning", force=True)
        else:
            self._output(summary_text, symbol_type="success", force=True)
