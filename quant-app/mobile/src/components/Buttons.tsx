import { ActivityIndicator, Pressable, View, type ViewStyle } from 'react-native';
import { colors, layout, radius, spacing } from '@/theme';
import { T } from './Text';

interface BtnProps {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
  style?: ViewStyle;
  accessibilityHint?: string;
}

function ButtonBase({
  label,
  onPress,
  disabled,
  loading,
  bg,
  fg,
  border,
  style,
  accessibilityHint,
}: BtnProps & { bg: string; fg: string; border?: string }) {
  const isDisabled = disabled || loading;
  return (
    <Pressable
      onPress={onPress}
      disabled={isDisabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{ disabled: !!isDisabled }}
      style={({ pressed }) => [
        {
          minHeight: layout.minTouch,
          borderRadius: radius.md,
          backgroundColor: bg,
          borderColor: border ?? 'transparent',
          borderWidth: border ? 1 : 0,
          alignItems: 'center',
          justifyContent: 'center',
          paddingHorizontal: spacing.lg,
          paddingVertical: spacing.md,
          opacity: isDisabled ? 0.4 : pressed ? 0.8 : 1,
        },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={fg} />
      ) : (
        <T variant="headline" style={{ color: fg }}>
          {label}
        </T>
      )}
    </Pressable>
  );
}

export function PrimaryButton(props: BtnProps) {
  return <ButtonBase {...props} bg={colors.accent.info} fg="#FFFFFF" />;
}

export function DangerButton(props: BtnProps) {
  return <ButtonBase {...props} bg={colors.accent.down} fg="#FFFFFF" />;
}

export function SecondaryButton(props: BtnProps) {
  return (
    <ButtonBase {...props} bg={colors.bg.elevated} fg={colors.text.primary} border={colors.border.subtle} />
  );
}

/** Inline two-button row helper. */
export function ButtonRow({ children }: { children: React.ReactNode }) {
  return <View style={{ flexDirection: 'row', gap: spacing.md }}>{children}</View>;
}
