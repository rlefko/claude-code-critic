/**
 * Button Component
 *
 * Canonical button implementation using design tokens.
 * This is the primary button component that should be reused.
 */

import React from 'react';
import '../styles/tokens.css';

export interface ButtonProps {
  /** Button label text */
  children: React.ReactNode;
  /** Button variant */
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost';
  /** Button size */
  size?: 'sm' | 'md' | 'lg';
  /** Disabled state */
  disabled?: boolean;
  /** Loading state */
  loading?: boolean;
  /** Click handler */
  onClick?: () => void;
  /** Button type */
  type?: 'button' | 'submit' | 'reset';
  /** Additional CSS classes */
  className?: string;
  /** Accessible label */
  'aria-label'?: string;
}

const variantStyles = {
  primary: {
    backgroundColor: 'var(--color-primary-600)',
    color: 'var(--color-text-inverse)',
    border: 'none',
    hoverBg: 'var(--color-primary-700)',
  },
  secondary: {
    backgroundColor: 'var(--color-neutral-100)',
    color: 'var(--color-text-primary)',
    border: 'none',
    hoverBg: 'var(--color-neutral-200)',
  },
  outline: {
    backgroundColor: 'transparent',
    color: 'var(--color-primary-600)',
    border: '1px solid var(--color-primary-600)',
    hoverBg: 'var(--color-primary-50)',
  },
  ghost: {
    backgroundColor: 'transparent',
    color: 'var(--color-text-primary)',
    border: 'none',
    hoverBg: 'var(--color-neutral-100)',
  },
};

const sizeStyles = {
  sm: {
    padding: 'var(--spacing-2) var(--spacing-3)',
    fontSize: 'var(--text-sm)',
    borderRadius: 'var(--radius-md)',
  },
  md: {
    padding: 'var(--spacing-2) var(--spacing-4)',
    fontSize: 'var(--text-base)',
    borderRadius: 'var(--radius-lg)',
  },
  lg: {
    padding: 'var(--spacing-3) var(--spacing-6)',
    fontSize: 'var(--text-lg)',
    borderRadius: 'var(--radius-lg)',
  },
};

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  disabled = false,
  loading = false,
  onClick,
  type = 'button',
  className = '',
  'aria-label': ariaLabel,
}) => {
  const variantStyle = variantStyles[variant];
  const sizeStyle = sizeStyles[size];

  const buttonStyle: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: 'var(--font-sans)',
    fontWeight: 'var(--font-medium)' as unknown as number,
    lineHeight: 'var(--leading-tight)',
    cursor: disabled || loading ? 'not-allowed' : 'pointer',
    opacity: disabled ? 0.5 : 1,
    transition: 'var(--transition-fast)',
    ...variantStyle,
    ...sizeStyle,
  };

  return (
    <button
      type={type}
      style={buttonStyle}
      onClick={disabled || loading ? undefined : onClick}
      disabled={disabled || loading}
      aria-label={ariaLabel}
      aria-disabled={disabled}
      aria-busy={loading}
      className={className}
    >
      {loading && (
        <span
          style={{
            marginRight: 'var(--spacing-2)',
            animation: 'spin 1s linear infinite',
          }}
          aria-hidden="true"
        >
          Loading...
        </span>
      )}
      {children}
    </button>
  );
};

export default Button;
