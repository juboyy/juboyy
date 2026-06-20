/**
 * Secure token storage (06 §3/§8): bearer tokens live only in device secure
 * storage, never in plain state or logs. Two scopes per 08 §2: `read` + `control`.
 */
import * as SecureStore from 'expo-secure-store';

const READ_KEY = 'qc.token.read';
const CONTROL_KEY = 'qc.token.control';
const BASE_URL_KEY = 'qc.api.baseUrl';

export type Scope = 'read' | 'control';

export async function getToken(scope: Scope): Promise<string | null> {
  return SecureStore.getItemAsync(scope === 'read' ? READ_KEY : CONTROL_KEY);
}

export async function setToken(scope: Scope, token: string): Promise<void> {
  await SecureStore.setItemAsync(scope === 'read' ? READ_KEY : CONTROL_KEY, token);
}

export async function clearToken(scope: Scope): Promise<void> {
  await SecureStore.deleteItemAsync(scope === 'read' ? READ_KEY : CONTROL_KEY);
}

export async function getStoredBaseUrl(): Promise<string | null> {
  return SecureStore.getItemAsync(BASE_URL_KEY);
}

export async function setStoredBaseUrl(url: string): Promise<void> {
  await SecureStore.setItemAsync(BASE_URL_KEY, url);
}
