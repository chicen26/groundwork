/**
 * Local programmes for this property's district.
 *
 * Chipping, cost-share, inspections — the things that make the plan affordable. Each links out to
 * the agency's own page rather than restating terms that change every funding round.
 *
 * The evacuation-zone entry is a link and nothing else, and carries its own disclaimer. Groundwork
 * provides no evacuation guidance, and a screen full of fire-agency links is exactly where someone
 * might expect it to.
 */

import { useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import type { LocalResource } from '@/api/types';
import { Card, ErrorNote, Loading, Screen } from '@/components/ui';
import { useCredentials } from '@/session';
import { colors, radius, spacing, type } from '@/theme';

const TYPE_LABELS: Record<string, string> = {
  chipping: 'Chipping',
  cost_share: 'Cost share',
  inspection: 'Inspection',
  rebate: 'Rebate',
  lookup: 'Look-up',
};

export default function ResourcesScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const credentials = useCredentials();

  const [resources, setResources] = useState<LocalResource[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!id) return;
    api
      .resourcesForProperty(credentials, id)
      .then(setResources)
      .catch((e: Error) => setError(e.message));
  }, [credentials, id]);

  useEffect(load, [load]);

  if (error) {
    return (
      <Screen style={styles.padded}>
        <ErrorNote message={error} onRetry={load} />
      </Screen>
    );
  }
  if (!resources) return <Loading label="Finding local programmes" />;

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.intro}>
          Programmes run by agencies near you. Terms and deadlines change each year, so check the
          agency&apos;s own page before planning around one.
        </Text>

        {resources.map((resource) => (
          <Pressable key={resource.key} onPress={() => Linking.openURL(resource.url)}>
            <Card>
              <View style={styles.header}>
                <Text style={styles.agency}>{resource.agency}</Text>
                <View style={styles.typeBadge}>
                  <Text style={styles.typeText}>{TYPE_LABELS[resource.type] ?? resource.type}</Text>
                </View>
              </View>

              <Text style={type.heading}>{resource.name}</Text>
              <Text style={styles.summary}>{resource.summary}</Text>

              {resource.disclaimer ? (
                <Text style={styles.disclaimer}>{resource.disclaimer}</Text>
              ) : null}

              {resource.phone ? <Text style={styles.phone}>{resource.phone}</Text> : null}
              <Text style={styles.link}>Open {resource.agency} →</Text>
            </Card>
          </Pressable>
        ))}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg },
  padded: { padding: spacing.lg },
  intro: { ...type.body, color: colors.textMuted, marginBottom: spacing.md },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  agency: { ...type.caption, color: colors.textMuted, flex: 1 },
  typeBadge: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
  },
  typeText: { fontSize: 11, fontWeight: '700', color: colors.textMuted },
  summary: { ...type.body, color: colors.textMuted, marginTop: spacing.sm },
  disclaimer: {
    ...type.caption,
    color: colors.textMuted,
    backgroundColor: colors.surfaceMuted,
    padding: spacing.sm,
    borderRadius: radius.sm,
    marginTop: spacing.sm,
  },
  phone: { ...type.label, color: colors.text, marginTop: spacing.sm },
  link: { ...type.label, color: colors.accent, marginTop: spacing.md },
});
