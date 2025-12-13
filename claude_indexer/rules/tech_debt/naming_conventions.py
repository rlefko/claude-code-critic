"""
Naming conventions detection rule.

Detects violations of language-specific naming conventions for
functions, classes, variables, and constants.
"""

import re
from typing import TYPE_CHECKING

from ..base import BaseRule, Evidence, RuleContext, Severity, Trigger
from ..fix import AutoFix

if TYPE_CHECKING:
    from ..base import Finding


class NamingConventionsRule(BaseRule):
    """Detect naming convention violations."""

    # Naming convention patterns by language and type
    # Each entry: (detection_pattern, expected_pattern_description, conversion_function_name)
    CONVENTIONS = {
        "python": {
            "function": {
                "detect": r"^\s*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(",
                "valid": r"^[a-z_][a-z0-9_]*$",  # snake_case
                "description": "snake_case (lowercase with underscores)",
                "example": "my_function_name",
            },
            "class": {
                "detect": r"^\s*class\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*[\(:]",
                "valid": r"^[A-Z][a-zA-Z0-9]*$",  # PascalCase
                "description": "PascalCase (capitalized words)",
                "example": "MyClassName",
            },
            "constant": {
                "detect": r"^\s*([A-Z][A-Z0-9_]*)\s*=",
                "valid": r"^[A-Z][A-Z0-9_]*$",  # UPPER_CASE
                "description": "UPPER_CASE (uppercase with underscores)",
                "example": "MY_CONSTANT",
            },
            "variable": {
                # Don't match ALL_UPPERCASE (those are constants)
                "detect": r"^\s*([a-z][a-zA-Z0-9_]*|[a-zA-Z_]*[a-z][a-zA-Z0-9_]*)\s*=(?!=)",
                "valid": r"^[a-z_][a-z0-9_]*$",  # snake_case
                "description": "snake_case (lowercase with underscores)",
                "example": "my_variable",
            },
        },
        "javascript": {
            "function": {
                "detect": r"(?:^|\s)function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*\(|(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>|\w+\s*=>)",
                "valid": r"^_?[a-z][a-zA-Z0-9]*$",  # camelCase (optional underscore prefix)
                "description": "camelCase (first word lowercase, no underscores)",
                "example": "myFunctionName",
            },
            "class": {
                "detect": r"^\s*class\s+([a-zA-Z_$][a-zA-Z0-9_$]*)",
                "valid": r"^[A-Z][a-zA-Z0-9_$]*$",  # PascalCase
                "description": "PascalCase (capitalized words)",
                "example": "MyClassName",
            },
            "constant": {
                "detect": r"^\s*const\s+([A-Z][A-Z0-9_]*)\s*=",
                "valid": r"^[A-Z][A-Z0-9_]*$",  # UPPER_CASE
                "description": "UPPER_CASE (uppercase with underscores)",
                "example": "MY_CONSTANT",
            },
        },
        "typescript": {
            "function": {
                "detect": r"(?:function\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*[\(<]|(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*(?::\s*\w+(?:<[^>]+>)?\s*)?=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>|\w+\s*=>))",
                "valid": r"^[a-z_$][a-zA-Z0-9_$]*$",  # camelCase
                "description": "camelCase (first word lowercase)",
                "example": "myFunctionName",
            },
            "class": {
                "detect": r"^\s*(?:export\s+)?class\s+([a-zA-Z_$][a-zA-Z0-9_$]*)",
                "valid": r"^[A-Z][a-zA-Z0-9_$]*$",  # PascalCase
                "description": "PascalCase (capitalized words)",
                "example": "MyClassName",
            },
            "interface": {
                "detect": r"^\s*(?:export\s+)?interface\s+([a-zA-Z_$][a-zA-Z0-9_$]*)",
                "valid": r"^[A-Z][a-zA-Z0-9_$]*$",  # PascalCase
                "description": "PascalCase (capitalized words)",
                "example": "MyInterfaceName",
            },
            "type": {
                "detect": r"^\s*(?:export\s+)?type\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=",
                "valid": r"^[A-Z][a-zA-Z0-9_$]*$",  # PascalCase
                "description": "PascalCase (capitalized words)",
                "example": "MyTypeName",
            },
            "constant": {
                "detect": r"^\s*const\s+([A-Z][A-Z0-9_]*)\s*(?::\s*\w+)?\s*=",
                "valid": r"^[A-Z][A-Z0-9_]*$",  # UPPER_CASE
                "description": "UPPER_CASE (uppercase with underscores)",
                "example": "MY_CONSTANT",
            },
        },
    }

    # Names to ignore (common exceptions)
    IGNORED_NAMES = {
        "_",  # Unused variable placeholder
        "__",
        "i",
        "j",
        "k",
        "n",
        "x",
        "y",
        "z",  # Loop/math variables
        "e",
        "ex",
        "err",  # Exception variables
        "f",
        "fp",  # File handles
        "db",
        "id",
        "pk",
        "fk",  # Common abbreviations
        "setUp",
        "tearDown",  # Test methods
        "setUpClass",
        "tearDownClass",
    }

    # Patterns that indicate special methods (don't enforce)
    SPECIAL_PATTERNS = [
        r"^__\w+__$",  # Python dunder methods
        r"^test_",  # Test methods (can be verbose)
        r"^_",  # Private/protected
    ]

    @property
    def rule_id(self) -> str:
        return "TECH_DEBT.NAMING_CONVENTIONS"

    @property
    def name(self) -> str:
        return "Naming Convention Detection"

    @property
    def category(self) -> str:
        return "tech_debt"

    @property
    def default_severity(self) -> Severity:
        return Severity.MEDIUM

    @property
    def triggers(self) -> list[Trigger]:
        return [Trigger.ON_WRITE, Trigger.ON_STOP, Trigger.ON_COMMIT]

    @property
    def supported_languages(self) -> list[str] | None:
        return ["python", "javascript", "typescript"]

    @property
    def description(self) -> str:
        return (
            "Detects violations of language-specific naming conventions. "
            "Consistent naming improves code readability and maintainability."
        )

    @property
    def is_fast(self) -> bool:
        return True

    def can_auto_fix(self) -> bool:
        return True

    def _is_special_name(self, name: str) -> bool:
        """Check if name is a special/ignored name."""
        if name in self.IGNORED_NAMES:
            return True
        return any(re.match(pattern, name) for pattern in self.SPECIAL_PATTERNS)

    def _to_snake_case(self, name: str) -> str:
        """Convert name to snake_case."""
        # Handle PascalCase and camelCase
        result = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        result = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", result)
        return result.lower()

    def _to_camel_case(self, name: str) -> str:
        """Convert name to camelCase."""
        # Handle snake_case
        parts = name.split("_")
        if len(parts) == 1:
            return name[0].lower() + name[1:] if name else name
        return parts[0].lower() + "".join(word.capitalize() for word in parts[1:])

    def _to_pascal_case(self, name: str) -> str:
        """Convert name to PascalCase."""
        # Handle snake_case
        parts = name.split("_")
        return "".join(word.capitalize() for word in parts)

    def check(self, context: RuleContext) -> list["Finding"]:
        """Check for naming convention violations.

        Args:
            context: RuleContext with file content

        Returns:
            List of findings for naming violations
        """
        findings = []
        language = context.language

        conventions = self.CONVENTIONS.get(language)
        if not conventions:
            return findings

        lines = context.lines
        # Track reported names to avoid duplicates
        reported_names: set[str] = set()

        for line_num, line in enumerate(lines, start=1):
            # Skip if line not in diff
            if not context.is_line_in_diff(line_num):
                continue

            # Skip comments
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            # Check each naming convention type
            for name_type, rules in conventions.items():
                detect_pattern = rules["detect"]
                valid_pattern = rules["valid"]
                description = rules["description"]
                example = rules["example"]

                match = re.search(detect_pattern, line)
                if match:
                    # Get the name from first non-None group
                    name = None
                    for group in match.groups():
                        if group:
                            name = group
                            break

                    if not name or name in reported_names:
                        continue

                    # Skip special names
                    if self._is_special_name(name):
                        continue

                    # Check if name matches expected pattern
                    if not re.match(valid_pattern, name):
                        reported_names.add(name)

                        # Suggest correction based on type
                        if name_type in ("function", "variable"):
                            if language == "python":
                                suggested = self._to_snake_case(name)
                            else:
                                suggested = self._to_camel_case(name)
                        elif name_type in ("class", "interface", "type"):
                            suggested = self._to_pascal_case(name)
                        else:
                            suggested = name.upper()

                        findings.append(
                            self._create_finding(
                                summary=f"Naming violation: {name_type} '{name}' should be {description}",
                                file_path=str(context.file_path),
                                line_number=line_num,
                                evidence=[
                                    Evidence(
                                        description=f"{name_type.capitalize()} '{name}' does not follow {description} convention",
                                        line_number=line_num,
                                        code_snippet=line.strip(),
                                        data={
                                            "name": name,
                                            "name_type": name_type,
                                            "expected_pattern": description,
                                            "example": example,
                                            "suggested": suggested,
                                        },
                                    )
                                ],
                                remediation_hints=[
                                    f"Rename '{name}' to follow {description} convention",
                                    f"Suggested name: '{suggested}'",
                                    f"Example: {example}",
                                ],
                                confidence=0.85,
                            )
                        )

        return findings

    def auto_fix(self, finding: "Finding", context: RuleContext) -> AutoFix | None:
        """Generate auto-fix to rename identifier.

        Note: This only fixes the current line. Full rename refactoring
        would require updating all references, which is complex.

        Args:
            finding: The finding to fix
            context: RuleContext for the file

        Returns:
            AutoFix to rename identifier on current line, or None
        """
        if finding.line_number is None:
            return None

        if not finding.evidence or not finding.evidence[0].data:
            return None

        data = finding.evidence[0].data
        old_name = data.get("name")
        new_name = data.get("suggested")

        if not old_name or not new_name or old_name == new_name:
            return None

        line = context.get_line_content(finding.line_number)
        if not line:
            return None

        # Replace the name in the line (word boundary match)
        new_line = re.sub(rf"\b{re.escape(old_name)}\b", new_name, line, count=1)

        if new_line == line:
            return None

        return AutoFix(
            finding=finding,
            old_code=line,
            new_code=new_line,
            line_start=finding.line_number,
            line_end=finding.line_number,
            description=f"Renamed '{old_name}' to '{new_name}' (note: may need manual updates to references)",
        )
