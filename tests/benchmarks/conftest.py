"""
Pytest fixtures for benchmark tests.
"""

import shutil
from collections.abc import Generator
from pathlib import Path

import pytest


@pytest.fixture
def fixture_path() -> Path:
    """Return the path to the UI test fixture repository."""
    return Path(__file__).parent.parent / "fixtures" / "ui_repo"


@pytest.fixture
def large_codebase(tmp_path: Path, fixture_path: Path) -> Generator[Path, None, None]:
    """
    Create a large codebase by replicating the fixture multiple times.

    This simulates a 1000+ file repository for Tier 1 performance testing.
    """
    large_path = tmp_path / "large_codebase"
    large_path.mkdir()

    # Create components directory structure
    components_dir = large_path / "components"
    components_dir.mkdir()

    styles_dir = large_path / "styles"
    styles_dir.mkdir()

    # Copy tokens.css as reference
    tokens_src = fixture_path / "styles" / "tokens.css"
    if tokens_src.exists():
        shutil.copy(tokens_src, styles_dir / "tokens.css")

    # Replicate components to create 1000+ files
    fixture_components = fixture_path / "components"
    if fixture_components.exists():
        for i in range(100):  # Create 100 copies of each component
            for component_file in fixture_components.iterdir():
                if component_file.is_file():
                    # Create numbered copy
                    suffix = component_file.suffix
                    stem = component_file.stem
                    new_name = f"{stem}_{i:03d}{suffix}"
                    dest = components_dir / new_name

                    # Copy and modify content slightly
                    content = component_file.read_text()
                    # Replace component names to make them unique
                    content = content.replace(stem, f"{stem}_{i:03d}")
                    dest.write_text(content)

    # Copy styles
    fixture_styles = fixture_path / "styles"
    if fixture_styles.exists():
        for style_file in fixture_styles.iterdir():
            if style_file.is_file() and style_file.name != "tokens.css":
                for i in range(50):  # Create 50 copies of each style file
                    suffix = style_file.suffix
                    stem = style_file.stem
                    new_name = f"{stem}_{i:03d}{suffix}"
                    dest = styles_dir / new_name
                    shutil.copy(style_file, dest)

    yield large_path

    # Cleanup happens automatically via tmp_path fixture


@pytest.fixture
def medium_codebase(tmp_path: Path, fixture_path: Path) -> Generator[Path, None, None]:
    """
    Create a medium-sized codebase (~100 files) for intermediate testing.
    """
    medium_path = tmp_path / "medium_codebase"
    medium_path.mkdir()

    components_dir = medium_path / "components"
    components_dir.mkdir()

    styles_dir = medium_path / "styles"
    styles_dir.mkdir()

    # Copy tokens.css
    tokens_src = fixture_path / "styles" / "tokens.css"
    if tokens_src.exists():
        shutil.copy(tokens_src, styles_dir / "tokens.css")

    # Create 10 copies of each component
    fixture_components = fixture_path / "components"
    if fixture_components.exists():
        for i in range(10):
            for component_file in fixture_components.iterdir():
                if component_file.is_file():
                    suffix = component_file.suffix
                    stem = component_file.stem
                    new_name = f"{stem}_{i:03d}{suffix}"
                    dest = components_dir / new_name
                    content = component_file.read_text()
                    content = content.replace(stem, f"{stem}_{i:03d}")
                    dest.write_text(content)

    yield medium_path


@pytest.fixture
def single_file_content() -> str:
    """Return content of a typical component file for single-file benchmarks."""
    return """
import React from 'react';

interface ButtonProps {
  label: string;
  variant?: 'primary' | 'secondary';
  onClick?: () => void;
}

const styles = {
  primary: {
    backgroundColor: '#3b82f6',  // Hardcoded - should be token
    color: 'white',
    padding: '8px 16px',
  },
  secondary: {
    backgroundColor: '#e5e7eb',
    color: '#374151',
    padding: '8px 16px',
  },
};

export const Button: React.FC<ButtonProps> = ({
  label,
  variant = 'primary',
  onClick,
}) => {
  return (
    <button style={styles[variant]} onClick={onClick}>
      {label}
    </button>
  );
};
"""


@pytest.fixture
def benchmark_iterations() -> int:
    """Return the number of iterations for benchmark tests."""
    return 10  # Run each benchmark 10 times for statistical significance
