import type { ReactNode } from 'react';
import { View } from 'react-native';
import { colors, layout, radius, spacing } from '@/theme';
import { T } from './Text';

/** Compact KPI tile used in the Risk grid (07 §5.4). */
export function KpiCard({
  label,
  value,
  valueNode,
  tone = 'primary',
}: {
  label: string;
  value?: string;
  valueNode?: ReactNode;
  tone?: 'primary' | 'up' | 'down' | 'secondary';
}) {
  const color =
    tone === 'up'
      ? colors.accent.up
      : tone === 'down'
        ? colors.accent.down
        : tone === 'secondary'
          ? colors.text.secondary
          : colors.text.primary;
  return (
    <View
      style={{
        flexGrow: 1,
        flexBasis: '46%',
        backgroundColor: colors.bg.surface,
        borderColor: colors.border.subtle,
        borderWidth: 1,
        borderRadius: radius.md,
        padding: layout.cardPadding,
        gap: spacing.xs,
      }}
    >
      <T variant="caption" color="secondary">
        {label}
      </T>
      {valueNode ?? (
        <T variant="title" mono style={{ color }}>
          {value}
        </T>
      )}
    </View>
  );
}

export function KpiGrid({ children }: { children: ReactNode }) {
  return (
    <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md }}>{children}</View>
  );
}
