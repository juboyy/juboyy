import { useState } from 'react';
import { Modal, Pressable, TextInput, View } from 'react-native';
import { colors, layout, radius, spacing } from '@/theme';
import { confirmWithBiometric } from '@/lib/biometric';
import { T } from './Text';
import { DangerButton, SecondaryButton } from './Buttons';

/**
 * ConfirmSheet (07 §2): bottom-sheet for control actions (arm/stop/kill). Requires
 * a typed confirmation phrase + a biometric prompt before firing (08 §2, 06).
 */
export interface ConfirmSheetProps {
  visible: boolean;
  title: string;
  message: string;
  /** Exact phrase the operator must type, e.g. "KILL" or "ARM LIVE". */
  confirmPhrase: string;
  confirmLabel: string;
  biometricPrompt: string;
  /** Optional extra checklist (e.g. runbook ack) that must all be checked. */
  checklist?: string[];
  onCancel: () => void;
  /** Called after typed-confirm + biometric succeed. */
  onConfirm: () => Promise<void> | void;
  loading?: boolean;
  error?: string | null;
}

export function ConfirmSheet({
  visible,
  title,
  message,
  confirmPhrase,
  confirmLabel,
  biometricPrompt,
  checklist,
  onCancel,
  onConfirm,
  loading,
  error,
}: ConfirmSheetProps) {
  const [typed, setTyped] = useState('');
  const [checks, setChecks] = useState<boolean[]>(() => (checklist ?? []).map(() => false));
  const [bioError, setBioError] = useState<string | null>(null);

  const phraseOk = typed.trim() === confirmPhrase;
  const checksOk = (checklist ?? []).every((_, i) => checks[i]);
  const canFire = phraseOk && checksOk && !loading;

  const reset = () => {
    setTyped('');
    setChecks((checklist ?? []).map(() => false));
    setBioError(null);
  };

  const handleConfirm = async () => {
    setBioError(null);
    const res = await confirmWithBiometric(biometricPrompt);
    if (!res.ok) {
      setBioError(res.reason ?? 'Authentication failed.');
      return;
    }
    await onConfirm();
    reset();
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onCancel}>
      <Pressable
        style={{ flex: 1, backgroundColor: '#000000AA', justifyContent: 'flex-end' }}
        onPress={onCancel}
      >
        <Pressable
          onPress={(e) => e.stopPropagation()}
          style={{
            backgroundColor: colors.bg.surface,
            borderTopLeftRadius: radius.lg,
            borderTopRightRadius: radius.lg,
            padding: spacing.xl,
            paddingBottom: spacing.xxl,
            gap: spacing.md,
            borderTopWidth: 1,
            borderColor: colors.border.subtle,
          }}
        >
          <T variant="title">{title}</T>
          <T variant="body" color="secondary">
            {message}
          </T>

          {checklist?.map((item, i) => (
            <Pressable
              key={i}
              onPress={() => setChecks((c) => c.map((v, idx) => (idx === i ? !v : v)))}
              accessibilityRole="checkbox"
              accessibilityState={{ checked: checks[i] }}
              style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm, minHeight: layout.minTouch }}
            >
              <View
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: radius.sm,
                  borderWidth: 1,
                  borderColor: colors.border.subtle,
                  backgroundColor: checks[i] ? colors.accent.info : colors.bg.elevated,
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                {checks[i] ? <T style={{ color: '#fff' }}>✓</T> : null}
              </View>
              <T variant="body" style={{ flex: 1 }}>
                {item}
              </T>
            </Pressable>
          ))}

          <T variant="caption" color="secondary">
            Type {`"${confirmPhrase}"`} to confirm
          </T>
          <TextInput
            value={typed}
            onChangeText={setTyped}
            autoCapitalize="characters"
            autoCorrect={false}
            placeholder={confirmPhrase}
            placeholderTextColor={colors.text.muted}
            accessibilityLabel="Confirmation phrase"
            style={{
              backgroundColor: colors.bg.elevated,
              borderColor: phraseOk ? colors.accent.up : colors.border.subtle,
              borderWidth: 1,
              borderRadius: radius.md,
              color: colors.text.primary,
              paddingHorizontal: spacing.md,
              paddingVertical: spacing.md,
              fontSize: 16,
            }}
          />

          {(error || bioError) && (
            <T variant="caption" color="down">
              {error ?? bioError}
            </T>
          )}

          <DangerButton
            label={confirmLabel}
            onPress={handleConfirm}
            disabled={!canFire}
            loading={loading}
            accessibilityHint="Requires biometric confirmation"
          />
          <SecondaryButton
            label="Cancel"
            onPress={() => {
              reset();
              onCancel();
            }}
          />
        </Pressable>
      </Pressable>
    </Modal>
  );
}
