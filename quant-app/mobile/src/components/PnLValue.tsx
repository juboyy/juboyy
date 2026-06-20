import { fmtPnl } from '@/lib/format';
import { T } from './Text';

/** Colored, mono, signed P&L (07 §2). +green / -red / 0 muted. */
export function PnLValue({
  value,
  variant = 'mono',
  suffix = '',
}: {
  value: number;
  variant?: 'mono' | 'display' | 'title' | 'headline' | 'body' | 'caption';
  suffix?: string;
}) {
  const color = value > 0 ? 'up' : value < 0 ? 'down' : 'muted';
  return (
    <T variant={variant} color={color} mono accessibilityLabel={`P and L ${fmtPnl(value)} ${suffix}`}>
      {fmtPnl(value)}
      {suffix}
    </T>
  );
}
