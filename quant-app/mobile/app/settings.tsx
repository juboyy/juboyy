import { useEffect, useState } from 'react';
import { Alert, TextInput, View } from 'react-native';
import { colors, radius, spacing } from '@/theme';
import {
  useConfig,
  useDisarm,
  useSetProfile,
  useStatus,
  useUpdateConfig,
} from '@/api/queries';
import { api } from '@/api/client';
import { config } from '@/api/config';
import { getStoredBaseUrl, setStoredBaseUrl, setToken } from '@/api/secure';
import {
  Banner,
  Card,
  ConfirmSheet,
  DangerButton,
  ErrorState,
  ModeBadge,
  ParamField,
  PrimaryButton,
  ProfileSelector,
  Screen,
  SecondaryButton,
  Skeleton,
  T,
} from '@/components';
import type { ConfigParamKey, ConfigParams, Profile } from '@/types';

/**
 * Settings / Profiles (07 §5.6): ProfileSelector, ParamField list (03 §7 ranges,
 * min/max validation), connection (base URL + token, secure), and the Mode & Arm
 * section. In MVP, Arm is disabled (paper only) with an explainer (01 MVP DoD).
 */

// Set to true once live arming is enabled (v1). MVP is paper-only.
const ARM_ENABLED = false;

const PARAM_LABEL: Record<ConfigParamKey, string> = {
  threshold_price: 'Threshold price',
  stake_usd: 'Stake (USD)',
  max_notional_usd: 'Max notional (USD)',
  daily_max_loss_pct: 'Daily max loss (%)',
  max_trades_per_day: 'Max trades / day',
  stop_loss_pct: 'Stop loss (%)',
  exit_before_sec: 'Exit before (sec)',
  hedge_enabled: 'Hedge enabled (0/1)',
  hedge_notional_usd: 'Hedge notional (USD)',
};

export default function SettingsScreen() {
  const cfg = useConfig();
  const status = useStatus();
  const setProfile = useSetProfile();
  const updateConfig = useUpdateConfig();
  const disarm = useDisarm();

  const [draft, setDraft] = useState<Partial<ConfigParams>>({});
  const [validity, setValidity] = useState<Record<string, boolean>>({});
  const [profileSheet, setProfileSheet] = useState<Profile | null>(null);
  const [armSheet, setArmSheet] = useState(false);
  const [armError, setArmError] = useState<string | null>(null);

  // Connection settings.
  const [baseUrl, setBaseUrl] = useState('');
  const [token, setTokenInput] = useState('');
  const [testResult, setTestResult] = useState<string | null>(null);

  useEffect(() => {
    void (async () => setBaseUrl((await getStoredBaseUrl()) ?? config.apiBaseUrl))();
  }, []);

  const allValid = Object.values(validity).every(Boolean);
  const profile = cfg.data?.profile ?? 'conservative';
  const armed = status.data?.armed ?? false;

  const saveParams = async () => {
    if (!allValid || Object.keys(draft).length === 0) return;
    try {
      await updateConfig.mutateAsync(draft);
      setDraft({});
      Alert.alert('Saved', 'Params updated within allowed ranges.');
    } catch (e) {
      Alert.alert('Rejected', e instanceof Error ? e.message : 'Validation failed.');
    }
  };

  const applyProfile = async () => {
    if (!profileSheet) return;
    await setProfile.mutateAsync(profileSheet);
    setProfileSheet(null);
  };

  const doArm = async () => {
    setArmError(null);
    try {
      await api.arm();
      setArmSheet(false);
      Alert.alert('Armed', 'LIVE armed. Caps and kill switch remain active.');
    } catch (e) {
      setArmError(e instanceof Error ? e.message : 'Arm failed.');
    }
  };

  const testConnection = async () => {
    setTestResult(null);
    try {
      await setStoredBaseUrl(baseUrl.trim());
      if (token.trim()) {
        await setToken('read', token.trim());
        await setToken('control', token.trim());
      }
      const h = await api.getHealth();
      setTestResult(`OK — ${h.state}, age ${h.age_sec}s`);
    } catch (e) {
      setTestResult(e instanceof Error ? `Failed — ${e.message}` : 'Failed.');
    }
  };

  if (cfg.isLoading) {
    return (
      <Screen title="Settings">
        <Skeleton rows={5} />
      </Screen>
    );
  }
  if (cfg.isError || !cfg.data) {
    return (
      <Screen title="Settings">
        <ErrorState message="Could not load config." onRetry={() => cfg.refetch()} />
      </Screen>
    );
  }

  const ranges = cfg.data.ranges;
  const params = cfg.data.params;

  return (
    <Screen title="Settings">
      {/* Profile */}
      <Card title="Profile">
        <ProfileSelector value={profile} onChange={(p) => setProfileSheet(p)} />
        <T variant="caption" color="muted" style={{ marginTop: spacing.sm }}>
          Switching profile is a control action (confirm + biometric).
        </T>
      </Card>

      {/* Params */}
      <Card title="Parameters">
        <View style={{ gap: spacing.md }}>
          {(Object.keys(params) as ConfigParamKey[]).map((k) => (
            <ParamField
              key={k}
              label={PARAM_LABEL[k]}
              value={draft[k] ?? params[k]}
              range={ranges[k]}
              onChange={(v, valid) => {
                setDraft((d) => ({ ...d, [k]: v }));
                setValidity((s) => ({ ...s, [k]: valid }));
              }}
            />
          ))}
        </View>
        <View style={{ marginTop: spacing.md }}>
          <PrimaryButton
            label="Save params"
            onPress={saveParams}
            disabled={!allValid || Object.keys(draft).length === 0 || updateConfig.isPending}
            loading={updateConfig.isPending}
          />
        </View>
      </Card>

      {/* Connection */}
      <Card title="Connection">
        <T variant="caption" color="secondary">
          API base URL
        </T>
        <TextInput
          value={baseUrl}
          onChangeText={setBaseUrl}
          autoCapitalize="none"
          autoCorrect={false}
          placeholder="https://host/api/v1"
          placeholderTextColor={colors.text.muted}
          style={inputStyle}
        />
        <T variant="caption" color="secondary" style={{ marginTop: spacing.sm }}>
          Bearer token (stored in secure storage)
        </T>
        <TextInput
          value={token}
          onChangeText={setTokenInput}
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
          placeholder="paste token"
          placeholderTextColor={colors.text.muted}
          style={inputStyle}
        />
        <View style={{ marginTop: spacing.md }}>
          <SecondaryButton label="Test connection" onPress={testConnection} />
        </View>
        {testResult ? (
          <T variant="caption" color={testResult.startsWith('OK') ? 'up' : 'down'} style={{ marginTop: spacing.sm }}>
            {testResult}
          </T>
        ) : null}
        {config.useMock ? (
          <T variant="caption" color="muted" style={{ marginTop: spacing.sm }}>
            Mock mode is ON (app.json extra.useMock). The app renders without a backend.
          </T>
        ) : null}
      </Card>

      {/* Mode & Arm */}
      <Card title="Mode & Arm" right={<ModeBadge mode={status.data?.mode ?? 'dry_run'} armed={armed} />}>
        {!ARM_ENABLED ? (
          <>
            <Banner tone="info" message="Paper only (MVP). Live arming is disabled." />
            <T variant="caption" color="muted" style={{ marginTop: spacing.sm }}>
              Live mode places real orders with real funds. Caps and kill switch remain
              active. Arming will be enabled in v1 behind the runbook checklist.
            </T>
          </>
        ) : armed ? (
          <DangerButton label="Disarm (back to paper)" onPress={() => disarm.mutate()} loading={disarm.isPending} />
        ) : (
          <>
            <T variant="caption" color="secondary" style={{ marginBottom: spacing.sm }}>
              Live mode places real orders with real funds. Caps and kill switch remain
              active. You accept the risk (see Security).
            </T>
            <DangerButton label="Arm Live…" onPress={() => setArmSheet(true)} />
          </>
        )}
      </Card>

      {/* Profile switch confirm */}
      <ConfirmSheet
        visible={profileSheet !== null}
        title="Switch profile?"
        message={`Switch active profile to "${profileSheet ?? ''}". This is a control action.`}
        confirmPhrase="SWITCH"
        confirmLabel="Confirm switch"
        biometricPrompt="Confirm profile switch"
        onCancel={() => setProfileSheet(null)}
        onConfirm={applyProfile}
        loading={setProfile.isPending}
      />

      {/* Arm live confirm (runbook ack + typed ARM LIVE + biometric) */}
      <ConfirmSheet
        visible={armSheet}
        title="Arm LIVE"
        message="Live mode places real orders with real funds. Caps and the kill switch remain active."
        confirmPhrase="ARM LIVE"
        confirmLabel="Arm live"
        biometricPrompt="Confirm arm live"
        checklist={[
          'I have read SAFE_OPERATION.md (runbook).',
          'The dedicated wallet is funded with losable capital only.',
          'I understand the kill switch and caps remain active.',
        ]}
        onCancel={() => {
          setArmSheet(false);
          setArmError(null);
        }}
        onConfirm={doArm}
        error={armError}
      />
    </Screen>
  );
}

const inputStyle = {
  backgroundColor: colors.bg.elevated,
  borderColor: colors.border.subtle,
  borderWidth: 1,
  borderRadius: radius.md,
  color: colors.text.primary,
  paddingHorizontal: spacing.md,
  paddingVertical: spacing.sm,
  fontSize: 16,
  marginTop: spacing.xs,
} as const;
