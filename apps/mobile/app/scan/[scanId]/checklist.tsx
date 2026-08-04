/**
 * The questions a photograph cannot answer.
 *
 * Not a fallback for a weak model — half the input. Every question maps to a rule, and answers are
 * saved as you go so a half-finished checklist is still worth something.
 *
 * "Yes" always means the hazard is present, matching how the engine reads it. No polarity to get
 * backwards between the screen and the score.
 */

import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import type { Question } from '@/api/types';
import { STATION_LABELS } from '@/api/types';
import { Button, Card, ErrorNote, Loading, Screen } from '@/components/ui';
import { useCredentials } from '@/session';
import { colors, radius, spacing, type } from '@/theme';

export default function ChecklistScreen() {
  const { scanId } = useLocalSearchParams<{ scanId: string }>();
  const credentials = useCredentials();
  const router = useRouter();

  const [questions, setQuestions] = useState<Question[] | null>(null);
  const [answers, setAnswers] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .getChecklist(credentials)
      .then(setQuestions)
      .catch((e: Error) => setError(e.message));
  }, [credentials]);

  async function answer(questionId: string, hazardPresent: boolean) {
    if (!scanId) return;
    setAnswers((current) => ({ ...current, [questionId]: hazardPresent }));
    try {
      // Saved one at a time: a checklist abandoned halfway should still count for what was answered.
      await api.submitChecklist(credentials, scanId, [
        { question_id: questionId, hazard_present: hazardPresent },
      ]);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'That answer did not save.');
      setAnswers((current) => {
        const next = { ...current };
        delete next[questionId];
        return next;
      });
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

  const grouped = questions.reduce<Record<string, Question[]>>((acc, question) => {
    (acc[question.station] ??= []).push(question);
    return acc;
  }, {});

  const answered = Object.keys(answers).length;

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        {error ? <ErrorNote message={error} /> : null}
        <Text style={styles.progress}>
          {answered} of {questions.length} answered
        </Text>

        {Object.entries(grouped).map(([station, group]) => (
          <View key={station}>
            <Text style={styles.stationHeading}>
              {STATION_LABELS[station as keyof typeof STATION_LABELS] ?? station}
            </Text>
            {group.map((question) => {
              const value = answers[question.id];
              return (
                <Card key={question.id}>
                  <Text style={type.body}>{question.prompt}</Text>
                  <Text style={styles.help}>{question.help_text}</Text>
                  <View style={styles.answerRow}>
                    <Choice
                      label="Yes"
                      selected={value === true}
                      tone={colors.critical}
                      onPress={() => answer(question.id, true)}
                    />
                    <Choice
                      label="No"
                      selected={value === false}
                      tone={colors.accent}
                      onPress={() => answer(question.id, false)}
                    />
                  </View>
                </Card>
              );
            })}
          </View>
        ))}

        <Button
          title="Done for now"
          onPress={() => router.back()}
          loading={saving}
          variant="secondary"
        />
        <Text style={styles.note}>
          Answers save as you go. You can leave anything you are unsure about and come back.
        </Text>
      </ScrollView>
    </Screen>
  );
}

function Choice({
  label,
  selected,
  tone,
  onPress,
}: {
  label: string;
  selected: boolean;
  tone: string;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[
        styles.choice,
        selected && { backgroundColor: tone, borderColor: tone },
      ]}
    >
      <Text style={[styles.choiceText, selected && styles.choiceTextSelected]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg },
  padded: { padding: spacing.lg },
  progress: { ...type.label, color: colors.textMuted, marginBottom: spacing.md },
  stationHeading: {
    ...type.label,
    color: colors.textMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    marginBottom: spacing.sm,
    marginTop: spacing.sm,
  },
  help: { ...type.caption, color: colors.textMuted, marginTop: spacing.xs },
  answerRow: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
  choice: {
    flex: 1,
    minHeight: 46,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: colors.surface,
  },
  choiceText: { ...type.label, color: colors.text },
  choiceTextSelected: { color: colors.textInverse },
  note: { ...type.caption, color: colors.textMuted, marginTop: spacing.md },
});
