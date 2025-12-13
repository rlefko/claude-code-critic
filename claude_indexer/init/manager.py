"""Main orchestrator for project initialization."""

from ..config.config_loader import ConfigLoader
from ..indexer_logging import get_logger
from .collection_manager import CollectionManager
from .generators import FileGenerator
from .hooks_installer import HooksInstaller
from .mcp_configurator import MCPConfigurator
from .project_detector import ProjectDetector
from .templates import TemplateManager
from .types import InitOptions, InitResult, InitStepResult, ProjectType

logger = get_logger()


class InitManager:
    """Orchestrates the complete project initialization process."""

    def __init__(
        self,
        options: InitOptions,
        config_loader: ConfigLoader | None = None,
    ):
        """Initialize the manager.

        Args:
            options: Initialization options.
            config_loader: Optional ConfigLoader for configuration.
        """
        self.options = options
        self.config_loader = config_loader or ConfigLoader()

        # Initialize components lazily
        self._detector: ProjectDetector | None = None
        self._template_manager: TemplateManager | None = None
        self._file_generator: FileGenerator | None = None
        self._hooks_installer: HooksInstaller | None = None
        self._collection_manager: CollectionManager | None = None
        self._mcp_configurator: MCPConfigurator | None = None

    @property
    def detector(self) -> ProjectDetector:
        """Get project detector (lazy init)."""
        if self._detector is None:
            self._detector = ProjectDetector(self.options.project_path)
        return self._detector

    def _init_components(self, collection_name: str, project_type: ProjectType) -> None:
        """Initialize all components after detection phase."""
        self._template_manager = TemplateManager(
            self.options.project_path,
            collection_name,
            project_type,
        )
        self._file_generator = FileGenerator(
            self.options.project_path,
            self._template_manager,
            project_type,
        )
        self._hooks_installer = HooksInstaller(
            self.options.project_path,
            collection_name,
        )
        self._collection_manager = CollectionManager(self.config_loader)
        self._mcp_configurator = MCPConfigurator(
            self.options.project_path,
            collection_name,
            self.config_loader,
        )

    def _detect_project_type(self) -> ProjectType:
        """Detect or use override for project type."""
        if self.options.project_type:
            return self.options.project_type
        return self.detector.detect_project_type()

    def _resolve_collection_name(self) -> str:
        """Resolve collection name from options or derive from project."""
        if self.options.collection_name:
            return self.options.collection_name
        return self.detector.derive_collection_name()

    def run(self) -> InitResult:
        """Execute the full initialization sequence.

        Returns:
            InitResult with all step results.
        """
        result = InitResult(
            success=True,
            project_path=self.options.project_path,
            collection_name="",
            project_type=ProjectType.GENERIC,
        )

        try:
            # Step 1: Detect project type
            result.project_type = self._detect_project_type()
            logger.info(f"Detected project type: {result.project_type.value}")

            # Step 2: Derive/validate collection name
            result.collection_name = self._resolve_collection_name()
            logger.info(f"Using collection: {result.collection_name}")

            # Initialize all components with detected info
            self._init_components(result.collection_name, result.project_type)

            # Step 3: Ensure .claude directory exists
            step = self._file_generator.ensure_claude_directory()
            result.add_step(step)

            # Step 4: Generate .claudeignore
            step = self._file_generator.generate_claudeignore(self.options.force)
            result.add_step(step)

            # Step 5: Generate .claude/settings.local.json
            step = self._file_generator.generate_claude_settings(self.options.force)
            result.add_step(step)

            # Step 6: Generate .claude/guard.config.json
            step = self._file_generator.generate_guard_config(self.options.force)
            result.add_step(step)

            # Step 7: Generate .claude-indexer/config.json
            step = self._file_generator.generate_project_config(
                result.collection_name, self.options.force
            )
            result.add_step(step)

            # Step 8: Update .gitignore
            step = self._file_generator.update_gitignore()
            result.add_step(step)

            # Step 9: Create Qdrant collection (graceful if unavailable)
            step = self._collection_manager.create_collection(
                result.collection_name, self.options.force
            )
            result.add_step(step)

            # Step 10: Install hooks (unless --no-hooks)
            if not self.options.no_hooks:
                step = self._hooks_installer.install_claude_hooks(self.options.force)
                result.add_step(step)

                step = self._hooks_installer.install_git_hooks(self.options.force)
                result.add_step(step)
            else:
                result.add_step(
                    InitStepResult(
                        step_name="hooks",
                        success=True,
                        skipped=True,
                        message="Skipped hooks installation (--no-hooks)",
                    )
                )

            # Step 11: Configure MCP
            step = self._mcp_configurator.configure_mcp_file(self.options.force)
            result.add_step(step)

            # Step 12: Run initial indexing (unless --no-index)
            if not self.options.no_index:
                step = self._run_initial_indexing(result.collection_name)
                result.add_step(step)
            else:
                result.add_step(
                    InitStepResult(
                        step_name="indexing",
                        success=True,
                        skipped=True,
                        message="Skipped initial indexing (--no-index)",
                    )
                )

            # Update overall success
            result.update_success()

        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            result.success = False
            result.errors.append(f"Initialization error: {e}")

        return result

    def _run_initial_indexing(self, collection_name: str) -> InitStepResult:
        """Run initial project indexing.

        Args:
            collection_name: Collection to index into.

        Returns:
            InitStepResult indicating success or failure.
        """
        try:
            from ..config.project_config import ProjectConfigManager
            from ..indexer import CoreIndexer

            # Load project config
            project_manager = ProjectConfigManager(self.options.project_path)
            if not project_manager.exists:
                return InitStepResult(
                    step_name="indexing",
                    success=False,
                    message="Project config not found - cannot run indexing",
                )

            # Load config with project settings
            config = self.config_loader.load(
                project_path=self.options.project_path,
            )

            # Create and run indexer
            indexer = CoreIndexer(
                project_path=str(self.options.project_path),
                collection_name=collection_name,
                config=config,
            )

            # Get file patterns from project config
            project_config = project_manager.load()
            include = project_config.indexing.file_patterns.include
            exclude = project_config.indexing.file_patterns.exclude

            # Run indexing
            result = indexer.index_project(
                include_patterns=include,
                exclude_patterns=exclude,
            )

            if result.success:
                return InitStepResult(
                    step_name="indexing",
                    success=True,
                    message=f"Indexed {result.items_processed} entities",
                    details={
                        "entities": result.items_processed,
                        "time": f"{result.processing_time:.2f}s",
                    },
                )
            else:
                error_msg = (
                    ", ".join(result.errors) if result.errors else "Unknown error"
                )
                return InitStepResult(
                    step_name="indexing",
                    success=False,
                    message=f"Indexing failed: {error_msg}",
                )

        except ImportError as e:
            return InitStepResult(
                step_name="indexing",
                success=True,
                skipped=True,
                warning=f"Indexer not available: {e}",
                message="Skipped indexing (missing dependencies)",
            )
        except ConnectionError as e:
            return InitStepResult(
                step_name="indexing",
                success=True,
                skipped=True,
                warning=f"Could not connect to Qdrant: {e}",
                message="Skipped indexing (Qdrant unavailable)",
            )
        except Exception as e:
            logger.error(f"Indexing failed: {e}")
            return InitStepResult(
                step_name="indexing",
                success=False,
                message=f"Indexing error: {e}",
            )

    def get_status(self) -> dict:
        """Get initialization status for the project.

        Returns:
            Dictionary with status information.
        """
        project_path = self.options.project_path

        status = {
            "project_path": str(project_path),
            "project_type": self.detector.detect_project_type().value,
            "is_git": self.detector.is_git_repository(),
            "files": {
                ".claudeignore": (project_path / ".claudeignore").exists(),
                ".claude/settings.local.json": (
                    project_path / ".claude" / "settings.local.json"
                ).exists(),
                ".claude/guard.config.json": (
                    project_path / ".claude" / "guard.config.json"
                ).exists(),
                ".claude-indexer/config.json": (
                    project_path / ".claude-indexer" / "config.json"
                ).exists(),
                ".mcp.json": (project_path / ".mcp.json").exists(),
            },
            "hooks_dir": (project_path / ".claude" / "hooks").exists(),
        }

        return status
