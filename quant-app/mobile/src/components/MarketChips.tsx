import { View } from 'react-native';
import { colors, radius, spacing } from '@/theme';
import { fmtPrice } from '@/lib/format';
import { T } from './Text';
import { Card } from './Card';
import type { MarketSnapshot } from '@/types';

/** Market chips (07 §5.1): btc move, skew, spread, top ask notional, rv. */
export function MarketChips({
  snapshot,
  btcMoveUsd,
  skewClob,
  rvUsd,
}: {
  snapshot: MarketSnapshot;
  btcMoveUsd?: number;
  skewClob?: number;
  rvUsd?: number;
}) {
  const move =
    btcMoveUsd ??
    (snapshot.btc_price_now != null && snapshot.btc_price_open != null
      ? snapshot.btc_price_now - snapshot.btc_price_open
      : null);

  const chips: { label: string; value: string }[] = [
    { label: 'BTC move', value: move != null ? `${move >= 0 ? '+' : ''}${move.toFixed(0)}` : '—' },
    { label: 'Skew', value: skewClob != null ? fmtPrice(skewClob, 3) : fmtPrice(snapshot.clob_up_ask, 2) },
    { label: 'Spread', value: fmtPrice(snapshot.min_spread, 3) },
    { label: 'Top ask $', value: snapshot.top_ask_notional_usd != null ? snapshot.top_ask_notional_usd.toFixed(0) : '—' },
    { label: 'RV $', value: rvUsd != null ? rvUsd.toFixed(1) : '—' },
  ];

  return (
    <Card title="Market">
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm }}>
        {chips.map((c) => (
          <View
            key={c.label}
            style={{
              backgroundColor: colors.bg.elevated,
              borderRadius: radius.pill,
              paddingHorizontal: spacing.md,
              paddingVertical: spacing.sm,
            }}
          >
            <T variant="caption" color="muted">
              {c.label}
            </T>
            <T variant="caption" mono>
              {c.value}
            </T>
          </View>
        ))}
      </View>
    </Card>
  );
}
