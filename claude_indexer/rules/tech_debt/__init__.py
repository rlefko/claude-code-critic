"""
Tech debt rules for detecting code quality issues.

This module contains rules for detecting technical debt including
TODO/FIXME markers, debug statements, commented code, complexity,
token drift, component duplication, and other maintainability concerns.

Rules in this module:
- TECH_DEBT.TODO_MARKERS - Detects TODO/FIXME/HACK markers
- TECH_DEBT.DEBUG_STATEMENTS - Detects print/console.log statements
- TECH_DEBT.COMMENTED_CODE - Detects blocks of commented code
- TECH_DEBT.COMPLEXITY - Detects high cyclomatic complexity
- TECH_DEBT.LARGE_FILES - Detects excessively large files
- TECH_DEBT.MAGIC_NUMBERS - Detects unexplained numeric literals
- TECH_DEBT.NAMING_CONVENTIONS - Detects naming convention violations
- TECH_DEBT.DEPRECATED_APIS - Detects deprecated API usage
- TECH_DEBT.DEAD_CODE - Detects unreachable code
- TECH_DEBT.TOKEN_DRIFT - Detects drift between similar code entities
- TECH_DEBT.COMPONENT_DUPLICATION - Detects duplicate functions/classes
"""

# Rules will be auto-discovered from this directory
