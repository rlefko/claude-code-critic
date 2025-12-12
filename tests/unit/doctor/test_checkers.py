"""Tests for doctor checker functions."""

import os
import sys
from collections import namedtuple
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_indexer.doctor.checkers import (
    check_claude_cli,
    check_collection_exists,
    check_openai_key,
    check_package_installed,
    check_project_initialized,
    check_python_version,
    check_qdrant_connection,
    check_voyage_key,
)
from claude_indexer.doctor.types import CheckCategory, CheckStatus


# Create a named tuple similar to sys.version_info
VersionInfo = namedtuple("VersionInfo", ["major", "minor", "micro", "releaselevel", "serial"])


class TestCheckPythonVersion:
    """Tests for check_python_version."""

    def test_current_version_passes(self):
        """Test that current Python version passes (we're running 3.10+)."""
        result = check_python_version()
        assert result.status == CheckStatus.PASS
        assert result.category == CheckCategory.PYTHON
        assert result.name == "python_version"
        assert "3.10+" in result.message

    def test_old_version_fails(self):
        """Test that Python < 3.10 fails."""
        old_version = VersionInfo(3, 9, 0, "final", 0)
        with patch.object(sys, "version_info", old_version):
            result = check_python_version()
            assert result.status == CheckStatus.FAIL
            assert "3.9.0" in result.message
            assert result.suggestion is not None
            assert "python.org" in result.suggestion.lower()

    def test_minimum_version_passes(self):
        """Test that Python 3.10 exactly passes."""
        min_version = VersionInfo(3, 10, 0, "final", 0)
        with patch.object(sys, "version_info", min_version):
            result = check_python_version()
            assert result.status == CheckStatus.PASS

    def test_newer_version_passes(self):
        """Test that newer Python versions pass."""
        new_version = VersionInfo(3, 12, 1, "final", 0)
        with patch.object(sys, "version_info", new_version):
            result = check_python_version()
            assert result.status == CheckStatus.PASS
            assert "3.12.1" in result.message


class TestCheckPackageInstalled:
    """Tests for check_package_installed."""

    def test_package_detected(self):
        """Test that package is detected (we're running the code)."""
        result = check_package_installed()
        assert result.category == CheckCategory.PYTHON
        assert result.name == "package_installed"
        # Should either pass or warn (development mode)
        assert result.status in (CheckStatus.PASS, CheckStatus.WARN)

    def test_package_version_detected(self):
        """Test with importlib.metadata working."""
        with patch("importlib.metadata.version", return_value="2.9.11"):
            result = check_package_installed()
            assert result.status == CheckStatus.PASS
            assert "2.9.11" in result.message


class TestCheckQdrantConnection:
    """Tests for check_qdrant_connection."""

    def test_connection_success(self):
        """Test successful Qdrant connection."""
        mock_client = MagicMock()
        mock_collections = MagicMock()
        mock_collections.collections = [MagicMock(name="col1"), MagicMock(name="col2")]
        mock_client.get_collections.return_value = mock_collections

        with patch("qdrant_client.QdrantClient", return_value=mock_client):
            result = check_qdrant_connection()
            assert result.status == CheckStatus.PASS
            assert result.category == CheckCategory.SERVICES
            assert "2 collections" in result.message

    def test_connection_refused(self):
        """Test connection refused error."""
        with patch("qdrant_client.QdrantClient", side_effect=Exception("Connection refused")):
            result = check_qdrant_connection()
            assert result.status == CheckStatus.FAIL
            assert "connection refused" in result.message.lower()
            assert result.suggestion is not None
            assert "docker" in result.suggestion.lower()

    def test_connection_with_config(self):
        """Test connection using config values."""
        mock_client = MagicMock()
        mock_collections = MagicMock()
        mock_collections.collections = []
        mock_client.get_collections.return_value = mock_collections

        with patch("qdrant_client.QdrantClient", return_value=mock_client) as mock_class:
            config = MagicMock()
            config.qdrant_url = "http://custom:6333"
            config.qdrant_api_key = "test-key"

            result = check_qdrant_connection(config)
            assert result.status == CheckStatus.PASS
            mock_class.assert_called_with(
                url="http://custom:6333", api_key="test-key", timeout=5
            )


class TestCheckClaudeCli:
    """Tests for check_claude_cli."""

    @patch("claude_indexer.doctor.checkers.shutil.which")
    def test_cli_found(self, mock_which):
        """Test when Claude CLI is found."""
        mock_which.return_value = "/usr/local/bin/claude"
        result = check_claude_cli()
        assert result.status == CheckStatus.PASS
        assert result.category == CheckCategory.SERVICES
        assert "/usr/local/bin/claude" in result.message

    @patch("claude_indexer.doctor.checkers.shutil.which")
    def test_cli_not_found(self, mock_which):
        """Test when Claude CLI is not found."""
        mock_which.return_value = None
        result = check_claude_cli()
        assert result.status == CheckStatus.WARN
        assert "not found" in result.message.lower()
        assert result.suggestion is not None


class TestCheckOpenaiKey:
    """Tests for check_openai_key."""

    def test_key_from_env(self):
        """Test detecting key from environment."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test1234567890abcdef"}):
            result = check_openai_key()
            assert result.status == CheckStatus.PASS
            assert result.category == CheckCategory.API_KEYS
            assert "sk-test" in result.message

    def test_key_from_config(self):
        """Test detecting key from config."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove env var if present
            os.environ.pop("OPENAI_API_KEY", None)
            config = MagicMock()
            config.openai_api_key = "sk-config1234567890abcd"
            result = check_openai_key(config)
            assert result.status == CheckStatus.PASS

    def test_key_invalid_format(self):
        """Test key with invalid format."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "invalid-key-format-1234567890"}):
            result = check_openai_key()
            assert result.status == CheckStatus.WARN
            assert "invalid" in result.message.lower()

    def test_key_missing(self):
        """Test when key is missing."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("OPENAI_API_KEY", None)
            result = check_openai_key()
            assert result.status == CheckStatus.WARN
            assert "not configured" in result.message.lower()
            assert result.suggestion is not None


class TestCheckVoyageKey:
    """Tests for check_voyage_key."""

    def test_key_from_env(self):
        """Test detecting key from environment."""
        with patch.dict(os.environ, {"VOYAGE_API_KEY": "voyage-test-1234"}):
            result = check_voyage_key()
            assert result.status == CheckStatus.PASS
            assert result.category == CheckCategory.API_KEYS

    def test_key_from_config(self):
        """Test detecting key from config."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("VOYAGE_API_KEY", None)
            config = MagicMock()
            config.voyage_api_key = "voyage-config-key"
            result = check_voyage_key(config)
            assert result.status == CheckStatus.PASS

    def test_key_missing(self):
        """Test when key is missing (warning, not failure)."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("VOYAGE_API_KEY", None)
            result = check_voyage_key()
            assert result.status == CheckStatus.WARN
            assert "optional" in result.message.lower()


class TestCheckProjectInitialized:
    """Tests for check_project_initialized."""

    def test_fully_initialized(self, tmp_path: Path):
        """Test fully initialized project."""
        (tmp_path / ".claude").mkdir()
        (tmp_path / ".claude-indexer").mkdir()
        (tmp_path / ".claudeignore").touch()

        result = check_project_initialized(tmp_path)
        assert result.status == CheckStatus.PASS
        assert result.category == CheckCategory.PROJECT
        assert "initialized" in result.message.lower()

    def test_partially_initialized(self, tmp_path: Path):
        """Test partially initialized project."""
        (tmp_path / ".claude").mkdir()
        # Missing .claude-indexer and .claudeignore

        result = check_project_initialized(tmp_path)
        assert result.status == CheckStatus.WARN
        assert "partially" in result.message.lower()
        assert result.suggestion is not None

    def test_not_initialized(self, tmp_path: Path):
        """Test uninitialized project."""
        result = check_project_initialized(tmp_path)
        assert result.status == CheckStatus.WARN
        assert "not initialized" in result.message.lower()
        assert "claude-indexer init" in result.suggestion.lower()


class TestCheckCollectionExists:
    """Tests for check_collection_exists."""

    def test_no_collection_name(self):
        """Test with no collection name provided."""
        result = check_collection_exists(None, "")
        assert result.status == CheckStatus.SKIP
        assert "no collection name" in result.message.lower()

    def test_collection_exists(self):
        """Test when collection exists."""
        mock_client = MagicMock()
        mock_collection_info = MagicMock()
        mock_collection_info.points_count = 1234
        mock_collection_info.status = MagicMock(value="green")
        mock_client.get_collection.return_value = mock_collection_info

        with patch("qdrant_client.QdrantClient", return_value=mock_client):
            result = check_collection_exists(None, "test-collection")
            assert result.status == CheckStatus.PASS
            assert "1,234 vectors" in result.message

    def test_collection_not_found(self):
        """Test when collection doesn't exist."""
        mock_client = MagicMock()
        mock_client.get_collection.side_effect = Exception("Collection not found")

        with patch("qdrant_client.QdrantClient", return_value=mock_client):
            result = check_collection_exists(None, "missing-collection")
            assert result.status == CheckStatus.WARN
            assert "not found" in result.message.lower()

    def test_qdrant_unavailable(self):
        """Test when Qdrant is unavailable."""
        with patch("qdrant_client.QdrantClient", side_effect=Exception("Connection refused")):
            result = check_collection_exists(None, "test-collection")
            assert result.status == CheckStatus.SKIP
            assert "unavailable" in result.message.lower()
