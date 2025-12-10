/**
 * Input Component
 *
 * Canonical text input implementation using design tokens.
 * Supports various states and validation feedback.
 */

import React, { forwardRef } from 'react';
import '../styles/tokens.css';

export interface InputProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'> {
  /** Input label */
  label?: string;
  /** Helper text */
  helperText?: string;
  /** Error message */
  error?: string;
  /** Input size */
  size?: 'sm' | 'md' | 'lg';
  /** Full width */
  fullWidth?: boolean;
  /** Left icon/element */
  startAdornment?: React.ReactNode;
  /** Right icon/element */
  endAdornment?: React.ReactNode;
}

const sizeStyles = {
  sm: {
    padding: 'var(--spacing-2)',
    fontSize: 'var(--text-sm)',
    height: '32px',
  },
  md: {
    padding: 'var(--spacing-2) var(--spacing-3)',
    fontSize: 'var(--text-base)',
    height: '40px',
  },
  lg: {
    padding: 'var(--spacing-3) var(--spacing-4)',
    fontSize: 'var(--text-lg)',
    height: '48px',
  },
};

export const Input = forwardRef<HTMLInputElement, InputProps>(
  (
    {
      label,
      helperText,
      error,
      size = 'md',
      fullWidth = false,
      startAdornment,
      endAdornment,
      disabled,
      className = '',
      id,
      ...rest
    },
    ref
  ) => {
    const inputId = id || `input-${Math.random().toString(36).substr(2, 9)}`;
    const sizeStyle = sizeStyles[size];
    const hasError = Boolean(error);

    const containerStyle: React.CSSProperties = {
      display: 'flex',
      flexDirection: 'column',
      width: fullWidth ? '100%' : 'auto',
    };

    const labelStyle: React.CSSProperties = {
      fontSize: 'var(--text-sm)',
      fontWeight: 'var(--font-medium)' as unknown as number,
      color: 'var(--color-text-primary)',
      marginBottom: 'var(--spacing-1)',
    };

    const inputWrapperStyle: React.CSSProperties = {
      display: 'flex',
      alignItems: 'center',
      position: 'relative',
    };

    const inputStyle: React.CSSProperties = {
      width: '100%',
      fontFamily: 'var(--font-sans)',
      backgroundColor: 'var(--color-bg-primary)',
      border: `1px solid ${hasError ? 'var(--color-error)' : 'var(--color-neutral-300)'}`,
      borderRadius: 'var(--radius-md)',
      color: 'var(--color-text-primary)',
      transition: 'var(--transition-fast)',
      outline: 'none',
      opacity: disabled ? 0.5 : 1,
      cursor: disabled ? 'not-allowed' : 'text',
      ...sizeStyle,
      paddingLeft: startAdornment ? 'var(--spacing-10)' : sizeStyle.padding,
      paddingRight: endAdornment ? 'var(--spacing-10)' : sizeStyle.padding,
    };

    const adornmentStyle: React.CSSProperties = {
      position: 'absolute',
      display: 'flex',
      alignItems: 'center',
      color: 'var(--color-text-tertiary)',
    };

    const helperStyle: React.CSSProperties = {
      fontSize: 'var(--text-sm)',
      color: hasError ? 'var(--color-error)' : 'var(--color-text-secondary)',
      marginTop: 'var(--spacing-1)',
    };

    return (
      <div style={containerStyle} className={className}>
        {label && (
          <label htmlFor={inputId} style={labelStyle}>
            {label}
          </label>
        )}
        <div style={inputWrapperStyle}>
          {startAdornment && (
            <span style={{ ...adornmentStyle, left: 'var(--spacing-3)' }}>
              {startAdornment}
            </span>
          )}
          <input
            ref={ref}
            id={inputId}
            style={inputStyle}
            disabled={disabled}
            aria-invalid={hasError}
            aria-describedby={helperText || error ? `${inputId}-helper` : undefined}
            {...rest}
          />
          {endAdornment && (
            <span style={{ ...adornmentStyle, right: 'var(--spacing-3)' }}>
              {endAdornment}
            </span>
          )}
        </div>
        {(helperText || error) && (
          <span id={`${inputId}-helper`} style={helperStyle}>
            {error || helperText}
          </span>
        )}
      </div>
    );
  }
);

Input.displayName = 'Input';

export default Input;
