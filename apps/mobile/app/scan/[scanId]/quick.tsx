/**
 * Quick Check: a real assessment without the camera.
 *
 * The full walk is seven photographs and twelve questions, and that is the right product for
 * someone who has decided to act. It is the wrong product for someone deciding whether to care.
 *
 * This exists because the checklist alone already covers every rule in the rulebook (a deliberate
 * design constraint, not a fallback), so answering the questions produces a genuine score, a
 * genuine plan, and genuine citations, with no photograph taken. The only thing missing is the
 * model's second opinion, and the screen says so rather than implying the result is lesser than
 * it is.
 *
 * One question fills the screen at a time, centred, with the progress bar as the only chrome:
 * a quiz should feel like a conversation, not a form.
 */

import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import type { Question } from '@/api/types';
import { Button, Card, ErrorNote, Loading, Screen } from '@/components/ui';
import { useCredentials } from '@/session';
import { colors, radius, spacing, type } from '@/theme';

export default function QuickCheckScreen() {
  const { scanId } = useLocalSearchParams<{ scanId: string }>();
  const credentials = useCredentials();
  const router = useRouter();

  const [questions, setQuestions] = useState<Question[] | null>(null);
  const [answers, setAnswers] = useState<Record<string, boolean>>({});
  const [index, setIndex] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [finishing, setFinishing] = useState(false);

  useEffect(() => {
    api
      .getChecklist(credentials)
      .then(setQuestions)
      .catch((e: Error) => setError(e.message));
  }, [credentials]);

  const current = useMemo(() => questions?.[index] ?? null, [questions, index]);

  async function answer(hazardPresent: boolean) {
    if (!scanId || !current) return;
    setAnswers((prev) => ({ ...prev, [current.id]: hazardPresent }));
    setIndex((prev) => prev + 1);
    try {
      await api.submitChecklist(credentials, scanId, [
        { question_id: current.id, hazard_present: hazardPresent },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'That answer did not save.');
    }
  }

  async function finish() {
    if (!scanId) return;
    setFinishing(true);
    try {
      const assessment = await api.assess(credentials, scanId);
      router.replace(`/scan/${scanId}/result?assessmentId=${assessment.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not build your plan.');
      setFinishing(false);
    }
  }

  if (error && !questions) {
    return (
      <Screen style={styles.padded}>
        <ErrorNote message={error} />
      </Screen>
    );
  }
  if (!questions) return <Loading label="Loading the questions" />;

  const done = index >= questions.length;

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        {error ? <ErrorNote message={error} /> : null}

        <View style={styles.progressRow}>
          <View style={styles.progressTrack}>
            <View
              style={[
                styles.progressFill,
                { width: `${(Math.min(index, questions.length) / questions.length) * 100}%` },
              ]}
            />
          </View>
          <Text style={styles.progressLabel}>
            {Math.min(index + (done ? 0 : 1), questions.length)}/{questions.length}
          </Text>
        </View>

        <View style={styles.stage}>
          {done ? (
            <Card style={styles.questionCard}>
              <Text style={type.title}>That&apos;s Everything!</Text>
              <Text style={styles.body}>
                Your plan is built from the same rulebook, with the same citations, as a full scan.
                The one thing it does not have is our model&apos;s second opinion on your
                photographs. You can add that any time by running a full scan on the same property.
              </Text>
              <Button title="Show me my plan" onPress={finish} loading={finishing} />
            </Card>
          ) : current ? (
            <Card style={styles.questionCard}>
              <Text style={styles.zone}>{zoneLabel(current.zone)}</Text>
              <Text style={styles.prompt}>{current.prompt}</Text>
              <Text style={styles.help}>{current.help_text}</Text>

              <View style={styles.answers}>
                <Pressable
                  accessibilityRole="button"
                  style={[styles.answerButton, styles.yes]}
                  onPress={() => answer(true)}
                >
                  <Text style={styles.answerTextLight}>Yes</Text>
                </Pressable>
                <Pressable
                  accessibilityRole="button"
                  style={[styles.answerButton, styles.no]}
                  onPress={() => answer(false)}
                >
                  <Text style={styles.answerTextLight}>No</Text>
                </Pressable>
              </View>

              <Pressable
                accessibilityRole="button"
                style={(state) => [
                  styles.skipButton,
                  ((state as { hovered?: boolean }).hovered ?? false) && styles.skipButtonHover,
                  state.pressed && styles.skipButtonPressed,
                ]}
                onPress={() => setIndex((prev) => prev + 1)}
              >
                <Text style={styles.skipText}>Skip</Text>
              </Pressable>
            </Card>
          ) : null}

          {index > 0 && !done ? (
            <Button
              title="Back"
              variant="quiet"
              onPress={() => setIndex((prev) => Math.max(0, prev - 1))}
            />
          ) : null}
        </View>

        <Text style={styles.note}>
          Skipped questions do not count either way. We never assume a hazard you did not confirm.
        </Text>
      </ScrollView>
    </Screen>
  );
}

function zoneLabel(zone: string): string {
  switch (zone) {
    case '0-5ft':
      return 'The first five feet';
    case '5-30ft':
      return 'Five to thirty feet';
    case '30-100ft':
      return 'Thirty to a hundred feet';
    default:
      return 'The house itself';
  }
}

const styles = StyleSheet.create({
  content: {
    padding: spacing.lg,
    flexGrow: 1,
    maxWidth: 640,
    width: '100%',
    alignSelf: 'center',
  },
  padded: { padding: spacing.lg },
  progressRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  progressTrack: {
    flex: 1,
    height: 8,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceMuted,
    overflow: 'hidden',
  },
  progressFill: { height: '100%', backgroundColor: colors.accent, borderRadius: radius.pill },
  progressLabel: { ...type.label, color: colors.textMuted },
  // The question owns the middle of the screen; everything else keeps to the edges.
  stage: { flexGrow: 1, justifyContent: 'center', paddingVertical: spacing.lg },
  questionCard: { padding: spacing.lg, marginBottom: spacing.sm },
  zone: {
    ...type.overline,
    color: colors.textMuted,
  },
  prompt: { ...type.title, marginTop: spacing.sm },
  help: { ...type.body, color: colors.textMuted, marginTop: spacing.sm },
  body: { ...type.body, color: colors.textMuted, marginVertical: spacing.md },
  answers: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xl },
  answerButton: {
    flex: 1,
    minHeight: 68,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  yes: { backgroundColor: colors.critical },
  no: { backgroundColor: colors.accent },
  answerTextLight: { ...type.heading, color: colors.textInverse },
  skipButton: {
    marginTop: spacing.md,
    minHeight: 52,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.water,
  },
  skipButtonHover: { backgroundColor: '#194F5D' },
  skipButtonPressed: { opacity: 0.85 },
  skipText: { ...type.heading, color: colors.textInverse },
  note: { ...type.caption, color: colors.textMuted, textAlign: 'center' },
});
