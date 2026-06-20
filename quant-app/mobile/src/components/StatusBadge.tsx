import { View } from 'react-native';
import { colors, radius, spacing } from '@/theme';
import { T } from './Text';
import type { BotState, Mode } from '@/types';

/**
 * StatusPill (RODANDO/PARADO/STALE) and ModeBadge (PAPER/LIVE) per 07 §2.
 * Status is conveyed by icon + text + color (never color alone).
 */

function Pill({ label, icon, color }: { label: string; icon: string; color: string }) {
  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        backgroundColor: color + '22',
        borderColor: color,
        borderWidth: 1,
        borderRadius: radius.pill,
        paddingHorizontal: spacing.sm,
        paddingVertical: 2,
        gap: 4,
      }}
      accessibilityLabel={`${label}`}
    >
      <T variant="caption" style={{ color }}>
        {icon}
      </T>
      <T variant="caption" style={{ color, fontWeight: '600' }}>
        {label}
      </T>
    </View>
  );
}

export function StatusPill({ state }: { state: BotState }) {
  switch (state) {
    case 'RODANDO':
      return <Pill label="RODANDO" icon="●" color={colors.accent.up} />;
    case 'PARADO':
      return <Pill label="PARADO" icon="■" color={colors.accent.down} />;
    case 'STALE':
      return <Pill label="STALE" icon="◐" color={colors.accent.warn} />;
  }
}

export function ModeBadge({ mode, armed }: { mode: Mode; armed?: boolean }) {
  if (mode === 'live') {
    return <Pill label={armed ? 'LIVE ARMED' : 'LIVE'} icon="◆" color={colors.accent.armed} />;
  }
  return <Pill label="PAPER" icon="◇" color={colors.accent.paper} />;
}

/** Generic small status badge (used for trade result / position status). */
export function StatusBadge({
  label,
  tone,
  icon,
}: {
  label: string;
  tone: 'up' | 'down' | 'info' | 'warn' | 'muted';
  icon?: string;
}) {
  const color =
    tone === 'up'
      ? colors.accent.up
      : tone === 'down'
        ? colors.accent.down
        : tone === 'warn'
          ? colors.accent.warn
          : tone === 'info'
            ? colors.accent.info
            : colors.text.muted;
  return <Pill label={label} icon={icon ?? '•'} color={color} />;
}
