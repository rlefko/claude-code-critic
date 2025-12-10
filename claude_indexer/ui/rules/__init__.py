"""UI consistency rules package.

This package provides the rule engine and built-in rules for
detecting UI consistency issues.
"""

from .base import BaseRule, RuleContext, RuleResult
from .diff_filter import DiffFilter, FilterResult, create_diff_filter
from .duplication import (
    ComponentDuplicateClusterRule,
    StyleDuplicateSetRule,
    StyleNearDuplicateSetRule,
    UtilityDuplicateSequenceRule,
)
from .engine import RuleEngine, RuleEngineConfig, create_rule_engine
from .inconsistency import (
    ButtonOutlierRule,
    CardOutlierRule,
    FocusRingInconsistentRule,
    InputOutlierRule,
    RoleOutlierRule,
)
from .smells import (
    ImportantNewUsageRule,
    SpecificityEscalationRule,
    SuppressionNoRationaleRule,
)
from .token_drift import (
    ColorNonTokenRule,
    RadiusOffScaleRule,
    SpacingOffScaleRule,
    TypographyOffScaleRule,
)

__all__ = [
    # Base classes
    "BaseRule",
    "RuleContext",
    "RuleResult",
    # Engine
    "RuleEngine",
    "RuleEngineConfig",
    "create_rule_engine",
    # Diff filter
    "DiffFilter",
    "FilterResult",
    "create_diff_filter",
    # Token drift rules
    "ColorNonTokenRule",
    "SpacingOffScaleRule",
    "RadiusOffScaleRule",
    "TypographyOffScaleRule",
    # Duplication rules
    "StyleDuplicateSetRule",
    "StyleNearDuplicateSetRule",
    "UtilityDuplicateSequenceRule",
    "ComponentDuplicateClusterRule",
    # Inconsistency rules
    "RoleOutlierRule",
    "ButtonOutlierRule",
    "InputOutlierRule",
    "CardOutlierRule",
    "FocusRingInconsistentRule",
    # Smell rules
    "SpecificityEscalationRule",
    "ImportantNewUsageRule",
    "SuppressionNoRationaleRule",
]
