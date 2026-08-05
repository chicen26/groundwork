import {
  Fraunces_600SemiBold,
  Fraunces_700Bold,
  Fraunces_900Black,
  useFonts,
} from '@expo-google-fonts/fraunces';
import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { LocaleProvider, useT } from '@/i18n';
import { SessionProvider } from '@/session';
import { colors, fonts } from '@/theme';

function Routes() {
  const t = useT();
  return (
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
      <Stack.Screen name="signin" options={{ title: t('Your account') }} />
      <Stack.Screen name="settings" options={{ title: t('Settings') }} />
      <Stack.Screen name="properties/new" options={{ title: t('Add a property') }} />
      <Stack.Screen name="properties/[id]" options={{ title: t('Property') }} />
      <Stack.Screen name="properties/[id]/edit" options={{ title: t('Edit property') }} />
      <Stack.Screen name="properties/[id]/lawn" options={{ title: t('Measure a lawn') }} />
      <Stack.Screen name="properties/[id]/resources" options={{ title: t('Local programmes') }} />
      <Stack.Screen name="scan/[scanId]/index" options={{ title: t('Yard scan') }} />
      <Stack.Screen
        name="scan/[scanId]/camera"
        options={{ title: t('Photograph'), headerShown: false }}
      />
      <Stack.Screen name="scan/[scanId]/quick" options={{ title: t('Quick check') }} />
      <Stack.Screen name="scan/[scanId]/checklist" options={{ title: t('A few questions') }} />
      <Stack.Screen name="scan/[scanId]/findings" options={{ title: t('What we spotted') }} />
      <Stack.Screen
        name="scan/[scanId]/result"
        options={{ title: t('Your plan'), headerBackVisible: false }}
      />
    </Stack>
  );
}

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
      <LocaleProvider>
        <SessionProvider>
          <StatusBar style="dark" />
          <Routes />
        </SessionProvider>
      </LocaleProvider>
    </SafeAreaProvider>
  );
}
