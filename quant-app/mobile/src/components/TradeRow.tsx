import { Pressable, View } from 'react-native';
import { colors, layout, radius, spacing } from '@/theme';
import { fmtPrice, fmtTime } from '@/lib/format';
import { T } from './Text';
import { SideTag } from './SideTag';
import { PnLValue } from './PnLValue';
import { StatusBadge } from './StatusBadge';
import type { TradeResult } from '@/types';

/**
 * TradeRow (07 §2/§5.3): time, side, move, skew, entry, cost, P&L, result.
 * Tap → detail.
 */
export function TradeRow({ trade, onPress }: { trade: TradeResult; onPress?: () => void }) {
  const resultTone = trade.result === 'win' ? 'up' : trade.result === 'loss' ? 'down' : 'muted';
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={`Trade ${trade.side} ${trade.result} P and L ${trade.realized_cashflow_pnl_usdc}`}
      style={({ pressed }) => ({
        backgroundColor: pressed ? colors.bg.elevated : colors.bg.surface,
        borderColor: colors.border.subtle,
        borderWidth: 1,
        borderRadius: radius.md,
        padding: layout.cardPadding,
        gap: spacing.sm,
        minHeight: layout.minTouch,
      })}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
          <SideTag side={trade.side} />
          <StatusBadge
            label={trade.result.toUpperCase()}
            tone={resultTone}
            icon={trade.result === 'win' ? '▲' : trade.result === 'loss' ? '▼' : '='}
          />
        </View>
        <PnLValue value={trade.realized_cashflow_pnl_usdc} suffix=" USDC" />
      </View>

      <View style={{ flexDirection: 'row', justifyContent: 'space-between', flexWrap: 'wrap' }}>
        <Field label="move" value={`${trade.btc_move_usd >= 0 ? '+' : ''}${trade.btc_move_usd.toFixed(0)}`} />
        <Field label="skew" value={fmtPrice(trade.skew)} />
        <Field label="entry" value={fmtPrice(trade.entry_price)} />
        <Field label="cost" value={trade.cost_usdc.toFixed(2)} />
      </View>

      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
        <T variant="caption" color="muted">
          {fmtTime(trade.ts)} · {trade.close_reason}
        </T>
        <T variant="caption" color="muted">
          {trade.mode === 'live' ? 'LIVE' : 'PAPER'}
        </T>
      </View>
    </Pressable>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <View style={{ alignItems: 'flex-start', marginRight: spacing.md }}>
      <T variant="caption" color="muted">
        {label}
      </T>
      <T variant="caption" mono>
        {value}
      </T>
    </View>
  );
}
