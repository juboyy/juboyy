import { useHealth, useRisk, useStatus } from '@/api/queries';
import type { BotState, Mode } from '@/types';

export interface GlobalBanner {
  tone: 'armed' | 'stale' | 'error' | 'dead' | 'info' | 'stopped';
  message: string;
}

export interface GlobalState {
  state: BotState;
  mode: Mode;
  armed: boolean;
  killed: boolean;
  isLoading: boolean;
  hasError: boolean;
  /** Ordered banners to render at the top of every screen (07 §4). */
  banners: GlobalBanner[];
}

/**
 * Derives the global RODANDO/PARADO/STALE + PAPER/LIVE state and the cross-screen
 * banners (07 §4) from /status, /health, /risk. STALE when age_sec>8 (07 §4).
 */
export function useGlobalState(): GlobalState {
  const status = useStatus();
  const health = useHealth();
  const risk = useRisk();

  const s = status.data;
  const h = health.data;
  const r = risk.data;

  const ageSec = h?.age_sec ?? 0;
  const isStale = (h?.state === 'STALE' || ageSec > 8) && !!s?.running;
  const state: BotState = s?.killed
    ? 'PARADO'
    : isStale
      ? 'STALE'
      : (s?.state ?? h?.state ?? 'PARADO');

  const banners: GlobalBanner[] = [];

  // dead-man (highest priority, 07 §4)
  if (h?.dead_man_tripped || r?.dead_man_tripped) {
    banners.push({
      tone: 'dead',
      message: 'Bot not responding — open position may be unmanaged.',
    });
  }

  // armed (live)
  if (s?.mode === 'live' && s?.armed) {
    banners.push({ tone: 'armed', message: 'LIVE — armed. Real orders with real funds.' });
  }

  // cap reached (risk-driven)
  if (r && (r.loss_cap_used_pct >= 100 || r.trades_cap_used_pct >= 100)) {
    banners.push({
      tone: 'error',
      message:
        r.loss_cap_used_pct >= 100
          ? 'Daily loss cap reached — new entries blocked.'
          : 'Trades/day cap reached — new entries blocked.',
    });
  }

  // stale
  if (state === 'STALE') {
    banners.push({ tone: 'stale', message: 'Quotes stale — entries paused.' });
  }

  // stopped / killed
  if (s?.killed) {
    banners.push({ tone: 'stopped', message: 'Bot stopped (killed) — new entries blocked.' });
  }

  // API error (show last-known cached values stamped stale, 07 §4)
  const hasError = status.isError || health.isError || risk.isError;
  if (hasError) {
    const stamp = s?.started_at ? '' : '';
    banners.push({
      tone: 'error',
      message: `API unreachable — showing last data.${stamp} Pull to retry.`,
    });
  }

  return {
    state,
    mode: s?.mode ?? 'dry_run',
    armed: s?.armed ?? false,
    killed: s?.killed ?? false,
    isLoading: status.isLoading || health.isLoading || risk.isLoading,
    hasError,
    banners,
  };
}
