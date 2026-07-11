import { spacing } from '@/theme';
import { Card, Screen, T } from '@/components';

/** About & Security (07 §3): non-custodial posture, kill switch, audit notes. */
export default function AboutScreen() {
  return (
    <Screen title="About & Security">
      <Card title="Quant Cockpit">
        <T variant="body" color="secondary">
          A mobile cockpit for a deterministic, momentum-follow-through bot trading
          Polymarket BTC 5-minute up/down markets. Watch the live signal, see every
          decision, control caps, and arm/kill from your phone.
        </T>
      </Card>

      <Card title="Safe by default">
        <T variant="body" color="secondary" style={{ marginBottom: spacing.sm }}>
          Dry-run / paper is the default. Live execution is gated behind an explicit
          arm flag, a typed confirmation, a biometric, and the runbook acknowledgement.
        </T>
        <T variant="caption" color="muted">
          Live-by-accident is a Sev-1; arming only flips a flag the adapter reads.
        </T>
      </Card>

      <Card title="Non-custodial">
        <T variant="body" color="secondary">
          Keys live only in the operator&apos;s execution environment. The app and
          backend never hold or transmit private keys. Addresses are always masked.
          No deposits, withdrawals, or bridging in-app.
        </T>
      </Card>

      <Card title="Kill switch & dead-man">
        <T variant="body" color="secondary">
          The header kill switch blocks new entries and attempts to close open
          positions; it is rate-limit-exempt and works even when quotes are stale.
          A dead-man banner + push fires if the process stops responding.
        </T>
      </Card>

      <Card title="Audit">
        <T variant="caption" color="muted">
          Every control call (arm/disarm/start/stop/kill/profile/config) is written to
          an append-only audit log (who / when / device). Tokens are revocable per
          device and stored in secure storage.
        </T>
      </Card>
    </Screen>
  );
}
