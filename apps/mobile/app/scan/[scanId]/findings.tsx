/**
 * What the model spotted, drawn on the photograph it spotted it in.
 *
 * The framing here carries the product's main honesty commitment. A detection is something
 * "flagged for review", never a verdict — and anything the model is unsure about is labelled
 * *possible* and left out of the score entirely until the person who owns the house confirms it.
 *
 * Confidence is always shown. Judges will point this at their own property, and a wrong red box
 * presented confidently is far more damaging than one presented as a question.
 */

import { useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Image, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import type { Finding } from '@/api/types';
import { HAZARD_LABELS } from '@/api/types';
import { Button, Card, ErrorNote, Loading, Screen } from '@/components/ui';
import { useCredentials } from '@/session';
import { colors, radius, spacing, type } from '@/theme';

const PHOTO_HEIGHT = 220;

export default function FindingsScreen() {
  const { scanId } = useLocalSearchParams<{ scanId: string }>();
  const credentials = useCredentials();

  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!scanId) return;
    api
      .listFindings(credentials, scanId)
      .then(setFindings)
      .catch((e: Error) => setError(e.message));
  }, [credentials, scanId]);

  useEffect(load, [load]);

  async function decide(finding: Finding, status: 'confirmed' | 'dismissed') {
    setBusyId(finding.id);
    try {
      await api.setFindingStatus(credentials, finding.id, status);
      setFindings((current) =>
        current
          ? current.map((f) =>
              f.id === finding.id ? { ...f, status, needs_confirmation: false } : f,
            )
          : current,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save that.');
    } finally {
      setBusyId(null);
    }
  }

  if (!findings) return <Loading label="Loading what we spotted" />;

  const model = findings.filter((f) => f.source === 'model');

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        {error ? <ErrorNote message={error} onRetry={load} /> : null}

        <Text style={styles.intro}>
          These are things our model flagged for review. It is advisory and it does get things wrong
          You know your property, so confirm what is real and wave off what is not.
        </Text>

        {model.length === 0 ? (
          <Card>
            <Text style={type.heading}>Nothing flagged yet</Text>
            <Text style={styles.body}>
              Either your photos are still being looked at, or nothing was spotted in them. The
              questions in the checklist cover every rule regardless, so your plan will still be
              complete.
            </Text>
          </Card>
        ) : null}

        {model.map((finding) => (
          <Card key={finding.id}>
            {finding.photo_id ? (
              <View style={styles.photoWrap}>
                <Image
                  source={{
                    uri: api.photoUrl(scanId ?? '', finding.photo_id),
                    headers: { 'X-Groundwork-User': credentials.userId },
                  }}
                  style={styles.photo}
                  resizeMode="cover"
                />
                {finding.bbox ? (
                  <View
                    style={[
                      styles.box,
                      {
                        left: `${finding.bbox.x * 100}%`,
                        top: `${finding.bbox.y * 100}%`,
                        width: `${finding.bbox.w * 100}%`,
                        height: `${finding.bbox.h * 100}%`,
                        borderColor: finding.needs_confirmation ? colors.moderate : colors.critical,
                      },
                    ]}
                  />
                ) : null}
              </View>
            ) : null}

            <Text style={type.heading}>{HAZARD_LABELS[finding.hazard] ?? finding.hazard}</Text>

            <Text style={styles.confidence}>
              {finding.needs_confirmation ? 'Possible: please confirm' : 'Flagged for review'}
              {finding.confidence !== null
                ? ` · ${Math.round(finding.confidence * 100)}% confident`
                : ''}
              {finding.model_version ? ` · model ${finding.model_version}` : ''}
            </Text>

            {finding.needs_confirmation ? (
              <Text style={styles.uncertain}>
                We are not sure enough about this one to count it. It will not affect your score
                unless you confirm it.
              </Text>
            ) : null}

            {finding.status === 'open' ? (
              <View style={styles.actions}>
                <View style={styles.action}>
                  <Button
                    title="Yes, that's there"
                    onPress={() => decide(finding, 'confirmed')}
                    loading={busyId === finding.id}
                  />
                </View>
                <View style={styles.action}>
                  <Button
                    title="Not right"
                    variant="secondary"
                    onPress={() => decide(finding, 'dismissed')}
                    loading={busyId === finding.id}
                  />
                </View>
              </View>
            ) : (
              <Text style={styles.decided}>
                {finding.status === 'confirmed'
                  ? 'You confirmed this.'
                  : finding.status === 'dismissed'
                    ? 'You waved this off. It does not affect your score.'
                    : 'Resolved.'}
              </Text>
            )}
          </Card>
        ))}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg },
  intro: { ...type.body, color: colors.textMuted, marginBottom: spacing.md },
  body: { ...type.body, color: colors.textMuted, marginTop: spacing.xs },
  photoWrap: {
    height: PHOTO_HEIGHT,
    borderRadius: radius.sm,
    overflow: 'hidden',
    marginBottom: spacing.md,
    backgroundColor: colors.surfaceMuted,
  },
  photo: { width: '100%', height: '100%' },
  box: {
    position: 'absolute',
    borderWidth: 3,
    borderRadius: 2,
  },
  confidence: {
    ...type.caption,
    color: colors.textMuted,
    marginTop: spacing.xs,
  },
  uncertain: { ...type.caption, color: colors.moderate, marginTop: spacing.sm },
  actions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
  action: { flex: 1 },
  decided: { ...type.caption, color: colors.accent, marginTop: spacing.md },
});
