/**
 * Outline the lawn, find out what replacing it is worth.
 *
 * Tap corners on the satellite view; the outline is sent to the server, which measures it
 * geodesically and does the rebate arithmetic. We deliberately do not compute the area on the phone
 * even though turf.js could: this number decides money, and there should be exactly one place it
 * comes from.
 *
 * The pre-approval warning is the first thing on the screen and repeats on every estimate. Removing
 * a lawn before the utility inspects it voids the rebate no matter how good the finished yard is —
 * that is the single most expensive mistake this screen could let someone make.
 */

import { useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import type { LatLng, LawnMapHandle } from '@/components/LawnMap';
import { LawnMap } from '@/components/LawnMap';
import type { LawnMeasurement, Property, RebateEstimate } from '@/api/types';
import { Button, Card, ErrorNote, Loading, Screen } from '@/components/ui';
import { useCredentials } from '@/session';
import { colors, radius, spacing, type } from '@/theme';

export default function LawnScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const credentials = useCredentials();

  const [property, setProperty] = useState<Property | null>(null);
  const [points, setPoints] = useState<LatLng[]>([]);
  const mapControls = useRef<LawnMapHandle | null>(null);
  const [result, setResult] = useState<LawnMeasurement | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(() => {
    if (!id) return;
    api
      .getProperty(credentials, id)
      .then(setProperty)
      .catch((e: Error) => setError(e.message));
  }, [credentials, id]);

  useEffect(load, [load]);

  async function measure() {
    if (!id || points.length < 3) return;
    setSaving(true);
    setError(null);
    try {
      // GeoJSON is [lng, lat], and the ring has to close by repeating the first corner.
      const ring = points.map((p) => [p.longitude, p.latitude]);
      ring.push(ring[0]);
      setResult(
        await api.measureLawn(credentials, id, {
          type: 'Polygon',
          coordinates: [ring],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not measure that outline.');
    } finally {
      setSaving(false);
    }
  }

  if (!property) return <Loading label="Loading your property" />;

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.warningBox}>
          <Text style={styles.warningTitle}>Apply before you dig</Text>
          <Text style={styles.warningBody}>
            Every one of these rebates needs approval and an inspection before you remove anything.
            Work started early is not eligible, even if the finished yard would have qualified.
          </Text>
        </View>

        {error ? <ErrorNote message={error} /> : null}

        <Text style={styles.instruction}>
          Tap the corners of the lawn you want to replace. Three corners minimum; tap Undo to fix a
          mistake.
        </Text>

        <View style={styles.mapWrap}>
          <LawnMap
            lat={property.lat}
            lng={property.lng}
            controlsRef={mapControls}
            onChange={(next) => {
              setPoints(next);
              setResult(null);
            }}
          />
        </View>

        <View style={styles.mapActions}>
          <View style={styles.mapAction}>
            <Button
              title="Undo"
              variant="secondary"
              onPress={() => mapControls.current?.undo()}
              disabled={points.length === 0}
            />
          </View>
          <View style={styles.mapAction}>
            <Button
              title="Start over"
              variant="secondary"
              onPress={() => mapControls.current?.clear()}
              disabled={points.length === 0}
            />
          </View>
        </View>

        <Button
          title={points.length < 3 ? 'Tap at least three corners' : 'Measure this lawn'}
          onPress={measure}
          disabled={points.length < 3}
          loading={saving}
        />

        {result ? <Results result={result} /> : null}
      </ScrollView>
    </Screen>
  );
}

function Results({ result }: { result: LawnMeasurement }) {
  const area = Math.round(Number(result.area_sqft));
  const gallons = Number(result.annual_gallons_saved);

  return (
    <View style={styles.results}>
      <Card>
        <Text style={type.title}>{area.toLocaleString()} sq ft</Text>
        <Text style={styles.muted}>
          Replacing this would save roughly {gallons.toLocaleString()} gallons a year.
        </Text>
        <Text style={styles.basis}>{result.savings_basis}</Text>
      </Card>

      {result.showing_all_programs ? (
        <Text style={styles.allPrograms}>
          We could not work out which water utility serves this address, so all three are shown.
          Check which one bills you — the rate and the cap are different.
        </Text>
      ) : null}

      {result.rebates.map((rebate) => (
        <RebateCard key={rebate.program_key} rebate={rebate} />
      ))}
    </View>
  );
}

function RebateCard({ rebate }: { rebate: RebateEstimate }) {
  return (
    <Card>
      <Text style={type.label}>{rebate.agency}</Text>
      <Text style={styles.programName}>
        {rebate.program_name}
        {rebate.tier_label ? ` · ${rebate.tier_label}` : ''}
      </Text>

      {rebate.eligible ? (
        <>
          <Text style={styles.amount}>${Number(rebate.amount_usd).toLocaleString()}</Text>
          <Text style={styles.muted}>estimated, at ${rebate.rate_per_sqft} per sq ft</Text>
          {rebate.capped ? (
            <Text style={styles.capped}>
              Your lawn would earn ${Number(rebate.uncapped_usd).toLocaleString()} at that rate, but
              this programme caps out at ${Number(rebate.cap_usd).toLocaleString()}.
            </Text>
          ) : null}
        </>
      ) : (
        <Text style={styles.ineligible}>{rebate.ineligible_reason}</Text>
      )}

      <Text style={styles.rebateWarning}>{rebate.warning}</Text>

      <Pressable onPress={() => Linking.openURL(rebate.url)}>
        <Text style={styles.link}>Open {rebate.agency}&apos;s application page →</Text>
      </Pressable>
    </Card>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg },
  warningBox: {
    backgroundColor: '#FFF4E5',
    borderRadius: radius.md,
    borderLeftWidth: 4,
    borderLeftColor: colors.high,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  warningTitle: { ...type.heading, color: colors.high },
  warningBody: { ...type.caption, color: colors.text, marginTop: spacing.xs },
  instruction: {
    ...type.body,
    color: colors.textMuted,
    marginBottom: spacing.sm,
  },
  mapWrap: {
    height: 320,
    borderRadius: radius.md,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: colors.border,
  },
  map: { flex: 1 },
  mapActions: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginVertical: spacing.sm,
  },
  mapAction: { flex: 1 },
  results: { marginTop: spacing.lg },
  muted: { ...type.caption, color: colors.textMuted, marginTop: spacing.xs },
  basis: {
    ...type.caption,
    color: colors.textMuted,
    marginTop: spacing.sm,
    fontStyle: 'italic',
  },
  allPrograms: {
    ...type.caption,
    color: colors.water,
    marginBottom: spacing.md,
  },
  programName: { ...type.heading, marginTop: spacing.xs },
  amount: {
    fontSize: 34,
    fontWeight: '800',
    color: colors.water,
    marginTop: spacing.sm,
  },
  capped: { ...type.caption, color: colors.textMuted, marginTop: spacing.sm },
  ineligible: { ...type.body, color: colors.textMuted, marginTop: spacing.sm },
  rebateWarning: { ...type.caption, color: colors.high, marginTop: spacing.md },
  link: { ...type.label, color: colors.accent, marginTop: spacing.md },
});
