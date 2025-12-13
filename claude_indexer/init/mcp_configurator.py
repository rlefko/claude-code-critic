"""MCP server configuration for initialization."""

import json
import subprocess
from pathlib import Path

from ..config.config_loader import ConfigLoader
from ..indexer_logging import get_logger
from .types import InitStepResult

logger = get_logger()


class MCPConfigurator:
    """Configures MCP server for the project."""

    # MCP server location relative to the package
    MCP_SERVER_REL_PATH = Path("mcp-qdrant-memory") / "dist" / "index.js"

    def __init__(
        self,
        project_path: Path,
        collection_name: str,
        config_loader: ConfigLoader | None = None,
    ):
        """Initialize MCP configurator.

        Args:
            project_path: Path to the project directory.
            collection_name: Name of the Qdrant collection.
            config_loader: Optional ConfigLoader for API keys and URLs.
        """
        self.project_path = Path(project_path).resolve()
        self.collection_name = collection_name
        self._config_loader = config_loader
        self._config = None

    def _get_config(self):
        """Get configuration lazily."""
        if self._config is None:
            if self._config_loader:
                self._config = self._config_loader.load()
            else:
                try:
                    loader = ConfigLoader()
                    self._config = loader.load()
                except Exception as e:
                    logger.debug(f"Could not load config: {e}")
                    self._config = None
        return self._config

    def _get_mcp_server_path(self) -> Path | None:
        """Get path to MCP server script."""
        # Try relative to this package
        package_dir = Path(__file__).parent.parent.parent
        mcp_path = package_dir / self.MCP_SERVER_REL_PATH

        if mcp_path.exists():
            return mcp_path

        # Try relative to project
        project_mcp = self.project_path / self.MCP_SERVER_REL_PATH
        if project_mcp.exists():
            return project_mcp

        return None

    def configure_mcp_file(self, force: bool = False) -> InitStepResult:
        """Create .mcp.json file with MCP server configuration.

        This creates a local MCP configuration file that Claude Code
        will automatically pick up.

        Args:
            force: If True, overwrite existing configuration.

        Returns:
            InitStepResult indicating success or failure.
        """
        mcp_path = self.project_path / ".mcp.json"

        if mcp_path.exists() and not force:
            return InitStepResult(
                step_name="mcp_config",
                success=True,
                skipped=True,
                message=".mcp.json already exists",
            )

        # Get MCP server path
        server_path = self._get_mcp_server_path()
        if server_path is None:
            return InitStepResult(
                step_name="mcp_config",
                success=True,
                skipped=True,
                warning="MCP server not found - run 'cd mcp-qdrant-memory && npm run build'",
                message="Skipped MCP configuration (server not built)",
            )

        # Get configuration for API keys
        config = self._get_config()
        if config is None:
            return InitStepResult(
                step_name="mcp_config",
                success=True,
                skipped=True,
                warning="Could not load configuration for API keys",
                message="Skipped MCP configuration (missing config)",
            )

        # Build MCP configuration
        server_name = f"{self.collection_name}-memory"
        env_config = {
            "QDRANT_URL": config.qdrant_url,
            "QDRANT_COLLECTION_NAME": self.collection_name,
        }

        # Add API keys if available
        if hasattr(config, "openai_api_key") and config.openai_api_key:
            env_config["OPENAI_API_KEY"] = config.openai_api_key

        if hasattr(config, "qdrant_api_key") and config.qdrant_api_key:
            env_config["QDRANT_API_KEY"] = config.qdrant_api_key

        if hasattr(config, "voyage_api_key") and config.voyage_api_key:
            env_config["VOYAGE_API_KEY"] = config.voyage_api_key
            env_config["EMBEDDING_PROVIDER"] = "voyage"

        if hasattr(config, "voyage_model") and config.voyage_model:
            env_config["EMBEDDING_MODEL"] = config.voyage_model

        mcp_config = {
            "mcpServers": {
                server_name: {
                    "type": "stdio",
                    "command": "node",
                    "args": [str(server_path)],
                    "env": env_config,
                }
            }
        }

        try:
            with open(mcp_path, "w") as f:
                json.dump(mcp_config, f, indent=2)

            return InitStepResult(
                step_name="mcp_config",
                success=True,
                message=f"Created {mcp_path} with server '{server_name}'",
                details={"server_name": server_name, "server_path": str(server_path)},
            )

        except OSError as e:
            return InitStepResult(
                step_name="mcp_config",
                success=False,
                message=f"Failed to create .mcp.json: {e}",
            )

    def configure_mcp_cli(self) -> InitStepResult:
        """Configure MCP server using 'claude mcp add' CLI command.

        This registers the MCP server globally with Claude Code.

        Returns:
            InitStepResult indicating success or failure.
        """
        # Get MCP server path
        server_path = self._get_mcp_server_path()
        if server_path is None:
            return InitStepResult(
                step_name="mcp_cli",
                success=True,
                skipped=True,
                warning="MCP server not found",
                message="Skipped MCP CLI configuration",
            )

        # Get configuration
        config = self._get_config()
        if config is None:
            return InitStepResult(
                step_name="mcp_cli",
                success=True,
                skipped=True,
                warning="Could not load configuration",
                message="Skipped MCP CLI configuration",
            )

        server_name = f"{self.collection_name}-memory"

        # Build command
        cmd = [
            "claude",
            "mcp",
            "add",
            server_name,
            "-e",
            f"QDRANT_URL={config.qdrant_url}",
            "-e",
            f"QDRANT_COLLECTION_NAME={self.collection_name}",
        ]

        if hasattr(config, "openai_api_key") and config.openai_api_key:
            cmd.extend(["-e", f"OPENAI_API_KEY={config.openai_api_key}"])

        if hasattr(config, "qdrant_api_key") and config.qdrant_api_key:
            cmd.extend(["-e", f"QDRANT_API_KEY={config.qdrant_api_key}"])

        if hasattr(config, "voyage_api_key") and config.voyage_api_key:
            cmd.extend(["-e", f"VOYAGE_API_KEY={config.voyage_api_key}"])
            cmd.extend(["-e", "EMBEDDING_PROVIDER=voyage"])

        cmd.extend(["--", "node", str(server_path)])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                return InitStepResult(
                    step_name="mcp_cli",
                    success=True,
                    message=f"Registered MCP server '{server_name}' with Claude Code",
                )
            else:
                error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                return InitStepResult(
                    step_name="mcp_cli",
                    success=False,
                    message=f"Failed to register MCP server: {error_msg}",
                )

        except FileNotFoundError:
            return InitStepResult(
                step_name="mcp_cli",
                success=True,
                skipped=True,
                warning="'claude' command not found - Claude Code may not be installed",
                message="Skipped MCP CLI configuration",
            )
        except subprocess.TimeoutExpired:
            return InitStepResult(
                step_name="mcp_cli",
                success=False,
                message="MCP registration timed out",
            )
        except Exception as e:
            return InitStepResult(
                step_name="mcp_cli",
                success=False,
                message=f"Error registering MCP server: {e}",
            )

    def get_mcp_status(self) -> dict:
        """Get current MCP configuration status.

        Returns:
            Dictionary with MCP status information.
        """
        status = {
            "mcp_json_exists": (self.project_path / ".mcp.json").exists(),
            "server_path": None,
            "server_exists": False,
        }

        server_path = self._get_mcp_server_path()
        if server_path:
            status["server_path"] = str(server_path)
            status["server_exists"] = True

        return status
