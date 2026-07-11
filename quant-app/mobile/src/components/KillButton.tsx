import { useState } from 'react';
import { Alert, Pressable } from 'react-native';
import { colors, radius, spacing, layout } from '@/theme';
import { useKill } from '@/api/queries';
import { T } from './Text';
import { ConfirmSheet } from './ConfirmSheet';

/**
 * KillButton (07 §5.7): always-visible header ⛔. Tap → ConfirmSheet (typed
 * "KILL" + biometric) → POST /control/kill. The kill path is rate-limit-exempt
 * and works even in error/stale states (08 §4).
 */
export function KillButton() {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const kill = useKill();

  const fire = async () => {
    setError(null);
    try {
      const res = await kill.mutateAsync();
      setOpen(false);
      if (res.positions_close_skipped > 0) {
        Alert.alert('Kill sent', 'Could not close a position — check host.');
      } else {
        Alert.alert(
          'Kill sent — new entries blocked',
          `Positions closed: ${res.positions_closed}.`,
        );
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Kill failed — retry.');
    }
  };

  return (
    <>
      <Pressable
        onPress={() => setOpen(true)}
        accessibilityRole="button"
        accessibilityLabel="Kill switch — block new entries and close open positions"
        hitSlop={8}
        style={({ pressed }) => ({
          flexDirection: 'row',
          alignItems: 'center',
          gap: 4,
          minHeight: layout.minTouch,
          paddingHorizontal: spacing.md,
          borderRadius: radius.pill,
          backgroundColor: pressed ? colors.accent.down : colors.accent.down + '22',
          borderWidth: 1,
          borderColor: colors.accent.down,
          justifyContent: 'center',
        })}
      >
        <T variant="caption" style={{ color: colors.accent.down, fontWeight: '700' }}>
          ⛔ KILL
        </T>
      </Pressable>

      <ConfirmSheet
        visible={open}
        title="Kill now?"
        message="Blocks new entries and attempts to close open positions. This is always processable, even when stale."
        confirmPhrase="KILL"
        confirmLabel="Confirm kill"
        biometricPrompt="Confirm kill switch"
        onCancel={() => {
          setOpen(false);
          setError(null);
        }}
        onConfirm={fire}
        loading={kill.isPending}
        error={error}
      />
    </>
  );
}
