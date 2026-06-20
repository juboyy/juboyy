import { View } from 'react-native';
import { colors, radius, spacing } from '@/theme';
import { fmtPrice } from '@/lib/format';
import { T } from './Text';
import { Card } from './Card';
import { SideTag } from './SideTag';
import { StatusBadge } from './StatusBadge';
import type { Decision, Signal, GateKey, SignalSubscores, SignalWeights } from '@/types';

/** Human labels for gates (07 §5.1 "why" surface). */
const GATE_LABEL: Record<GateKey, string> = {
  health: 'Process healthy',
  in_window: 'In entry window (60–150s)',
  momentum_present: 'Momentum present',
  spread_ok: 'Spread acceptable',
  notional_ok: 'Liquidity / notional ok',
  skew_agreement: 'CLOB / gamma skew agree',
  ask_ge_threshold: 'Ask ≥ threshold',
  ask_le_max: 'Ask ≤ max price',
  risk_allows: 'Risk allows entry',
};

const SUBSCORE_LABEL: Record<keyof SignalSubscores, string> = {
  momentum_score: 'Momentum',
  skew_score: 'Skew',
  liquidity_score: 'Liquidity',
  imbalance_score: 'Imbalance',
  time_decay_score: 'Time decay',
  rv_penalty: 'RV penalty',
  agreement_bonus: 'Agreement bonus',
};

const SUBSCORE_WEIGHT: Partial<Record<keyof SignalSubscores, keyof SignalWeights>> = {
  momentum_score: 'w_mom',
  skew_score: 'w_skew',
  liquidity_score: 'w_liq',
  imbalance_score: 'w_imb',
  time_decay_score: 'w_time',
  rv_penalty: 'w_vol',
};

function actionTone(action: Decision['action']): 'up' | 'down' | 'info' | 'warn' | 'muted' {
  switch (action) {
    case 'enter':
      return 'up';
    case 'exit':
      return 'down';
    case 'hedge':
      return 'info';
    case 'hold':
      return 'warn';
    case 'skip':
      return 'muted';
  }
}

/** SignalCard (07 §5.1): chosen side, ask, total_score vs enter_score_min, action + reason. */
export function SignalCard({ signal, decision }: { signal: Signal; decision?: Decision }) {
  const scoreFrac = Math.max(0, Math.min(1, signal.total_score / Math.max(signal.enter_score_min * 1.5, 0.01)));
  const passColor = signal.gates_passed ? colors.accent.up : colors.accent.warn;

  // Microcopy per 07 §5.1 / §6 — always states mode (paper).
  const sideStr = signal.chosen_side ? signal.chosen_side.toUpperCase() : '—';
  const askStr = fmtPrice(signal.chosen_side_ask);
  const modeStr = decision ? (decision.mode === 'live' ? 'live' : 'paper') : 'paper';
  const micro =
    decision?.action === 'enter'
      ? `Conditions met — would enter ${sideStr} @ ${askStr} (${modeStr})`
      : `No trade: ${signal.failed_gate ? GATE_LABEL[signal.failed_gate] : 'conditions not met'}`;

  return (
    <Card
      title="Signal"
      right={
        decision ? (
          <StatusBadge label={decision.action.toUpperCase()} tone={actionTone(decision.action)} />
        ) : undefined
      }
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.md, marginBottom: spacing.md }}>
        {signal.chosen_side ? <SideTag side={signal.chosen_side} size="body" /> : null}
        <T variant="display" mono>
          {askStr}
        </T>
        <T variant="caption" color="muted">
          ask
        </T>
      </View>

      <View style={{ marginBottom: spacing.sm }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
          <T variant="caption" color="secondary">
            Score
          </T>
          <T variant="caption" mono style={{ color: passColor }}>
            {signal.total_score.toFixed(2)} / min {signal.enter_score_min.toFixed(2)}
          </T>
        </View>
        <View
          style={{
            height: 8,
            backgroundColor: colors.bg.elevated,
            borderRadius: radius.pill,
            marginTop: spacing.xs,
            overflow: 'hidden',
          }}
        >
          <View style={{ width: `${scoreFrac * 100}%`, height: '100%', backgroundColor: passColor }} />
        </View>
      </View>

      <T variant="body" color={decision?.action === 'enter' ? 'up' : 'secondary'}>
        {micro}
      </T>
    </Card>
  );
}

/** ScoreBreakdown (07 §5.1): per-subscore bars + weights. */
export function ScoreBreakdown({ signal }: { signal: Signal }) {
  const keys = Object.keys(signal.subscores) as (keyof SignalSubscores)[];
  return (
    <Card title="Score breakdown">
      <View style={{ gap: spacing.md }}>
        {keys.map((k) => {
          const v = signal.subscores[k];
          const wk = SUBSCORE_WEIGHT[k];
          const weight = wk ? signal.weights[wk] : undefined;
          const isPenalty = k === 'rv_penalty';
          const frac = Math.max(0, Math.min(1, Math.abs(v)));
          const color = isPenalty ? colors.accent.warn : colors.accent.info;
          return (
            <View key={k}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                <T variant="caption" color="secondary">
                  {SUBSCORE_LABEL[k]}
                  {weight != null ? `  ·  w ${weight.toFixed(2)}` : ''}
                </T>
                <T variant="caption" mono>
                  {isPenalty ? '−' : ''}
                  {v.toFixed(3)}
                </T>
              </View>
              <View
                style={{
                  height: 6,
                  backgroundColor: colors.bg.elevated,
                  borderRadius: radius.pill,
                  marginTop: 4,
                  overflow: 'hidden',
                }}
              >
                <View style={{ width: `${frac * 100}%`, height: '100%', backgroundColor: color }} />
              </View>
            </View>
          );
        })}
      </View>
    </Card>
  );
}

/** GateList (07 §2/§5.1): each gate ✓/✗, failed gate emphasized. */
export function GateList({ signal }: { signal: Signal }) {
  const keys = Object.keys(signal.gates) as GateKey[];
  return (
    <Card title="Gates (why)">
      <View style={{ gap: spacing.sm }}>
        {keys.map((k) => {
          const pass = signal.gates[k];
          const failed = signal.failed_gate === k;
          return (
            <View
              key={k}
              style={{
                flexDirection: 'row',
                alignItems: 'center',
                justifyContent: 'space-between',
                backgroundColor: failed ? colors.accent.down + '22' : 'transparent',
                borderRadius: radius.sm,
                paddingHorizontal: failed ? spacing.sm : 0,
                paddingVertical: 2,
              }}
              accessibilityLabel={`${GATE_LABEL[k]} ${pass ? 'pass' : 'fail'}`}
            >
              <T variant="body" color={failed ? 'down' : 'primary'}>
                {GATE_LABEL[k]}
              </T>
              <T
                variant="body"
                style={{ color: pass ? colors.accent.up : colors.accent.down, fontWeight: '700' }}
              >
                {pass ? '✓' : '✗'}
              </T>
            </View>
          );
        })}
      </View>
    </Card>
  );
}
