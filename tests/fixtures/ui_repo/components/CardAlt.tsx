/**
 * ContentBox Component
 *
 * STYLE DUPLICATE: This component duplicates styles from Card.tsx
 * and should be flagged for consolidation.
 *
 * Issues:
 * - Duplicated variant styles (identical to Card)
 * - Duplicated padding styles (identical to Card)
 * - Should reuse Card or extract shared styles
 */

import React from 'react';
import '../styles/tokens.css';

export interface ContentBoxProps {
  /** Box content */
  children: React.ReactNode;
  /** Box heading */
  heading?: string;
  /** Box description */
  description?: string;
  /** Visual style */
  appearance?: 'flat' | 'raised' | 'bordered';
  /** Content spacing */
  spacing?: 'compact' | 'normal' | 'spacious';
}

// STYLE DUPLICATE: Same values as Card.tsx variantStyles
const appearanceStyles = {
  flat: {
    backgroundColor: 'var(--color-bg-primary)',
    boxShadow: 'var(--shadow-sm)',
    border: '1px solid var(--color-neutral-200)',
  },
  raised: {
    backgroundColor: 'var(--color-bg-primary)',
    boxShadow: 'var(--shadow-lg)',
    border: 'none',
  },
  bordered: {
    backgroundColor: 'transparent',
    boxShadow: 'none',
    border: '1px solid var(--color-neutral-300)',
  },
};

// STYLE DUPLICATE: Same values as Card.tsx paddingStyles
const spacingStyles = {
  compact: { padding: 'var(--spacing-3)' },
  normal: { padding: 'var(--spacing-4)' },
  spacious: { padding: 'var(--spacing-6)' },
};

export const ContentBox: React.FC<ContentBoxProps> = ({
  children,
  heading,
  description,
  appearance = 'flat',
  spacing = 'normal',
}) => {
  const appearanceStyle = appearanceStyles[appearance];
  const spacingStyle = spacingStyles[spacing];

  // STYLE DUPLICATE: Same styles as Card.tsx
  const boxStyle: React.CSSProperties = {
    borderRadius: 'var(--radius-lg)',
    overflow: 'hidden',
    transition: 'var(--transition-normal)',
    ...appearanceStyle,
    ...spacingStyle,
  };

  // STYLE DUPLICATE: Same as Card.tsx headerStyle
  const headerAreaStyle: React.CSSProperties = {
    marginBottom: heading || description ? 'var(--spacing-4)' : 0,
  };

  // STYLE DUPLICATE: Same as Card.tsx titleStyle
  const headingStyle: React.CSSProperties = {
    fontSize: 'var(--text-lg)',
    fontWeight: 'var(--font-semibold)' as unknown as number,
    color: 'var(--color-text-primary)',
    margin: 0,
    lineHeight: 'var(--leading-tight)',
  };

  // STYLE DUPLICATE: Same as Card.tsx subtitleStyle
  const descriptionStyle: React.CSSProperties = {
    fontSize: 'var(--text-sm)',
    color: 'var(--color-text-secondary)',
    marginTop: 'var(--spacing-1)',
    margin: 0,
  };

  return (
    <div style={boxStyle}>
      {(heading || description) && (
        <div style={headerAreaStyle}>
          {heading && <h3 style={headingStyle}>{heading}</h3>}
          {description && <p style={descriptionStyle}>{description}</p>}
        </div>
      )}
      {children}
    </div>
  );
};

export default ContentBox;
