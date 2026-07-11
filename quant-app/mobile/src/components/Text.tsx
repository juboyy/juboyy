import { Text as RNText, type TextProps, type TextStyle } from 'react-native';
import { colors, type as typeScale, monoFamily } from '@/theme';

type Variant = keyof typeof typeScale;
type ColorKey = 'primary' | 'secondary' | 'muted' | 'up' | 'down' | 'info' | 'warn';

interface Props extends TextProps {
  variant?: Variant;
  color?: ColorKey;
  mono?: boolean;
}

function resolveColor(key: ColorKey): string {
  switch (key) {
    case 'primary':
      return colors.text.primary;
    case 'secondary':
      return colors.text.secondary;
    case 'muted':
      return colors.text.muted;
    case 'up':
      return colors.accent.up;
    case 'down':
      return colors.accent.down;
    case 'info':
      return colors.accent.info;
    case 'warn':
      return colors.accent.warn;
  }
}

/** Typed text honoring the 07 §1 type scale + color tokens. */
export function T({ variant = 'body', color = 'primary', mono = false, style, ...rest }: Props) {
  const base = typeScale[variant];
  const composed: TextStyle = {
    fontSize: base.fontSize,
    lineHeight: base.lineHeight,
    fontWeight: base.fontWeight,
    color: resolveColor(color),
    ...(mono ? { fontFamily: monoFamily, fontVariant: ['tabular-nums'] } : {}),
  };
  return <RNText style={[composed, style]} {...rest} />;
}
