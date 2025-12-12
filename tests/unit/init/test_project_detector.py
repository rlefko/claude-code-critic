"""Tests for project detector functionality."""

import json
import pytest
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
