"""
Modern persistent progress bar for indexing operations.

This module provides a beautiful, Homebrew-style progress bar that updates
in place, showing detailed progress information during indexing.

Supports quiet mode (suppress all output) and NO_COLOR mode (disable ANSI codes).
"""

from __future__ import annotations

import os
import sys
import time
import shutil
from typing import Optional
from dataclasses import dataclass


def _should_use_color() -> bool:
    """Check if colors should be used based on environment."""
    # NO_COLOR environment variable (standard convention)
    if "NO_COLOR" in os.environ:
        return False
    # FORCE_COLOR overrides
    if "FORCE_COLOR" in os.environ:
        return True
    # Check if stdout is a TTY
    if hasattr(sys.stdout, "isatty") and not sys.stdout.isatty():
        return False
    return True


@dataclass
class ProgressState:
    """Track progress state for the bar."""
    current: int = 0
    total: int = 0
    start_time: float = 0.0
    last_update_time: float = 0.0
    files_per_second: float = 0.0
    current_batch: int = 0
    total_batches: int = 0
    memory_mb: int = 0
    tier_info: str = ""


class ModernProgressBar:
    """
    A beautiful, persistent progress bar similar to Homebrew's style.
    Updates in place with smooth animations and detailed information.

    Supports:
    - quiet mode: suppress all visual output
    - use_color: respect NO_COLOR env var and --no-color flag
    """

    def __init__(
        self,
        total_items: int,
        description: str = "Processing",
        quiet: bool = False,
        use_color: bool | None = None,
    ):
        """
        Initialize the progress bar.

        Args:
            total_items: Total number of items to process
            description: Description of the operation
            quiet: Suppress all progress output (for quiet mode)
            use_color: Use ANSI colors. None = auto-detect from env/TTY
        """
        self.state = ProgressState(
            total=total_items,
            start_time=time.time()
        )
        self.description = description
        self.quiet = quiet

        # Auto-detect color if not explicitly set
        if use_color is None:
            self.use_color = _should_use_color()
        else:
            self.use_color = use_color

        self.terminal_width = shutil.get_terminal_size(fallback=(80, 20)).columns
        self.last_line_length = 0
        self.spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self.spinner_index = 0

        # Color codes (only apply if use_color is True)
        self._init_colors()

    def _init_colors(self) -> None:
        """Initialize color codes based on use_color setting."""
        if self.use_color:
            self.GREEN = "\033[92m"
            self.YELLOW = "\033[93m"
            self.BLUE = "\033[94m"
            self.CYAN = "\033[96m"
            self.RED = "\033[91m"
            self.RESET = "\033[0m"
            self.BOLD = "\033[1m"
            self.DIM = "\033[2m"
        else:
            # No colors - empty strings
            self.GREEN = ""
            self.YELLOW = ""
            self.BLUE = ""
            self.CYAN = ""
            self.RED = ""
            self.RESET = ""
            self.BOLD = ""
            self.DIM = ""

    def update(self,
               current: Optional[int] = None,
               batch_num: Optional[int] = None,
               total_batches: Optional[int] = None,
               memory_mb: Optional[int] = None,
               tier_info: Optional[str] = None):
        """
        Update the progress bar.

        Args:
            current: Current item number
            batch_num: Current batch number
            total_batches: Total number of batches
            memory_mb: Current memory usage in MB
            tier_info: Information about file tiers
        """
        if current is not None:
            self.state.current = current
        if batch_num is not None:
            self.state.current_batch = batch_num
        if total_batches is not None:
            self.state.total_batches = total_batches
        if memory_mb is not None:
            self.state.memory_mb = memory_mb
        if tier_info is not None:
            self.state.tier_info = tier_info

        # Calculate metrics
        elapsed = time.time() - self.state.start_time
        if elapsed > 0:
            self.state.files_per_second = self.state.current / elapsed

        # Render the bar
        self._render()

    def complete(self) -> None:
        """Mark the progress bar as complete."""
        if self.quiet:
            return
        self.state.current = self.state.total
        self._render()
        sys.stdout.write("\n")
        sys.stdout.flush()

    def _render(self) -> None:
        """Render the progress bar to terminal."""
        # Skip rendering in quiet mode
        if self.quiet:
            return
        # Calculate percentage
        if self.state.total > 0:
            percentage = (self.state.current / self.state.total) * 100
        else:
            percentage = 0

        # Calculate ETA
        if self.state.files_per_second > 0:
            remaining = self.state.total - self.state.current
            eta_seconds = remaining / self.state.files_per_second
            eta_str = self._format_time(eta_seconds)
        else:
            eta_str = "calculating"

        # Build the progress bar
        bar_width = min(40, self.terminal_width - 60)  # Leave room for text
        filled_width = int(bar_width * percentage / 100)

        # Use block characters for smooth progress
        if filled_width == bar_width:
            bar = "█" * bar_width
        else:
            # Calculate partial block
            remainder = (bar_width * percentage / 100) - filled_width
            partial_block = self._get_partial_block(remainder)
            bar = "█" * filled_width + partial_block + "░" * (bar_width - filled_width - 1)

        # Get spinner
        spinner = self.spinner_frames[self.spinner_index]
        self.spinner_index = (self.spinner_index + 1) % len(self.spinner_frames)

        # Format the line
        if self.state.current_batch > 0:
            batch_info = f"Batch {self.state.current_batch}/{self.state.total_batches}"
            if self.state.tier_info:
                batch_info += f" {self.state.tier_info}"
        else:
            batch_info = self.description

        # Build the full line
        line = (
            f"\r{spinner} {self.BOLD}{batch_info}{self.RESET} "
            f"{self.GREEN}[{bar}]{self.RESET} "
            f"{self.CYAN}{percentage:5.1f}%{self.RESET} "
            f"({self.state.current}/{self.state.total}) "
        )

        # Add speed and ETA
        if self.state.files_per_second > 0:
            line += f"{self.DIM}{self.state.files_per_second:.1f} files/s{self.RESET} "
            line += f"ETA: {self.YELLOW}{eta_str}{self.RESET} "

        # Add memory if available
        if self.state.memory_mb > 0:
            mem_color = self.YELLOW if self.state.memory_mb > 1500 else self.GREEN
            line += f"{mem_color}{self.state.memory_mb}MB{self.RESET}"

        # Clear any remaining characters from previous line
        clear_length = max(0, self.last_line_length - len(line))
        line += " " * clear_length

        # Write the line
        sys.stdout.write(line)
        sys.stdout.flush()

        self.last_line_length = len(line)

    def _get_partial_block(self, fraction: float) -> str:
        """Get a partial block character based on fraction filled."""
        blocks = ["░", "▒", "▓", "█"]
        index = min(int(fraction * len(blocks)), len(blocks) - 1)
        return blocks[index]

    def _format_time(self, seconds: float) -> str:
        """Format seconds into human-readable time."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}m {secs}s"
        else:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}h {minutes}m"

    def finish(self, success: bool = True) -> None:
        """
        Finish the progress bar with a final status.

        Args:
            success: Whether the operation completed successfully
        """
        # In quiet mode, only show failure messages
        if self.quiet and success:
            return

        elapsed = time.time() - self.state.start_time
        elapsed_str = self._format_time(elapsed)

        # Clear the line (only if we were rendering)
        if not self.quiet:
            sys.stdout.write("\r" + " " * self.last_line_length + "\r")

        if success:
            status = f"{self.GREEN}✓{self.RESET}" if self.use_color else "[OK]"
            message = f"{status} {self.BOLD}{self.description} complete{self.RESET}"
        else:
            status = f"{self.RED}✗{self.RESET}" if self.use_color else "[FAIL]"
            message = f"{status} {self.BOLD}{self.description} failed{self.RESET}"

        # Final statistics
        stats = (
            f"  Processed {self.state.current}/{self.state.total} files "
            f"in {elapsed_str} "
            f"({self.state.files_per_second:.1f} files/s average)"
        )

        sys.stdout.write(message + "\n")
        if not self.quiet:
            sys.stdout.write(f"{self.DIM}{stats}{self.RESET}\n")
        sys.stdout.flush()


class BatchProgressBar(ModernProgressBar):
    """
    Specialized progress bar for batch processing with tier information.
    """

    def update_batch(self,
                    batch_num: int,
                    total_batches: int,
                    files_in_batch: int,
                    files_completed: int,
                    total_files: int,
                    memory_mb: int,
                    light_files: int = 0,
                    batch_size: int = 0):
        """
        Update progress for batch processing.

        Args:
            batch_num: Current batch number
            total_batches: Total number of batches
            files_in_batch: Number of files in current batch
            files_completed: Total files completed so far
            total_files: Total files to process
            memory_mb: Current memory usage
            light_files: Number of light tier files in batch
            batch_size: Current batch size
        """
        # Format tier information
        tier_info = ""
        if light_files > 0:
            tier_info = f"({light_files} light)"

        # Update with all information
        self.update(
            current=files_completed,
            batch_num=batch_num,
            total_batches=total_batches,
            memory_mb=memory_mb,
            tier_info=tier_info
        )


def demo_progress_bar():
    """Demo the progress bar with simulated data."""
    import random

    total_files = 500
    batch_size = 25
    total_batches = (total_files + batch_size - 1) // batch_size

    bar = BatchProgressBar(total_files, "Indexing project")

    files_completed = 0
    for batch_num in range(1, total_batches + 1):
        # Simulate batch processing
        files_in_batch = min(batch_size, total_files - files_completed)
        light_files = random.randint(0, files_in_batch // 2)

        # Process files in batch
        for _ in range(files_in_batch):
            files_completed += 1
            memory = 200 + random.randint(0, 800)

            bar.update_batch(
                batch_num=batch_num,
                total_batches=total_batches,
                files_in_batch=files_in_batch,
                files_completed=files_completed,
                total_files=total_files,
                memory_mb=memory,
                light_files=light_files,
                batch_size=batch_size
            )

            time.sleep(0.02)  # Simulate processing time

    bar.finish(success=True)


if __name__ == "__main__":
    demo_progress_bar()