import { Pressable, Share, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { spacing } from '@/theme';
import { fmtDateTime, fmtPrice, maskAddress } from '@/lib/format';
import { useTrade } from '@/api/queries';
import {
  Card,
  ErrorState,
  PnLValue,
  Screen,
  SideTag,
  Skeleton,
  StatusBadge,
  T,
} from '@/components';

/**
 * Trade detail (07 §5.3): entry, shares, cost, close_reason, btc_move, skew,
 * seconds_left_at_entry, cost breakdown (fees/slippage/gas), masked tx, mode.
 */
export default function TradeDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const trade = useTrade(id ?? '');

  if (trade.isLoading) {
    return (
      <Screen title="Trade">
        <Skeleton rows={4} />
      </Screen>
    );
  }
  if (trade.isError || !trade.data) {
    return (
      <Screen title="Trade">
        <ErrorState message="Could not load this trade." onRetry={() => trade.refetch()} />
      </Screen>
    );
  }

  const t = trade.data;
  const resultTone = t.result === 'win' ? 'up' : t.result === 'loss' ? 'down' : 'muted';
  const costTotal = t.fees_usdc + t.slippage_usdc + t.gas_usdc;

  return (
    <Screen title="Trade detail">
      <Card>
        <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.md }}>
          <SideTag side={t.side} size="body" />
          <StatusBadge
            label={t.result.toUpperCase()}
            tone={resultTone}
            icon={t.result === 'win' ? '▲' : t.result === 'loss' ? '▼' : '='}
          />
        </View>
        <View style={{ alignItems: 'center', marginBottom: spacing.md }}>
          <T variant="caption" color="secondary">
            Realized P&L (net)
          </T>
          <PnLValue value={t.realized_cashflow_pnl_usdc} variant="display" suffix=" USDC" />
        </View>
        <T variant="caption" color="muted" style={{ textAlign: 'center' }}>
          {fmtDateTime(t.ts)} · {t.market_slug} · {t.mode === 'live' ? 'LIVE' : 'PAPER'}
        </T>
      </Card>

      <Card title="Entry">
        <Row label="Profile" value={t.profile} />
        <Row label="Entry price" value={fmtPrice(t.entry_price)} />
        <Row label="Shares" value={String(t.shares)} />
        <Row label="Cost" value={`${t.cost_usdc.toFixed(2)} USDC`} />
        <Row label="Threshold" value={fmtPrice(t.threshold_price)} />
        <Row label="Stake" value={`${t.stake_usd} USDC`} />
        <Row label="Seconds left at entry" value={String(t.seconds_left_at_entry)} />
      </Card>

      <Card title="Signal inputs">
        <Row label="BTC move (USD)" value={`${t.btc_move_usd >= 0 ? '+' : ''}${t.btc_move_usd.toFixed(1)}`} />
        <Row label="Skew" value={fmtPrice(t.skew, 3)} />
      </Card>

      <Card title="Close">
        <Row label="Reason" value={t.close_reason} />
        <Row label="Status" value={t.close_status} />
        <Row label="Success" value={t.close_success ? 'yes' : 'no'} />
        <Row label="Skipped" value={t.close_skipped ? 'yes' : 'no'} />
      </Card>

      <Card title="Cost breakdown">
        <Row label="Fees" value={`${t.fees_usdc.toFixed(2)} USDC`} />
        <Row label="Slippage" value={`${t.slippage_usdc.toFixed(2)} USDC`} />
        <Row label="Gas" value={`${t.gas_usdc.toFixed(2)} USDC`} />
        <Row label="Total costs" value={`${costTotal.toFixed(2)} USDC`} />
      </Card>

      <Card title="On-chain (masked)">
        <CopyRow label="Open tx" value={t.open_tx} />
        <CopyRow label="Close tx" value={t.close_tx} />
      </Card>
    </Screen>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 }}>
      <T variant="caption" color="secondary">
        {label}
      </T>
      <T variant="caption" mono>
        {value}
      </T>
    </View>
  );
}

function CopyRow({ label, value }: { label: string; value: string | null }) {
  const masked = maskAddress(value);
  return (
    <Pressable
      onPress={() => {
        if (value) void Share.share({ message: value }).catch(() => undefined);
      }}
      style={{ flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6 }}
      accessibilityRole="button"
      accessibilityLabel={`${label} ${masked}, tap to copy`}
    >
      <T variant="caption" color="secondary">
        {label}
      </T>
      <T variant="caption" mono color="info">
        {masked} ⧉
      </T>
    </Pressable>
  );
}
