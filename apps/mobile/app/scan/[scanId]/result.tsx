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

import AsyncStorage from '@react-native-async-storage/async-storage';
import { File, Paths } from 'expo-file-system';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as Sharing from 'expo-sharing';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Platform, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

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
import { colors, radius, scoreColor, severityColor, shadow, spacing, type } from '@/theme';

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

  // Marking work done must be *seen* to work: the page jumps back to the score and says what
  // moved, because the number changing off-screen reads as nothing having happened.
  const [lastChange, setLastChange] = useState<{ from: number; to: number } | null>(null);

  // The tour: one section at a time, highlighted and explained. Runs itself on the first visit.
  const [tourStep, setTourStep] = useState<number | null>(null);
  const scrollRef = useRef<ScrollView | null>(null);
  const sectionY = useRef<Record<string, number>>({});

  const load = useCallback(() => {
    setError(null);
    const request = assessmentId
      ? api.getAssessment(credentials, assessmentId)
      : api.assess(credentials, scanId ?? '');
    request.then(setAssessment).catch((e: Error) => setError(e.message));
  }, [assessmentId, credentials, scanId]);

  useEffect(load, [load]);

  useEffect(() => {
    if (!assessment) return;
    AsyncStorage.getItem(TOUR_SEEN_KEY).then((seen) => {
      if (!seen) setTourStep(0);
    });
  }, [assessment !== null]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (tourStep === null) return;
    const y = sectionY.current[TOUR_STEPS[tourStep].key];
    scrollRef.current?.scrollTo({ y: Math.max(0, (y ?? 0) - 76), animated: true });
  }, [tourStep]);

  function endTour() {
    setTourStep(null);
    AsyncStorage.setItem(TOUR_SEEN_KEY, 'yes');
  }

  const trackSection = (key: string) => ({
    onLayout: (event: { nativeEvent: { layout: { y: number } } }) => {
      sectionY.current[key] = event.nativeEvent.layout.y;
    },
  });

  async function complete(item: PlanItem) {
    if (!scanId || !assessment) return;
    setBusyId(item.id);
    const before = assessment.score;
    try {
      await api.completePlanItem(credentials, item.id);
      // Re-assess so the score reflects the work rather than an optimistic guess. It should land
      // on exactly the number the item promised.
      const updated = await api.assess(credentials, scanId);
      setAssessment(updated);
      setLastChange({ from: before, to: updated.score });
      scrollRef.current?.scrollTo({ y: 0, animated: true });
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
      if (Platform.OS === 'web') {
        // No share sheet on the web; fetch with the auth header and hand the browser a blob link.
        const response = await fetch(api.reportUrl(assessment.id), {
          headers: { 'X-Groundwork-User': credentials.userId },
        });
        if (!response.ok) throw new Error('Could not build the document.');
        const url = URL.createObjectURL(await response.blob());
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = `groundwork-${assessment.id}.pdf`;
        anchor.click();
        URL.revokeObjectURL(url);
        return;
      }
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
  const band = scoreBand(assessment.score);

  const highlight = (key: string) =>
    tourStep !== null && TOUR_STEPS[tourStep].key === key ? styles.tourHighlight : undefined;

  return (
    <Screen>
      <ScrollView ref={scrollRef} contentContainerStyle={styles.content}>
        {error ? <ErrorNote message={error} /> : null}

        {lastChange && lastChange.to !== lastChange.from ? (
          <View style={styles.changeBanner}>
            <Text style={styles.changeText}>
              Nice work. Your score moved from {lastChange.from} to {lastChange.to}.
            </Text>
          </View>
        ) : null}

        {/* The dashboard: the number, its meaning, and the three counts that matter, at a glance. */}
        <View style={styles.dashboard} {...trackSection('score')}>
          <View
            style={[
              styles.scoreTile,
              { borderColor: scoreColor(assessment.score) },
              highlight('score'),
            ]}
          >
            <Text style={[styles.score, { color: scoreColor(assessment.score) }]}>
              {assessment.score}
            </Text>
            <Text style={[styles.scoreBandLabel, { color: scoreColor(assessment.score) }]}>
              {band.label}
            </Text>
            <Text style={styles.scoreLabel}>Readiness score</Text>
          </View>
          <View style={[styles.statColumn, highlight('stats')]}>
            <StatTile value={bindingCount} label="Required by law" tone={colors.critical} />
            <StatTile
              value={remaining.length - bindingCount}
              label="Recommended"
              tone={colors.water}
            />
            <StatTile value={done.length} label="Done" tone={colors.accent} />
          </View>
        </View>

        <View {...trackSection('meaning')}>
          <Card style={[styles.meaningCard, highlight('meaning')]}>
            <Text style={type.overline}>What this score means</Text>
            <Text style={styles.meaningText}>{band.meaning}</Text>
            <Text style={styles.scoreExplain}>
              You are meeting {Math.round(assessment.breakdown.met_weight)} of{' '}
              {Math.round(assessment.breakdown.applicable_weight)} points of what applies to your
              property.
            </Text>
            <Pressable onPress={() => setShowWorking((v) => !v)}>
              <Text style={styles.link}>
                {showWorking ? 'Hide the working' : 'Show the working'}
              </Text>
            </Pressable>
          </Card>
        </View>

        {tourStep === null ? (
          <Pressable onPress={() => setTourStep(0)}>
            <Text style={styles.tourLink}>New here? Take the 30-second tour</Text>
          </Pressable>
        ) : null}

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

        <View {...trackSection('plan')} style={highlight('plan')}>
          {bindingCount > 0 ? (
            <Text style={styles.leadIn}>
              {bindingCount} of these {bindingCount === 1 ? 'is' : 'are'} required by law today.
              Those come first.
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
                    ? `Mark done · score goes to ${item.score_if_done}`
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
        </View>

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

        <View {...trackSection('pdf')}>
          <Card style={highlight('pdf')}>
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
        </View>

        <Button title="Back to my property" onPress={() => router.replace('/')} />

        <Disclaimer text={assessment.disclaimer} />
      </ScrollView>

      {tourStep !== null ? (
        <View style={styles.tourCard}>
          <Text style={type.overline}>
            Tour · {tourStep + 1} of {TOUR_STEPS.length}
          </Text>
          <Text style={styles.tourTitle}>{TOUR_STEPS[tourStep].title}</Text>
          <Text style={styles.tourText}>{TOUR_STEPS[tourStep].text}</Text>
          <View style={styles.tourButtons}>
            <Pressable onPress={endTour} hitSlop={8}>
              <Text style={styles.tourSkip}>Skip</Text>
            </Pressable>
            <Button
              title={tourStep === TOUR_STEPS.length - 1 ? 'Got it' : 'Next'}
              onPress={() =>
                tourStep === TOUR_STEPS.length - 1 ? endTour() : setTourStep(tourStep + 1)
              }
            />
          </View>
        </View>
      ) : null}
    </Screen>
  );
}

const TOUR_SEEN_KEY = 'groundwork.tour.plan.v1';

const TOUR_STEPS: { key: string; title: string; text: string }[] = [
  {
    key: 'score',
    title: 'Your readiness score',
    text: 'From 0 to 100, computed from the state and local rules that actually apply to your property. The color and the word tell you the band at a glance.',
  },
  {
    key: 'stats',
    title: 'The three counts',
    text: 'What the law requires today, what is recommended on top of that, and what you have already finished.',
  },
  {
    key: 'meaning',
    title: 'What it means',
    text: 'The score in plain words. "Show the working" opens every rule behind the number, each with its citation, so nothing here is a black box.',
  },
  {
    key: 'plan',
    title: 'Your plan',
    text: 'Each card is one task, with its legal status, rough time and cost, and the exact score you will have once it is done. Mark it done and the number at the top updates immediately.',
  },
  {
    key: 'pdf',
    title: 'Take it with you',
    text: 'Create a PDF of the whole assessment for your records or your insurer. It is your documentation, not an official inspection.',
  },
];

/** The band a score falls in, and the sentence that tells you what living there means. */
function scoreBand(score: number): { label: string; meaning: string } {
  if (score >= 80) {
    return {
      label: 'Strong',
      meaning:
        'Your yard broadly meets the rules that apply to it. Keep it maintained, especially through fire season, and re-check after windstorms.',
    };
  }
  if (score >= 60) {
    return {
      label: 'Getting there',
      meaning:
        'Most of what applies is met, but real gaps remain. The items below close them, starting with anything the law requires today.',
    };
  }
  if (score >= 40) {
    return {
      label: 'Needs work',
      meaning:
        'Several rules that apply to your property are not met yet. Start with the items required by law; they matter most to inspectors and insurers.',
    };
  }
  return {
    label: 'At risk',
    meaning:
      'Most of what applies to your property is unmet. The plan below is ordered so the highest-stakes work comes first; even one afternoon moves this number.',
  };
}

function StatTile({ value, label, tone }: { value: number; label: string; tone: string }) {
  return (
    <View style={styles.statTile}>
      <Text style={[styles.statValue, { color: tone }]}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.lg,
    maxWidth: 680,
    width: '100%',
    alignSelf: 'center',
  },
  padded: { padding: spacing.lg },
  dashboard: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.sm },
  scoreTile: {
    flex: 1.3,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    borderWidth: 2,
    padding: spacing.md,
    gap: 2,
  },
  score: { fontSize: 64, fontWeight: '800', letterSpacing: -2, lineHeight: 68 },
  scoreBandLabel: { ...type.label, fontSize: 15 },
  scoreLabel: { ...type.caption, color: colors.textMuted },
  statColumn: { flex: 1, gap: spacing.sm },
  statTile: {
    flex: 1,
    backgroundColor: colors.surface,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    paddingHorizontal: spacing.sm + 4,
    paddingVertical: spacing.sm,
    justifyContent: 'center',
  },
  statValue: { ...type.title, fontSize: 22, lineHeight: 26 },
  statLabel: { ...type.caption, fontSize: 11.5, lineHeight: 15, color: colors.textMuted },
  meaningCard: { gap: spacing.xs },
  meaningText: { ...type.body, color: colors.text },
  scoreExplain: {
    ...type.caption,
    color: colors.textMuted,
    marginTop: spacing.xs,
  },
  link: { ...type.label, color: colors.accent, marginTop: spacing.sm },
  changeBanner: {
    backgroundColor: colors.accentMuted,
    borderLeftWidth: 4,
    borderLeftColor: colors.accent,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  changeText: { ...type.label, color: colors.accent },
  tourLink: {
    ...type.label,
    color: colors.accent,
    textAlign: 'center',
    marginBottom: spacing.md,
  },
  tourHighlight: {
    borderWidth: 2,
    borderColor: colors.ember,
    borderRadius: radius.lg,
    shadowColor: colors.ember,
    shadowOpacity: 0.25,
    shadowRadius: 12,
    shadowOffset: { width: 0, height: 0 },
  },
  tourCard: {
    position: 'absolute',
    left: spacing.md,
    right: spacing.md,
    bottom: spacing.md,
    maxWidth: 560,
    alignSelf: 'center',
    width: 'auto',
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md + 4,
    gap: spacing.xs,
    borderWidth: 1,
    borderColor: colors.border,
    ...shadow.raised,
  },
  tourTitle: { ...type.heading },
  tourText: { ...type.caption, color: colors.textMuted, lineHeight: 19 },
  tourButtons: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.sm,
  },
  tourSkip: { ...type.label, color: colors.textMuted },
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
