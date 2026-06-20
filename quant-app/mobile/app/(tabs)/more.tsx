import { Pressable, View } from 'react-native';
import { useRouter } from 'expo-router';
import { colors, layout, radius, spacing } from '@/theme';
import { Card, Screen, T } from '@/components';

/** More hub (07 §3): Equity · Settings/Profiles · About/Security. */
const LINKS: { title: string; subtitle: string; path: '/equity' | '/settings' | '/about'; glyph: string }[] = [
  { title: 'Equity', subtitle: 'Curve, drawdown, equity_usd', path: '/equity', glyph: '📈' },
  { title: 'Settings & Profiles', subtitle: 'Profile, params, connection, arm live', path: '/settings', glyph: '⚙' },
  { title: 'About & Security', subtitle: 'Non-custodial, kill switch, audit', path: '/about', glyph: '🛡' },
];

export default function MoreScreen() {
  const router = useRouter();
  return (
    <Screen title="More">
      {LINKS.map((l) => (
        <Pressable
          key={l.path}
          onPress={() => router.push(l.path)}
          accessibilityRole="button"
          accessibilityLabel={l.title}
          style={({ pressed }) => ({
            backgroundColor: pressed ? colors.bg.elevated : colors.bg.surface,
            borderColor: colors.border.subtle,
            borderWidth: 1,
            borderRadius: radius.lg,
            padding: layout.cardPadding,
            minHeight: layout.minTouch,
            flexDirection: 'row',
            alignItems: 'center',
            gap: spacing.md,
          })}
        >
          <T variant="title">{l.glyph}</T>
          <View style={{ flex: 1 }}>
            <T variant="headline">{l.title}</T>
            <T variant="caption" color="secondary">
              {l.subtitle}
            </T>
          </View>
          <T variant="title" color="muted">
            ›
          </T>
        </Pressable>
      ))}

      <Card>
        <T variant="caption" color="muted">
          Read-only by default. Control actions (arm/kill/profile) require a typed
          confirmation and biometric. Keys never leave the operator&apos;s host.
        </T>
      </Card>
    </Screen>
  );
}
