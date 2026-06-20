import { View } from 'react-native';
import { colors, radius, spacing } from '@/theme';
import { T } from './Text';
import { SecondaryButton } from './Buttons';

/** Shared non-happy states (07 §2/§4): Empty, Error, Skeleton. */

export function EmptyState({ message }: { message: string }) {
  return (
    <View style={{ alignItems: 'center', paddingVertical: spacing.xxl, gap: spacing.sm }}>
      <T variant="headline" color="secondary">
        Nothing here yet
      </T>
      <T variant="body" color="muted" style={{ textAlign: 'center' }}>
        {message}
      </T>
    </View>
  );
}

export function ErrorState({
  message,
  onRetry,
  lastStamp,
}: {
  message: string;
  onRetry?: () => void;
  lastStamp?: string;
}) {
  return (
    <View style={{ alignItems: 'center', paddingVertical: spacing.xl, gap: spacing.md }}>
      <T variant="headline" color="down">
        ⚠ Something went wrong
      </T>
      <T variant="body" color="secondary" style={{ textAlign: 'center' }}>
        {message}
      </T>
      {lastStamp ? (
        <T variant="caption" color="muted">
          Showing last data from {lastStamp}
        </T>
      ) : null}
      {onRetry ? (
        <View style={{ minWidth: 140 }}>
          <SecondaryButton label="Retry" onPress={onRetry} />
        </View>
      ) : null}
    </View>
  );
}

/** A grey shimmer-less skeleton block (no heavy animation; dark theme). */
export function SkeletonBlock({ height = 64 }: { height?: number }) {
  return (
    <View
      style={{
        height,
        backgroundColor: colors.bg.elevated,
        borderRadius: radius.md,
        marginBottom: spacing.md,
      }}
    />
  );
}

export function Skeleton({ rows = 3 }: { rows?: number }) {
  return (
    <View>
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonBlock key={i} />
      ))}
    </View>
  );
}
