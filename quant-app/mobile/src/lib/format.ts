/** Formatting helpers for prices, P&L, money, time, addresses (07 microcopy). */

/** Signed P&L in USDC, mono, e.g. "+2.03" / "-3.50". */
export function fmtPnl(v: number, dp = 2): string {
  const sign = v > 0 ? '+' : v < 0 ? '-' : '';
  return `${sign}${Math.abs(v).toFixed(dp)}`;
}

/** Plain USDC amount, e.g. "4.97". */
export function fmtUsdc(v: number | null | undefined, dp = 2): string {
  if (v == null) return '—';
  return v.toFixed(dp);
}

/** Probability/price in [0,1], e.g. 0.71. */
export function fmtPrice(v: number | null | undefined, dp = 2): string {
  if (v == null) return '—';
  return v.toFixed(dp);
}

/** Percent value already expressed 0–100, e.g. 68.6 → "68.6%". */
export function fmtPct(v: number | null | undefined, dp = 1): string {
  if (v == null) return '—';
  return `${v.toFixed(dp)}%`;
}

/** Mask a 0x address to 0x1234…ab12 (06: addresses always masked). */
export function maskAddress(addr: string | null | undefined): string {
  if (!addr) return '—';
  if (addr.includes('…')) return addr; // already masked
  if (addr.length <= 10) return addr;
  return `${addr.slice(0, 6)}…${addr.slice(-4)}`;
}

/** Seconds → "m:ss" for countdown. */
export function fmtClock(totalSec: number): string {
  const s = Math.max(0, Math.floor(totalSec));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${String(sec).padStart(2, '0')}`;
}

/** ISO → short local time "HH:MM:SS". */
export function fmtTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/** ISO → short date+time. */
export function fmtDateTime(iso: string): string {
  const d = new Date(iso);
  return `${d.toLocaleDateString()} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
}

/** Side glyph — never color-alone (07 §1 / WCAG 1.4.1). */
export function sideGlyph(side: 'up' | 'down'): string {
  return side === 'up' ? '▲' : '▼';
}

export function sideLabel(side: 'up' | 'down'): string {
  return side === 'up' ? 'UP' : 'DOWN';
}
