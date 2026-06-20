import { View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, spacing } from '@/theme';
import { useGlobalState } from '@/lib/globalState';
import { T } from './Text';
import { StatusPill, ModeBadge } from './StatusBadge';
import { KillButton } from './KillButton';

/**
 * AppHeader (07 §2/§3): title + global StatusPill (RODANDO/PARADO/STALE) +
 * ModeBadge (PAPER/LIVE) + always-reachable header Kill switch.
 */
export function AppHeader({ title }: { title: string }) {
  const insets = useSafeAreaInsets();
  const g = useGlobalState();

  return (
    <View
      style={{
        paddingTop: insets.top + spacing.sm,
        paddingBottom: spacing.sm,
        paddingHorizontal: spacing.lg,
        backgroundColor: colors.bg.base,
        borderBottomWidth: 1,
        borderBottomColor: colors.border.subtle,
        gap: spacing.sm,
      }}
    >
      <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
        <T variant="title">{title}</T>
        <KillButton />
      </View>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: spacing.sm }}>
        <StatusPill state={g.state} />
        <ModeBadge mode={g.mode} armed={g.armed} />
      </View>
    </View>
  );
}
