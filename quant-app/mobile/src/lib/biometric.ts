/**
 * Biometric gate for control actions (08 §2, 06): arm/kill require a device
 * biometric prompt in addition to a typed confirmation. If no biometric hardware
 * is enrolled we fall back to the OS passcode; if neither is available we surface
 * a clear failure so the UI can refuse the control action.
 */
import * as LocalAuthentication from 'expo-local-authentication';

export interface BiometricResult {
  ok: boolean;
  reason?: string;
}

export async function confirmWithBiometric(promptMessage: string): Promise<BiometricResult> {
  const hasHardware = await LocalAuthentication.hasHardwareAsync();
  const enrolled = await LocalAuthentication.isEnrolledAsync();

  if (!hasHardware || !enrolled) {
    // Device passcode fallback (disableDeviceFallback=false is the default).
    const res = await LocalAuthentication.authenticateAsync({
      promptMessage,
      fallbackLabel: 'Use passcode',
    });
    if (!res.success) {
      return { ok: false, reason: 'Biometric/passcode authentication unavailable or cancelled.' };
    }
    return { ok: true };
  }

  const res = await LocalAuthentication.authenticateAsync({
    promptMessage,
    cancelLabel: 'Cancel',
    fallbackLabel: 'Use passcode',
  });
  if (!res.success) {
    return { ok: false, reason: 'Authentication failed or cancelled.' };
  }
  return { ok: true };
}
