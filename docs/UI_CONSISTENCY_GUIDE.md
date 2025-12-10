# UI Consistency Guide

> Complete guide to using the UI Consistency Guard system for maintaining design system integrity.

## Overview

The UI Consistency Guard is a three-tier system that ensures design token compliance and prevents style drift across your codebase. It detects:

- **Token drift** - Hardcoded colors, spacing, and other values that should use design tokens
- **Style duplication** - Repeated CSS patterns that should be consolidated
- **Component duplication** - Similar components across frameworks (React, Vue, Svelte)
- **CSS smells** - Specificity escalation, `!important` overuse, and other anti-patterns
- **Role inconsistencies** - Outlier styling for similar UI elements (buttons, inputs, cards)

## Three-Tier Architecture

### Tier 0: Pre-commit Guard

**Target latency: <300ms p95**

Fast feedback during development. Runs automatically on each commit to catch issues before they enter the codebase.

```bash
# Runs automatically via pre-commit hook
# Or manually:
claude-indexer ui-guard src/components/Button.tsx
```

**What it checks:**
- Token drift in changed files
- New `!important` declarations
- Obvious duplicates within the changeset

### Tier 1: CI Audit

**Target latency: <10 minutes for 1000+ file repos**

Comprehensive analysis during pull requests. Performs cross-file duplicate detection and generates detailed reports.

```bash
# Run full CI audit
claude-indexer quality-gates run ui --format sarif -o results.sarif

# Run with verbose output
claude-indexer quality-gates run ui --verbose
```

**What it checks:**
- All Tier 0 checks across entire codebase
- Cross-file style duplicate detection
- Component similarity clustering
- Role-based outlier detection
- Baseline vs new issue separation

### Tier 2: /redesign Command

**Target latency: <5 minutes for focused audit**

On-demand design critique with actionable recommendations. Used when planning refactoring or design system updates.

```bash
# Full design audit
claude-indexer redesign

# Focus on specific area
claude-indexer redesign --focus "button components"

# Include runtime analysis (requires Playwright)
claude-indexer redesign --with-runtime
```

**What it provides:**
- Evidence-backed design critique
- Consolidated recommendations
- Priority-ranked cleanup plan
- Visual diff when using runtime mode

---

## Rule Reference

### Token Drift Rules

These rules detect hardcoded values that should use design tokens.

#### COLOR.NON_TOKEN

**Severity: FAIL**

Detects hardcoded colors that should use CSS custom properties.

```tsx
// BAD - triggers COLOR.NON_TOKEN
const styles = {
  backgroundColor: '#3b82f6',
  color: 'white',
};

// GOOD - uses design tokens
const styles = {
  backgroundColor: 'var(--color-primary-600)',
  color: 'var(--color-text-inverse)',
};
```

#### SPACING.OFF_SCALE

**Severity: FAIL**

Detects spacing values not on your design scale.

```css
/* BAD - off-scale spacing */
.container {
  padding: 13px;  /* Not on 4px/8px scale */
  margin: 7px;
}

/* GOOD - on-scale spacing */
.container {
  padding: var(--spacing-3);  /* 12px */
  margin: var(--spacing-2);   /* 8px */
}
```

#### RADIUS.OFF_SCALE

**Severity: FAIL**

Detects border-radius values not matching your token scale.

```css
/* BAD - arbitrary radius */
.card {
  border-radius: 5px;
}

/* GOOD - token-based radius */
.card {
  border-radius: var(--radius-md);
}
```

#### TYPOGRAPHY.OFF_SCALE

**Severity: FAIL**

Detects font sizes, weights, or line heights outside your type scale.

```css
/* BAD - arbitrary typography */
.heading {
  font-size: 19px;
  font-weight: 550;
}

/* GOOD - type scale values */
.heading {
  font-size: var(--font-size-xl);
  font-weight: var(--font-weight-semibold);
}
```

---

### Duplication Rules

These rules detect repeated patterns that should be consolidated.

#### STYLE.DUPLICATE_SET

**Severity: WARN**

Detects identical CSS property sets across files.

```tsx
// File: Button.tsx
const buttonStyles = {
  padding: '8px 16px',
  borderRadius: '4px',
  fontWeight: 600,
};

// File: Card.tsx - DUPLICATE detected
const cardButtonStyles = {
  padding: '8px 16px',
  borderRadius: '4px',
  fontWeight: 600,
};

// RECOMMENDATION: Extract to shared utility
// src/styles/button-base.css
```

#### STYLE.NEAR_DUPLICATE_SET

**Severity: WARN**

Detects style sets with >85% similarity but slight variations.

```tsx
// Button.tsx
const primary = { padding: '8px 16px', background: 'blue' };

// SubmitButton.tsx - NEAR_DUPLICATE (only background differs)
const submit = { padding: '8px 16px', background: 'green' };

// RECOMMENDATION: Use variant pattern instead
```

#### UTILITY.DUPLICATE_SEQUENCE

**Severity: WARN**

Detects repeated Tailwind/utility class sequences.

```html
<!-- Multiple files have this exact sequence -->
<div class="flex items-center justify-between px-4 py-2 bg-white rounded-lg shadow-sm">

<!-- RECOMMENDATION: Extract to component or @apply directive -->
```

#### COMPONENT.DUPLICATE_CLUSTER

**Severity: WARN**

Detects similar component structures across your codebase.

```
Duplicate cluster detected:
  - src/components/Button.tsx
  - src/components/ButtonVariant.tsx
  - src/components/VueButton.vue

Similarity: 87%
RECOMMENDATION: Consolidate into single component with variants
```

---

### CSS Smell Rules

These rules detect problematic CSS patterns.

#### CSS.SPECIFICITY.ESCALATION

**Severity: WARN**

Detects selectors with excessive specificity.

```css
/* BAD - specificity escalation */
.app .main .content .card .card-header .title {
  color: red;
}

body #root .container > .item[data-active="true"]:not(.disabled) {
  background: blue;
}

/* GOOD - flat, low-specificity selectors */
.card-title {
  color: var(--color-text-primary);
}

.item--active {
  background: var(--color-bg-active);
}
```

#### IMPORTANT.NEW_USAGE

**Severity: FAIL**

Detects new `!important` declarations (baseline declarations are exempted).

```css
/* BAD - new !important usage */
.button {
  background: blue !important;  /* FAIL: New !important */
}

/* If !important is truly necessary, document why: */
/* ui-suppress: legacy-override - overrides third-party styles */
.button {
  background: blue !important;
}
```

#### SUPPRESSION.NO_RATIONALE

**Severity: WARN**

Detects suppression comments without explanation.

```css
/* BAD - no rationale */
/* ui-suppress */
.override { color: red !important; }

/* GOOD - includes rationale */
/* ui-suppress: vendor-override - Material UI specificity conflict */
.override { color: red !important; }
```

---

### Inconsistency Rules

These rules detect outlier styling for similar UI roles.

#### ROLE.OUTLIER.BUTTON

**Severity: WARN**

Detects buttons with styling that deviates significantly from the norm.

```
Role outlier detected: src/components/SpecialButton.tsx
  - padding: 4px (norm: 8-16px)
  - border-radius: 0px (norm: 4-8px)

Consider aligning with design system button styles.
```

#### ROLE.OUTLIER.INPUT

**Severity: WARN**

Detects input fields with inconsistent styling.

#### ROLE.OUTLIER.CARD

**Severity: WARN**

Detects card components with outlier styling.

#### FOCUS.RING.INCONSISTENT

**Severity: WARN**

Detects inconsistent focus ring styling across interactive elements.

```css
/* Inconsistent focus rings detected */
.button-a:focus { outline: 2px solid blue; }
.button-b:focus { box-shadow: 0 0 0 2px blue; }
.button-c:focus { outline: none; }  /* Accessibility concern */

/* RECOMMENDATION: Use consistent focus utility */
.focus-ring:focus {
  outline: var(--focus-ring-width) solid var(--focus-ring-color);
  outline-offset: var(--focus-ring-offset);
}
```

---

## Configuration

### Basic Configuration

Create `.ui-quality.yaml` in your project root:

```yaml
# Token sources
tokens:
  css_vars:
    paths:
      - src/styles/tokens.css
      - src/styles/colors.css

# Files to scan
scanning:
  paths:
    - src/**/*.tsx
    - src/**/*.css
    - src/**/*.scss
  exclude:
    - node_modules
    - dist
    - "**/*.test.tsx"

# Gating behavior
gating:
  mode: strict  # 'strict' or 'lenient'
```

### Advanced Configuration

```yaml
tokens:
  # CSS custom properties
  css_vars:
    paths:
      - src/styles/tokens.css
    prefixes:
      - --color-
      - --spacing-
      - --radius-
      - --font-
      - --shadow-

  # Tailwind integration
  tailwind:
    config_path: tailwind.config.js

  # Figma integration (optional)
  figma:
    file_key: ${FIGMA_FILE_KEY}
    access_token: ${FIGMA_ACCESS_TOKEN}

scanning:
  paths:
    - src/**/*.tsx
    - src/**/*.jsx
    - src/**/*.vue
    - src/**/*.svelte
    - src/**/*.css
    - src/**/*.scss
  exclude:
    - node_modules
    - dist
    - coverage
    - "**/*.stories.tsx"
    - "**/*.test.tsx"

gating:
  mode: strict
  similarity_thresholds:
    duplicate: 0.95      # Exact duplicates
    near_duplicate: 0.85 # Similar patterns
    outlier: 1.5         # Standard deviations for outlier detection
  min_confidence: 0.7

# Rule customization
rules:
  COLOR.NON_TOKEN:
    enabled: true
    severity: FAIL
  STYLE.DUPLICATE_SET:
    enabled: true
    severity: WARN
    min_occurrences: 3   # Only flag if 3+ duplicates
  IMPORTANT.NEW_USAGE:
    enabled: true
    severity: FAIL

# Baseline configuration
baseline:
  path: .ui-quality/baseline.json
  auto_update: false
```

---

## Suppression Comments

To suppress specific findings with justification:

```tsx
// Single-line suppression
// ui-suppress: COLOR.NON_TOKEN - brand color not in token system
const brandColor = '#FF6B35';

// Block suppression
/* ui-suppress-start: STYLE.DUPLICATE_SET - intentional variant styles */
const variantA = { padding: '8px' };
const variantB = { padding: '8px' };
/* ui-suppress-end */
```

```css
/* CSS suppression */
/* ui-suppress: CSS.SPECIFICITY.ESCALATION - overriding third-party library */
.mui-override .MuiButton-root {
  background: var(--color-primary-600);
}
```

---

## Troubleshooting

### "Too many findings"

1. **Start with a baseline**: Run `claude-indexer quality-gates baseline update` to establish current state
2. **Focus on new issues**: Baseline issues won't block CI
3. **Incremental cleanup**: Use the cleanup map to prioritize fixes

### "False positives"

1. **Adjust thresholds**: Lower `similarity_thresholds` in config
2. **Use suppressions**: Document intentional patterns with `ui-suppress`
3. **Exclude files**: Add test/story files to exclude list

### "CI too slow"

1. **Enable caching**: Default on, stored in `.ui-quality/cache/`
2. **Limit scope**: Use `scanning.paths` to focus on source files
3. **Incremental mode**: Only analyze changed files in PRs

### "Token sources not detected"

1. **Check paths**: Ensure token file paths are correct
2. **Verify format**: CSS custom properties must use `--` prefix
3. **Check prefixes**: Configure `tokens.css_vars.prefixes` if using non-standard naming

---

## Best Practices

### Adoption Strategy

1. **Phase 1: Observation**
   - Run audit without blocking CI
   - Establish baseline
   - Review cleanup map

2. **Phase 2: Prevention**
   - Enable pre-commit guard
   - Block new violations in CI
   - Baseline protects legacy code

3. **Phase 3: Cleanup**
   - Work through cleanup map P1 items
   - Gradually reduce baseline
   - Track progress over time

### Design System Integration

1. **Token-first**: Define tokens before components
2. **Document tokens**: Keep token documentation current
3. **Enforce early**: Add UI guard to new projects from start
4. **Review regularly**: Run `/redesign` quarterly

### Team Workflow

1. **Pre-commit guard**: Catches 80% of issues instantly
2. **CI audit**: Comprehensive check on PRs
3. **Design reviews**: Use `/redesign` output in design discussions
4. **Cleanup sprints**: Dedicated time to reduce baseline

---

## Integration Points

### Git Hooks

```yaml
# .pre-commit-config.yaml
repos:
  - repo: local
    hooks:
      - id: ui-guard
        name: UI Consistency Guard
        entry: claude-indexer ui-guard
        language: system
        files: \.(tsx|jsx|vue|svelte|css|scss)$
        pass_filenames: true
```

### GitHub Actions

See [UI CI Setup Guide](UI_CI_SETUP.md) for detailed GitHub Actions configuration.

### VS Code Integration

The UI Guard integrates with VS Code through the SARIF Viewer extension:

1. Install "SARIF Viewer" extension
2. Run audit with SARIF output
3. View findings inline in editor

---

## Performance Benchmarks

| Operation | Target | Typical |
|-----------|--------|---------|
| Single file (Tier 0) | <100ms | 50-80ms |
| Batch 10 files (Tier 0) | <300ms | 150-250ms |
| Full repo 100 files (Tier 1) | <60s | 30-45s |
| Full repo 1000 files (Tier 1) | <10min | 5-8min |
| Focused audit (Tier 2) | <5min | 2-3min |

### Cache Performance

- **Cold cache**: Full analysis time
- **Warm cache**: 50-70% faster on subsequent runs
- **Incremental mode**: Only changed files analyzed

---

## Further Reading

- [UI CI Setup Guide](UI_CI_SETUP.md) - CI/CD integration details
- [UI Tool TDD](../UI_TOOL_TDD.md) - Technical design document
- [UI Tool PRD](../UI_TOOL_PRD.md) - Product requirements
- [UI Development Roadmap](../UI_TOOL_DEVELOPMENT_ROADMAP.md) - Implementation phases
