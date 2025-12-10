/**
 * ActionButton Component
 *
 * NEAR-DUPLICATE: This component is structurally similar to Button.tsx
 * and should be detected as a near-duplicate for consolidation.
 *
 * Differences from Button.tsx:
 * - Different component name (ActionButton vs Button)
 * - Slightly different prop names (kind vs variant)
 * - Missing some features (no loading state)
 * - Some hardcoded values mixed with tokens
 */

import React from 'react';
import '../styles/tokens.css';

export interface ActionButtonProps {
  /** Button content */
  label: React.ReactNode;
  /** Button kind (similar to variant) */
  kind?: 'primary' | 'secondary' | 'outline';
  /** Button size */
  size?: 'small' | 'medium' | 'large';
  /** Disabled state */
  isDisabled?: boolean;
  /** Click handler */
  onPress?: () => void;
  /** HTML button type */
  buttonType?: 'button' | 'submit' | 'reset';
}

// NEAR-DUPLICATE: Same structure as Button but different naming
const kindStyles = {
  primary: {
    backgroundColor: 'var(--color-primary-600)',
    color: 'var(--color-text-inverse)',
    border: 'none',
  },
  secondary: {
    backgroundColor: 'var(--color-neutral-100)',
    color: 'var(--color-text-primary)',
    border: 'none',
  },
  outline: {
    backgroundColor: 'transparent',
    color: 'var(--color-primary-600)',
    border: '1px solid var(--color-primary-600)',
  },
};

// SIZE INCONSISTENCY: Uses different values than Button
const sizeMap = {
  small: {
    padding: '6px 12px',  // HARDCODED: Should use tokens
    fontSize: 'var(--text-sm)',
    borderRadius: '6px',  // HARDCODED: Should use var(--radius-md)
  },
  medium: {
    padding: 'var(--spacing-2) var(--spacing-4)',
    fontSize: 'var(--text-base)',
    borderRadius: 'var(--radius-lg)',
  },
  large: {
    padding: '12px 24px',  // HARDCODED: Should use tokens
    fontSize: 'var(--text-lg)',
    borderRadius: '8px',   // HARDCODED: Should use var(--radius-lg)
  },
};

export const ActionButton: React.FC<ActionButtonProps> = ({
  label,
  kind = 'primary',
  size = 'medium',
  isDisabled = false,
  onPress,
  buttonType = 'button',
}) => {
  const kindStyle = kindStyles[kind];
  const sizeStyle = sizeMap[size];

  const buttonStyle: React.CSSProperties = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontFamily: 'var(--font-sans)',
    fontWeight: 500,  // HARDCODED: Should use var(--font-medium)
    lineHeight: 1.25, // HARDCODED: Should use var(--leading-tight)
    cursor: isDisabled ? 'not-allowed' : 'pointer',
    opacity: isDisabled ? 0.5 : 1,
    transition: '150ms ease-in-out',  // HARDCODED: Should use var(--transition-fast)
    ...kindStyle,
    ...sizeStyle,
  };

  return (
    <button
      type={buttonType}
      style={buttonStyle}
      onClick={isDisabled ? undefined : onPress}
      disabled={isDisabled}
      aria-disabled={isDisabled}
    >
      {label}
    </button>
  );
};

export default ActionButton;
