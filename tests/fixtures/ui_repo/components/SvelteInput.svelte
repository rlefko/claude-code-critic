<!--
  SvelteInput Component

  TOKEN DRIFT + CROSS-FRAMEWORK: This Svelte component has token drift
  issues similar to InputLegacy.tsx, demonstrating cross-framework
  token drift detection.

  Issues:
  - COLOR.NON_TOKEN: Hardcoded colors in Svelte context
  - SPACING.OFF_SCALE: Non-standard spacing values
  - TYPOGRAPHY.OFF_SCALE: Hardcoded font sizes
-->

<script lang="ts">
  export let label: string = '';
  export let placeholder: string = '';
  export let value: string = '';
  export let error: string = '';
  export let disabled: boolean = false;
  export let size: 'sm' | 'md' | 'lg' = 'md';

  // Generate unique ID
  const inputId = `input-${Math.random().toString(36).substr(2, 9)}`;

  $: hasError = Boolean(error);
</script>

<div class="input-container">
  {#if label}
    <label for={inputId} class="label">{label}</label>
  {/if}

  <input
    id={inputId}
    type="text"
    class="input input-{size}"
    class:error={hasError}
    class:disabled
    {placeholder}
    bind:value
    {disabled}
    aria-invalid={hasError}
    aria-describedby={hasError ? `${inputId}-error` : undefined}
  />

  {#if hasError}
    <span id={`${inputId}-error`} class="error-message">{error}</span>
  {/if}
</div>

<style>
  /* TOKEN DRIFT: Using hardcoded values instead of CSS custom properties */

  .input-container {
    display: flex;
    flex-direction: column;
    margin-bottom: 16px; /* HARDCODED: Should use var(--spacing-4) */
  }

  /* COLOR.NON_TOKEN: Hardcoded color */
  .label {
    font-size: 14px; /* HARDCODED: Should use var(--text-sm) */
    font-weight: 500; /* HARDCODED: Should use var(--font-medium) */
    color: #374151; /* HARDCODED: Should use var(--color-text-primary) */
    margin-bottom: 4px; /* HARDCODED: Should use var(--spacing-1) */
  }

  /* MULTIPLE TOKEN DRIFT ISSUES */
  .input {
    width: 100%;
    font-family: system-ui, -apple-system, sans-serif; /* HARDCODED */
    background-color: #ffffff; /* HARDCODED: Should use var(--color-bg-primary) */
    border: 1px solid #d1d5db; /* HARDCODED: Should use var(--color-neutral-300) */
    border-radius: 6px; /* HARDCODED: Should use var(--radius-md) */
    color: #111827; /* HARDCODED: Should use var(--color-text-primary) */
    transition: 150ms ease-in-out; /* HARDCODED: Should use var(--transition-fast) */
    outline: none;
  }

  /* SPACING.OFF_SCALE: Non-standard sizes */
  .input-sm {
    padding: 6px 10px; /* HARDCODED: Non-standard values */
    font-size: 13px; /* HARDCODED: Off-scale (not in token set) */
    height: 30px; /* HARDCODED: Non-standard */
  }

  .input-md {
    padding: 8px 12px; /* HARDCODED: Should use var(--spacing-2) var(--spacing-3) */
    font-size: 16px; /* HARDCODED: Should use var(--text-base) */
    height: 40px;
  }

  .input-lg {
    padding: 10px 16px; /* HARDCODED: Should use var(--spacing-3) var(--spacing-4) */
    font-size: 18px; /* HARDCODED: Should use var(--text-lg) */
    height: 48px;
  }

  /* COLOR.NON_TOKEN: Focus state with hardcoded colors */
  .input:focus {
    border-color: #3b82f6; /* HARDCODED: Should use var(--color-primary-500) */
    box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2); /* HARDCODED */
  }

  /* COLOR.NON_TOKEN: Error state with hardcoded colors */
  .input.error {
    border-color: #ef4444; /* HARDCODED: Should use var(--color-error) */
  }

  .input.error:focus {
    box-shadow: 0 0 0 2px rgba(239, 68, 68, 0.2); /* HARDCODED */
  }

  .input.disabled {
    opacity: 0.5;
    cursor: not-allowed;
    background-color: #f3f4f6; /* HARDCODED: Should use var(--color-bg-tertiary) */
  }

  /* COLOR.NON_TOKEN + TYPOGRAPHY.OFF_SCALE */
  .error-message {
    font-size: 12px; /* HARDCODED: Should use var(--text-xs) */
    color: #dc2626; /* HARDCODED: Should use var(--color-error) */
    margin-top: 4px; /* HARDCODED: Should use var(--spacing-1) */
  }
</style>
