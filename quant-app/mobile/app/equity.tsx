import { useState } from 'react';
import { View, useWindowDimensions } from 'react-native';
import { spacing } from '@/theme';
import { fmtUsdc, maskAddress } from '@/lib/format';
import { useEquity } from '@/api/queries';
import {
  Card,
  EquitySparkline,
  ErrorState,
  PnLValue,
  Screen,
  Skeleton,
  T,
} from '@/components';

type Range = 'session' | '7d' | '30d' | 'all';
const RANGES: Range[] = ['session', '7d', '30d', 'all'];

/**
 * Equity screen (07 §5.5): EquityChart of equity_curve[].cum_pnl, hero pnl_total
 * + equity_usd, range toggles, drawdown shading.
 */
export default function EquityScreen() {
  const [range, setRange] = useState<Range>('session');
  const equity = useEquity(range);
  const { width } = useWindowDimensions();
  const [refreshing, setRefreshing] = useState(false);

  const onRefresh = async () => {
    setRefreshing(true);
    await equity.refetch();
    setRefreshing(false);
  };

  const acc = equity.data;
  const last = acc?.equity_curve[acc.equity_curve.length - 1]?.cum_pnl ?? 0;

  return (
    <Screen title="Equity" onRefresh={onRefresh} refreshing={refreshing}>
      {equity.isLoading ? (
        <Skeleton rows={3} />
      ) : equity.isError || !acc ? (
        <ErrorState message="Could not load equity." onRetry={() => equity.refetch()} />
      ) : (
        <>
          <View style={{ flexDirection: 'row', gap: spacing.sm }}>
            {RANGES.map((rg) => (
              <T
                key={rg}
                variant="caption"
                color={range === rg ? 'info' : 'secondary'}
                onPress={() => setRange(rg)}
                style={{ paddingVertical: 6, paddingHorizontal: 10, opacity: range === rg ? 1 : 0.6 }}
              >
                {rg}
              </T>
            ))}
          </View>

          <Card>
            <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: spacing.md }}>
              <View>
                <T variant="caption" color="secondary">
                  P&L total
                </T>
                <PnLValue value={last} variant="display" suffix=" USDC" />
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <T variant="caption" color="secondary">
                  Equity
                </T>
                <T variant="title" mono>
                  {fmtUsdc(acc.equity_usd)} {acc.currency}
                </T>
              </View>
            </View>
            <EquitySparkline points={acc.equity_curve} width={width - spacing.lg * 4} height={140} />
          </Card>

          <Card title="Account">
            <View style={{ gap: spacing.sm }}>
              <Row label="Funder (masked)" value={maskAddress(acc.funder_address_masked)} />
              <Row label="Signature type" value={String(acc.signature_type)} />
              <Row label="Currency" value={acc.currency} />
            </View>
            <T variant="caption" color="muted" style={{ marginTop: spacing.md }}>
              Equity curve builds as trades settle. Keys never leave the operator host.
            </T>
          </Card>
        </>
      )}
    </Screen>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
      <T variant="caption" color="secondary">
        {label}
      </T>
      <T variant="caption" mono>
        {value}
      </T>
    </View>
  );
}
