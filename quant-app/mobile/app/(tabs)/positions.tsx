import { useState } from 'react';
import { usePositions, useSnapshot } from '@/api/queries';
import {
  Banner,
  EmptyState,
  ErrorState,
  PositionRow,
  Screen,
  Skeleton,
} from '@/components';

/**
 * Positions screen (07 §5.2): open Position rows with live mark, unrealized P&L,
 * stop, seconds_left. No manual close in MVP — exits are engine-driven; Kill in
 * the header forces an exit.
 */
export default function PositionsScreen() {
  const positions = usePositions();
  const snapshot = useSnapshot();
  const [refreshing, setRefreshing] = useState(false);

  const onRefresh = async () => {
    setRefreshing(true);
    await Promise.all([positions.refetch(), snapshot.refetch()]);
    setRefreshing(false);
  };

  return (
    <Screen title="Positions" onRefresh={onRefresh} refreshing={refreshing}>
      {positions.isLoading ? (
        <Skeleton rows={2} />
      ) : positions.isError ? (
        <ErrorState message="Could not load positions." onRetry={() => positions.refetch()} />
      ) : (positions.data ?? []).length === 0 ? (
        <EmptyState message="No open positions." />
      ) : (
        <>
          <Banner tone="info" message="Exits are engine-driven. Use Kill (header) to force-close." />
          {(positions.data ?? []).map((p) => (
            <PositionRow key={p.order_id} position={p} snapshot={snapshot.data} />
          ))}
        </>
      )}
    </Screen>
  );
}
