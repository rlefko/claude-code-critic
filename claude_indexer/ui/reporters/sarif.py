"""SARIF exporter for UI consistency findings.

This module exports findings to SARIF (Static Analysis Results
Interchange Format) for integration with GitHub code scanning.

SARIF Specification: https://docs.oasis-open.org/sarif/sarif/v2.1.0/
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..models import Finding, Severity, UIAnalysisResult

    from ..ci.audit_runner import CIAuditResult


@dataclass
class SARIFConfig:
    """Configuration for SARIF output."""

    tool_name: str = "ui-consistency-guard"
    tool_version: str = "1.0.0"
    tool_information_uri: str = (
        "https://github.com/anthropics/claude-code-memory"
    )
    tool_organization: str = "Claude Code Memory"
    include_baseline: bool = False  # Whether to include baseline findings
    include_remediation: bool = True  # Whether to include fix suggestions


# Rule metadata for SARIF
RULE_METADATA = {
    "COLOR.NON_TOKEN": {
        "name": "Non-token Color",
        "shortDescription": "Hardcoded color not in design tokens",
        "fullDescription": (
            "A color value was used that doesn't match any defined design token. "
            "Using design tokens ensures visual consistency across the application."
        ),
        "helpUri": "https://github.com/anthropics/claude-code-memory#color-tokens",
        "tags": ["design-system", "consistency", "color"],
    },
    "SPACING.OFF_SCALE": {
        "name": "Off-scale Spacing",
        "shortDescription": "Spacing value outside design scale",
        "fullDescription": (
            "A spacing value was used that doesn't match the defined spacing scale. "
            "Use values like 4, 8, 12, 16, 24, 32, etc."
        ),
        "helpUri": "https://github.com/anthropics/claude-code-memory#spacing-scale",
        "tags": ["design-system", "consistency", "spacing"],
    },
    "RADIUS.OFF_SCALE": {
        "name": "Off-scale Radius",
        "shortDescription": "Border radius outside design scale",
        "fullDescription": (
            "A border-radius value was used that doesn't match the defined radius scale."
        ),
        "helpUri": "https://github.com/anthropics/claude-code-memory#radius-scale",
        "tags": ["design-system", "consistency", "shape"],
    },
    "TYPOGRAPHY.OFF_SCALE": {
        "name": "Off-scale Typography",
        "shortDescription": "Typography value outside design scale",
        "fullDescription": (
            "A font-size or line-height was used that doesn't match the typography scale."
        ),
        "helpUri": "https://github.com/anthropics/claude-code-memory#typography",
        "tags": ["design-system", "consistency", "typography"],
    },
    "STYLE.DUPLICATE_SET": {
        "name": "Duplicate Style Set",
        "shortDescription": "Identical CSS declaration set found elsewhere",
        "fullDescription": (
            "The same CSS declarations appear in multiple places. "
            "Consider extracting to a shared utility class."
        ),
        "helpUri": "https://github.com/anthropics/claude-code-memory#duplicates",
        "tags": ["duplication", "maintainability"],
    },
    "STYLE.NEAR_DUPLICATE_SET": {
        "name": "Near-duplicate Style Set",
        "shortDescription": "Almost identical CSS declaration set found elsewhere",
        "fullDescription": (
            "Very similar CSS declarations appear in multiple places. "
            "Consider consolidating into a parameterized style."
        ),
        "helpUri": "https://github.com/anthropics/claude-code-memory#near-duplicates",
        "tags": ["duplication", "maintainability"],
    },
    "UTILITY.DUPLICATE_SEQUENCE": {
        "name": "Duplicate Utility Sequence",
        "shortDescription": "Same sequence of utility classes used elsewhere",
        "fullDescription": (
            "The same sequence of utility classes appears in multiple places. "
            "Consider creating a composite class."
        ),
        "helpUri": "https://github.com/anthropics/claude-code-memory#utilities",
        "tags": ["duplication", "maintainability"],
    },
    "COMPONENT.DUPLICATE_CLUSTER": {
        "name": "Duplicate Component Cluster",
        "shortDescription": "Semantically similar component exists",
        "fullDescription": (
            "A component with similar structure and styling already exists. "
            "Consider reusing the existing component or extracting a shared base."
        ),
        "helpUri": "https://github.com/anthropics/claude-code-memory#components",
        "tags": ["duplication", "architecture", "reuse"],
    },
    "ROLE.OUTLIER.BUTTON": {
        "name": "Button Style Outlier",
        "shortDescription": "Button styling differs from most other buttons",
        "fullDescription": (
            "This button has styling that differs from the majority of buttons. "
            "Consider aligning with the standard button styles."
        ),
        "helpUri": "https://github.com/anthropics/claude-code-memory#consistency",
        "tags": ["consistency", "component", "button"],
    },
    "ROLE.OUTLIER.INPUT": {
        "name": "Input Style Outlier",
        "shortDescription": "Input styling differs from most other inputs",
        "fullDescription": (
            "This input has styling that differs from the majority of inputs. "
            "Consider aligning with the standard input styles."
        ),
        "helpUri": "https://github.com/anthropics/claude-code-memory#consistency",
        "tags": ["consistency", "component", "input"],
    },
    "ROLE.OUTLIER.CARD": {
        "name": "Card Style Outlier",
        "shortDescription": "Card styling differs from most other cards",
        "fullDescription": (
            "This card has styling that differs from the majority of cards. "
            "Consider aligning with the standard card styles."
        ),
        "helpUri": "https://github.com/anthropics/claude-code-memory#consistency",
        "tags": ["consistency", "component", "card"],
    },
    "FOCUS.RING.INCONSISTENT": {
        "name": "Inconsistent Focus Ring",
        "shortDescription": "Focus ring styling differs from standards",
        "fullDescription": (
            "The focus ring on this element differs from the standard focus ring style. "
            "Consistent focus indicators improve accessibility."
        ),
        "helpUri": "https://github.com/anthropics/claude-code-memory#accessibility",
        "tags": ["accessibility", "focus", "consistency"],
    },
    "CSS.SPECIFICITY.ESCALATION": {
        "name": "CSS Specificity Escalation",
        "shortDescription": "Deep selector chain detected",
        "fullDescription": (
            "A CSS selector with high specificity was detected. "
            "High specificity makes styles harder to override and maintain."
        ),
        "helpUri": "https://github.com/anthropics/claude-code-memory#specificity",
        "tags": ["maintainability", "css", "specificity"],
    },
    "IMPORTANT.NEW_USAGE": {
        "name": "New !important Usage",
        "shortDescription": "New !important declaration detected",
        "fullDescription": (
            "A new !important declaration was added. "
            "Consider fixing specificity issues instead of using !important."
        ),
        "helpUri": "https://github.com/anthropics/claude-code-memory#important",
        "tags": ["maintainability", "css", "important"],
    },
    "SUPPRESSION.NO_RATIONALE": {
        "name": "Suppression Without Rationale",
        "shortDescription": "Rule suppression without explanation",
        "fullDescription": (
            "A rule was suppressed without providing a rationale. "
            "Always document why a suppression is necessary."
        ),
        "helpUri": "https://github.com/anthropics/claude-code-memory#suppressions",
        "tags": ["documentation", "maintainability"],
    },
}


class SARIFExporter:
    """Exports findings to SARIF format for GitHub Security tab.

    SARIF (Static Analysis Results Interchange Format) is an OASIS
    standard for representing static analysis results.
    """

    SARIF_VERSION = "2.1.0"
    SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"

    def __init__(self, config: SARIFConfig | None = None):
        """Initialize the SARIF exporter.

        Args:
            config: Optional export configuration.
        """
        self.config = config or SARIFConfig()

    def export(
        self,
        result: "CIAuditResult | UIAnalysisResult",
        output_path: Path | None = None,
    ) -> dict[str, Any]:
        """Export findings to SARIF format.

        Args:
            result: Audit result to export.
            output_path: Optional path to write SARIF file.

        Returns:
            SARIF document as dictionary.
        """
        # Get findings based on result type and config
        findings = self._get_findings(result)

        # Build SARIF document
        sarif_doc = self._build_sarif_document(findings)

        # Write to file if path provided
        if output_path:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(sarif_doc, f, indent=2)

        return sarif_doc

    def export_json(
        self,
        result: "CIAuditResult | UIAnalysisResult",
    ) -> str:
        """Export findings to SARIF JSON string.

        Args:
            result: Audit result to export.

        Returns:
            SARIF document as JSON string.
        """
        sarif_doc = self.export(result)
        return json.dumps(sarif_doc, indent=2)

    def _get_findings(
        self, result: "CIAuditResult | UIAnalysisResult"
    ) -> list["Finding"]:
        """Extract findings from result based on config.

        Args:
            result: Audit result.

        Returns:
            List of findings to include.
        """
        # Handle CIAuditResult
        if hasattr(result, "new_findings"):
            if self.config.include_baseline:
                return result.new_findings + result.baseline_findings
            return result.new_findings

        # Handle UIAnalysisResult
        return result.findings

    def _build_sarif_document(self, findings: list["Finding"]) -> dict[str, Any]:
        """Build complete SARIF document structure.

        Args:
            findings: List of findings to include.

        Returns:
            SARIF document dictionary.
        """
        # Build rule definitions from unique rule IDs
        rule_ids = list(set(f.rule_id for f in findings))
        rules = self._build_rule_definitions(rule_ids)

        # Create rule index lookup
        rule_index = {rule_id: idx for idx, rule_id in enumerate(rule_ids)}

        # Build results
        results = [
            self._build_result(finding, rule_index.get(finding.rule_id, 0))
            for finding in findings
        ]

        return {
            "$schema": self.SARIF_SCHEMA,
            "version": self.SARIF_VERSION,
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": self.config.tool_name,
                            "version": self.config.tool_version,
                            "informationUri": self.config.tool_information_uri,
                            "organization": self.config.tool_organization,
                            "rules": rules,
                        }
                    },
                    "results": results,
                }
            ],
        }

    def _build_rule_definitions(self, rule_ids: list[str]) -> list[dict[str, Any]]:
        """Build SARIF rule definitions from unique rule IDs.

        Args:
            rule_ids: List of unique rule IDs.

        Returns:
            List of SARIF rule definition dictionaries.
        """
        rules = []
        for rule_id in rule_ids:
            metadata = RULE_METADATA.get(rule_id, {})

            rule = {
                "id": rule_id,
                "name": metadata.get("name", rule_id.replace(".", " ").title()),
                "shortDescription": {
                    "text": metadata.get("shortDescription", f"Rule {rule_id}")
                },
                "fullDescription": {
                    "text": metadata.get(
                        "fullDescription", f"UI consistency rule: {rule_id}"
                    )
                },
                "defaultConfiguration": {
                    "level": self._default_level_for_rule(rule_id)
                },
                "properties": {
                    "tags": metadata.get("tags", ["ui-consistency"]),
                },
            }

            if "helpUri" in metadata:
                rule["helpUri"] = metadata["helpUri"]

            rules.append(rule)

        return rules

    def _build_result(self, finding: "Finding", rule_index: int) -> dict[str, Any]:
        """Build SARIF result object from Finding.

        Args:
            finding: Finding to convert.
            rule_index: Index of the rule in the rules array.

        Returns:
            SARIF result dictionary.
        """
        result: dict[str, Any] = {
            "ruleId": finding.rule_id,
            "ruleIndex": rule_index,
            "level": self._severity_to_sarif_level(finding.severity),
            "message": {"text": finding.summary},
        }

        # Add location if available
        if finding.source_ref:
            result["locations"] = [self._build_location(finding.source_ref)]

        # Add remediation hints as markdown help
        if self.config.include_remediation and finding.remediation_hints:
            result["fixes"] = [
                {
                    "description": {"text": hint},
                }
                for hint in finding.remediation_hints[:3]  # Max 3 hints
            ]

        # Add confidence as property
        result["properties"] = {
            "confidence": finding.confidence,
            "isNew": finding.is_new,
        }

        return result

    def _build_location(self, source_ref: Any) -> dict[str, Any]:
        """Build SARIF location from SymbolRef.

        Args:
            source_ref: SymbolRef with file and line info.

        Returns:
            SARIF location dictionary.
        """
        location: dict[str, Any] = {
            "physicalLocation": {
                "artifactLocation": {"uri": source_ref.file_path},
                "region": {
                    "startLine": source_ref.start_line,
                },
            }
        }

        # Add end line if different from start
        if source_ref.end_line and source_ref.end_line != source_ref.start_line:
            location["physicalLocation"]["region"]["endLine"] = source_ref.end_line

        return location

    def _severity_to_sarif_level(self, severity: "Severity") -> str:
        """Map Severity to SARIF level.

        Args:
            severity: Finding severity.

        Returns:
            SARIF level string (error/warning/note).
        """
        from ..models import Severity

        mapping = {
            Severity.FAIL: "error",
            Severity.WARN: "warning",
            Severity.INFO: "note",
        }
        return mapping.get(severity, "warning")

    def _default_level_for_rule(self, rule_id: str) -> str:
        """Get default SARIF level for a rule.

        Args:
            rule_id: The rule identifier.

        Returns:
            Default SARIF level string.
        """
        # Token drift and important rules default to error
        if any(
            x in rule_id
            for x in ["NON_TOKEN", "OFF_SCALE", "IMPORTANT", "NO_RATIONALE"]
        ):
            return "error"

        # Duplicates and outliers are warnings
        if any(x in rule_id for x in ["DUPLICATE", "OUTLIER", "INCONSISTENT"]):
            return "warning"

        return "warning"


__all__ = [
    "SARIFConfig",
    "SARIFExporter",
]
