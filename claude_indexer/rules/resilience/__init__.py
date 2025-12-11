"""
Resilience rules for detecting reliability issues.

This module contains rules for detecting resilience problems
including swallowed exceptions, missing timeouts, missing retry logic,
unsafe null access, infinite loops, resource leaks, and concurrency issues.

Rules in this module:
- RESILIENCE.UNSAFE_NULL - Detects potentially unsafe null/None access
- RESILIENCE.UNSAFE_LOOP - Detects loops without clear termination
- RESILIENCE.UNSAFE_RESOURCE - Detects unclosed resources (memory leaks)
- RESILIENCE.UNSAFE_CONCURRENCY - Detects race conditions and concurrency issues
"""

# Rules will be auto-discovered from this directory
