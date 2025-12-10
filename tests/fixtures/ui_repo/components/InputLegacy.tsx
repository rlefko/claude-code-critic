/**
 * LegacyInput Component
 *
 * TOKEN DRIFT: This component uses hardcoded colors and values
 * instead of design tokens. Should be flagged for token drift violations.
 *
 * Issues detected by UI Guard:
 * - COLOR.NON_TOKEN: Hardcoded hex colors
 * - SPACING.OFF_SCALE: Non-standard spacing values
 * - RADIUS.OFF_SCALE: Non-standard border radius
 */

import React from 'react';

export interface LegacyInputProps {
  /** Input label */
  label?: string;
  /** Placeholder text */
  placeholder?: string;
  /** Input value */
  value?: string;
  /** Change handler */
  onChange?: (e: React.ChangeEvent<HTMLInputElement>) => void;
  /** Error state */
  hasError?: boolean;
  /** Error message */
  errorMessage?: string;
  /** Disabled state */
  disabled?: boolean;
}

export const LegacyInput: React.FC<LegacyInputProps> = ({
  label,
  placeholder,
  value,
  onChange,
  hasError = false,
  errorMessage,
  disabled = false,
}) => {
  // TOKEN DRIFT: All these values should use CSS custom properties

  const containerStyle: React.CSSProperties = {
    display: 'flex',
    flexDirection: 'column',
    marginBottom: '16px',  // HARDCODED: Should use var(--spacing-4)
  };

  // COLOR.NON_TOKEN: Hardcoded colors
  const labelStyle: React.CSSProperties = {
    fontSize: '14px',      // HARDCODED: Should use var(--text-sm)
    fontWeight: 500,       // HARDCODED: Should use var(--font-medium)
    color: '#1f2937',      // HARDCODED: Should use var(--color-text-primary)
    marginBottom: '4px',   // HARDCODED: Should use var(--spacing-1)
  };

  // MULTIPLE TOKEN DRIFT ISSUES
  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '8px 12px',   // HARDCODED: Should use var(--spacing-2) var(--spacing-3)
    fontSize: '16px',      // HARDCODED: Should use var(--text-base)
    fontFamily: 'system-ui, -apple-system, sans-serif',  // HARDCODED: Should use var(--font-sans)
    backgroundColor: '#ffffff',  // HARDCODED: Should use var(--color-bg-primary)
    border: hasError
      ? '1px solid #ef4444'     // HARDCODED: Should use var(--color-error)
      : '1px solid #d1d5db',    // HARDCODED: Should use var(--color-neutral-300)
    borderRadius: '6px',        // HARDCODED: Should use var(--radius-md)
    color: '#111827',           // HARDCODED: Should use var(--color-text-primary)
    transition: '150ms ease-in-out',  // HARDCODED: Should use var(--transition-fast)
    outline: 'none',
    opacity: disabled ? 0.5 : 1,
    cursor: disabled ? 'not-allowed' : 'text',
  };

  // COLOR.NON_TOKEN: Hardcoded error color
  const errorStyle: React.CSSProperties = {
    fontSize: '12px',      // HARDCODED: Should use var(--text-xs)
    color: '#dc2626',      // HARDCODED: Should use var(--color-error)
    marginTop: '4px',      // HARDCODED: Should use var(--spacing-1)
  };

  // FOCUS STYLES with hardcoded colors
  const handleFocus = (e: React.FocusEvent<HTMLInputElement>) => {
    e.target.style.borderColor = '#3b82f6';  // HARDCODED: Should use var(--color-primary-500)
    e.target.style.boxShadow = '0 0 0 2px rgba(59, 130, 246, 0.2)';  // HARDCODED
  };

  const handleBlur = (e: React.FocusEvent<HTMLInputElement>) => {
    e.target.style.borderColor = hasError ? '#ef4444' : '#d1d5db';  // HARDCODED
    e.target.style.boxShadow = 'none';
  };

  return (
    <div style={containerStyle}>
      {label && <label style={labelStyle}>{label}</label>}
      <input
        style={inputStyle}
        placeholder={placeholder}
        value={value}
        onChange={onChange}
        disabled={disabled}
        onFocus={handleFocus}
        onBlur={handleBlur}
      />
      {hasError && errorMessage && (
        <span style={errorStyle}>{errorMessage}</span>
      )}
    </div>
  );
};

export default LegacyInput;
