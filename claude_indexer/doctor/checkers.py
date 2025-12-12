"""Individual health check implementations."""

import shutil
import sys
from pathlib import Path
from typing import Any, Optional

from .types import CheckCategory, CheckResult, CheckStatus


def check_python_version() -> CheckResult:
    """Check if Python version is 3.10 or higher."""
    version = sys.version_info
    version_str = f"{version.major}.{version.minor}.{version.micro}"

    if version >= (3, 10):
        return CheckResult(
            name="python_version",
            category=CheckCategory.PYTHON,
            status=CheckStatus.PASS,
            message=f"Python {version_str} (required: 3.10+)",
            details={"version": version_str, "major": version.major, "minor": version.minor},
        )
    else:
        return CheckResult(
            name="python_version",
            category=CheckCategory.PYTHON,
            status=CheckStatus.FAIL,
            message=f"Python {version_str} is below minimum (required: 3.10+)",
            suggestion="Install Python 3.10+ from https://python.org",
            details={"version": version_str, "major": version.major, "minor": version.minor},
        )


def check_package_installed() -> CheckResult:
    """Check if claude-indexer package is installed."""
    try:
        from importlib.metadata import version

        pkg_version = version("claude-indexer")
        return CheckResult(
            name="package_installed",
            category=CheckCategory.PYTHON,
            status=CheckStatus.PASS,
            message=f"claude-indexer {pkg_version} installed",
            details={"version": pkg_version},
        )
    except Exception:
        # Package might be installed in development mode
        try:
            from claude_indexer import __version__

            return CheckResult(
                name="package_installed",
                category=CheckCategory.PYTHON,
                status=CheckStatus.PASS,
                message=f"claude-indexer {__version__} installed (development mode)",
                details={"version": __version__, "mode": "development"},
            )
        except Exception:
            return CheckResult(
                name="package_installed",
                category=CheckCategory.PYTHON,
                status=CheckStatus.WARN,
                message="claude-indexer package version not detected",
                suggestion="Package may be installed in development mode",
            )


def check_qdrant_connection(config: Optional[Any] = None) -> CheckResult:
    """Check Qdrant database connectivity."""
    try:
        from qdrant_client import QdrantClient

        # Get URL and API key from config or use defaults
        url = "http://localhost:6333"
        api_key = None

        if config:
            url = getattr(config, "qdrant_url", url)
            api_key = getattr(config, "qdrant_api_key", None)
            # Don't use default-key as actual key
            if api_key == "default-key":
                api_key = None

        client = QdrantClient(url=url, api_key=api_key, timeout=5)
        collections = client.get_collections()
        collection_count = len(collections.collections)

        return CheckResult(
            name="qdrant_connection",
            category=CheckCategory.SERVICES,
            status=CheckStatus.PASS,
            message=f"Qdrant ({url}) - {collection_count} collections",
            details={
                "url": url,
                "collection_count": collection_count,
                "collections": [c.name for c in collections.collections],
            },
        )
    except ImportError:
        return CheckResult(
            name="qdrant_connection",
            category=CheckCategory.SERVICES,
            status=CheckStatus.FAIL,
            message="qdrant-client package not installed",
            suggestion="Run: pip install qdrant-client",
        )
    except Exception as e:
        error_msg = str(e)
        # Simplify common error messages
        if "Connection refused" in error_msg or "connect" in error_msg.lower():
            return CheckResult(
                name="qdrant_connection",
                category=CheckCategory.SERVICES,
                status=CheckStatus.FAIL,
                message="Qdrant not reachable (connection refused)",
                suggestion="Run: docker run -p 6333:6333 qdrant/qdrant",
                details={"error": error_msg},
            )
        return CheckResult(
            name="qdrant_connection",
            category=CheckCategory.SERVICES,
            status=CheckStatus.FAIL,
            message=f"Qdrant connection failed: {error_msg[:50]}",
            suggestion="Run: docker run -p 6333:6333 qdrant/qdrant",
            details={"error": error_msg},
        )


def check_claude_cli() -> CheckResult:
    """Check if Claude Code CLI is available."""
    claude_path = shutil.which("claude")

    if claude_path:
        return CheckResult(
            name="claude_cli",
            category=CheckCategory.SERVICES,
            status=CheckStatus.PASS,
            message=f"Claude Code CLI found at {claude_path}",
            details={"path": claude_path},
        )
    else:
        return CheckResult(
            name="claude_cli",
            category=CheckCategory.SERVICES,
            status=CheckStatus.WARN,
            message="Claude Code CLI not found",
            suggestion="Install from: https://claude.com/download",
        )


def check_openai_key(config: Optional[Any] = None) -> CheckResult:
    """Check if OpenAI API key is configured."""
    import os

    # Check environment variable first
    api_key = os.environ.get("OPENAI_API_KEY", "")

    # Check config if available
    if not api_key and config:
        api_key = getattr(config, "openai_api_key", "")

    if api_key:
        # Validate format (should start with sk-)
        masked = f"{api_key[:7]}...{api_key[-4:]}" if len(api_key) > 15 else "***"
        if api_key.startswith("sk-"):
            return CheckResult(
                name="openai_api_key",
                category=CheckCategory.API_KEYS,
                status=CheckStatus.PASS,
                message=f"OpenAI API key configured ({masked})",
                details={"masked_key": masked, "source": "env" if os.environ.get("OPENAI_API_KEY") else "config"},
            )
        else:
            return CheckResult(
                name="openai_api_key",
                category=CheckCategory.API_KEYS,
                status=CheckStatus.WARN,
                message="OpenAI API key may be invalid (doesn't start with sk-)",
                suggestion="Verify your API key at https://platform.openai.com/api-keys",
                details={"masked_key": masked},
            )
    else:
        return CheckResult(
            name="openai_api_key",
            category=CheckCategory.API_KEYS,
            status=CheckStatus.WARN,
            message="OpenAI API key not configured",
            suggestion="Set OPENAI_API_KEY env var or add to settings.txt",
        )


def check_voyage_key(config: Optional[Any] = None) -> CheckResult:
    """Check if Voyage AI API key is configured."""
    import os

    # Check environment variable first
    api_key = os.environ.get("VOYAGE_API_KEY", "")

    # Check config if available
    if not api_key and config:
        api_key = getattr(config, "voyage_api_key", "")

    if api_key:
        masked = f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
        return CheckResult(
            name="voyage_api_key",
            category=CheckCategory.API_KEYS,
            status=CheckStatus.PASS,
            message=f"Voyage AI API key configured ({masked})",
            details={"masked_key": masked, "source": "env" if os.environ.get("VOYAGE_API_KEY") else "config"},
        )
    else:
        return CheckResult(
            name="voyage_api_key",
            category=CheckCategory.API_KEYS,
            status=CheckStatus.WARN,
            message="Voyage AI API key not configured (optional)",
            suggestion="Optional: Set VOYAGE_API_KEY for Voyage AI embeddings",
        )


def check_project_initialized(project_path: Path) -> CheckResult:
    """Check if project is initialized with Claude Code Memory."""
    claude_dir = project_path / ".claude"
    indexer_dir = project_path / ".claude-indexer"
    claudeignore = project_path / ".claudeignore"

    files_found = []
    files_missing = []

    if claude_dir.exists():
        files_found.append(".claude/")
    else:
        files_missing.append(".claude/")

    if indexer_dir.exists():
        files_found.append(".claude-indexer/")
    else:
        files_missing.append(".claude-indexer/")

    if claudeignore.exists():
        files_found.append(".claudeignore")
    else:
        files_missing.append(".claudeignore")

    if claude_dir.exists() and indexer_dir.exists():
        return CheckResult(
            name="project_initialized",
            category=CheckCategory.PROJECT,
            status=CheckStatus.PASS,
            message=f"Project initialized ({len(files_found)} config files found)",
            details={
                "project_path": str(project_path),
                "files_found": files_found,
                "files_missing": files_missing,
            },
        )
    elif files_found:
        return CheckResult(
            name="project_initialized",
            category=CheckCategory.PROJECT,
            status=CheckStatus.WARN,
            message=f"Project partially initialized (missing: {', '.join(files_missing)})",
            suggestion="Run: claude-indexer init",
            details={
                "project_path": str(project_path),
                "files_found": files_found,
                "files_missing": files_missing,
            },
        )
    else:
        return CheckResult(
            name="project_initialized",
            category=CheckCategory.PROJECT,
            status=CheckStatus.WARN,
            message="Project not initialized",
            suggestion="Run: claude-indexer init",
            details={"project_path": str(project_path)},
        )


def check_collection_exists(config: Optional[Any], collection_name: str) -> CheckResult:
    """Check if the specified collection exists in Qdrant."""
    if not collection_name:
        return CheckResult(
            name="collection_exists",
            category=CheckCategory.PROJECT,
            status=CheckStatus.SKIP,
            message="No collection name specified",
        )

    try:
        from qdrant_client import QdrantClient

        # Get URL and API key from config or use defaults
        url = "http://localhost:6333"
        api_key = None

        if config:
            url = getattr(config, "qdrant_url", url)
            api_key = getattr(config, "qdrant_api_key", None)
            if api_key == "default-key":
                api_key = None

        client = QdrantClient(url=url, api_key=api_key, timeout=5)

        # Check if collection exists
        try:
            collection_info = client.get_collection(collection_name)
            vector_count = collection_info.points_count or 0

            return CheckResult(
                name="collection_exists",
                category=CheckCategory.PROJECT,
                status=CheckStatus.PASS,
                message=f"Collection '{collection_name}' ({vector_count:,} vectors)",
                details={
                    "collection_name": collection_name,
                    "vector_count": vector_count,
                    "status": collection_info.status.value if collection_info.status else "unknown",
                },
            )
        except Exception:
            return CheckResult(
                name="collection_exists",
                category=CheckCategory.PROJECT,
                status=CheckStatus.WARN,
                message=f"Collection '{collection_name}' not found",
                suggestion="Run: claude-indexer index -c " + collection_name,
                details={"collection_name": collection_name},
            )
    except ImportError:
        return CheckResult(
            name="collection_exists",
            category=CheckCategory.PROJECT,
            status=CheckStatus.SKIP,
            message="Cannot check collection (qdrant-client not installed)",
        )
    except Exception as e:
        return CheckResult(
            name="collection_exists",
            category=CheckCategory.PROJECT,
            status=CheckStatus.SKIP,
            message=f"Cannot check collection (Qdrant unavailable)",
            details={"error": str(e)},
        )
