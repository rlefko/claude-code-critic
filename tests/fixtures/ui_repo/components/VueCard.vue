<template>
  <!--
    VueCard Component

    STYLE DUPLICATE: This Vue component duplicates styles from Card.tsx
    Should be detected as a cross-framework style duplicate.
  -->
  <div
    :style="cardStyle"
    :class="className"
    :data-testid="testId"
    :role="clickable ? 'button' : undefined"
    :tabindex="clickable ? 0 : undefined"
    @click="handleClick"
  >
    <div v-if="title || subtitle" :style="headerStyle">
      <h3 v-if="title" :style="titleStyle">{{ title }}</h3>
      <p v-if="subtitle" :style="subtitleStyle">{{ subtitle }}</p>
    </div>
    <slot></slot>
  </div>
</template>

<script lang="ts">
import { defineComponent, computed, PropType } from 'vue';

type CardVariant = 'default' | 'elevated' | 'outlined';
type CardPadding = 'none' | 'sm' | 'md' | 'lg';

// STYLE DUPLICATE: Same as Card.tsx variantStyles
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

// STYLE DUPLICATE: Same as Card.tsx paddingStyles
const paddingStyles = {
  none: { padding: '0' },
  sm: { padding: 'var(--spacing-3)' },
  md: { padding: 'var(--spacing-4)' },
  lg: { padding: 'var(--spacing-6)' },
};

export default defineComponent({
  name: 'VueCard',

  props: {
    title: {
      type: String,
      default: undefined,
    },
    subtitle: {
      type: String,
      default: undefined,
    },
    variant: {
      type: String as PropType<CardVariant>,
      default: 'default',
    },
    padding: {
      type: String as PropType<CardPadding>,
      default: 'md',
    },
    clickable: {
      type: Boolean,
      default: false,
    },
    className: {
      type: String,
      default: '',
    },
    testId: {
      type: String,
      default: undefined,
    },
  },

  emits: ['click'],

  setup(props, { emit }) {
    // STYLE DUPLICATE: Same style computation as Card.tsx
    const cardStyle = computed(() => {
      const variantStyle = variantStyles[props.variant];
      const paddingStyle = paddingStyles[props.padding];

      return {
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
        transition: 'var(--transition-normal)',
        cursor: props.clickable ? 'pointer' : 'default',
        ...variantStyle,
        ...paddingStyle,
      };
    });

    // STYLE DUPLICATE: Same as Card.tsx headerStyle
    const headerStyle = computed(() => ({
      marginBottom: props.title || props.subtitle ? 'var(--spacing-4)' : '0',
    }));

    // STYLE DUPLICATE: Same as Card.tsx titleStyle
    const titleStyle = {
      fontSize: 'var(--text-lg)',
      fontWeight: 'var(--font-semibold)',
      color: 'var(--color-text-primary)',
      margin: '0',
      lineHeight: 'var(--leading-tight)',
    };

    // STYLE DUPLICATE: Same as Card.tsx subtitleStyle
    const subtitleStyle = {
      fontSize: 'var(--text-sm)',
      color: 'var(--color-text-secondary)',
      marginTop: 'var(--spacing-1)',
      margin: '0',
    };

    const handleClick = () => {
      if (props.clickable) {
        emit('click');
      }
    };

    return {
      cardStyle,
      headerStyle,
      titleStyle,
      subtitleStyle,
      handleClick,
    };
  },
});
</script>

<style scoped>
@import '../styles/tokens.css';
</style>
