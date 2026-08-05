import {
  Fraunces_600SemiBold,
  Fraunces_700Bold,
  Fraunces_900Black,
  useFonts,
} from '@expo-google-fonts/fraunces';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { SessionProvider } from '@/session';
import { colors, fonts } from '@/theme';

export default function RootLayout() {
  // The serif is the brand; a flash of system font would look like a different product loading.
  const [fontsLoaded] = useFonts({
    Fraunces_600SemiBold,
    Fraunces_700Bold,
    Fraunces_900Black,
  });
  if (!fontsLoaded) return null;

  return (
    <SafeAreaProvider>
      <SessionProvider>
        <StatusBar style="dark" />
        <Stack
          screenOptions={{
            headerStyle: { backgroundColor: colors.background },
            headerTintColor: colors.text,
            headerTitleStyle: { fontFamily: fonts.display, fontSize: 19 },
            headerShadowVisible: false,
            contentStyle: { backgroundColor: colors.background },
          }}
        >
          <Stack.Screen name="index" options={{ title: 'Groundwork' }} />
          <Stack.Screen name="settings" options={{ title: 'Settings' }} />
          <Stack.Screen name="properties/new" options={{ title: 'Add a property' }} />
          <Stack.Screen name="properties/[id]" options={{ title: 'Property' }} />
          <Stack.Screen name="properties/[id]/edit" options={{ title: 'Edit property' }} />
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
