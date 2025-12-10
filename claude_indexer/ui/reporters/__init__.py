"""Reporters for UI consistency findings.

This package provides output formatters for UI consistency findings,
including SARIF for GitHub integration.
"""

from .sarif import SARIFConfig, SARIFExporter

__all__ = [
    "SARIFConfig",
    "SARIFExporter",
]
