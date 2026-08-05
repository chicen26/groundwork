/**
 * A property: what the published maps say about it, and the way into a scan.
 *
 * One narrow column with room to breathe — a pin on a map, the zone on the state's scale, then
 * four quiet doors. Every resolved answer names the map it came from, and anything we could not
 * determine says so plainly: a blank field would read as "you do not have a fire district";
 * "we could not determine this" is the truth.
 */

import { Stack, useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import type { Property } from '@/api/types';
import { AlertStrip } from '@/components/AlertStrip';
import { AmbientBackground } from '@/components/AmbientBackground';
import { MiniMap } from '@/components/MiniMap';
import { RiskMeter } from '@/components/RiskMeter';
import { Card, ErrorNote, Loading, Screen, ZoneBadge } from '@/components/ui';
import { useCredentials } from '@/session';
import { colors, radius, spacing, type } from '@/theme';

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

  async function startScan(mode: 'quick' | 'full') {
    if (!property) return;
    setStarting(true);
    try {
      // Both modes are the same scan underneath — the quick path just goes straight to the
      // questions, so switching between them later never loses anything already answered.
      const scan = await api.startScan(credentials, property.id);
      router.push(mode === 'quick' ? `/scan/${scan.id}/quick` : `/scan/${scan.id}`);
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
      <AmbientBackground />
      <Stack.Screen
        options={{
          headerRight: () => (
            <Pressable onPress={() => router.push(`/properties/${property.id}/edit`)} hitSlop={12}>
              <Text style={styles.editLink}>Edit</Text>
            </Pressable>
          ),
        }}
      />
      <ScrollView contentContainerStyle={styles.content}>
        <AlertStrip lat={property.lat} lng={property.lng} />

        <Text style={type.title}>{property.label ?? property.address}</Text>
        {property.label ? <Text style={styles.muted}>{property.address}</Text> : null}

        <MiniMap lat={property.lat} lng={property.lng} zoom={15} height={170} />

        <Card style={styles.zoneCard}>
          <ZoneBadge fhsz={geo.fhsz} />
          <RiskMeter fhsz={geo.fhsz} />
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

        <Text style={[type.overline, styles.sectionOverline]}>Where to next</Text>

        <ActionRow
          icon="⚡"
          tint={colors.accentMuted}
          title="Quick check"
          sub="Two minutes, no camera. Same rulebook, same citations."
          onPress={() => startScan('quick')}
          disabled={starting}
          emphasized
        />
        <ActionRow
          icon="📷"
          tint={colors.emberMuted}
          title="Full scan with photos"
          sub="Seven photographs so the model can flag what you might walk past."
          onPress={() => startScan('full')}
          disabled={starting}
        />
        <ActionRow
          icon="💧"
          tint={colors.waterMuted}
          title="What is your lawn worth?"
          sub="Outline it on a satellite view; we measure and price the rebate."
          onPress={() => router.push(`/properties/${property.id}/lawn`)}
        />
        <ActionRow
          icon="🌱"
          tint={colors.surfaceMuted}
          title="Local programmes"
          sub="Chipping, cost-share, and inspections from agencies near you."
          onPress={() => router.push(`/properties/${property.id}/resources`)}
        />
      </ScrollView>
    </Screen>
  );
}

function ActionRow({
  icon,
  tint,
  title,
  sub,
  onPress,
  disabled,
  emphasized,
}: {
  icon: string;
  tint: string;
  title: string;
  sub: string;
  onPress: () => void;
  disabled?: boolean;
  emphasized?: boolean;
}) {
  return (
    <Pressable onPress={onPress} disabled={disabled} accessibilityRole="button">
      {({ pressed }) => (
        <View
          style={[
            styles.action,
            emphasized && styles.actionEmphasized,
            pressed && styles.actionPressed,
            disabled && styles.actionDisabled,
          ]}
        >
          <View style={[styles.actionIcon, { backgroundColor: tint }]}>
            <Text style={styles.actionIconText}>{icon}</Text>
          </View>
          <View style={styles.actionBody}>
            <Text style={[type.heading, emphasized && styles.actionTitleEmphasized]}>{title}</Text>
            <Text style={[styles.actionSub, emphasized && styles.actionSubEmphasized]}>{sub}</Text>
          </View>
          <Text style={[styles.chevron, emphasized && styles.actionTitleEmphasized]}>›</Text>
        </View>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.lg,
    paddingBottom: spacing.xxl,
    gap: spacing.md,
    maxWidth: 620,
    width: '100%',
    alignSelf: 'center',
  },
  padded: { padding: spacing.lg },
  muted: { ...type.body, color: colors.textMuted, marginTop: -spacing.sm },
  body: { ...type.body, color: colors.textMuted, marginVertical: spacing.sm },
  source: { ...type.caption, color: colors.textMuted, marginTop: spacing.xs },
  zoneCard: { gap: spacing.sm, marginBottom: 0 },
  factRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: spacing.md,
    paddingVertical: spacing.sm + 2,
    borderTopWidth: 1,
    borderTopColor: colors.surfaceMuted,
  },
  factLabel: { ...type.caption, color: colors.textMuted },
  factValue: {
    ...type.label,
    color: colors.text,
    flexShrink: 1,
    textAlign: 'right',
  },
  caveat: { ...type.caption, color: colors.textMuted },
  editLink: { ...type.label, color: colors.accent },
  sectionOverline: { color: colors.textMuted, marginTop: spacing.md },
  action: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border,
  },
  actionEmphasized: {
    backgroundColor: colors.ink,
    borderColor: colors.ink,
  },
  actionPressed: { opacity: 0.85 },
  actionDisabled: { opacity: 0.5 },
  actionIcon: {
    width: 44,
    height: 44,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionIconText: { fontSize: 20 },
  actionBody: { flex: 1, gap: 2 },
  actionTitleEmphasized: { color: colors.textInverse },
  actionSub: { ...type.caption, color: colors.textMuted },
  actionSubEmphasized: { color: colors.creamMuted },
  chevron: { fontSize: 26, color: colors.textMuted, fontWeight: '300' },
});
