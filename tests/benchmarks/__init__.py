"""
Performance benchmark tests for UI consistency checking.

These tests validate that the UI consistency checker meets latency targets:
- Tier 0 (Pre-commit): <300ms p95
- Tier 1 (CI Audit): <10 min for 1000+ file repos
- Tier 2 (/redesign): <5 min for focused audit
"""
