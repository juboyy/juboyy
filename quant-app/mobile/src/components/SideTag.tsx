import { View } from 'react-native';
import { colors, radius, spacing } from '@/theme';
import { sideGlyph, sideLabel } from '@/lib/format';
import { T } from './Text';
import type { Side } from '@/types';

/** ▲ UP / ▼ DOWN, colored — glyph + label, never color alone (07 §2). */
export function SideTag({ side, size = 'caption' }: { side: Side; size?: 'caption' | 'body' }) {
  const color = side === 'up' ? colors.accent.up : colors.accent.down;
  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: 4,
        backgroundColor: color + '22',
        borderColor: color,
        borderWidth: 1,
        borderRadius: radius.sm,
        paddingHorizontal: spacing.sm,
        paddingVertical: 2,
      }}
      accessibilityLabel={`Side ${sideLabel(side)}`}
    >
      <T variant={size} style={{ color, fontWeight: '600' }}>
        {sideGlyph(side)} {sideLabel(side)}
      </T>
    </View>
  );
}
