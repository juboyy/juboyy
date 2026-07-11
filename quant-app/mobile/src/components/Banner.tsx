import { View } from 'react-native';
import { colors, radius, spacing } from '@/theme';
import { T } from './Text';

type Tone = 'armed' | 'stale' | 'error' | 'dead' | 'info' | 'stopped';

const TONE: Record<Tone, { bg: string; fg: string; icon: string }> = {
  armed: { bg: colors.accent.armed, fg: '#FFFFFF', icon: '◆' },
  stale: { bg: colors.accent.warn, fg: '#0B0E11', icon: '◐' },
  error: { bg: colors.accent.down, fg: '#FFFFFF', icon: '⚠' },
  dead: { bg: colors.accent.down, fg: '#FFFFFF', icon: '☠' },
  info: { bg: colors.accent.info, fg: '#FFFFFF', icon: 'ℹ' },
  stopped: { bg: colors.bg.elevated, fg: colors.text.secondary, icon: '■' },
};

/** Global-state banner (07 §4): armed / stale / dead-man / error / stopped. */
export function Banner({ tone, message }: { tone: Tone; message: string }) {
  const t = TONE[tone];
  return (
    <View
      accessibilityRole="alert"
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: spacing.sm,
        backgroundColor: tone === 'stopped' ? t.bg : t.bg,
        borderRadius: radius.md,
        paddingHorizontal: spacing.md,
        paddingVertical: spacing.sm,
        borderWidth: tone === 'stopped' ? 1 : 0,
        borderColor: colors.border.subtle,
      }}
    >
      <T variant="caption" style={{ color: t.fg }}>
        {t.icon}
      </T>
      <T variant="caption" style={{ color: t.fg, flex: 1, fontWeight: '600' }}>
        {message}
      </T>
    </View>
  );
}
