# UI Quality Metrics Dashboard

> **Phase 9** | Metrics & Success Criteria for UI Consistency System

This document covers the metrics collection, tracking, and reporting system for UI quality measurements.

---

## Overview

The metrics system tracks progress toward UI consistency goals defined in the PRD:

| Metric | Target | Description |
|--------|--------|-------------|
| Hardcoded color reduction | 50% over 3 months | Reduction in unique hardcoded color values |
| Duplicate clusters resolved | 10+ per month | Cross-file duplicate patterns eliminated |
| Suppression rate | <5% | Percentage of baseline issues suppressed |
| /redesign plan adoption | >70% | Tasks completed from generated plans |
| Tier 0 p95 latency | <300ms | Pre-commit guard performance |
| Tier 1 p95 latency | <10min | CI audit performance |
| Tier 2 p95 latency | <5min | /redesign command performance |

---

## CLI Commands

### View Current Metrics

```bash
# Display metrics dashboard (default)
claude-indexer quality-gates metrics show

# JSON output for CI integration
claude-indexer quality-gates metrics show --format json

# Markdown output for reports
claude-indexer quality-gates metrics show --format markdown
```

**Example Output:**

```
UI Quality Metrics Dashboard
============================

Token Drift Reduction
  Unique hardcoded colors:  42 -> 18 (57.1% reduction) [TARGET: 50%]
  Unique hardcoded spacings: 28 -> 12 (57.1% reduction)

Deduplication Progress
  Duplicate clusters:       15 remaining
  Resolved this month:      12 [TARGET: 10]

Quality Indicators
  Suppression rate:         3.2% [TARGET: <5%]
  /redesign plan adoption:  78% [TARGET: >70%]

Performance (p95)
  Tier 0 (pre-commit):     185ms [TARGET: <300ms]
  Tier 1 (CI audit):       4.2min [TARGET: <10min]
  Tier 2 (/redesign):      2.8min [TARGET: <5min]

All targets ON TRACK
```

### View Metrics History

```bash
# Show 30-day trend (default)
claude-indexer quality-gates metrics history

# Custom time range
claude-indexer quality-gates metrics history --days 90

# CSV output for spreadsheets
claude-indexer quality-gates metrics history --format csv

# JSON output for analysis
claude-indexer quality-gates metrics history --format json
```

### Export Metrics

```bash
# Export to JSON file
claude-indexer quality-gates metrics export metrics.json

# Export to CSV file
claude-indexer quality-gates metrics export metrics.csv --format csv

# Export to Prometheus format
claude-indexer quality-gates metrics export metrics.prom --format prometheus
```

### Reset Metrics

```bash
# Clear all metrics history (with confirmation)
claude-indexer quality-gates metrics reset

# Force reset without confirmation
claude-indexer quality-gates metrics reset --force
```

---

## Automatic Metrics Recording

Metrics are automatically recorded after each audit run:

- **Tier 0 (Pre-commit)**: Recorded during `ui-guard` incremental checks
- **Tier 1 (CI Audit)**: Recorded during `quality-gates run ui` full audits
- **Tier 2 (/redesign)**: Recorded during focused design critique runs

To disable automatic recording:

```yaml
# In .ui-quality/config.yaml
ci:
  recordMetrics: false
```

---

## Metrics Data Model

### MetricSnapshot

Each audit run creates a snapshot with:

```python
MetricSnapshot:
    timestamp: str           # ISO format timestamp
    tier: int                # 0, 1, or 2
    unique_hardcoded_colors: int
    unique_hardcoded_spacings: int
    duplicate_clusters_found: int
    total_findings: int
    new_findings: int
    baseline_findings: int
    suppression_rate: float
    analysis_time_ms: float
    files_analyzed: int
    cache_hit_rate: float
    commit_hash: str | None
    branch_name: str | None
```

### PerformancePercentiles

Performance tracking per tier:

```python
PerformancePercentiles:
    tier: int
    p50_ms: float   # Median latency
    p95_ms: float   # 95th percentile
    p99_ms: float   # 99th percentile
    sample_count: int
```

### MetricsReport

Full report stored in `.ui-quality/metrics.json`:

```python
MetricsReport:
    version: str
    project_path: str
    snapshots: list[MetricSnapshot]
    plan_records: list[PlanAdoptionRecord]
    baseline_unique_colors: int
    baseline_unique_spacings: int
    baseline_duplicate_clusters: int
    current_unique_colors: int
    current_unique_spacings: int
    current_duplicate_clusters: int
    current_suppression_rate: float
    tier_0_percentiles: PerformancePercentiles
    tier_1_percentiles: PerformancePercentiles
    tier_2_percentiles: PerformancePercentiles
    targets: dict
    created_at: str
    last_updated: str
```

---

## CI Integration

### GitHub Actions Example

```yaml
name: UI Quality Check

on: [push, pull_request]

jobs:
  ui-quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Run UI Audit
        run: |
          claude-indexer quality-gates run ui --format sarif -o results.sarif

      - name: Export Metrics
        run: |
          claude-indexer quality-gates metrics export metrics.json

      - name: Upload Metrics
        uses: actions/upload-artifact@v4
        with:
          name: ui-metrics
          path: metrics.json
```

### Prometheus Integration

Export metrics in Prometheus format for monitoring dashboards:

```bash
claude-indexer quality-gates metrics export /metrics/ui_quality.prom --format prometheus
```

**Output Format:**

```prometheus
# HELP ui_quality_hardcoded_colors Current count of unique hardcoded colors
# TYPE ui_quality_hardcoded_colors gauge
ui_quality_hardcoded_colors 18

# HELP ui_quality_suppression_rate Current suppression rate
# TYPE ui_quality_suppression_rate gauge
ui_quality_suppression_rate 0.032

# HELP ui_quality_latency_p95_ms P95 latency in milliseconds
# TYPE ui_quality_latency_p95_ms gauge
ui_quality_latency_p95_ms{tier="0"} 185.0
ui_quality_latency_p95_ms{tier="1"} 252000.0
ui_quality_latency_p95_ms{tier="2"} 168000.0

# HELP ui_quality_plan_adoption Plan adoption rate
# TYPE ui_quality_plan_adoption gauge
ui_quality_plan_adoption 0.78
```

### Grafana Dashboard

Use the Prometheus metrics to create Grafana dashboards:

1. Add Prometheus data source pointing to your metrics endpoint
2. Create panels for:
   - Token drift reduction over time
   - Duplicate cluster trend
   - Performance percentiles by tier
   - Plan adoption rate

---

## Risk Mitigation Configurations

The metrics system includes risk mitigation settings for safer UI analysis:

### Deterministic Data Mode

```yaml
# In .ui-quality/config.yaml
riskMitigation:
  deterministicData:
    enabled: true
    seed: 42
    mockTimestamps: true
    mockUserData: true
```

When enabled, analysis uses deterministic data to ensure reproducible results.

### PII Redaction

```yaml
riskMitigation:
  piiRedaction:
    enabled: true
    redactEmails: true
    redactNames: true
    redactPhoneNumbers: true
    redactAddresses: true
    redactionPlaceholder: "[REDACTED]"
    blurImages: true
    customPatterns:
      - "\\d{3}-\\d{2}-\\d{4}"  # SSN pattern
```

Automatically redacts sensitive data from analysis results and screenshots.

### Storybook Preference

```yaml
riskMitigation:
  storybookPreference:
    preferStorybook: true
    storybookOnly: false
    storyPatterns:
      - "Components/**"
      - "!Components/Internal/**"
    skipStories:
      - "Deprecated/*"
```

Prioritizes Storybook stories over live routes for safer component analysis.

---

## Storage Location

Metrics are stored in:

```
.ui-quality/
  metrics.json    # Full metrics report
  config.yaml     # Configuration including risk mitigations
  baseline.json   # Baseline issues
```

---

## Troubleshooting

### No Metrics Data

If `metrics show` displays no data:

1. Ensure audits have been run: `claude-indexer quality-gates run ui`
2. Check that `recordMetrics` is not disabled in config
3. Verify `.ui-quality/metrics.json` exists

### Incorrect Baseline Comparison

If reduction percentages seem wrong:

1. Check baseline values: `claude-indexer quality-gates baseline show`
2. Update baseline if needed: `claude-indexer quality-gates baseline update`
3. Verify correct project path is being used

### Performance Issues

If metrics recording is slow:

1. The metrics system adds minimal overhead (<10ms per audit)
2. Rolling window limits snapshots to prevent unbounded growth
3. Consider reducing `--days` parameter for history queries

---

## API Reference

### MetricsCollector

```python
from claude_indexer.ui.metrics import MetricsCollector

collector = MetricsCollector(project_path, config)

# Load existing report
report = collector.load()

# Record an audit run
collector.record_audit_run(audit_result, tier=1)

# Record plan generation
plan_id = collector.record_plan_generated(total_tasks=5)

# Update plan progress
collector.record_plan_progress(plan_id, completed_tasks=3)

# Save report
collector.save()

# Reset all data
collector.reset()
```

### MetricsAggregator

```python
from claude_indexer.ui.metrics import MetricsAggregator

aggregator = MetricsAggregator(report)

# Calculate reductions
color_reduction = aggregator.calculate_color_reduction()
spacing_reduction = aggregator.calculate_spacing_reduction()

# Get clusters resolved in 30-day window
resolved = aggregator.calculate_clusters_resolved_this_month()

# Calculate performance percentiles
percentiles = aggregator.calculate_percentiles(tier=1)

# Get trend data for charting
trend = aggregator.get_trend_data("colors", days=30)

# Check if target is met
is_met = aggregator.is_target_met("color_reduction_percent")

# Generate full summary
summary = aggregator.generate_summary()

# Export formats
prometheus = aggregator.export_prometheus()
csv_header = aggregator.export_csv_header()
csv_rows = aggregator.export_csv_rows(days=30)
```

---

## See Also

- [UI Consistency Guide](UI_CONSISTENCY_GUIDE.md) - Complete UI analysis documentation
- [UI CI Setup](UI_CI_SETUP.md) - CI integration guide
- [CLI Reference](CLI_REFERENCE.md) - Full CLI command reference
