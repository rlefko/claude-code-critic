"""Type definitions for the init module."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


class ProjectType(Enum):
    """Detected project type based on configuration files."""

    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    REACT = "react"
    NEXTJS = "nextjs"
    VUE = "vue"
    GENERIC = "generic"


@dataclass
class InitOptions:
    """Configuration options for the init command."""

    project_path: Path
    collection_name: Optional[str] = None  # Auto-derived if not provided
    project_type: Optional[ProjectType] = None  # Auto-detected if not provided
    no_index: bool = False
    no_hooks: bool = False
    force: bool = False
    verbose: bool = False
    quiet: bool = False


@dataclass
class InitStepResult:
    """Result of a single initialization step."""

    step_name: str
    success: bool
    message: str
    skipped: bool = False
    warning: Optional[str] = None
    details: Optional[Dict[str, Any]] = None


@dataclass
class InitResult:
    """Complete result of the initialization process."""

    success: bool
    project_path: Path
    collection_name: str
    project_type: ProjectType
    steps: List[InitStepResult] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def add_step(self, step: InitStepResult) -> None:
        """Add a step result and track warnings."""
        self.steps.append(step)
        if step.warning:
            self.warnings.append(step.warning)
        if not step.success and not step.skipped:
            self.errors.append(f"{step.step_name}: {step.message}")

    def update_success(self) -> None:
        """Update overall success based on step results."""
        # Success if no critical failures (skipped steps don't count as failures)
        self.success = all(s.success or s.skipped for s in self.steps)
