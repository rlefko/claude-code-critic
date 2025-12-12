"""Template loading and variable substitution for initialization."""

import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from ..indexer_logging import get_logger
from .types import ProjectType

logger = get_logger()


class TemplateManager:
    """Load and process templates with variable substitution."""

    # Templates directory relative to this file
    TEMPLATES_DIR = Path(__file__).parent.parent.parent / "templates"

    def __init__(
        self,
        project_path: Path,
        collection_name: str,
        project_type: ProjectType,
    ):
        self.project_path = Path(project_path).resolve()
        self.collection_name = collection_name
        self.project_type = project_type
        self.variables = self._build_variables()

    def _build_variables(self) -> Dict[str, str]:
        """Build template variable dictionary."""
        # Try to find the venv python
        venv_python = self._find_venv_python()

        return {
            "PROJECT_NAME": self.project_path.name,
            "PROJECT_PATH": str(self.project_path),
            "COLLECTION_NAME": self.collection_name,
            "GENERATION_DATE": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "HOOKS_PATH": str(self.project_path / ".claude" / "hooks"),
            "VENV_PYTHON": venv_python,
            "PROJECT_TYPE": self.project_type.value,
        }

    def _find_venv_python(self) -> str:
        """Find the virtual environment Python path."""
        # Check common venv locations
        venv_paths = [
            self.project_path / ".venv" / "bin" / "python",
            self.project_path / "venv" / "bin" / "python",
            self.project_path / ".venv" / "Scripts" / "python.exe",  # Windows
            self.project_path / "venv" / "Scripts" / "python.exe",  # Windows
        ]

        for path in venv_paths:
            if path.exists():
                return str(path)

        # Fallback to system python
        return sys.executable or "python3"

    def load_template(self, template_name: str) -> Optional[str]:
        """Load template file content.

        Args:
            template_name: Name of template file (e.g., '.claudeignore.template')

        Returns:
            Template content or None if not found.
        """
        template_path = self.TEMPLATES_DIR / template_name
        if not template_path.exists():
            logger.warning(f"Template not found: {template_path}")
            return None

        try:
            with open(template_path, "r", encoding="utf-8") as f:
                return f.read()
        except IOError as e:
            logger.error(f"Failed to read template {template_name}: {e}")
            return None

    def process_template(self, template_content: str) -> str:
        """Substitute variables in template.

        Supports {{VARIABLE_NAME}} syntax.
        """
        result = template_content

        for key, value in self.variables.items():
            # Handle both {{VAR}} and {{ VAR }} formats
            patterns = [
                f"{{{{{key}}}}}",  # {{VAR}}
                f"{{{{ {key} }}}}",  # {{ VAR }}
            ]
            for pattern in patterns:
                result = result.replace(pattern, value)

        return result

    def load_and_process(self, template_name: str) -> Optional[str]:
        """Load a template and process variable substitution.

        Args:
            template_name: Name of template file.

        Returns:
            Processed template content or None if template not found.
        """
        content = self.load_template(template_name)
        if content is None:
            return None
        return self.process_template(content)

    def copy_template(
        self,
        template_name: str,
        destination: Path,
        process_variables: bool = True,
    ) -> bool:
        """Copy a template to the destination with optional variable substitution.

        Args:
            template_name: Name of template file.
            destination: Destination path for the output file.
            process_variables: Whether to process variable substitution.

        Returns:
            True if successful, False otherwise.
        """
        if process_variables:
            content = self.load_and_process(template_name)
            if content is None:
                return False

            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                with open(destination, "w", encoding="utf-8") as f:
                    f.write(content)
                return True
            except IOError as e:
                logger.error(f"Failed to write to {destination}: {e}")
                return False
        else:
            # Direct copy without processing
            source = self.TEMPLATES_DIR / template_name
            if not source.exists():
                return False
            try:
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
                return True
            except IOError as e:
                logger.error(f"Failed to copy template to {destination}: {e}")
                return False

    def add_variable(self, key: str, value: Any) -> None:
        """Add or update a template variable."""
        self.variables[key] = str(value)

    @classmethod
    def get_available_templates(cls) -> list[str]:
        """Get list of available template files."""
        if not cls.TEMPLATES_DIR.exists():
            return []

        return [
            f.name
            for f in cls.TEMPLATES_DIR.iterdir()
            if f.is_file() and f.suffix == ".template"
        ]
