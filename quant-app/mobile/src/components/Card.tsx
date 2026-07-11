import type { ReactNode } from 'react';
import { View, type ViewStyle } from 'react-native';
import { colors, layout, radius, spacing } from '@/theme';
import { T } from './Text';

interface Props {
  title?: string;
  right?: ReactNode;
  children: ReactNode;
  style?: ViewStyle;
}

/** Surface card (bg/surface, radius lg, 16 padding) per 07 §1. */
export function Card({ title, right, children, style }: Props) {
  return (
    <View
      style={[
        {
          backgroundColor: colors.bg.surface,
          borderRadius: radius.lg,
          padding: layout.cardPadding,
          borderWidth: 1,
          borderColor: colors.border.subtle,
        },
        style,
      ]}
    >
      {(title || right) && (
        <View
          style={{
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            marginBottom: spacing.md,
          }}
        >
          {title ? <T variant="headline">{title}</T> : <View />}
          {right}
        </View>
      )}
      {children}
    </View>
  );
}
