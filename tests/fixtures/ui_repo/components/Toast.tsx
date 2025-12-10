/**
 * Toast Component
 *
 * FOCUS.RING.INCONSISTENT: This component has inconsistent focus ring
 * styling compared to other components in the design system.
 *
 * Issues:
 * - Focus ring color differs from other components
 * - Focus ring width is inconsistent
 * - Missing focus-visible styling
 */

import React, { useEffect, useState } from 'react';
import '../styles/tokens.css';

export interface ToastProps {
  /** Toast message */
  message: string;
  /** Toast variant */
  variant?: 'info' | 'success' | 'warning' | 'error';
  /** Duration in ms (0 = persistent) */
  duration?: number;
  /** Close handler */
  onClose?: () => void;
  /** Show close button */
  showClose?: boolean;
  /** Action button */
  action?: {
    label: string;
    onClick: () => void;
  };
}

const variantStyles = {
  info: {
    backgroundColor: 'var(--color-info)',
    icon: 'ℹ️',
  },
  success: {
    backgroundColor: 'var(--color-success)',
    icon: '✓',
  },
  warning: {
    backgroundColor: 'var(--color-warning)',
    icon: '⚠️',
  },
  error: {
    backgroundColor: 'var(--color-error)',
    icon: '✕',
  },
};

export const Toast: React.FC<ToastProps> = ({
  message,
  variant = 'info',
  duration = 5000,
  onClose,
  showClose = true,
  action,
}) => {
  const [isVisible, setIsVisible] = useState(true);
  const variantStyle = variantStyles[variant];

  useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(() => {
        setIsVisible(false);
        onClose?.();
      }, duration);
      return () => clearTimeout(timer);
    }
  }, [duration, onClose]);

  if (!isVisible) return null;

  const toastStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--spacing-3)',
    padding: 'var(--spacing-3) var(--spacing-4)',
    backgroundColor: variantStyle.backgroundColor,
    color: 'var(--color-text-inverse)',
    borderRadius: 'var(--radius-lg)',
    boxShadow: 'var(--shadow-lg)',
    minWidth: '300px',
    maxWidth: '500px',
  };

  const iconStyle: React.CSSProperties = {
    fontSize: 'var(--text-lg)',
    flexShrink: 0,
  };

  const messageStyle: React.CSSProperties = {
    flex: 1,
    fontSize: 'var(--text-sm)',
    fontWeight: 'var(--font-medium)' as unknown as number,
  };

  // FOCUS.RING.INCONSISTENT: Non-standard focus ring styling
  // Other components use var(--focus-ring-offset) but this uses custom values
  const closeButtonStyle: React.CSSProperties = {
    background: 'rgba(255, 255, 255, 0.2)',
    border: 'none',
    borderRadius: 'var(--radius-md)',
    padding: 'var(--spacing-1)',
    cursor: 'pointer',
    color: 'inherit',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: '24px',
    height: '24px',
    transition: 'var(--transition-fast)',
    // INCONSISTENT: Using different focus ring than other buttons
    outline: 'none',
  };

  // FOCUS.RING.INCONSISTENT: Action button has different focus styling
  const actionButtonStyle: React.CSSProperties = {
    background: 'rgba(255, 255, 255, 0.2)',
    border: '1px solid rgba(255, 255, 255, 0.3)',
    borderRadius: 'var(--radius-md)',
    padding: 'var(--spacing-1) var(--spacing-3)',
    cursor: 'pointer',
    color: 'inherit',
    fontSize: 'var(--text-sm)',
    fontWeight: 'var(--font-medium)' as unknown as number,
    transition: 'var(--transition-fast)',
    outline: 'none',
    // INCONSISTENT: Focus ring color and width differ from Button component
  };

  // FOCUS.RING.INCONSISTENT: Custom focus handlers with non-standard styling
  const handleCloseButtonFocus = (e: React.FocusEvent<HTMLButtonElement>) => {
    // Using different focus ring than standard components
    e.target.style.boxShadow = '0 0 0 2px white';  // INCONSISTENT: Should use var(--focus-ring-offset)
  };

  const handleCloseButtonBlur = (e: React.FocusEvent<HTMLButtonElement>) => {
    e.target.style.boxShadow = 'none';
  };

  const handleActionButtonFocus = (e: React.FocusEvent<HTMLButtonElement>) => {
    // INCONSISTENT: 3px ring instead of standard 2px
    e.target.style.boxShadow = '0 0 0 3px rgba(255, 255, 255, 0.5)';
    e.target.style.outline = '2px solid transparent';  // Different approach
  };

  const handleActionButtonBlur = (e: React.FocusEvent<HTMLButtonElement>) => {
    e.target.style.boxShadow = 'none';
    e.target.style.outline = 'none';
  };

  const handleClose = () => {
    setIsVisible(false);
    onClose?.();
  };

  return (
    <div style={toastStyle} role="alert" aria-live="polite">
      <span style={iconStyle} aria-hidden="true">
        {variantStyle.icon}
      </span>
      <span style={messageStyle}>{message}</span>
      {action && (
        <button
          style={actionButtonStyle}
          onClick={action.onClick}
          onFocus={handleActionButtonFocus}
          onBlur={handleActionButtonBlur}
        >
          {action.label}
        </button>
      )}
      {showClose && (
        <button
          style={closeButtonStyle}
          onClick={handleClose}
          onFocus={handleCloseButtonFocus}
          onBlur={handleCloseButtonBlur}
          aria-label="Close notification"
        >
          ✕
        </button>
      )}
    </div>
  );
};

export default Toast;
