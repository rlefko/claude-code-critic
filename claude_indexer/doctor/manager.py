"""Main orchestrator for system health checks."""

from pathlib import Path
from typing import Any, Optional

from ..config.config_loader import ConfigLoader
from ..indexer_logging import get_logger
from .checkers import (
    check_claude_cli,
    check_collection_exists,
    check_openai_key,
    check_package_installed,
    check_project_initialized,
    check_python_version,
    check_qdrant_connection,
    check_voyage_key,
)
from .types import DoctorOptions, DoctorResult

logger = get_logger()


class DoctorManager:
    """Orchestrates all system health checks."""

    def __init__(
        self,
        options: DoctorOptions,
        config_loader: Optional[ConfigLoader] = None,
    ):
        """Initialize the doctor manager.

        Args:
            options: Doctor command options.
            config_loader: Optional ConfigLoader for configuration.
        """
        self.options = options
        self.config_loader = config_loader or ConfigLoader()
        self._config: Optional[Any] = None

    def _load_config(self) -> Optional[Any]:
        """Load configuration, gracefully handling failures."""
        if self._config is not None:
            return self._config

        try:
            self._config = self.config_loader.load(
                project_path=self.options.project_path
            )
            return self._config
        except Exception as e:
            logger.debug(f"Config loading failed: {e}")
            return None

    def run(self) -> DoctorResult:
        """Execute all health checks.

        Returns:
            DoctorResult with all check results.
        """
        result = DoctorResult()
        config = self._load_config()

        # Python Environment checks
        logger.debug("Running Python environment checks")
        result.add_check(check_python_version())
        result.add_check(check_package_installed())

        # External Services checks
        logger.debug("Running external services checks")
        result.add_check(check_qdrant_connection(config))
        result.add_check(check_claude_cli())

        # API Keys checks
        logger.debug("Running API keys checks")
        result.add_check(check_openai_key(config))
        result.add_check(check_voyage_key(config))

        # Project Status checks (if project path provided)
        if self.options.project_path:
            logger.debug(f"Running project checks for {self.options.project_path}")
            result.add_check(check_project_initialized(self.options.project_path))

            # Collection check (if collection name provided)
            if self.options.collection_name:
                result.add_check(
                    check_collection_exists(config, self.options.collection_name)
                )

        logger.info(
            f"Health check complete: {result.passed} passed, "
            f"{result.warnings} warnings, {result.failures} failures"
        )

        return result

    def run_quick(self) -> DoctorResult:
        """Run only essential checks (Python and Qdrant).

        Returns:
            DoctorResult with essential check results.
        """
        result = DoctorResult()
        config = self._load_config()

        # Essential checks only
        result.add_check(check_python_version())
        result.add_check(check_qdrant_connection(config))

        return result
