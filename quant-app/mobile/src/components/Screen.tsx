import type { ReactNode } from 'react';
import { RefreshControl, ScrollView, View } from 'react-native';
import { colors, layout, spacing } from '@/theme';
import { useGlobalState } from '@/lib/globalState';
import { AppHeader } from './AppHeader';
import { Banner } from './Banner';

/**
 * Screen scaffold: AppHeader (with kill + global badges) + cross-screen banners
 * (07 §4) + a scrollable body with pull-to-refresh. The Kill control in the
 * header is never blocked by loading/error states.
 */
export function Screen({
  title,
  children,
  onRefresh,
  refreshing,
  scroll = true,
}: {
  title: string;
  children: ReactNode;
  onRefresh?: () => void;
  refreshing?: boolean;
  scroll?: boolean;
}) {
  const g = useGlobalState();

  const banners =
    g.banners.length > 0 ? (
      <View style={{ paddingHorizontal: layout.screenGutter, paddingTop: spacing.sm, gap: spacing.sm }}>
        {g.banners.map((b, i) => (
          <Banner key={`${b.tone}-${i}`} tone={b.tone} message={b.message} />
        ))}
      </View>
    ) : null;

  return (
    <View style={{ flex: 1, backgroundColor: colors.bg.base }}>
      <AppHeader title={title} />
      {banners}
      {scroll ? (
        <ScrollView
          contentContainerStyle={{ padding: layout.screenGutter, gap: spacing.lg, paddingBottom: spacing.xxl }}
          refreshControl={
            onRefresh ? (
              <RefreshControl
                refreshing={!!refreshing}
                onRefresh={onRefresh}
                tintColor={colors.text.secondary}
              />
            ) : undefined
          }
        >
          {children}
        </ScrollView>
      ) : (
        <View style={{ flex: 1, padding: layout.screenGutter, gap: spacing.lg }}>{children}</View>
      )}
    </View>
  );
}
