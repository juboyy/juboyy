import { useMemo, useState } from 'react';
import { View } from 'react-native';
import { useRouter } from 'expo-router';
import { spacing } from '@/theme';
import { useTrades } from '@/api/queries';
import {
  EmptyState,
  ErrorState,
  Screen,
  Skeleton,
  T,
  TradeRow,
} from '@/components';
import type { TradeOutcome } from '@/types';

/**
 * Trade History screen (07 §5.3): reverse-chronological TradeResult rows
 * (side, move, skew, entry, cost, P&L, status). Tap → detail. Result filter.
 */
const FILTERS: (TradeOutcome | 'all')[] = ['all', 'win', 'loss', 'breakeven'];

export default function HistoryScreen() {
  const router = useRouter();
  const trades = useTrades();
  const [filter, setFilter] = useState<TradeOutcome | 'all'>('all');
  const [refreshing, setRefreshing] = useState(false);

  const onRefresh = async () => {
    setRefreshing(true);
    await trades.refetch();
    setRefreshing(false);
  };

  const rows = useMemo(() => {
    const data = trades.data ?? [];
    const filtered = filter === 'all' ? data : data.filter((t) => t.result === filter);
    return [...filtered].sort((a, b) => b.ts.localeCompare(a.ts));
  }, [trades.data, filter]);

  return (
    <Screen title="History" onRefresh={onRefresh} refreshing={refreshing}>
      <View style={{ flexDirection: 'row', gap: spacing.sm, flexWrap: 'wrap' }}>
        {FILTERS.map((f) => (
          <View key={f} style={{ opacity: filter === f ? 1 : 0.5 }}>
            <T
              variant="caption"
              color={filter === f ? 'info' : 'secondary'}
              onPress={() => setFilter(f)}
              style={{ paddingVertical: 6, paddingHorizontal: 10 }}
            >
              {f.toUpperCase()}
            </T>
          </View>
        ))}
      </View>

      {trades.isLoading ? (
        <Skeleton rows={4} />
      ) : trades.isError ? (
        <ErrorState message="Could not load trade history." onRetry={() => trades.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState message="No trades yet — running in paper mode." />
      ) : (
        rows.map((t) => (
          <TradeRow
            key={`${t.ts}-${t.open_tx ?? t.market_slug}`}
            trade={t}
            onPress={() =>
              router.push({
                pathname: '/trade/[id]',
                params: { id: t.open_tx ?? t.market_slug },
              })
            }
          />
        ))
      )}
    </Screen>
  );
}
