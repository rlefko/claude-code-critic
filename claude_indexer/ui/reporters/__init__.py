"""Reporters for UI consistency findings.

This package provides output formatters for UI consistency findings,
including SARIF for GitHub integration and HTML for /redesign reports.
"""

from .html import HTMLReportConfig, HTMLReporter
from .sarif import SARIFConfig, SARIFExporter

__all__ = [
    "HTMLReportConfig",
    "HTMLReporter",
    "SARIFConfig",
    "SARIFExporter",
]
