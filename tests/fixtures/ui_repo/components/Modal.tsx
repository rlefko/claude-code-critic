/**
 * Modal Component
 *
 * CSS SMELL: This component uses !important declarations
 * which should be flagged by the UI consistency checker.
 *
 * Issues:
 * - IMPORTANT.NEW_USAGE: Multiple !important declarations
 * - CSS.SPECIFICITY.ESCALATION: Inline styles with !important
 */

import React, { useEffect, useCallback } from 'react';
import '../styles/tokens.css';

export interface ModalProps {
  /** Whether modal is open */
  isOpen: boolean;
  /** Close handler */
  onClose: () => void;
  /** Modal title */
  title?: string;
  /** Modal content */
  children: React.ReactNode;
  /** Modal size */
  size?: 'sm' | 'md' | 'lg' | 'xl';
  /** Close on backdrop click */
  closeOnBackdrop?: boolean;
  /** Close on escape key */
  closeOnEscape?: boolean;
}

const sizeStyles = {
  sm: { maxWidth: '400px' },
  md: { maxWidth: '500px' },
  lg: { maxWidth: '700px' },
  xl: { maxWidth: '900px' },
};

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  size = 'md',
  closeOnBackdrop = true,
  closeOnEscape = true,
}) => {
  const handleEscape = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape' && closeOnEscape) {
        onClose();
      }
    },
    [onClose, closeOnEscape]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      // CSS SMELL: Using !important to override body styles
      document.body.style.cssText = 'overflow: hidden !important;';
    }
    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = '';
    };
  }, [isOpen, handleEscape]);

  if (!isOpen) return null;

  const sizeStyle = sizeStyles[size];

  // CSS SMELL: !important in inline styles
  const backdropStyle: React.CSSProperties = {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 'var(--z-modal-backdrop)' as unknown as number,
    // @ts-ignore - Using important for specificity override
    animation: 'fadeIn 150ms ease-out !important',
  };

  // CSS SMELL: Multiple style overrides that require !important
  const modalStyle: React.CSSProperties = {
    backgroundColor: 'var(--color-bg-primary)',
    borderRadius: 'var(--radius-xl)',
    boxShadow: 'var(--shadow-xl)',
    width: '100%',
    ...sizeStyle,
    margin: 'var(--spacing-4)',
    maxHeight: 'calc(100vh - 32px)',
    overflow: 'hidden',
    display: 'flex',
    flexDirection: 'column',
    zIndex: 'var(--z-modal)' as unknown as number,
  };

  const headerStyle: React.CSSProperties = {
    padding: 'var(--spacing-4) var(--spacing-6)',
    borderBottom: '1px solid var(--color-neutral-200)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  };

  const titleStyle: React.CSSProperties = {
    fontSize: 'var(--text-lg)',
    fontWeight: 'var(--font-semibold)' as unknown as number,
    color: 'var(--color-text-primary)',
    margin: 0,
  };

  // CSS SMELL: Close button with !important for reset
  const closeButtonStyle: React.CSSProperties = {
    background: 'none',
    border: 'none',
    padding: 'var(--spacing-2)',
    cursor: 'pointer',
    color: 'var(--color-text-tertiary)',
    borderRadius: 'var(--radius-md)',
    // @ts-ignore
    transition: 'var(--transition-fast) !important',
  };

  const contentStyle: React.CSSProperties = {
    padding: 'var(--spacing-6)',
    overflowY: 'auto',
    flex: 1,
  };

  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget && closeOnBackdrop) {
      onClose();
    }
  };

  return (
    <div
      style={backdropStyle}
      onClick={handleBackdropClick}
      role="dialog"
      aria-modal="true"
      aria-labelledby={title ? 'modal-title' : undefined}
    >
      <div style={modalStyle}>
        {title && (
          <div style={headerStyle}>
            <h2 id="modal-title" style={titleStyle}>
              {title}
            </h2>
            <button
              style={closeButtonStyle}
              onClick={onClose}
              aria-label="Close modal"
            >
              ✕
            </button>
          </div>
        )}
        <div style={contentStyle}>{children}</div>
      </div>
    </div>
  );
};

// CSS SMELL: Global styles with !important
const globalStyles = `
  .modal-open {
    overflow: hidden !important;
  }

  @keyframes fadeIn {
    from {
      opacity: 0 !important;
    }
    to {
      opacity: 1 !important;
    }
  }
`;

export default Modal;
