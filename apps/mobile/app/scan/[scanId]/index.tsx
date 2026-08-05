/**
 * The guided walk.
 *
 * Seven stations and a set of questions, in whatever order suits the person holding the phone. The
 * scan is resumable by design: ten minutes around a house is long enough that people get
 * interrupted, and starting over would lose us testers.
 */

import { useFocusEffect, useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import type { ScanSummary, Station } from '@/api/types';
import { STATION_HINTS, STATION_LABELS } from '@/api/types';
import { Button, Card, ErrorNote, Loading, Screen } from '@/components/ui';
import { useCredentials } from '@/session';
import { colors, radius, spacing, type } from '@/theme';

const ALL_STATIONS: Station[] = [
  'front_elevation',
  'left_side',
  'right_side',
  'rear_elevation',
  'deck_porch',
  'roofline',
  'perimeter_0_5ft',
];

export default function ScanScreen() {
  const { scanId } = useLocalSearchParams<{ scanId: string }>();
  const credentials = useCredentials();
  const router = useRouter();

  const [scan, setScan] = useState<ScanSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [assessing, setAssessing] = useState(false);

  const load = useCallback(() => {
    if (!scanId) return;
    setError(null);
    api
      .getScan(credentials, scanId)
      .then(setScan)
      .catch((e: Error) => setError(e.message));
  }, [credentials, scanId]);

  useFocusEffect(load);

  async function finish() {
    if (!scanId) return;
    setAssessing(true);
    try {
      const assessment = await api.assess(credentials, scanId);
      router.push(`/scan/${scanId}/result?assessmentId=${assessment.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not build your plan.');
    } finally {
      setAssessing(false);
    }
  }

  if (error) {
    return (
      <Screen style={styles.padded}>
        <ErrorNote message={error} onRetry={load} />
      </Screen>
    );
  }
  if (!scan) return <Loading label="Loading your scan" />;

  const photographed = new Set(scan.stations_photographed);
  const questionsDone = scan.questions_answered >= scan.questions_total;

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.progress}>
          {photographed.size} of {ALL_STATIONS.length} photographed · {scan.questions_answered} of{' '}
          {scan.questions_total} questions answered
        </Text>

        {scan.photos_pending_inference > 0 ? (
          <Text style={styles.pending}>
            {scan.photos_pending_inference} photo
            {scan.photos_pending_inference === 1 ? '' : 's'} still being looked at. You can carry
            on.
          </Text>
        ) : null}

        {ALL_STATIONS.map((station) => {
          const done = photographed.has(station);
          return (
            <Pressable
              key={station}
              onPress={() => router.push(`/scan/${scanId}/camera?station=${station}`)}
            >
              <Card style={done ? styles.doneCard : undefined}>
                <View style={styles.row}>
                  <View style={styles.rowText}>
                    <Text style={type.heading}>{STATION_LABELS[station]}</Text>
                    <Text style={styles.hint}>{STATION_HINTS[station]}</Text>
                  </View>
                  <View style={[styles.tick, done && styles.tickDone]}>
                    <Text style={[styles.tickText, done && styles.tickTextDone]}>
                      {done ? '✓' : ''}
                    </Text>
                  </View>
                </View>
                {done ? <Text style={styles.retake}>Tap to retake</Text> : null}
              </Card>
            </Pressable>
          );
        })}

        <Pressable onPress={() => router.push(`/scan/${scanId}/checklist`)}>
          <Card style={questionsDone ? styles.doneCard : undefined}>
            <Text style={type.heading}>Questions about what a photo cannot show</Text>
            <Text style={styles.hint}>
              Gutters, vents, and the far end of the property. {scan.questions_answered} of{' '}
              {scan.questions_total} answered.
            </Text>
          </Card>
        </Pressable>

        {scan.open_findings > 0 ? (
          <Pressable onPress={() => router.push(`/scan/${scanId}/findings`)}>
            <Card>
              <Text style={type.heading}>Review what we spotted</Text>
              <Text style={styles.hint}>
                {scan.open_findings} thing{scan.open_findings === 1 ? '' : 's'} flagged for you to
                confirm or wave off.
              </Text>
            </Card>
          </Pressable>
        ) : null}

        <Button title="Build my plan" onPress={finish} loading={assessing} />
        <Text style={styles.note}>
          You can build a plan at any point. Answering more questions and photographing more of the
          yard makes it more complete.
        </Text>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg },
  padded: { padding: spacing.lg },
  progress: {
    ...type.label,
    color: colors.textMuted,
    marginBottom: spacing.md,
  },
  pending: { ...type.caption, color: colors.water, marginBottom: spacing.md },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  rowText: { flex: 1 },
  hint: { ...type.caption, color: colors.textMuted, marginTop: spacing.xs },
  retake: { ...type.caption, color: colors.accent, marginTop: spacing.sm },
  doneCard: { borderColor: colors.accent, backgroundColor: colors.accentMuted },
  tick: {
    width: 28,
    height: 28,
    borderRadius: radius.pill,
    borderWidth: 1.5,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tickDone: { backgroundColor: colors.accent, borderColor: colors.accent },
  tickText: { color: 'transparent' },
  tickTextDone: { color: colors.textInverse, fontWeight: '700' },
  note: { ...type.caption, color: colors.textMuted, marginTop: spacing.md },
});
