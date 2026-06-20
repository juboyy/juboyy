import { View } from 'react-native';
import { spacing } from '@/theme';
import { fmtClock, fmtPrice } from '@/lib/format';
import { T } from './Text';
import { Card } from './Card';
import { SideTag } from './SideTag';
import { PnLValue } from './PnLValue';
import type { MarketSnapshot, Position } from '@/types';

/**
 * PositionRow (07 §2/§5.2): side, entry_price, shares, cost, live mark,
 * unrealized P&L, stop_loss_price, seconds_left. Live mark comes from the
 * current snapshot's same-side bid (exit pricing, 05 §1).
 */
export function PositionRow({ position, snapshot }: { position: Position; snapshot?: MarketSnapshot }) {
  const mark =
    position.side === 'up' ? snapshot?.clob_up_bid ?? null : snapshot?.clob_down_bid ?? null;
  const unrealized = mark != null ? (mark - position.entry_price) * position.shares : null;
  const secondsLeft = snapshot?.seconds_left ?? position.seconds_left_at_entry;

  return (
    <Card>
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: spacing.md }}>
        <SideTag side={position.side} size="body" />
        <T variant="caption" color="muted" mono>
          {position.order_id}
        </T>
      </View>

      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.lg }}>
        <Stat label="Entry" value={fmtPrice(position.entry_price)} />
        <Stat label="Mark" value={mark != null ? fmtPrice(mark) : '—'} />
        <Stat label="Shares" value={String(position.shares)} />
        <Stat label="Cost" value={`${position.cost_usdc.toFixed(2)}`} />
        <Stat label="Stop" value={fmtPrice(position.stop_loss_price)} />
        <Stat label="Closes in" value={fmtClock(secondsLeft)} />
      </View>

      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginTop: spacing.md,
        }}
      >
        <T variant="caption" color="secondary">
          Unrealized P&L
        </T>
        {unrealized != null ? (
          <PnLValue value={unrealized} variant="headline" suffix=" USDC" />
        ) : (
          <T variant="headline" color="muted" mono>
            —
          </T>
        )}
      </View>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View>
      <T variant="caption" color="muted">
        {label}
      </T>
      <T variant="body" mono>
        {value}
      </T>
    </View>
  );
}
