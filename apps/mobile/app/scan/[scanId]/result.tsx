/**
 * The score and the plan.
 *
 * Three commitments show up on this screen:
 *
 * 1. The score shows its work. A number next to a legal citation has to be explainable, so the
 *    formula and the weights behind it are one tap away rather than hidden.
 * 2. Every task says what is asking for it, and whether that is law today, a draft, or advice.
 * 3. Checking a task off previews the exact score it produces — the same arithmetic the server
 *    runs, so the promise cannot disagree with the result.
 */

import { File, Paths } from 'expo-file-system';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as Sharing from 'expo-sharing';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import type { Assessment, PlanItem } from '@/api/types';
import {
  Button,
  Card,
  Disclaimer,
  ErrorNote,
  LegalStatusBadge,
  Loading,
  Screen,
} from '@/components/ui';
import { useCredentials } from '@/session';
import { colors, radius, scoreColor, severityColor, spacing, type } from '@/theme';

export default function ResultScreen() {
  const { scanId, assessmentId } = useLocalSearchParams<{
    scanId: string;
    assessmentId?: string;
  }>();
  const credentials = useCredentials();
  const router = useRouter();

  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showWorking, setShowWorking] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  const load = useCallback(() => {
    setError(null);
    const request = assessmentId
      ? api.getAssessment(credentials, assessmentId)
      : api.assess(credentials, scanId ?? '');
    request.then(setAssessment).catch((e: Error) => setError(e.message));
  }, [assessmentId, credentials, scanId]);

  useEffect(load, [load]);

  async function complete(item: PlanItem) {
    if (!scanId) return;
    setBusyId(item.id);
    try {
      await api.completePlanItem(credentials, item.id);
      // Re-assess so the score reflects the work rather than an optimistic guess. It should land
      // on exactly the number the item promised.
      const updated = await api.assess(credentials, scanId);
      setAssessment(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not mark that done.');
    } finally {
      setBusyId(null);
    }
  }

  async function downloadReport() {
    if (!assessment) return;
    setDownloading(true);
    setError(null);
    try {
      // Written to a file and handed to the share sheet: the PDF exists to leave the phone, and
      // it carries someone's address and photographs, so the user chooses where it goes rather
      // than us picking for them.
      const task = File.createDownloadTask(
        api.reportUrl(assessment.id),
        new File(Paths.cache, `groundwork-${assessment.id}.pdf`),
        {
          headers: { 'X-Groundwork-User': credentials.userId },
        },
      );
      const file = await task.downloadAsync();
      if (!file) {
        throw new Error('The document did not finish downloading.');
      }
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(file.uri, { mimeType: 'application/pdf' });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not build the document.');
    } finally {
      setDownloading(false);
    }
  }

  if (error && !assessment) {
    return (
      <Screen style={styles.padded}>
        <ErrorNote message={error} onRetry={load} />
      </Screen>
    );
  }
  if (!assessment) return <Loading label="Working out your plan" />;

  const remaining = assessment.plan.filter((item) => !item.done);
  const done = assessment.plan.filter((item) => item.done);
  const bindingCount = remaining.filter((item) => item.rule_status === 'in_effect').length;

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        {error ? <ErrorNote message={error} /> : null}

        <View style={styles.scoreBlock}>
          <Text style={[styles.score, { color: scoreColor(assessment.score) }]}>
            {assessment.score}
          </Text>
          <Text style={styles.scoreLabel}>Readiness score</Text>
          <Text style={styles.scoreExplain}>
            You are meeting {Math.round(assessment.breakdown.met_weight)} of{' '}
            {Math.round(assessment.breakdown.applicable_weight)} points of what applies to your
            property.
          </Text>
          <Pressable onPress={() => setShowWorking((v) => !v)}>
            <Text style={styles.link}>{showWorking ? 'Hide the working' : 'Show the working'}</Text>
          </Pressable>
        </View>

        {showWorking ? (
          <Card>
            <Text style={type.label}>How this is calculated</Text>
            <Text style={styles.formula}>{assessment.breakdown.formula}</Text>
            <Text style={styles.rulebook}>Rulebook {assessment.rulebook_version}</Text>
            {assessment.breakdown.rules.map((rule) => (
              <View key={rule.rule_id} style={styles.workingRow}>
                <Text
                  style={[
                    styles.workingMark,
                    { color: rule.met ? colors.accent : colors.critical },
                  ]}
                >
                  {rule.met ? '✓' : '✗'}
                </Text>
                <View style={styles.workingText}>
                  <Text style={type.caption}>{rule.title}</Text>
                  <Text style={styles.citation}>
                    {rule.citation} · {rule.authority}
                  </Text>
                </View>
                <Text style={styles.weight}>
                  {rule.met ? `+${rule.weight}` : `0 / ${rule.weight}`}
                </Text>
              </View>
            ))}
          </Card>
        ) : null}

        {bindingCount > 0 ? (
          <Text style={styles.leadIn}>
            {bindingCount} of these {bindingCount === 1 ? 'is' : 'are'} required by law today. Those
            come first.
          </Text>
        ) : null}

        {remaining.map((item) => (
          <Card key={item.id}>
            <View style={styles.itemHeader}>
              <View
                style={[styles.severityDot, { backgroundColor: severityColor(item.severity) }]}
              />
              <Text style={styles.itemTitle}>{item.title}</Text>
            </View>

            <LegalStatusBadge status={item.rule_status} />

            <Text style={styles.itemDetail}>{item.detail}</Text>

            {item.caveat ? <Text style={styles.caveat}>{item.caveat}</Text> : null}

            <Text style={styles.citation}>
              {item.citation}
              {item.zone ? ` · ${item.zone}` : ''}
            </Text>

            <View style={styles.metaRow}>
              {item.effort_hours !== null ? (
                <Text style={styles.meta}>About {item.effort_hours}h</Text>
              ) : null}
              {item.cost_est_usd !== null ? (
                <Text style={styles.meta}>
                  {item.cost_est_usd === 0 ? 'No cost' : `~$${item.cost_est_usd}`}
                </Text>
              ) : null}
            </View>

            <Button
              title={
                item.score_if_done !== null
                  ? `Mark done — score goes to ${item.score_if_done}`
                  : 'Mark done'
              }
              variant="secondary"
              loading={busyId === item.id}
              onPress={() => complete(item)}
            />
          </Card>
        ))}

        {remaining.length === 0 ? (
          <Card>
            <Text style={type.heading}>Nothing outstanding</Text>
            <Text style={styles.itemDetail}>
              Every rule that applies to your property is met, based on what you photographed and
              answered.
            </Text>
          </Card>
        ) : null}

        {done.length > 0 ? (
          <>
            <Text style={styles.leadIn}>Done</Text>
            {done.map((item) => (
              <Card key={item.id} style={styles.doneCard}>
                <Text style={styles.doneTitle}>{item.title}</Text>
              </Card>
            ))}
          </>
        ) : null}

        <Card>
          <Text style={type.heading}>Documentation for your insurer</Text>
          <Text style={styles.itemDetail}>
            A PDF of this assessment: your zone, your score, the work you have completed with its
            photographs, and what is still outstanding. It is your own documentation, not an
            inspection or a certification.
          </Text>
          <Button
            title="Create the document"
            variant="secondary"
            onPress={downloadReport}
            loading={downloading}
          />
        </Card>

        <Button title="Back to my property" variant="quiet" onPress={() => router.replace('/')} />

        <Disclaimer text={assessment.disclaimer} />
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg },
  padded: { padding: spacing.lg },
  scoreBlock: { alignItems: 'center', marginBottom: spacing.lg },
  score: { fontSize: 76, fontWeight: '800', letterSpacing: -2 },
  scoreLabel: { ...type.label, color: colors.textMuted },
  scoreExplain: {
    ...type.caption,
    color: colors.textMuted,
    textAlign: 'center',
    marginTop: spacing.sm,
  },
  link: { ...type.label, color: colors.accent, marginTop: spacing.sm },
  formula: { ...type.caption, color: colors.textMuted, marginTop: spacing.xs },
  rulebook: {
    ...type.caption,
    color: colors.textMuted,
    marginBottom: spacing.sm,
  },
  workingRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.border,
  },
  workingMark: { fontWeight: '700', width: 16 },
  workingText: { flex: 1 },
  weight: { ...type.caption, color: colors.textMuted },
  leadIn: { ...type.label, color: colors.textMuted, marginBottom: spacing.sm },
  itemHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginBottom: spacing.sm,
  },
  severityDot: { width: 10, height: 10, borderRadius: radius.pill },
  itemTitle: { ...type.heading, flex: 1 },
  itemDetail: { ...type.body, color: colors.textMuted, marginTop: spacing.sm },
  caveat: {
    ...type.caption,
    color: colors.draft,
    backgroundColor: colors.draftMuted,
    padding: spacing.sm,
    borderRadius: radius.sm,
    marginTop: spacing.sm,
  },
  citation: { ...type.caption, color: colors.textMuted, marginTop: spacing.sm },
  metaRow: {
    flexDirection: 'row',
    gap: spacing.md,
    marginVertical: spacing.sm,
  },
  meta: { ...type.caption, color: colors.textMuted },
  doneCard: { backgroundColor: colors.accentMuted, borderColor: colors.accent },
  doneTitle: { ...type.body, color: colors.accent },
});
