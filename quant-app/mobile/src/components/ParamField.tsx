import { useState } from 'react';
import { TextInput, View } from 'react-native';
import { colors, radius, spacing } from '@/theme';
import { T } from './Text';
import type { ParamRange } from '@/types';

/**
 * ParamField (07 §2/§5.6): labeled numeric input with min/max validation from
 * the 03 §7 ranges. Out-of-range is flagged client-side (server also validates).
 */
export function ParamField({
  label,
  value,
  range,
  onChange,
}: {
  label: string;
  value: number;
  range: ParamRange;
  onChange: (v: number, valid: boolean) => void;
}) {
  const [text, setText] = useState(String(value));
  const parsed = Number(text);
  const valid = Number.isFinite(parsed) && parsed >= range.min && parsed <= range.max;

  const handle = (t: string) => {
    setText(t);
    const n = Number(t);
    onChange(n, Number.isFinite(n) && n >= range.min && n <= range.max);
  };

  return (
    <View style={{ gap: spacing.xs }}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
        <T variant="caption" color="secondary">
          {label}
        </T>
        <T variant="caption" color="muted">
          [{range.min}–{range.max}]
        </T>
      </View>
      <TextInput
        value={text}
        onChangeText={handle}
        keyboardType="decimal-pad"
        accessibilityLabel={`${label}, allowed ${range.min} to ${range.max}`}
        style={{
          backgroundColor: colors.bg.elevated,
          borderColor: valid ? colors.border.subtle : colors.accent.down,
          borderWidth: 1,
          borderRadius: radius.md,
          color: colors.text.primary,
          paddingHorizontal: spacing.md,
          paddingVertical: spacing.sm,
          fontSize: 16,
        }}
      />
      {!valid && (
        <T variant="caption" color="down">
          Must be in [{range.min}, {range.max}]
        </T>
      )}
    </View>
  );
}
