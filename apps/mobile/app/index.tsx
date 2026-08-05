/**
 * Home: the properties you have added, or the way in if you have not.
 *
 * Sign-in is a single tap while Supabase auth is unconfigured — the backend accepts a development
 * identity header, and asking a homeowner to create an account before they have seen the product
 * would cost more testers than it protects.
 */

import { Link, Stack, useFocusEffect, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { FlatList, Pressable, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import type { Property } from '@/api/types';
import { PrivacyNote } from '@/components/PrivacyNote';
import { Button, Card, ErrorNote, Loading, Screen, ZoneBadge } from '@/components/ui';
import { newUserId, useSession } from '@/session';
import { colors, spacing, type } from '@/theme';

export default function HomeScreen() {
  const { credentials, loading: sessionLoading, signIn } = useSession();
  const router = useRouter();
  const [properties, setProperties] = useState<Property[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!credentials) return;
    setError(null);
    api
      .listProperties(credentials)
      .then(setProperties)
      .catch((e: Error) => setError(e.message));
  }, [credentials]);

  // Reload on focus: coming back from a finished scan should show the new state, not a stale list.
  useFocusEffect(load);

  if (sessionLoading) return <Loading />;

  if (!credentials) {
    return (
      <Screen style={styles.welcome}>
        <Text style={type.display}>Groundwork</Text>
        <Text style={styles.tagline}>
          One scan of your yard. One plan that makes it fire-safe and water-wise — and shows the
          rebates that pay for it.
        </Text>
        <Button title="Get started" onPress={() => signIn(newUserId())} />
        <PrivacyNote />
        <Text style={styles.fineprint}>
          Groundwork gives educational guidance based on published state and local requirements. It
          is not an official inspection and does not provide evacuation advice.
        </Text>
      </Screen>
    );
  }

  if (error) {
    return (
      <Screen style={styles.padded}>
        <ErrorNote message={error} onRetry={load} />
      </Screen>
    );
  }

  if (!properties) return <Loading label="Loading your properties" />;

  return (
    <Screen>
      <Stack.Screen
        options={{
          headerRight: () => (
            <Pressable onPress={() => router.push('/settings')} hitSlop={12}>
              <Text style={styles.gear}>⚙︎</Text>
            </Pressable>
          ),
        }}
      />
      <FlatList
        contentContainerStyle={styles.list}
        data={properties}
        keyExtractor={(item) => item.id}
        ListEmptyComponent={
          <Card>
            <Text style={type.heading}>No properties yet</Text>
            <Text style={styles.body}>
              Add your address and we will look up its fire hazard zone, then walk you through
              photographing the yard.
            </Text>
          </Card>
        }
        ListFooterComponent={
          <Link href="/properties/new" asChild>
            <Button title="Add a property" onPress={() => router.push('/properties/new')} />
          </Link>
        }
        renderItem={({ item }) => (
          <Pressable onPress={() => router.push(`/properties/${item.id}`)}>
            <Card>
              <Text style={type.heading}>{item.label ?? item.address}</Text>
              {item.label ? <Text style={styles.body}>{item.address}</Text> : null}
              <View style={styles.badgeRow}>
                <ZoneBadge fhsz={item.geo.fhsz} />
              </View>
            </Card>
          </Pressable>
        )}
      />
    </Screen>
  );
}

const styles = StyleSheet.create({
  welcome: {
    padding: spacing.lg,
    justifyContent: 'center',
    gap: spacing.lg,
  },
  tagline: { ...type.body, color: colors.textMuted },
  fineprint: { ...type.caption, color: colors.textMuted },
  padded: { padding: spacing.lg },
  list: { padding: spacing.lg },
  body: { ...type.body, color: colors.textMuted, marginTop: spacing.xs },
  badgeRow: { marginTop: spacing.sm, flexDirection: 'row' },
  gear: { fontSize: 22, color: colors.text },
});
