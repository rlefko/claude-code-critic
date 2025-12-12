"""
SQL injection detection rule.

Detects potential SQL injection vulnerabilities from string concatenation,
f-strings, and format strings used in SQL queries.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, Finding, RuleContext, Severity, Trigger

if TYPE_CHECKING:
    pass


class SQLInjectionRule(BaseRule):
    """Detect SQL injection vulnerabilities."""

    # SQL keywords to look for
    SQL_KEYWORDS = r"(SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|EXEC|EXECUTE|UNION|WHERE)"

    # Language-specific patterns for SQL injection
    # Format: (pattern, description, confidence)
    PATTERNS = {
        "python": [
            # f-string with SQL keywords
            (
                r'f["\'].*?' + SQL_KEYWORDS + r".*?\{",
                "SQL query with f-string interpolation",
                0.95,
            ),
            # .format() with SQL
            (
                r'["\'].*?' + SQL_KEYWORDS + r'.*?["\']\.format\s*\(',
                "SQL query with .format() interpolation",
                0.90,
            ),
            # % formatting with SQL
            (
                r'["\'].*?' + SQL_KEYWORDS + r'.*?%[sd].*?["\'].*?%\s*[\(\[]',
                "SQL query with % formatting",
                0.90,
            ),
            # String concatenation with SQL keywords
            (
                r'["\'].*?' + SQL_KEYWORDS + r'.*?["\']\s*\+',
                "SQL query with string concatenation",
                0.85,
            ),
            # execute with concatenation
            (
                r'\.execute\s*\(\s*["\'].*?\+',
                "SQL execute with string concatenation",
                0.90,
            ),
            # execute with f-string
            (
                r'\.execute\s*\(\s*f["\']',
                "SQL execute with f-string",
                0.95,
            ),
            # cursor operations with dynamic strings
            (
                r"cursor\.(execute|executemany)\s*\([^,)]*(\+|\.format|\{)",
                "Cursor execution with dynamic SQL",
                0.90,
            ),
        ],
        "javascript": [
            # Template literals with SQL
            (
                r"`.*?" + SQL_KEYWORDS + r".*?\$\{",
                "SQL query with template literal interpolation",
                0.95,
            ),
            # String concatenation with SQL
            (
                r'["\'].*?' + SQL_KEYWORDS + r'.*?["\']\s*\+',
                "SQL query with string concatenation",
                0.85,
            ),
            # query() with concatenation
            (
                r'\.query\s*\(\s*[`"\']\s*.*?\+',
                "SQL query with string concatenation",
                0.85,
            ),
            # query() with template literal
            (
                r"\.query\s*\(\s*`[^`]*\$\{",
                "SQL query with template literal",
                0.90,
            ),
            # execute with dynamic string
            (
                r'\.execute\s*\(\s*[`"\']\s*.*?(\+|\$\{)',
                "SQL execute with dynamic string",
                0.90,
            ),
        ],
        "typescript": [
            # Same as JavaScript
            (
                r"`.*?" + SQL_KEYWORDS + r".*?\$\{",
                "SQL query with template literal interpolation",
                0.95,
            ),
            (
                r'["\'].*?' + SQL_KEYWORDS + r'.*?["\']\s*\+',
                "SQL query with string concatenation",
                0.85,
            ),
            (
                r"\.query\s*\(\s*`[^`]*\$\{",
                "SQL query with template literal",
                0.90,
            ),
        ],
        "java": [
            # String concatenation with SQL
            (
                r'["\'].*?' + SQL_KEYWORDS + r'.*?["\']\s*\+',
                "SQL query with string concatenation",
                0.85,
            ),
            # Statement.execute with concatenation
            (
                r"(Statement|Connection)\.(execute|executeQuery|executeUpdate)\s*\([^)]*\+",
                "SQL Statement with string concatenation",
                0.90,
            ),
            # String.format with SQL
            (
                r'String\.format\s*\(\s*["\'].*?' + SQL_KEYWORDS,
                "SQL query with String.format()",
                0.90,
            ),
        ],
        "php": [
            # String interpolation in SQL
            (
                r'["\'].*?' + SQL_KEYWORDS + r".*?\$\w+",
                "SQL query with variable interpolation",
                0.90,
            ),
            # Concatenation with SQL
            (
                r'["\'].*?' + SQL_KEYWORDS + r'.*?["\']\s*\.',
                "SQL query with string concatenation",
                0.85,
            ),
            # mysqli_query with variable
            (
                r'mysqli_query\s*\([^,]+,\s*["\'][^"\']*\$',
                "mysqli_query with variable interpolation",
                0.90,
            ),
            # PDO query without prepared statement
            (
                r'\$\w+->query\s*\(\s*["\'][^"\']*\$',
                "PDO query with variable interpolation",
                0.90,
            ),
        ],
        "go": [
            # fmt.Sprintf with SQL
            (
                r'fmt\.Sprintf\s*\(\s*["`].*?' + SQL_KEYWORDS,
                "SQL query with fmt.Sprintf()",
                0.90,
            ),
            # String concatenation
            (
                r'["`].*?' + SQL_KEYWORDS + r'.*?["`]\s*\+',
                "SQL query with string concatenation",
                0.85,
            ),
            # db.Exec/Query with formatting
            (
                r"db\.(Exec|Query|QueryRow)\s*\(\s*fmt\.Sprintf",
                "SQL query with fmt.Sprintf()",
                0.90,
            ),
        ],
        "ruby": [
            # String interpolation with SQL
            (
                r'["\'].*?' + SQL_KEYWORDS + r".*?#\{",
                "SQL query with string interpolation",
                0.90,
            ),
            # String concatenation
            (
                r'["\'].*?' + SQL_KEYWORDS + r'.*?["\']\s*\+',
                "SQL query with string concatenation",
                0.85,
            ),
            # execute with interpolation
            (
                r'\.execute\s*\(\s*["\'].*?#\{',
                "SQL execute with string interpolation",
                0.90,
            ),
        ],
    }

    # Patterns indicating safe parameterized queries
    SAFE_PATTERNS = [
        r"\?\s*\)",  # Placeholder ?
        r"\$\d+",  # PostgreSQL-style $1, $2
        r":\w+",  # Named parameters :name
        r"%\(.*?\)s",  # Python dict formatting with psycopg2
        r"bindValue|bindParam",  # PHP PDO
        r"setString|setInt|setParameter",  # Java PreparedStatement
        r"\.prepare\s*\(",  # Prepared statement
        r"Prepared|PreparedStatement",
    ]

    @property
    def rule_id(self) -> str:
        return "SECURITY.SQL_INJECTION"

    @property
    def name(self) -> str:
        return "SQL Injection Detection"

    @property
    def category(self) -> str:
        return "security"

    @property
    def default_severity(self) -> Severity:
        return Severity.CRITICAL

    @property
    def triggers(self) -> list[Trigger]:
        return [Trigger.ON_WRITE, Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        return list(self.PATTERNS.keys())

    @property
    def description(self) -> str:
        return (
            "Detects potential SQL injection vulnerabilities from string "
            "concatenation, interpolation, or formatting used in SQL queries."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def _is_likely_safe(self, line: str, surrounding_lines: list[str]) -> bool:
        """Check if the query appears to use parameterized queries."""
        text_to_check = line + " " + " ".join(surrounding_lines)
        for pattern in self.SAFE_PATTERNS:
            if re.search(pattern, text_to_check, re.IGNORECASE):
                return True
        return False

    def check(self, context: RuleContext) -> list[Finding]:
        """Check for SQL injection vulnerabilities.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for detected SQL injection risks
        """
        findings = []
        language = context.language

        # Get patterns for this language
        patterns = self.PATTERNS.get(language, [])
        if not patterns:
            return findings

        file_path_str = str(context.file_path)

        # Check if this is a test file
        is_test_file = any(
            marker in file_path_str.lower()
            for marker in ["test_", "_test", "tests/", "spec/", "mock/", "fixture"]
        )

        lines = context.lines

        for line_num, line in enumerate(lines, start=1):
            # Skip if line not in diff
            if not context.is_line_in_diff(line_num):
                continue

            # Skip comment lines
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            # Skip lines with nosec markers
            if "nosec" in line.lower() or "noqa" in line.lower():
                continue

            for pattern, description, base_confidence in patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # Get surrounding lines for context
                    start = max(0, line_num - 3)
                    end = min(len(lines), line_num + 3)
                    surrounding = lines[start:end]

                    # Check if it looks like a safe parameterized query nearby
                    if self._is_likely_safe(line, surrounding):
                        continue

                    # Adjust confidence
                    if is_test_file:
                        confidence = base_confidence * 0.5
                    else:
                        confidence = base_confidence

                    findings.append(
                        self._create_finding(
                            summary=f"Potential SQL injection: {description}",
                            file_path=file_path_str,
                            line_number=line_num,
                            evidence=[
                                Evidence(
                                    description=description,
                                    line_number=line_num,
                                    code_snippet=line.strip(),
                                    data={
                                        "language": language,
                                        "is_test_file": is_test_file,
                                    },
                                )
                            ],
                            remediation_hints=self._get_remediation_hints(language),
                            confidence=confidence,
                        )
                    )
                    break  # Only report first match per line

        return findings

    def _get_remediation_hints(self, language: str) -> list[str]:
        """Get language-specific remediation hints."""
        hints = {
            "python": [
                "Use parameterized queries: cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))",
                "Use an ORM like SQLAlchemy or Django ORM",
                "If using psycopg2, use %s placeholders with tuple parameter",
            ],
            "javascript": [
                "Use parameterized queries: db.query('SELECT * FROM users WHERE id = $1', [userId])",
                "Use an ORM like Sequelize, TypeORM, or Prisma",
                "Never concatenate user input into SQL strings",
            ],
            "typescript": [
                "Use parameterized queries with prepared statements",
                "Use TypeORM, Prisma, or similar type-safe query builders",
                "Leverage TypeScript's type system to validate inputs",
            ],
            "java": [
                "Use PreparedStatement: PreparedStatement ps = conn.prepareStatement('SELECT * FROM users WHERE id = ?')",
                "Use JPA/Hibernate with named parameters",
                "Never use Statement with string concatenation",
            ],
            "php": [
                "Use PDO prepared statements: $stmt = $pdo->prepare('SELECT * FROM users WHERE id = ?')",
                "Use mysqli_prepare() with bound parameters",
                "Use an ORM like Doctrine or Eloquent",
            ],
            "go": [
                "Use parameterized queries: db.Query('SELECT * FROM users WHERE id = $1', userId)",
                "Use database/sql with placeholder parameters",
                "Consider using sqlx or GORM for safer queries",
            ],
            "ruby": [
                "Use parameterized queries: Model.where('id = ?', user_id)",
                "ActiveRecord methods like .find() and .where() are safe with proper usage",
                "Never interpolate user input directly into SQL strings",
            ],
        }
        return hints.get(
            language,
            [
                "Use parameterized/prepared statements instead of string concatenation",
                "Use an ORM or query builder with built-in SQL injection protection",
                "Validate and sanitize all user inputs",
            ],
        )
