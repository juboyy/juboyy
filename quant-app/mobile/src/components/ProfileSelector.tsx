import { Pressable, View } from 'react-native';
import { colors, layout, radius, spacing } from '@/theme';
import { T } from './Text';
import type { Profile } from '@/types';

/** ProfileSelector (07 §2/§5.6): conservative/aggressive segmented control. */
export function ProfileSelector({
  value,
  onChange,
  disabled,
}: {
  value: Profile;
  onChange: (p: Profile) => void;
  disabled?: boolean;
}) {
  const options: Profile[] = ['conservative', 'aggressive'];
  return (
    <View
      style={{
        flexDirection: 'row',
        backgroundColor: colors.bg.elevated,
        borderRadius: radius.md,
        padding: spacing.xs,
        opacity: disabled ? 0.5 : 1,
      }}
      accessibilityRole="radiogroup"
    >
      {options.map((opt) => {
        const active = opt === value;
        return (
          <Pressable
            key={opt}
            onPress={() => !disabled && onChange(opt)}
            disabled={disabled}
            accessibilityRole="radio"
            accessibilityState={{ selected: active }}
            style={{
              flex: 1,
              minHeight: layout.minTouch - 8,
              borderRadius: radius.sm,
              backgroundColor: active ? colors.accent.info : 'transparent',
              alignItems: 'center',
              justifyContent: 'center',
              paddingVertical: spacing.sm,
            }}
          >
            <T variant="body" style={{ color: active ? '#FFFFFF' : colors.text.secondary, fontWeight: '600' }}>
              {opt[0]?.toUpperCase()}
              {opt.slice(1)}
            </T>
          </Pressable>
        );
      })}
    </View>
  );
}
