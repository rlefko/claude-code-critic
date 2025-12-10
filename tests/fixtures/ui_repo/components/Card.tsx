/**
 * Card Component
 *
 * Canonical card implementation using design tokens.
 * This is the primary card component for content containers.
 */

import React from 'react';
import '../styles/tokens.css';

export interface CardProps {
  /** Card content */
  children: React.ReactNode;
  /** Card title */
  title?: string;
  /** Card subtitle */
  subtitle?: string;
  /** Card variant */
  variant?: 'default' | 'elevated' | 'outlined';
  /** Padding size */
  padding?: 'none' | 'sm' | 'md' | 'lg';
  /** Click handler (makes card interactive) */
  onClick?: () => void;
  /** Additional CSS classes */
  className?: string;
  /** Test ID for testing */
  'data-testid'?: string;
}

const variantStyles = {
  default: {
    backgroundColor: 'var(--color-bg-primary)',
    boxShadow: 'var(--shadow-sm)',
    border: '1px solid var(--color-neutral-200)',
  },
  elevated: {
    backgroundColor: 'var(--color-bg-primary)',
    boxShadow: 'var(--shadow-lg)',
    border: 'none',
  },
  outlined: {
    backgroundColor: 'transparent',
    boxShadow: 'none',
    border: '1px solid var(--color-neutral-300)',
  },
};

const paddingStyles = {
  none: { padding: 0 },
  sm: { padding: 'var(--spacing-3)' },
  md: { padding: 'var(--spacing-4)' },
  lg: { padding: 'var(--spacing-6)' },
};

export const Card: React.FC<CardProps> = ({
  children,
  title,
  subtitle,
  variant = 'default',
  padding = 'md',
  onClick,
  className = '',
  'data-testid': testId,
}) => {
  const variantStyle = variantStyles[variant];
  const paddingStyle = paddingStyles[padding];

  const cardStyle: React.CSSProperties = {
    borderRadius: 'var(--radius-lg)',
    overflow: 'hidden',
    transition: 'var(--transition-normal)',
    cursor: onClick ? 'pointer' : 'default',
    ...variantStyle,
    ...paddingStyle,
  };

  const headerStyle: React.CSSProperties = {
    marginBottom: title || subtitle ? 'var(--spacing-4)' : 0,
  };

  const titleStyle: React.CSSProperties = {
    fontSize: 'var(--text-lg)',
    fontWeight: 'var(--font-semibold)' as unknown as number,
    color: 'var(--color-text-primary)',
    margin: 0,
    lineHeight: 'var(--leading-tight)',
  };

  const subtitleStyle: React.CSSProperties = {
    fontSize: 'var(--text-sm)',
    color: 'var(--color-text-secondary)',
    marginTop: 'var(--spacing-1)',
    margin: 0,
  };

  return (
    <div
      style={cardStyle}
      onClick={onClick}
      className={className}
      data-testid={testId}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      {(title || subtitle) && (
        <div style={headerStyle}>
          {title && <h3 style={titleStyle}>{title}</h3>}
          {subtitle && <p style={subtitleStyle}>{subtitle}</p>}
        </div>
      )}
      {children}
    </div>
  );
};

export default Card;
