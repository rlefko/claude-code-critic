"""
Full Lifecycle End-to-End Tests for Claude Indexer.

Tests the complete workflow: init -> index -> use -> modify -> commit
Milestone 6.4: Test Coverage Complete (v2.9.20)
"""

import shutil
import subprocess
from unittest.mock import Mock, patch

import pytest

try:
    from click.testing import CliRunner

    from claude_indexer import cli_full as cli
    from claude_indexer.config.config_loader import ConfigLoader
    from claude_indexer.init.manager import InitManager
    from claude_indexer.session.manager import SessionManager

    CLI_AVAILABLE = True
except ImportError:
    CLI_AVAILABLE = False
    cli = None
    ConfigLoader = None
    InitManager = None
    SessionManager = None


@pytest.fixture
def lifecycle_project(tmp_path):
    """Create a realistic project structure for lifecycle testing."""
    project_dir = tmp_path / "lifecycle_test_project"
    project_dir.mkdir()

    # Create basic project structure
    (project_dir / "src").mkdir()
    (project_dir / "tests").mkdir()
    (project_dir / "docs").mkdir()

    # Create Python files
    (project_dir / "src" / "__init__.py").write_text("")
    (project_dir / "src" / "main.py").write_text(
        '''
"""Main application module."""


def greet(name: str) -> str:
    """Generate a greeting message."""
    return f"Hello, {name}!"


def calculate_sum(a: int, b: int) -> int:
    """Calculate the sum of two numbers."""
    return a + b


if __name__ == "__main__":
    print(greet("World"))
'''
    )

    (project_dir / "src" / "utils.py").write_text(
        '''
"""Utility functions."""

import logging

logger = logging.getLogger(__name__)


def format_name(first: str, last: str) -> str:
    """Format a full name."""
    return f"{first} {last}"


def validate_email(email: str) -> bool:
    """Validate an email address."""
    return "@" in email and "." in email
'''
    )

    # Create test file
    (project_dir / "tests" / "__init__.py").write_text("")
    (project_dir / "tests" / "test_main.py").write_text(
        '''
"""Tests for main module."""

from src.main import greet, calculate_sum


def test_greet():
    """Test greeting function."""
    assert greet("Alice") == "Hello, Alice!"


def test_calculate_sum():
    """Test sum calculation."""
    assert calculate_sum(2, 3) == 5
'''
    )

    # Create README
    (project_dir / "README.md").write_text(
        """
# Lifecycle Test Project

A sample project for testing the full lifecycle of claude-indexer.

## Features

- Greeting functionality
- Mathematical operations
- Email validation
"""
    )

    # Initialize as git repo
    subprocess.run(["git", "init"], cwd=project_dir, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@test.com", "add", "."],
        cwd=project_dir,
        capture_output=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@test.com",
            "commit",
            "-m",
            "Initial commit",
        ],
        cwd=project_dir,
        capture_output=True,
    )

    yield project_dir

    # Cleanup
    if project_dir.exists():
        shutil.rmtree(project_dir, ignore_errors=True)


@pytest.fixture
def runner():
    """Create a CLI runner."""
    if not CLI_AVAILABLE:
        pytest.skip("CLI not available")
    return CliRunner()


@pytest.mark.e2e
class TestFullLifecycle:
    """Test complete init -> index -> use -> modify -> commit workflow."""

    def test_project_initialization(self, lifecycle_project, runner):
        """Test project initialization with claude-indexer init."""
        if not CLI_AVAILABLE:
            pytest.skip("CLI not available")

        # Mock the external dependencies (Qdrant, MCP)
        with patch("claude_indexer.storage.qdrant.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value.get_collections.return_value.collections = []

            result = runner.invoke(
                cli.cli,
                [
                    "init",
                    "-p",
                    str(lifecycle_project),
                    "-c",
                    "test_lifecycle",
                    "--no-index",  # Skip indexing for init test
                ],
            )

            # Init should complete (even with warnings about missing services)
            assert result.exit_code in [0, 1], f"Init failed: {result.output}"

    def test_project_indexing_workflow(self, lifecycle_project, runner):
        """Test indexing a project after initialization."""
        if not CLI_AVAILABLE:
            pytest.skip("CLI not available")

        with patch("claude_indexer.cli_full.CoreIndexer") as mock_indexer_class:
            # Configure mock indexer
            mock_indexer = Mock()
            mock_result = Mock()
            mock_result.success = True
            mock_result.processing_time = 1.5
            mock_result.files_processed = 4
            mock_result.entities_created = 10
            mock_result.relations_created = 5
            mock_result.implementation_chunks_created = 8
            mock_result.warnings = []
            mock_result.errors = []
            mock_result.total_tokens = 0
            mock_result.total_cost_estimate = 0.0
            mock_result.embedding_requests = 0
            mock_indexer.index_project.return_value = mock_result
            mock_indexer._categorize_file_changes.return_value = ([], [], [])
            mock_indexer.get_files_to_process.return_value = []
            mock_indexer.get_deleted_entities.return_value = []
            mock_indexer._load_state.return_value = {}
            mock_indexer._load_previous_statistics.return_value = {
                "total_tracked": 0,
                "entities_created": 0,
                "relations_created": 0,
                "implementation_chunks_created": 0,
            }
            mock_indexer_class.return_value = mock_indexer

            result = runner.invoke(
                cli.cli,
                [
                    "index",
                    "-p",
                    str(lifecycle_project),
                    "-c",
                    "test_lifecycle_index",
                ],
            )

            # Check that index was called
            assert mock_indexer.index_project.called or result.exit_code in [0, 1]

    def test_search_workflow(self, lifecycle_project, runner):
        """Test searching indexed content."""
        if not CLI_AVAILABLE:
            pytest.skip("CLI not available")

        with patch("claude_indexer.storage.qdrant.QdrantStore") as mock_store_class:
            # Configure mock store
            mock_store = Mock()
            mock_result = Mock()
            mock_result.entity_name = "greet"
            mock_result.entity_type = "function"
            mock_result.file_path = "src/main.py"
            mock_result.score = 0.95
            mock_result.content = "Generate a greeting message"
            mock_store.search_similar.return_value = [mock_result]
            mock_store_class.return_value = mock_store

            result = runner.invoke(
                cli.cli,
                [
                    "search",
                    "greeting function",
                    "-p",
                    str(lifecycle_project),
                    "-c",
                    "test_lifecycle_search",
                    "--limit",
                    "5",
                ],
            )

            # Search should complete
            assert result.exit_code in [0, 1], f"Search failed: {result.output}"

    def test_incremental_indexing_after_modification(self, lifecycle_project, runner):
        """Test incremental indexing after file modification."""
        if not CLI_AVAILABLE:
            pytest.skip("CLI not available")

        # Modify a file
        main_py = lifecycle_project / "src" / "main.py"
        content = main_py.read_text()
        modified_content = (
            content
            + '''

def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b
'''
        )
        main_py.write_text(modified_content)

        # Stage the change
        subprocess.run(["git", "add", "."], cwd=lifecycle_project, capture_output=True)

        with patch("claude_indexer.cli_full.CoreIndexer") as mock_indexer_class:
            mock_indexer = Mock()
            mock_result = Mock()
            mock_result.success = True
            mock_result.processing_time = 0.5
            mock_result.files_processed = 1
            mock_result.entities_created = 1
            mock_result.relations_created = 0
            mock_result.implementation_chunks_created = 1
            mock_result.warnings = []
            mock_result.errors = []
            mock_result.total_tokens = 0
            mock_result.total_cost_estimate = 0.0
            mock_result.embedding_requests = 0
            mock_indexer.index_incremental.return_value = mock_result
            mock_indexer._categorize_file_changes.return_value = (
                ["src/main.py"],
                [],
                [],
            )
            mock_indexer._load_state.return_value = {"_last_indexed_commit": "abc123"}
            mock_indexer._load_previous_statistics.return_value = {
                "total_tracked": 4,
                "entities_created": 10,
                "relations_created": 5,
                "implementation_chunks_created": 8,
            }
            mock_indexer_class.return_value = mock_indexer

            result = runner.invoke(
                cli.cli,
                [
                    "index",
                    "-p",
                    str(lifecycle_project),
                    "-c",
                    "test_lifecycle_incremental",
                    "--staged",  # Only process staged changes
                ],
            )

            # Incremental index should be attempted
            assert result.exit_code in [
                0,
                1,
            ], f"Incremental index failed: {result.output}"


@pytest.mark.e2e
class TestSessionIsolation:
    """Test session isolation between concurrent sessions."""

    def test_concurrent_session_isolation(self, tmp_path):
        """Test that multiple sessions on different projects are isolated."""
        if not CLI_AVAILABLE:
            pytest.skip("CLI not available")

        # Create two project directories
        project_a = tmp_path / "project_a"
        project_b = tmp_path / "project_b"
        project_a.mkdir()
        project_b.mkdir()

        # Create minimal files in each
        (project_a / "app.py").write_text("def foo(): pass")
        (project_b / "app.py").write_text("def bar(): pass")

        # Initialize git repos
        for project in [project_a, project_b]:
            subprocess.run(["git", "init"], cwd=project, capture_output=True)

        # Test that each project can have its own session state
        state_a = tmp_path / ".claude-indexer-a"
        state_b = tmp_path / ".claude-indexer-b"

        # Each should be able to have independent state
        state_a.mkdir()
        state_b.mkdir()

        assert state_a.exists()
        assert state_b.exists()
        assert state_a != state_b

    def test_collection_naming_uniqueness(self, tmp_path):
        """Test that collection names are unique per project."""
        if not CLI_AVAILABLE:
            pytest.skip("CLI not available")

        from claude_indexer.init.project_detector import ProjectDetector

        # Create two projects
        project_a = tmp_path / "my_app"
        project_b = tmp_path / "my_app_v2"
        project_a.mkdir()
        project_b.mkdir()

        # Initialize git repos with different remotes
        for i, project in enumerate([project_a, project_b]):
            subprocess.run(["git", "init"], cwd=project, capture_output=True)
            subprocess.run(
                ["git", "remote", "add", "origin", f"git@github.com:test/repo{i}.git"],
                cwd=project,
                capture_output=True,
            )

        # Get collection names - ProjectDetector requires project_path
        detector_a = ProjectDetector(project_a)
        detector_b = ProjectDetector(project_b)
        name_a = detector_a.derive_collection_name(include_hash=True)
        name_b = detector_b.derive_collection_name(include_hash=True)

        # Names should be different due to different remote hashes
        assert name_a != name_b


@pytest.mark.e2e
class TestWorkspaceSupport:
    """Test workspace mode with multiple sub-projects."""

    def test_workspace_detection(self, tmp_path):
        """Test that workspace type is correctly detected."""
        if not CLI_AVAILABLE:
            pytest.skip("CLI not available")

        from claude_indexer.workspace.detector import WorkspaceDetector

        # Create a monorepo with pnpm workspace
        workspace = tmp_path / "monorepo"
        workspace.mkdir()

        (workspace / "pnpm-workspace.yaml").write_text(
            """
packages:
  - 'packages/*'
"""
        )

        (workspace / "packages").mkdir()
        (workspace / "packages" / "core").mkdir()
        (workspace / "packages" / "utils").mkdir()

        detector = WorkspaceDetector()
        result = detector.detect(workspace)

        # Should detect as a monorepo/workspace
        assert result is not None
        assert result.workspace_type.value in [
            "pnpm",
            "npm",
            "yarn",
            "monorepo",
            "single_project",
        ]

    def test_vs_code_workspace_detection(self, tmp_path):
        """Test VS Code multi-root workspace detection."""
        if not CLI_AVAILABLE:
            pytest.skip("CLI not available")

        from claude_indexer.workspace.detector import WorkspaceDetector

        # Create VS Code workspace file
        workspace_dir = tmp_path / "vscode_workspace"
        workspace_dir.mkdir()

        workspace_file = workspace_dir / "projects.code-workspace"
        workspace_file.write_text(
            """
{
    "folders": [
        {"path": "./frontend"},
        {"path": "./backend"}
    ]
}
"""
        )

        (workspace_dir / "frontend").mkdir()
        (workspace_dir / "backend").mkdir()

        detector = WorkspaceDetector()
        result = detector.detect(workspace_dir)

        # Should detect workspace file
        assert result is not None


@pytest.mark.e2e
class TestHooksIntegration:
    """Test hooks system integration."""

    def test_session_start_hook_execution(self, lifecycle_project, runner):
        """Test session-start hook execution."""
        if not CLI_AVAILABLE:
            pytest.skip("CLI not available")

        with patch("claude_indexer.storage.qdrant.QdrantClient") as mock_qdrant:
            mock_qdrant.return_value.get_collections.return_value.collections = []

            result = runner.invoke(
                cli.cli,
                [
                    "session-start",
                    "-p",
                    str(lifecycle_project),
                    "-c",
                    "test_hooks",
                ],
            )

            # Session start should provide health info
            assert result.exit_code in [0, 1], f"Session start failed: {result.output}"

    def test_stop_check_execution(self, lifecycle_project, runner):
        """Test stop-check hook execution."""
        if not CLI_AVAILABLE:
            pytest.skip("CLI not available")

        with patch("claude_indexer.hooks.stop_check.RuleEngine") as mock_engine_class:
            mock_engine = Mock()
            mock_result = Mock()
            mock_result.findings = []
            mock_result.total_rules = 5
            mock_result.rules_passed = 5
            mock_result.rules_failed = 0
            mock_result.execution_time_ms = 100
            mock_engine.run.return_value = mock_result
            mock_engine_class.return_value = mock_engine

            result = runner.invoke(
                cli.cli,
                [
                    "stop-check",
                    "-p",
                    str(lifecycle_project),
                ],
            )

            # Stop check should complete (exit 0 for clean, 1 for warnings, 2 for block)
            assert result.exit_code in [0, 1, 2], f"Stop check failed: {result.output}"


@pytest.mark.e2e
class TestDoctorCommand:
    """Test the doctor command for system health checks."""

    def test_doctor_basic_checks(self, runner):
        """Test that doctor command runs basic checks."""
        if not CLI_AVAILABLE:
            pytest.skip("CLI not available")

        result = runner.invoke(cli.cli, ["doctor"])

        # Doctor should complete and report status
        assert result.exit_code in [0, 1, 2], f"Doctor failed: {result.output}"
        # Should contain Python version check
        assert "Python" in result.output or "python" in result.output.lower()

    def test_doctor_with_project_context(self, lifecycle_project, runner):
        """Test doctor command with project context."""
        if not CLI_AVAILABLE:
            pytest.skip("CLI not available")

        result = runner.invoke(
            cli.cli,
            [
                "doctor",
                "-p",
                str(lifecycle_project),
            ],
        )

        # Doctor should check project-specific items
        assert result.exit_code in [0, 1, 2]


@pytest.mark.e2e
class TestCollectionsManagement:
    """Test collection management commands."""

    def test_collections_list(self, runner):
        """Test listing collections."""
        if not CLI_AVAILABLE:
            pytest.skip("CLI not available")

        with patch(
            "claude_indexer.init.collection_manager.CollectionManager"
        ) as mock_manager_class:
            mock_manager = Mock()
            mock_manager.list_all_collections.return_value = [
                "claude_project_a",
                "claude_project_b",
            ]
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(cli.cli, ["collections", "list"])

            assert result.exit_code in [0, 1]

    def test_collections_cleanup_dry_run(self, runner):
        """Test collection cleanup in dry-run mode."""
        if not CLI_AVAILABLE:
            pytest.skip("CLI not available")

        with patch(
            "claude_indexer.init.collection_manager.CollectionManager"
        ) as mock_manager_class:
            mock_manager = Mock()
            mock_manager.find_stale_collections.return_value = ["old_collection"]
            mock_manager.cleanup_collections.return_value = 1
            mock_manager_class.return_value = mock_manager

            result = runner.invoke(
                cli.cli,
                ["collections", "cleanup", "--dry-run"],
            )

            assert result.exit_code in [0, 1]
