<template>
  <!--
    VueButton Component

    CROSS-FRAMEWORK DUPLICATE: This Vue component is structurally identical
    to Button.tsx and should be detected as a cross-framework duplicate.

    The UI consistency checker should identify:
    - Same variant options (primary, secondary, outline, ghost)
    - Same size options (sm, md, lg)
    - Same styling approach
    - Recommend consolidating into shared tokens/styles
  -->
  <button
    :type="type"
    :style="buttonStyle"
    :disabled="disabled || loading"
    :aria-disabled="disabled"
    :aria-busy="loading"
    :aria-label="ariaLabel"
    :class="className"
    @click="handleClick"
  >
    <span v-if="loading" class="loading-indicator" aria-hidden="true">
      Loading...
    </span>
    <slot></slot>
  </button>
</template>

<script lang="ts">
import { defineComponent, computed, PropType } from 'vue';

type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost';
type ButtonSize = 'sm' | 'md' | 'lg';

// CROSS-FRAMEWORK DUPLICATE: Same as Button.tsx variantStyles
const variantStyles = {
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
  ghost: {
    backgroundColor: 'transparent',
    color: 'var(--color-text-primary)',
    border: 'none',
  },
};

// CROSS-FRAMEWORK DUPLICATE: Same as Button.tsx sizeStyles
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

export default defineComponent({
  name: 'VueButton',

  props: {
    variant: {
      type: String as PropType<ButtonVariant>,
      default: 'primary',
    },
    size: {
      type: String as PropType<ButtonSize>,
      default: 'md',
    },
    disabled: {
      type: Boolean,
      default: false,
    },
    loading: {
      type: Boolean,
      default: false,
    },
    type: {
      type: String as PropType<'button' | 'submit' | 'reset'>,
      default: 'button',
    },
    className: {
      type: String,
      default: '',
    },
    ariaLabel: {
      type: String,
      default: undefined,
    },
  },

  emits: ['click'],

  setup(props, { emit }) {
    // CROSS-FRAMEWORK DUPLICATE: Same style computation as Button.tsx
    const buttonStyle = computed(() => {
      const variantStyle = variantStyles[props.variant];
      const sizeStyle = sizeStyles[props.size];

      return {
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: 'var(--font-sans)',
        fontWeight: 'var(--font-medium)',
        lineHeight: 'var(--leading-tight)',
        cursor: props.disabled || props.loading ? 'not-allowed' : 'pointer',
        opacity: props.disabled ? 0.5 : 1,
        transition: 'var(--transition-fast)',
        ...variantStyle,
        ...sizeStyle,
      };
    });

    const handleClick = () => {
      if (!props.disabled && !props.loading) {
        emit('click');
      }
    };

    return {
      buttonStyle,
      handleClick,
    };
  },
});
</script>

<style scoped>
/* CROSS-FRAMEWORK DUPLICATE: Same CSS patterns as Button.tsx */
@import '../styles/tokens.css';

.loading-indicator {
  margin-right: var(--spacing-2);
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}
</style>
