# UI Test Fixture Repository

This directory contains a comprehensive test fixture for validating the UI Consistency Guard system.

## Structure

```
ui_repo/
├── components/           # Component fixtures
│   ├── Button.tsx       # Canonical React button (uses tokens)
│   ├── ButtonVariant.tsx # Near-duplicate (should WARN)
│   ├── Card.tsx         # Canonical React card (uses tokens)
│   ├── CardAlt.tsx      # Style duplicate (should WARN)
│   ├── Input.tsx        # Canonical input (uses tokens)
│   ├── InputLegacy.tsx  # Token drift example (should FAIL)
│   ├── Modal.tsx        # CSS smell (!important usage)
│   ├── Toast.tsx        # Inconsistent focus ring
│   ├── VueButton.vue    # Cross-framework duplicate
│   ├── VueCard.vue      # Cross-framework style duplicate
│   └── SvelteInput.svelte # Cross-framework token drift
├── styles/
│   ├── tokens.css       # Design token definitions
│   ├── overrides.css    # CSS specificity escalation
│   ├── utilities.scss   # Duplicate utility patterns
│   └── legacy.css       # Baseline issues (shouldn't block)
├── tailwind.config.js   # Token source configuration
├── .ui-quality.yaml     # UI quality checker config
└── README.md            # This file
```

## Expected Detections

### Token Drift (FAIL)
- `InputLegacy.tsx` - 15+ hardcoded color values
- `SvelteInput.svelte` - Hardcoded colors and spacing

### Near-Duplicates (WARN)
- `Button.tsx` ↔ `ButtonVariant.tsx` - Same structure, different naming
- `Button.tsx` ↔ `VueButton.vue` - Cross-framework duplicate
- `Card.tsx` ↔ `CardAlt.tsx` - Identical styling
- `Card.tsx` ↔ `VueCard.vue` - Cross-framework style duplicate

### CSS Smells (WARN/FAIL)
- `Modal.tsx` - `!important` usage (FAIL for new files)
- `overrides.css` - Deep selector chains, specificity escalation
- `utilities.scss` - Duplicate utility class patterns

### Inconsistencies (WARN)
- `Toast.tsx` - Focus ring styling differs from other components

### Baseline Issues (INFO)
- `legacy.css` - All issues should be classified as baseline

## Test Scenarios

### Scenario 1: Duplicate Detection
The checker should identify that `CardAlt.tsx` duplicates styles from `Card.tsx`:
- Same variant styles object structure
- Same padding styles
- Same title/subtitle styling

### Scenario 2: Cross-Framework Detection
The checker should detect that `VueButton.vue` is structurally identical to `Button.tsx`:
- Same variant options
- Same size options
- Same styling approach

### Scenario 3: Token Drift
`InputLegacy.tsx` should trigger multiple TOKEN.NON_COLOR findings:
- `#1f2937` instead of `var(--color-text-primary)`
- `#ef4444` instead of `var(--color-error)`
- etc.

### Scenario 4: CSS Smell Detection
`overrides.css` should trigger CSS.SPECIFICITY.ESCALATION for selectors like:
```css
.app-container .main-content .sidebar .nav-list .nav-item .nav-link
```

### Scenario 5: Baseline Separation
Issues in `legacy.css` should be classified as baseline and:
- Reported as INFO
- Not block CI
- Appear in the cleanup map

## Usage

```bash
# Run UI quality check on this fixture
claude-indexer quality-gates run ui -p tests/fixtures/ui_repo

# Generate SARIF report
claude-indexer quality-gates run ui -p tests/fixtures/ui_repo --format sarif

# View baseline cleanup map
claude-indexer quality-gates baseline show -p tests/fixtures/ui_repo
```

## Expected Results

| Rule ID | Count | Files |
|---------|-------|-------|
| COLOR.NON_TOKEN | 20+ | InputLegacy.tsx, SvelteInput.svelte, legacy.css |
| SPACING.OFF_SCALE | 10+ | InputLegacy.tsx, ButtonVariant.tsx, legacy.css |
| STYLE.DUPLICATE_SET | 5+ | CardAlt.tsx, utilities.scss |
| COMPONENT.DUPLICATE_CLUSTER | 3 | ButtonVariant.tsx, VueButton.vue, VueCard.vue |
| CSS.SPECIFICITY.ESCALATION | 8+ | overrides.css |
| IMPORTANT.NEW_USAGE | 5+ | Modal.tsx, overrides.css |
| FOCUS.RING.INCONSISTENT | 2 | Toast.tsx |

## Adding New Test Cases

When adding new test scenarios:

1. Create the component/style file with clear comments marking the issue
2. Update this README with expected detection
3. Add corresponding test case in `tests/integration/test_ui_fixtures.py`
4. Update expected counts in `tests/regression/test_ui_snapshots.py`
