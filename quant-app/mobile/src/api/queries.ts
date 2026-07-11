/**
 * TanStack Query hooks over the typed API client. Read endpoints poll on the
 * `config.pollSec` cadence (08 §5 REST fallback). Control actions are mutations.
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from '@tanstack/react-query';
import { api } from './client';
import { config } from './config';
import type {
  Account,
  BotStatus,
  ConfigParams,
  ConfigResponse,
  Decision,
  Health,
  MarketSnapshot,
  Position,
  Profile,
  RiskState,
  Signal,
  TradeResult,
} from '@/types';

const pollMs = config.pollSec * 1000;

export const qk = {
  status: ['status'] as const,
  snapshot: ['snapshot'] as const,
  signal: ['signal'] as const,
  decision: ['decision'] as const,
  positions: ['positions'] as const,
  trades: (limit?: number) => ['trades', limit ?? 200] as const,
  trade: (id: string) => ['trade', id] as const,
  risk: ['risk'] as const,
  equity: (range: string) => ['equity', range] as const,
  config: ['config'] as const,
  health: ['health'] as const,
};

export function useStatus(): UseQueryResult<BotStatus> {
  return useQuery({ queryKey: qk.status, queryFn: api.getStatus, refetchInterval: pollMs });
}
export function useSnapshot(): UseQueryResult<MarketSnapshot> {
  return useQuery({ queryKey: qk.snapshot, queryFn: api.getSnapshot, refetchInterval: pollMs });
}
export function useSignal(): UseQueryResult<Signal> {
  return useQuery({ queryKey: qk.signal, queryFn: api.getSignal, refetchInterval: pollMs });
}
export function useDecision(): UseQueryResult<Decision> {
  return useQuery({ queryKey: qk.decision, queryFn: api.getDecision, refetchInterval: pollMs });
}
export function usePositions(): UseQueryResult<Position[]> {
  return useQuery({ queryKey: qk.positions, queryFn: api.getPositions, refetchInterval: pollMs });
}
export function useTrades(limit?: number): UseQueryResult<TradeResult[]> {
  return useQuery({ queryKey: qk.trades(limit), queryFn: () => api.getTrades({ limit }) });
}
export function useTrade(id: string): UseQueryResult<TradeResult> {
  return useQuery({ queryKey: qk.trade(id), queryFn: () => api.getTrade(id), enabled: !!id });
}
export function useRisk(): UseQueryResult<RiskState> {
  return useQuery({ queryKey: qk.risk, queryFn: api.getRisk, refetchInterval: pollMs });
}
export function useEquity(range: 'session' | '7d' | '30d' | 'all'): UseQueryResult<Account> {
  return useQuery({ queryKey: qk.equity(range), queryFn: () => api.getEquity(range) });
}
export function useConfig(): UseQueryResult<ConfigResponse> {
  return useQuery({ queryKey: qk.config, queryFn: api.getConfig });
}
export function useHealth(): UseQueryResult<Health> {
  return useQuery({ queryKey: qk.health, queryFn: api.getHealth, refetchInterval: pollMs });
}

/** Invalidate the resync set (08 §5 reconnect → re-fetch /status + /risk). */
function useResync(): () => void {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: qk.status });
    void qc.invalidateQueries({ queryKey: qk.risk });
    void qc.invalidateQueries({ queryKey: qk.positions });
    void qc.invalidateQueries({ queryKey: qk.signal });
    void qc.invalidateQueries({ queryKey: qk.decision });
  };
}

export function useKill() {
  const resync = useResync();
  return useMutation({ mutationFn: api.kill, onSuccess: resync });
}
export function useArm() {
  const resync = useResync();
  return useMutation({ mutationFn: api.arm, onSuccess: resync });
}
export function useDisarm() {
  const resync = useResync();
  return useMutation({ mutationFn: api.disarm, onSuccess: resync });
}
export function useSetProfile() {
  const resync = useResync();
  return useMutation({ mutationFn: (p: Profile) => api.setProfile(p), onSuccess: resync });
}
export function useUpdateConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (params: Partial<ConfigParams>) => api.updateConfig(params),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.config }),
  });
}
