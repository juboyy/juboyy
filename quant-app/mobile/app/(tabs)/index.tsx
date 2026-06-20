import { useState } from 'react';
import { View } from 'react-native';
import { spacing } from '@/theme';
import { useDecision, useSignal, useSnapshot } from '@/api/queries';
import { useGlobalState } from '@/lib/globalState';
import {
  Banner,
  Card,
  CountdownRing,
  GateList,
  MarketChips,
  Screen,
  ScoreBreakdown,
  SignalCard,
  Skeleton,
  T,
} from '@/components';

/**
 * Live screen (07 §5.1): hero CountdownRing, SignalCard, ScoreBreakdown + GateList
 * ("why"), market chips, and the armed/idle banner. Default tab.
 */
export default function LiveScreen() {
  const snapshot = useSnapshot();
  const signal = useSignal();
  const decision = useDecision();
  const g = useGlobalState();
  const [refreshing, setRefreshing] = useState(false);

  const onRefresh = async () => {
    setRefreshing(true);
    await Promise.all([snapshot.refetch(), signal.refetch(), decision.refetch()]);
    setRefreshing(false);
  };

  const snap = snapshot.data;
  const sig = signal.data;
  const dec = decision.data;
  const inWindow = sig?.gates.in_window ?? false;

  return (
    <Screen title="Live" onRefresh={onRefresh} refreshing={refreshing}>
      {/* Idle vs armed banner (07 §5.1). The cap/stale/dead banners come from Screen. */}
      {g.mode === 'live' && g.armed ? null : (
        <Banner tone="info" message="Paper mode — no real orders. Watching the live signal." />
      )}

      {snap ? (
        <View
          style={{ alignItems: 'center', paddingVertical: spacing.md }}
        >
          <CountdownRing
            secondsLeft={snap.seconds_left}
            inWindow={inWindow}
            marketSlug={snap.market_slug}
          />
        </View>
      ) : (
        <Skeleton rows={1} />
      )}

      {sig ? <SignalCard signal={sig} decision={dec} /> : <Skeleton rows={2} />}

      {sig ? <ScoreBreakdown signal={sig} /> : null}
      {sig ? <GateList signal={sig} /> : null}

      {snap ? (
        <MarketChips
          snapshot={snap}
          btcMoveUsd={
            snap.btc_price_now != null && snap.btc_price_open != null
              ? snap.btc_price_now - snap.btc_price_open
              : undefined
          }
          skewClob={snap.clob_up_ask ?? undefined}
        />
      ) : null}

      <Card>
        <T variant="caption" color="muted">
          Equity → open from More. Tap a trade in History for the full decision payload.
        </T>
      </Card>
    </Screen>
  );
}
