# UI Quality CI Setup Guide

This guide covers setting up the UI consistency checker as part of your CI/CD pipeline.

## Overview

The UI Quality Gate system provides:
- **Cross-file duplicate detection** - Find and consolidate repeated styles
- **Baseline management** - Separate new issues from existing (inherited) debt
- **SARIF export** - GitHub Security tab integration
- **Cleanup recommendations** - Prioritized list of fixes

## Prerequisites

- Python 3.10+
- `claude-indexer` package installed
- Design token configuration (`.ui-quality.yaml`)

## Quick Start

### 1. Run the Quality Gate

```bash
# Basic run (outputs to CLI)
claude-indexer quality-gates run ui

# JSON output for automation
claude-indexer quality-gates run ui --format json

# SARIF export for GitHub
claude-indexer quality-gates run ui --format sarif -o results.sarif
```

### 2. Configure for Your Project

Create `.ui-quality.yaml` in your project root:

```yaml
# Token sources (pick one or more)
tokens:
  css_vars:
    paths:
      - src/styles/tokens.css
      - src/styles/colors.css
  tailwind:
    config_path: tailwind.config.js
  figma:
    file_key: YOUR_FIGMA_FILE_KEY
    access_token: ${FIGMA_ACCESS_TOKEN}

# Scanning configuration
scanning:
  paths:
    - src/**/*.tsx
    - src/**/*.css
  exclude:
    - node_modules
    - dist

# Gating thresholds
gating:
  mode: strict  # or 'lenient'
  similarity_thresholds:
    duplicate: 0.95
    near_duplicate: 0.85
    outlier: 1.5
  min_confidence: 0.7
```

## CI Integration

### GitHub Actions

Create `.github/workflows/ui-quality.yml`:

```yaml
name: UI Quality Gate

on:
  pull_request:
    paths:
      - '**.tsx'
      - '**.css'
      - '**.scss'
      - '.ui-quality.yaml'

jobs:
  ui-quality:
    runs-on: ubuntu-latest
    permissions:
      security-events: write
      contents: read

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        run: pip install claude-indexer

      - name: Run UI Quality Gate
        run: |
          claude-indexer quality-gates run ui \
            --format sarif \
            -o results.sarif

      - name: Upload SARIF to GitHub Security
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: results.sarif
          category: ui-consistency
```

### Pre-commit Hook

The UI Guard can also run as a pre-commit hook (see Phase 4):

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: ui-guard
        name: UI Consistency Guard
        entry: claude-indexer ui-guard
        language: system
        files: \.(tsx|css|scss)$
        pass_filenames: true
```

## Baseline Management

### Understanding Baselines

The baseline system tracks existing issues separately from new issues:
- **New findings** - Block CI if severity is FAIL
- **Baseline findings** - Informational, don't block CI

This enables progressive adoption without forcing immediate cleanup.

### Managing the Baseline

```bash
# View current baseline
claude-indexer quality-gates baseline show

# Update baseline with current findings
claude-indexer quality-gates baseline update

# Reset baseline (start fresh)
claude-indexer quality-gates baseline reset
```

### Baseline File

The baseline is stored in `.ui-quality/baseline.json`. Consider committing this file to track progress.

## Cleanup Map

The cleanup map provides prioritized recommendations:

```bash
# View cleanup map
claude-indexer quality-gates baseline show
```

Sample output:
```
CLEANUP MAP (156 total issues)
Estimated effort: medium (a few days)

  P1: [COLOR.NON_TOKEN] 45 issues (low effort)
       -> Replace hardcoded colors with design tokens
  P2: [STYLE.DUPLICATE_SET] 28 issues (medium effort)
       -> Extract to shared CSS class or utility
  P3: [COMPONENT.DUPLICATE_CLUSTER] 12 issues (high effort)
       -> Extract shared component with variants
```

## SARIF Integration

SARIF (Static Analysis Results Interchange Format) enables GitHub Security tab integration.

### Viewing Results

1. SARIF results appear in the Security tab
2. Results are categorized by rule type
3. Click findings to see source locations

### Custom SARIF Configuration

```python
from claude_indexer.ui.reporters.sarif import SARIFConfig, SARIFExporter

config = SARIFConfig(
    tool_name="my-ui-checker",
    tool_version="1.0.0",
    include_baseline=False,  # Exclude inherited issues
    include_remediation=True,  # Include fix suggestions
)

exporter = SARIFExporter(config)
sarif_doc = exporter.export(result)
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Pass - No blocking issues |
| 1 | Fail - New FAIL severity issues found |

Baseline issues don't affect exit codes.

## Performance

### Caching

The system caches fingerprints to speed up repeated runs:
- Cache location: `.ui-quality/cache/`
- Invalidation: Content hash change or config change
- Target hit rate: >90% on incremental runs

### Performance Targets

| Operation | Target |
|-----------|--------|
| Full repo (1000 files) | <10 minutes |
| Incremental (10 files) | <30 seconds |
| SARIF export | <1 second |

### Disabling Cache

```bash
claude-indexer quality-gates run ui --no-cache
```

## Troubleshooting

### Common Issues

**"No token sources configured"**
- Add token configuration to `.ui-quality.yaml`
- Ensure token files exist at specified paths

**"High false positive rate"**
- Adjust `similarity_thresholds` in config
- Add suppress comments to intentional patterns

**"CI taking too long"**
- Enable caching (default)
- Limit scan paths in config
- Consider incremental mode for PRs

### Debug Mode

```bash
# Verbose output
claude-indexer quality-gates run ui --verbose

# Check what would be analyzed
claude-indexer quality-gates run ui --dry-run
```

## Rule Reference

| Rule ID | Description | Severity |
|---------|-------------|----------|
| COLOR.NON_TOKEN | Hardcoded color | FAIL |
| SPACING.OFF_SCALE | Off-scale spacing | FAIL |
| RADIUS.OFF_SCALE | Off-scale border radius | FAIL |
| TYPOGRAPHY.OFF_SCALE | Off-scale typography | FAIL |
| STYLE.DUPLICATE_SET | Exact CSS duplicates | WARN |
| STYLE.NEAR_DUPLICATE_SET | Near-duplicate CSS | WARN |
| UTILITY.DUPLICATE_SEQUENCE | Repeated utility classes | WARN |
| COMPONENT.DUPLICATE_CLUSTER | Similar components | WARN |
| ROLE.OUTLIER.* | Style outliers | WARN |
| FOCUS.RING.INCONSISTENT | Inconsistent focus rings | WARN |
| CSS.SPECIFICITY.ESCALATION | High specificity selectors | WARN |
| IMPORTANT.NEW_USAGE | New !important usage | FAIL |
| SUPPRESSION.NO_RATIONALE | Suppression without reason | WARN |

## Further Reading

- [UI Tool TDD](../UI_TOOL_TDD.md) - Technical design document
- [UI Tool PRD](../UI_TOOL_PRD.md) - Product requirements
- [UI Development Roadmap](../UI_TOOL_DEVELOPMENT_ROADMAP.md) - Implementation phases
