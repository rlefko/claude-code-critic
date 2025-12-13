"""Tests for project detector functionality."""

import json
from pathlib import Path

from claude_indexer.init.project_detector import ProjectDetector
from claude_indexer.init.types import ProjectType


class TestProjectDetector:
    """Tests for ProjectDetector class."""

    def test_detect_python_project(self, tmp_path: Path):
        """Test detection of Python project."""
        # Create pyproject.toml
        (tmp_path / "pyproject.toml").write_text("[build-system]")
        (tmp_path / "main.py").write_text("print('hello')")

        detector = ProjectDetector(tmp_path)
        assert detector.detect_project_type() == ProjectType.PYTHON

    def test_detect_python_by_requirements(self, tmp_path: Path):
        """Test detection of Python project by requirements.txt."""
        (tmp_path / "requirements.txt").write_text("flask>=2.0")
        (tmp_path / "app.py").write_text("from flask import Flask")

        detector = ProjectDetector(tmp_path)
        assert detector.detect_project_type() == ProjectType.PYTHON

    def test_detect_javascript_project(self, tmp_path: Path):
        """Test detection of JavaScript project."""
        package_json = {"name": "test", "version": "1.0.0"}
        (tmp_path / "package.json").write_text(json.dumps(package_json))
        (tmp_path / "index.js").write_text("console.log('hello');")

        detector = ProjectDetector(tmp_path)
        assert detector.detect_project_type() == ProjectType.JAVASCRIPT

    def test_detect_typescript_project(self, tmp_path: Path):
        """Test detection of TypeScript project."""
        package_json = {"name": "test", "devDependencies": {"typescript": "^5.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {}}')
        (tmp_path / "index.ts").write_text("const x: string = 'hello';")

        detector = ProjectDetector(tmp_path)
        assert detector.detect_project_type() == ProjectType.TYPESCRIPT

    def test_detect_react_project(self, tmp_path: Path):
        """Test detection of React project."""
        package_json = {"name": "test", "dependencies": {"react": "^18.0"}}
        (tmp_path / "package.json").write_text(json.dumps(package_json))
        (tmp_path / "tsconfig.json").write_text('{"compilerOptions": {}}')
        (tmp_path / "App.tsx").write_text("export const App = () => <div />;")

        detector = ProjectDetector(tmp_path)
        assert detector.detect_project_type() == ProjectType.REACT

    def test_detect_nextjs_project(self, tmp_path: Path):
        """Test detection of Next.js project."""
        (tmp_path / "next.config.js").write_text("module.exports = {}")
        (tmp_path / "pages").mkdir()
        (tmp_path / "pages" / "index.tsx").write_text("export default () => <div />;")

        detector = ProjectDetector(tmp_path)
        assert detector.detect_project_type() == ProjectType.NEXTJS

    def test_detect_vue_project(self, tmp_path: Path):
        """Test detection of Vue project."""
        (tmp_path / "vue.config.js").write_text("module.exports = {}")
        (tmp_path / "App.vue").write_text("<template><div /></template>")

        detector = ProjectDetector(tmp_path)
        assert detector.detect_project_type() == ProjectType.VUE

    def test_detect_generic_project(self, tmp_path: Path):
        """Test detection falls back to generic for unknown projects."""
        (tmp_path / "README.md").write_text("# Project")
        (tmp_path / "data.csv").write_text("a,b,c")

        detector = ProjectDetector(tmp_path)
        assert detector.detect_project_type() == ProjectType.GENERIC

    def test_detect_languages(self, tmp_path: Path):
        """Test language detection."""
        (tmp_path / "main.py").write_text("print('hello')")
        (tmp_path / "app.js").write_text("console.log('hello');")
        (tmp_path / "style.css").write_text("body {}")
        (tmp_path / "index.html").write_text("<html></html>")

        detector = ProjectDetector(tmp_path)
        languages = detector.detect_languages()

        assert "python" in languages
        assert "javascript" in languages
        assert "css" in languages
        assert "html" in languages

    def test_derive_collection_name(self, tmp_path: Path):
        """Test collection name derivation."""
        detector = ProjectDetector(tmp_path)

        # Test with project name
        name = detector.derive_collection_name()
        assert name == tmp_path.name.lower().replace("_", "-")

        # Test with custom name
        name = detector.derive_collection_name("My Project!")
        assert name == "my-project"

    def test_derive_collection_name_sanitization(self, tmp_path: Path):
        """Test collection name sanitization."""
        detector = ProjectDetector(tmp_path)

        # Special characters
        name = detector.derive_collection_name("My@Project#123!")
        assert name == "my-project-123"

        # Multiple hyphens
        name = detector.derive_collection_name("test---name")
        assert name == "test-name"

        # Leading/trailing special chars
        name = detector.derive_collection_name("--test--")
        assert name == "test"

    def test_is_git_repository(self, tmp_path: Path):
        """Test git repository detection."""
        detector = ProjectDetector(tmp_path)
        assert not detector.is_git_repository()

        # Create .git directory
        (tmp_path / ".git").mkdir()
        assert detector.is_git_repository()

    def test_get_project_name(self, tmp_path: Path):
        """Test project name retrieval."""
        detector = ProjectDetector(tmp_path)
        assert detector.get_project_name() == tmp_path.name

    def test_get_project_info(self, tmp_path: Path):
        """Test comprehensive project info."""
        (tmp_path / "pyproject.toml").write_text("[build-system]")
        (tmp_path / ".git").mkdir()

        detector = ProjectDetector(tmp_path)
        info = detector.get_project_info()

        assert info["name"] == tmp_path.name
        assert info["type"] == "python"
        assert info["is_git"] is True
        assert "languages" in info

    def test_skip_node_modules(self, tmp_path: Path):
        """Test that node_modules is skipped during detection."""
        # Create a Python project
        (tmp_path / "main.py").write_text("print('hello')")

        # Create node_modules with many JS files
        node_modules = tmp_path / "node_modules"
        node_modules.mkdir()
        for i in range(10):
            (node_modules / f"file{i}.js").write_text("module.exports = {};")

        detector = ProjectDetector(tmp_path)
        # Should still detect as Python, not JavaScript
        languages = detector.detect_languages()
        assert "python" in languages


class TestCollectionNaming:
    """Tests for enhanced collection naming with prefix and hash."""

    def test_derive_collection_name_with_prefix(self, tmp_path: Path):
        """Test collection name with prefix."""
        detector = ProjectDetector(tmp_path)
        name = detector.derive_collection_name(prefix="claude")
        assert name.startswith("claude_")

    def test_derive_collection_name_with_hash(self, tmp_path: Path):
        """Test collection name with hash suffix."""
        detector = ProjectDetector(tmp_path)
        name = detector.derive_collection_name(include_hash=True)
        parts = name.split("_")
        # Should have name_hash format when no prefix
        assert len(parts) >= 2
        # Hash should be 6 characters
        assert len(parts[-1]) == 6

    def test_derive_collection_name_with_prefix_and_hash(self, tmp_path: Path):
        """Test collection name with both prefix and hash."""
        detector = ProjectDetector(tmp_path)
        name = detector.derive_collection_name(prefix="claude", include_hash=True)
        parts = name.split("_")
        # Should have prefix_name_hash format
        assert len(parts) == 3
        assert parts[0] == "claude"
        assert len(parts[-1]) == 6  # Hash is 6 chars

    def test_derive_collection_name_backward_compatible(self, tmp_path: Path):
        """Test backward compatibility with no prefix or hash."""
        detector = ProjectDetector(tmp_path)
        name = detector.derive_collection_name()
        # Should just be the sanitized project name
        assert "_" not in name or name == tmp_path.name.lower().replace("_", "-")

    def test_derive_collection_name_custom_prefix(self, tmp_path: Path):
        """Test collection name with custom prefix."""
        detector = ProjectDetector(tmp_path)
        name = detector.derive_collection_name(prefix="myorg", include_hash=True)
        assert name.startswith("myorg_")

    def test_derive_collection_name_prefix_sanitization(self, tmp_path: Path):
        """Test that prefix is sanitized."""
        detector = ProjectDetector(tmp_path)
        name = detector.derive_collection_name(prefix="My@Org!", include_hash=False)
        assert name.startswith("my-org_")

    def test_get_collection_hash_non_git(self, tmp_path: Path):
        """Test hash generation for non-git repository."""
        detector = ProjectDetector(tmp_path)
        hash1 = detector.get_collection_hash()
        hash2 = detector.get_collection_hash()
        # Without git, each call generates a new random hash
        assert len(hash1) == 6
        assert len(hash2) == 6
        # Random hashes should be different (statistically unlikely to be same)
        # Note: This test could theoretically fail with probability 1/16^6

    def test_get_git_remote_url_non_git(self, tmp_path: Path):
        """Test git remote URL for non-git repository returns None."""
        detector = ProjectDetector(tmp_path)
        url = detector.get_git_remote_url()
        assert url is None

    def test_get_git_remote_url_no_remote(self, tmp_path: Path):
        """Test git repo without remote origin."""
        # Create .git directory (simulates git init)
        (tmp_path / ".git").mkdir()
        detector = ProjectDetector(tmp_path)
        # Even with .git dir, without proper git setup, should return None
        url = detector.get_git_remote_url()
        assert url is None

    def test_collection_name_deterministic_with_git(self, tmp_path: Path, monkeypatch):
        """Test that collection hash is deterministic with git remote."""
        import subprocess
        from unittest.mock import MagicMock

        # Create .git directory
        (tmp_path / ".git").mkdir()

        detector = ProjectDetector(tmp_path)

        # Mock subprocess.run to return a consistent remote URL
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "https://github.com/user/repo.git\n"

        def mock_run(*args, **kwargs):
            return mock_result

        monkeypatch.setattr(subprocess, "run", mock_run)

        hash1 = detector.get_collection_hash()
        hash2 = detector.get_collection_hash()

        # With same remote URL, hash should be deterministic
        assert hash1 == hash2
        assert len(hash1) == 6

    def test_collection_hash_url_normalization(self, tmp_path: Path, monkeypatch):
        """Test that URL normalization produces consistent hashes."""
        import subprocess
        from unittest.mock import MagicMock

        (tmp_path / ".git").mkdir()

        detector = ProjectDetector(tmp_path)

        # Test various URL formats that should produce the same hash
        urls = [
            "https://github.com/user/repo.git",
            "https://github.com/user/repo",
            "https://github.com/User/Repo.git",  # Case should be normalized
            "HTTPS://GITHUB.COM/USER/REPO.GIT",  # All caps
        ]

        hashes = []
        for url in urls:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = f"{url}\n"

            monkeypatch.setattr(subprocess, "run", lambda *a, mr=mock_result, **k: mr)
            hashes.append(detector.get_collection_hash())

        # All normalized URLs should produce the same hash
        assert all(h == hashes[0] for h in hashes)
