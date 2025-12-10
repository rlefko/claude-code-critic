---
description: Comprehensive UI audit with evidence-backed design critique and implementation plan
argument-hint: [area-of-focus]
---

# UI Redesign Analysis

You are performing a comprehensive UI consistency and design audit. This command runs in **plan-mode only** - you will analyze and propose changes but NOT make any direct code modifications.

**Area of focus**: $1 (if specified, restricts analysis to routes, stories, or components matching this keyword)

## Pre-Flight Checks

Before running the analysis, verify:
1. UI quality config exists (`ui-quality.config.json`) or use defaults
2. Project has UI files (.tsx, .jsx, .vue, .svelte, .css, .scss)
3. For runtime analysis: Playwright is available and a dev server can be started

## Analysis Protocol

Execute this multi-phase analysis to generate an evidence-backed design critique and implementation plan.

### Phase 1: Static Analysis

Run the CI-tier UI audit on the codebase:

1. Extract style and component fingerprints from all UI files
2. Run cross-file clustering to find duplicates and near-duplicates
3. Identify token drift (hardcoded colors, off-scale spacing, typography)
4. Detect CSS smells (specificity escalation, !important usage)
5. Load baseline to separate new issues from existing technical debt

### Phase 2: Runtime Analysis (Playwright)

If Playwright is available and `include_runtime` is enabled:

1. Start the development server or Storybook
2. Build target list filtered by focus argument:
   - **Route matching**: `/checkout`, `/settings/*` - matches URL paths
   - **Story matching**: `Button--primary`, `Modal` - matches Storybook stories
   - **Component matching**: `AuthModal`, `PaymentForm` - matches component names
   - **Keyword matching**: `authentication`, `forms` - semantic filter
3. For each target page/story:
   - Disable CSS animations for stable screenshots
   - Wait for stable layout
   - Capture role-based elements (buttons, inputs, cards, headings)
   - Extract computed styles for key properties
   - Take element screenshots for visual clustering
   - Capture pseudo-states (hover, focus, disabled)

### Phase 3: Visual Clustering

Cluster captured elements to identify:
- Visually identical components with different code implementations
- Inconsistent variants of the same component role
- Style outliers that deviate from the majority pattern

### Phase 4: Generate Critique

Analyze all collected data to generate evidence-backed critiques:

**Consistency Critiques:**
- Token adherence rates (% of values using design tokens)
- Variant counts per role (e.g., "6 button variants, expected max 3")
- Style outliers (e.g., "one button has radius 6px, most use 8px")

**Visual Hierarchy Critiques:**
- Heading scale consistency (are h1-h6 following a type scale?)
- Contrast ratio checks (WCAG 2.1 AA compliance)
- Spacing rhythm (are spacings from the design scale?)

**Affordance Critiques:**
- Focus visibility (do interactive elements have visible focus rings?)
- Tap target sizes (minimum 44x44px for touch)
- Form label coverage (do inputs have proper labels?)
- Feedback states (loading, disabled, error states present?)

### Phase 5: Generate Implementation Plan

Convert critiques into prioritized, actionable tasks:

1. **Scope grouping**: Tasks ordered by tokens > components > pages
2. **Priority scoring**: `score = impact / (1 + effort_score)`
3. **Quick wins**: Identify high-impact, low-effort tasks
4. **Acceptance criteria**: Generate testable criteria per task
5. **Evidence linking**: Link tasks to screenshots and file:line locations

### Phase 6: Generate Reports

Output comprehensive report with:
- Screenshot galleries showing variant clusters
- Computed style diffs highlighting differences
- Clickable file:line links for IDE navigation
- Prioritized task list with acceptance criteria

## Output Format

Present findings in this structure:

---

## Design Critique Summary

**Token Adherence**: {X}% ({Y} off-scale values)
**Role Consistency**: {N} button variants, {M} input variants, {P} card variants
**Accessibility**: {A} focus visibility issues, {B} tap target issues

---

## Consistency Issues

### 1. **{Issue Title}** ({SEVERITY})

{Description of the issue with quantitative data}

**Evidence:**
- [Screenshot Gallery: {N} variants side-by-side]
- `{file_path}:{line}` - {specific issue}

**Recommendation:** {Suggested fix}

---

## Visual Hierarchy Issues

{Similar format for hierarchy critiques}

---

## Affordance Issues

{Similar format for affordance critiques}

---

## Implementation Plan

### Quick Wins (High Impact, Low Effort)
1. {Task title} - Impact: {X}% | Effort: Low
   - AC: {Acceptance criteria}

### Token-Level Tasks
{Numbered tasks with acceptance criteria}

### Component-Level Tasks
{Numbered tasks with acceptance criteria}

### Page-Level Tasks
{Numbered tasks with acceptance criteria}

---

## Next Steps

After reviewing this critique and plan:

"Which tasks would you like me to implement? Enter task numbers (e.g., '1,3') or 'all' to see detailed implementation steps:"

Based on selection, I will:
- Show detailed implementation steps for each selected task
- Present before/after code changes where applicable
- Wait for your approval before making any modifications

**IMPORTANT**: I will NOT make any code changes until you explicitly approve each modification. This ensures you maintain full control over what gets changed in your codebase.

---

## Report Location

The full HTML report with screenshot galleries is saved to:
`.ui-redesign-reports/redesign_report_{timestamp}.html`

Open this file in a browser to see the visual evidence and navigate to specific issues.
