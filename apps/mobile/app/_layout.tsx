import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { SessionProvider } from '@/session';
import { colors } from '@/theme';

export default function RootLayout() {
  return (
    <SafeAreaProvider>
      <SessionProvider>
        <StatusBar style="dark" />
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: colors.background },
            headerTintColor: colors.text,
            headerTitleStyle: { fontWeight: '700' },
            headerShadowVisible: false,
            contentStyle: { backgroundColor: colors.background },
          }}
        >
          <Stack.Screen name="index" options={{ title: 'Groundwork' }} />
          <Stack.Screen name="properties/new" options={{ title: 'Add a property' }} />
          <Stack.Screen name="properties/[id]" options={{ title: 'Property' }} />
          <Stack.Screen name="properties/[id]/lawn" options={{ title: 'Measure a lawn' }} />
          <Stack.Screen name="properties/[id]/resources" options={{ title: 'Local programmes' }} />
          <Stack.Screen name="scan/[scanId]/index" options={{ title: 'Yard scan' }} />
          <Stack.Screen
            name="scan/[scanId]/camera"
            options={{ title: 'Photograph', headerShown: false }}
          />
          <Stack.Screen name="scan/[scanId]/quick" options={{ title: 'Quick check' }} />
          <Stack.Screen name="scan/[scanId]/checklist" options={{ title: 'A few questions' }} />
          <Stack.Screen name="scan/[scanId]/findings" options={{ title: 'What we spotted' }} />
          <Stack.Screen
            name="scan/[scanId]/result"
            options={{ title: 'Your plan', headerBackVisible: false }}
          />
        </Stack>
      </SessionProvider>
    </SafeAreaProvider>
  );
}
