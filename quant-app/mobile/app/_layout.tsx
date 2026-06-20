import { useRef } from 'react';
import { StatusBar } from 'expo-status-bar';
import { Stack } from 'expo-router';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { colors } from '@/theme';
import { config } from '@/api/config';
import { useStream } from '@/api/ws';
import { qk } from '@/api/queries';

/**
 * Root layout: providers (QueryClient + safe area + gesture handler), the WS
 * stream wiring that seeds the query cache (08 §5), and the navigation stack that
 * hosts the bottom-tab group.
 */

function makeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        // REST poll fallback cadence; WS frames update the cache live (08 §5).
        staleTime: (config.pollSec * 1000) / 2,
        retry: 2,
        refetchOnWindowFocus: true,
      },
    },
  });
}

/** Bridges WS frames into the TanStack Query cache so screens render live data. */
function StreamBridge({ client }: { client: QueryClient }) {
  useStream((frame) => {
    switch (frame.type) {
      case 'signal':
        client.setQueryData(qk.signal, frame.data);
        break;
      case 'snapshot':
        client.setQueryData(qk.snapshot, frame.data);
        break;
      case 'decision':
        client.setQueryData(qk.decision, frame.data);
        break;
      case 'risk':
        client.setQueryData(qk.risk, frame.data);
        break;
      case 'status':
        client.setQueryData(qk.status, frame.data);
        break;
      case 'alert':
        // Alerts also surface via banners (driven by /risk + /health refetch).
        void client.invalidateQueries({ queryKey: qk.risk });
        void client.invalidateQueries({ queryKey: qk.health });
        break;
      case 'heartbeat':
        break;
    }
  });
  return null;
}

export default function RootLayout() {
  const clientRef = useRef<QueryClient | null>(null);
  if (!clientRef.current) clientRef.current = makeClient();
  const client = clientRef.current;

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: colors.bg.base }}>
      <SafeAreaProvider>
        <QueryClientProvider client={client}>
          <StreamBridge client={client} />
          <StatusBar style="light" />
          <Stack
            screenOptions={{
              headerShown: false,
              contentStyle: { backgroundColor: colors.bg.base },
            }}
          >
            <Stack.Screen name="(tabs)" />
            <Stack.Screen name="trade/[id]" options={{ presentation: 'card' }} />
            <Stack.Screen name="equity" />
            <Stack.Screen name="settings" />
            <Stack.Screen name="about" />
          </Stack>
        </QueryClientProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
