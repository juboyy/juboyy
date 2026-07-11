import Constants from 'expo-constants';

/**
 * Runtime config. The `useMock` flag (app.json `expo.extra.useMock`) switches the
 * whole app between the in-memory mock data layer and a live backend base URL.
 * When mock is on, the app renders every screen WITHOUT a backend (08 read shapes).
 */

interface ExtraConfig {
  useMock?: boolean;
  apiBaseUrl?: string;
  wsBaseUrl?: string;
}

const extra = (Constants.expoConfig?.extra ?? {}) as ExtraConfig;

export const config = {
  /** Master switch: mock data layer vs live REST/WS backend. */
  useMock: extra.useMock ?? true,
  /** REST base, e.g. https://<host>/api/v1 (08 §1). */
  apiBaseUrl: extra.apiBaseUrl ?? 'https://localhost/api/v1',
  /** WS base, e.g. wss://<host>/api/v1 (08 §5). */
  wsBaseUrl: extra.wsBaseUrl ?? 'wss://localhost/api/v1',
  /** REST poll fallback cadence when the socket is down (08 §5, ~5s). */
  pollSec: 5,
} as const;

export type AppConfig = typeof config;
