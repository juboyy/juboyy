import { useState } from 'react';
import { View } from 'react-native';
import { spacing } from '@/theme';
import { fmtPct, fmtUsdc } from '@/lib/format';
import { useConfig, useRisk } from '@/api/queries';
import {
  Banner,
  Card,
  ErrorState,
  Gauge,
  KpiCard,
  KpiGrid,
  PnLValue,
  PositionRow,
  Screen,
  Skeleton,
  StatusBadge,
  T,
} from '@/components';

/**
 * Risk / Limits screen (07 §5.4): two CapGauges (loss + trades), a KPI grid,
 * a status row (profile/mode/armed/killed/dead-man), the open position, and the
 * active params.
 */
export default function RiskScreen() {
  const risk = useRisk();
  const cfg = useConfig();
  const [refreshing, setRefreshing] = useState(false);

  const onRefresh = async () => {
    setRefreshing(true);
    await Promise.all([risk.refetch(), cfg.refetch()]);
    setRefreshing(false);
  };

  const r = risk.data;

  return (
    <Screen title="Risk" onRefresh={onRefresh} refreshing={refreshing}>
      {risk.isLoading ? (
        <Skeleton rows={4} />
      ) : risk.isError || !r ? (
        <ErrorState message="Could not load risk state." onRetry={() => risk.refetch()} />
      ) : (
        <>
          {(r.loss_cap_used_pct >= 100 || r.trades_cap_used_pct >= 100) && (
            <Banner tone="error" message="Daily cap reached — new entries blocked." />
          )}

          <Card title="Caps">
            <View style={{ gap: spacing.lg }}>
              <Gauge
                label="Daily loss cap"
                usedPct={r.loss_cap_used_pct}
                caption={`Cap ${fmtUsdc(r.daily_loss_cap_usd)} USDC (${fmtPct(r.daily_loss_cap_pct, 0)} of bankroll)`}
              />
              <Gauge
                label="Trades / day"
                usedPct={r.trades_cap_used_pct}
                caption={`${r.trades_today} of ${r.max_trades_per_day} used today`}
              />
            </View>
          </Card>

          <KpiGrid>
            <KpiCard label="P&L today" valueNode={<PnLValue value={r.pnl_today} variant="title" />} />
            <KpiCard label="P&L total" valueNode={<PnLValue value={r.pnl_total} variant="title" />} />
            <KpiCard label="Win rate" value={fmtPct(r.win_rate)} />
            <KpiCard label="Wins / Losses" value={`${r.wins} / ${r.losses}`} />
            <KpiCard label="Best trade" valueNode={<PnLValue value={r.best_trade} variant="title" />} />
            <KpiCard label="Worst trade" valueNode={<PnLValue value={r.worst_trade} variant="title" />} />
          </KpiGrid>

          <Card title="Status">
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm }}>
              <StatusBadge label={r.profile.toUpperCase()} tone="info" icon="◈" />
              <StatusBadge label={r.mode === 'live' ? 'LIVE' : 'PAPER'} tone={r.mode === 'live' ? 'down' : 'info'} icon={r.mode === 'live' ? '◆' : '◇'} />
              <StatusBadge label={r.armed ? 'ARMED' : 'DISARMED'} tone={r.armed ? 'down' : 'muted'} icon={r.armed ? '◆' : '○'} />
              <StatusBadge label={r.killed ? 'KILLED' : 'LIVEABLE'} tone={r.killed ? 'down' : 'up'} icon={r.killed ? '⛔' : '●'} />
              <StatusBadge
                label={r.dead_man_tripped ? 'DEAD-MAN' : 'HEARTBEAT OK'}
                tone={r.dead_man_tripped ? 'down' : 'up'}
                icon={r.dead_man_tripped ? '☠' : '♥'}
              />
            </View>
          </Card>

          {r.open_position ? (
            <View style={{ gap: spacing.sm }}>
              <T variant="headline">Open position</T>
              <PositionRow position={r.open_position} />
            </View>
          ) : null}

          {cfg.data ? (
            <Card title="Active params">
              <View style={{ gap: spacing.sm }}>
                {(Object.keys(cfg.data.params) as (keyof typeof cfg.data.params)[]).map((k) => (
                  <View key={k} style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                    <T variant="caption" color="secondary">
                      {k}
                    </T>
                    <T variant="caption" mono>
                      {String(cfg.data!.params[k])}
                    </T>
                  </View>
                ))}
              </View>
            </Card>
          ) : null}
        </>
      )}
    </Screen>
  );
}
