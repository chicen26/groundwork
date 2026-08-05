/**
 * A property: what the published maps say about it, and the way into a scan.
 *
 * Every resolved answer names the map it came from, and anything we could not determine says so
 * plainly. A blank field would read as "you do not have a fire district"; "we could not determine
 * this" is the truth.
 */

import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import type { Property } from '@/api/types';
import { AlertStrip } from '@/components/AlertStrip';
import { Button, Card, ErrorNote, Loading, Screen, ZoneBadge } from '@/components/ui';
import { useCredentials } from '@/session';
import { colors, spacing, type } from '@/theme';

const UNRESOLVED_LABELS: Record<string, string> = {
  fhsz: 'fire hazard zone',
  fire_district: 'fire district',
  water_utility: 'water utility',
};

export default function PropertyScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const credentials = useCredentials();
  const router = useRouter();

  const [property, setProperty] = useState<Property | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  const load = useCallback(() => {
    if (!id) return;
    setError(null);
    api
      .getProperty(credentials, id)
      .then(setProperty)
      .catch((e: Error) => setError(e.message));
  }, [credentials, id]);

  useFocusEffect(load);

  async function startScan() {
    if (!property) return;
    setStarting(true);
    try {
      const scan = await api.startScan(credentials, property.id);
      router.push(`/scan/${scan.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start a scan.');
    } finally {
      setStarting(false);
    }
  }

  if (error) {
    return (
      <Screen style={styles.padded}>
        <ErrorNote message={error} onRetry={load} />
      </Screen>
    );
  }
  if (!property) return <Loading />;

  const { geo } = property;

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <AlertStrip lat={property.lat} lng={property.lng} />
        <Text style={type.title}>{property.label ?? property.address}</Text>
        {property.label ? <Text style={styles.muted}>{property.address}</Text> : null}

        <Card>
          <ZoneBadge fhsz={geo.fhsz} />
          {geo.fhsz_source_version ? (
            <Text style={styles.source}>
              {geo.fhsz_responsibility === 'LRA' ? 'Local' : 'State'} responsibility area ·{' '}
              {geo.fhsz_source_version}
            </Text>
          ) : null}

          {geo.fhsz === 'very_high' ? (
            <Text style={styles.body}>
              Properties in a Very High zone carry defensible-space obligations under state law, and
              would be covered by the proposed Zone 0 rule for the first five feet.
            </Text>
          ) : null}

          <View style={styles.factRow}>
            <Text style={styles.factLabel}>Fire district</Text>
            <Text style={styles.factValue}>{geo.fire_district ?? 'Not determined'}</Text>
          </View>
          <View style={styles.factRow}>
            <Text style={styles.factLabel}>Water utility</Text>
            <Text style={styles.factValue}>{geo.water_utility ?? 'Not determined'}</Text>
          </View>

          {geo.unresolved.length > 0 ? (
            <Text style={styles.caveat}>
              We could not determine your{' '}
              {geo.unresolved.map((key) => UNRESOLVED_LABELS[key] ?? key).join(' or ')}. Rather than
              guess, we have left it blank — the wrong agency would send you to the wrong place.
            </Text>
          ) : null}
        </Card>

        <Card>
          <Text style={type.heading}>Scan your yard</Text>
          <Text style={styles.body}>
            Seven photographs and a short set of questions. About ten minutes, and you can stop and
            pick it up later.
          </Text>
          <Button title="Start a scan" onPress={startScan} loading={starting} />
        </Card>

        <Card>
          <Text style={type.heading}>What is your lawn worth?</Text>
          <Text style={styles.body}>
            Outline the lawn on a satellite view and we will measure it and work out what your water
            utility pays to replace it.
          </Text>
          <Button
            title="Measure a lawn"
            variant="secondary"
            onPress={() => router.push(`/properties/${property.id}/lawn`)}
          />
        </Card>

        <Card>
          <Text style={type.heading}>Local programmes</Text>
          <Text style={styles.body}>
            Chipping, cost-share, and inspections from agencies near you.
          </Text>
          <Button
            title="See what is available"
            variant="secondary"
            onPress={() => router.push(`/properties/${property.id}/resources`)}
          />
        </Card>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg },
  padded: { padding: spacing.lg },
  muted: { ...type.body, color: colors.textMuted, marginBottom: spacing.md },
  body: { ...type.body, color: colors.textMuted, marginVertical: spacing.sm },
  source: { ...type.caption, color: colors.textMuted, marginTop: spacing.sm },
  factRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    marginTop: spacing.sm,
  },
  factLabel: { ...type.caption, color: colors.textMuted },
  factValue: {
    ...type.label,
    color: colors.text,
    flexShrink: 1,
    textAlign: 'right',
  },
  caveat: { ...type.caption, color: colors.textMuted, marginTop: spacing.md },
});
