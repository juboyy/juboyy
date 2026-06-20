/**
 * Design tokens from `docs/07_UX_UI.md` §1.
 * Dark trading theme. Up/down are green/red but NEVER color-alone — always paired
 * with a glyph + label (WCAG 1.4.1); enforced at the component level.
 */

export const colors = {
  bg: {
    base: '#0B0E11', // app background
    surface: '#141A1F', // cards, sheets
    elevated: '#1C242B', // inputs, raised rows
  },
  border: {
    subtle: '#263038', // dividers
  },
  text: {
    primary: '#E8EDF2',
    secondary: '#9AA7B2',
    muted: '#5E6B76',
  },
  accent: {
    up: '#1FBF75', // long / win / RODANDO
    down: '#F0506E', // short / loss / PARADO
    info: '#3B82F6', // links, neutral highlights
    warn: '#F5A524', // stale, cap-near, caution
    armed: '#F0506E', // live-armed banner (danger)
    paper: '#3B82F6', // dry-run badge
  },
} as const;

/** 07 §1 type scale (system font; SF Pro / Roboto). */
export const type = {
  display: { fontSize: 34, lineHeight: 40, fontWeight: '700' as const },
  title: { fontSize: 22, lineHeight: 28, fontWeight: '600' as const },
  headline: { fontSize: 17, lineHeight: 24, fontWeight: '600' as const },
  body: { fontSize: 15, lineHeight: 22, fontWeight: '400' as const },
  caption: { fontSize: 13, lineHeight: 18, fontWeight: '400' as const },
  mono: { fontSize: 15, lineHeight: 20, fontWeight: '500' as const },
} as const;

/** Base unit 4px; scale 4/8/12/16/24/32 (07 §1). */
export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  pill: 999,
} as const;

/** Card padding 16, screen gutter 16, min touch target 44x44 (07 §1). */
export const layout = {
  cardPadding: spacing.lg,
  screenGutter: spacing.lg,
  minTouch: 44,
} as const;

/** Monospace family for prices / P&L / addresses (tabular). */
export const monoFamily = 'Courier' as const;

export const theme = { colors, type, spacing, radius, layout, monoFamily } as const;
export type Theme = typeof theme;
