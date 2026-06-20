import { View } from 'react-native';
import { colors, radius, spacing } from '@/theme';
import { T } from './Text';

/**
 * CapGauge — horizontal progress bar for loss_cap_used_pct / trades_cap_used_pct
 * (07 §2). Amber ≥70%, red ≥100%. Status conveyed by color + numeric label.
 */
export function Gauge({
  label,
  usedPct,
  caption,
}: {
  label: string;
  usedPct: number;
  caption?: string;
}) {
  const pct = Math.max(0, Math.min(100, usedPct));
  const color =
    usedPct >= 100 ? colors.accent.down : usedPct >= 70 ? colors.accent.warn : colors.accent.up;
  return (
    <View accessibilityLabel={`${label} ${pct.toFixed(1)} percent of cap`}>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          marginBottom: spacing.xs,
        }}
      >
        <T variant="caption" color="secondary">
          {label}
        </T>
        <T variant="caption" mono style={{ color }}>
          {pct.toFixed(1)}%
        </T>
      </View>
      <View
        style={{
          height: 10,
          backgroundColor: colors.bg.elevated,
          borderRadius: radius.pill,
          overflow: 'hidden',
        }}
      >
        <View
          style={{
            width: `${pct}%`,
            height: '100%',
            backgroundColor: color,
            borderRadius: radius.pill,
          }}
        />
      </View>
      {caption ? (
        <T variant="caption" color="muted" style={{ marginTop: spacing.xs }}>
          {caption}
        </T>
      ) : null}
    </View>
  );
}
