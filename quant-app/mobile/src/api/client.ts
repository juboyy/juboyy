/**
 * Typed API client per `docs/08_API_SPEC.md`.
 *
 * - All responses wrap data: { schema_version, ts, data } (08 §1).
 * - Bearer token auth, two scopes: read (GET) / control (POST) (08 §2).
 * - When `config.useMock` is true, every method returns from the mock layer so
 *   the app renders with no backend.
 *
 * Read endpoints are safe; control endpoints (arm/disarm/start/stop/kill/profile/
 * config) require the control scope and additionally a client-side biometric +
 * typed confirm (enforced in the UI, not here).
 */

import { config } from './config';
import { getToken, getStoredBaseUrl, type Scope } from './secure';
import * as mock from './mock';
import type {
  Account,
  BotStatus,
  ConfigParams,
  ConfigResponse,
  ControlAck,
  Decision,
  Health,
  KillResult,
  MarketSnapshot,
  Position,
  Profile,
  RiskState,
  Signal,
  TradeResult,
} from '@/types';

/** Standard envelope (08 §1). */
interface Envelope<T> {
  schema_version: string;
  ts: string;
  data: T;
}

/** Error body (08 §1). */
export interface ApiErrorBody {
  error: { code: string; message: string; detail?: Record<string, unknown> };
}

export class ApiError extends Error {
  code: string;
  status: number;
  detail?: Record<string, unknown>;
  constructor(status: number, code: string, message: string, detail?: Record<string, unknown>) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

async function baseUrl(): Promise<string> {
  return (await getStoredBaseUrl()) ?? config.apiBaseUrl;
}

async function request<T>(
  path: string,
  opts: { method?: 'GET' | 'POST'; scope: Scope; body?: unknown } = { scope: 'read' },
): Promise<T> {
  const method = opts.method ?? 'GET';
  const token = await getToken(opts.scope);
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${await baseUrl()}${path}`, {
    method,
    headers,
    body: opts.body != null ? JSON.stringify(opts.body) : undefined,
  });

  const json: unknown = await res.json().catch(() => null);

  if (!res.ok) {
    const err = (json as ApiErrorBody | null)?.error;
    throw new ApiError(
      res.status,
      err?.code ?? 'unavailable',
      err?.message ?? `Request failed (${res.status})`,
      err?.detail,
    );
  }
  return (json as Envelope<T>).data;
}

// ---------------------------------------------------------------------------
// Read endpoints (08 §3)
// ---------------------------------------------------------------------------
export const api = {
  async getStatus(): Promise<BotStatus> {
    if (config.useMock) return mock.mockStatus();
    return request<BotStatus>('/status', { scope: 'read' });
  },

  async getSnapshot(): Promise<MarketSnapshot> {
    if (config.useMock) return mock.mockSnapshot();
    return request<MarketSnapshot>('/snapshot', { scope: 'read' });
  },

  async getSignal(): Promise<Signal> {
    if (config.useMock) return mock.mockSignal();
    return request<Signal>('/signal', { scope: 'read' });
  },

  async getDecision(): Promise<Decision> {
    if (config.useMock) return mock.mockDecision();
    return request<Decision>('/decision', { scope: 'read' });
  },

  async getPositions(): Promise<Position[]> {
    if (config.useMock) return mock.mockPositions();
    return request<Position[]>('/positions', { scope: 'read' });
  },

  async getTrades(params?: { limit?: number; before?: string }): Promise<TradeResult[]> {
    if (config.useMock) return mock.mockTrades(params?.limit);
    const q = new URLSearchParams();
    if (params?.limit != null) q.set('limit', String(params.limit));
    if (params?.before) q.set('before', params.before);
    const qs = q.toString();
    return request<TradeResult[]>(`/trades${qs ? `?${qs}` : ''}`, { scope: 'read' });
  },

  async getTrade(orderId: string): Promise<TradeResult> {
    if (config.useMock) {
      const t = mock.mockTrade(orderId);
      if (!t) throw new ApiError(404, 'not_found', 'Trade not found');
      return t;
    }
    return request<TradeResult>(`/trades/${encodeURIComponent(orderId)}`, { scope: 'read' });
  },

  async getRisk(): Promise<RiskState> {
    if (config.useMock) return mock.mockRisk();
    return request<RiskState>('/risk', { scope: 'read' });
  },

  async getEquity(range: 'session' | '7d' | '30d' | 'all' = 'session'): Promise<Account> {
    if (config.useMock) return mock.mockEquity();
    return request<Account>(`/equity?range=${range}`, { scope: 'read' });
  },

  async getConfig(): Promise<ConfigResponse> {
    if (config.useMock) return mock.mockConfig();
    return request<ConfigResponse>('/config', { scope: 'read' });
  },

  async getHealth(): Promise<Health> {
    if (config.useMock) return mock.mockHealth();
    return request<Health>('/health', { scope: 'read' });
  },

  // -------------------------------------------------------------------------
  // Control endpoints (08 §4) — control scope; UI gates with biometric+typed confirm.
  // -------------------------------------------------------------------------
  async kill(): Promise<KillResult> {
    if (config.useMock) return mock.mockKill();
    return request<KillResult>('/control/kill', {
      method: 'POST',
      scope: 'control',
      body: { confirm: 'KILL' },
    });
  },

  async arm(): Promise<ControlAck> {
    if (config.useMock) return mock.mockArm();
    return request<ControlAck>('/control/arm', {
      method: 'POST',
      scope: 'control',
      body: { confirm: 'ARM LIVE', runbook_ack: true },
    });
  },

  async disarm(): Promise<ControlAck> {
    if (config.useMock) return mock.mockDisarm();
    return request<ControlAck>('/control/disarm', { method: 'POST', scope: 'control', body: {} });
  },

  async setProfile(profile: Profile): Promise<ControlAck> {
    if (config.useMock) return mock.mockSetProfile(profile);
    return request<ControlAck>('/control/profile', {
      method: 'POST',
      scope: 'control',
      body: { profile },
    });
  },

  async start(profile: Profile, mode: 'dry_run' | 'live' = 'dry_run'): Promise<ControlAck> {
    if (config.useMock) return mock.mockStart(profile);
    return request<ControlAck>('/control/start', {
      method: 'POST',
      scope: 'control',
      body: { profile, mode },
    });
  },

  async stop(): Promise<ControlAck> {
    if (config.useMock) return mock.mockStop();
    return request<ControlAck>('/control/stop', { method: 'POST', scope: 'control', body: {} });
  },

  async updateConfig(params: Partial<ConfigParams>): Promise<ControlAck> {
    if (config.useMock) return mock.mockConfigUpdate();
    return request<ControlAck>('/control/config', {
      method: 'POST',
      scope: 'control',
      body: { params },
    });
  },
};

export type Api = typeof api;
