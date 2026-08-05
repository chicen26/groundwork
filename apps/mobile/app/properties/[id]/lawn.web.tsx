/**
 * Web fallback for lawn measurement.
 *
 * The satellite drawing tool needs the native map component, so on the web this screen is honest
 * about that and still useful: it shows every rebate programme's real rates, caps, and minimums
 * from the same config the calculator uses, plus the pre-approval warning.
 */

import { useEffect, useState } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { API_BASE_URL } from '@/api/client';
import { Card, ErrorNote, Loading, Screen } from '@/components/ui';
import { colors, radius, spacing, type } from '@/theme';

interface Program {
  key: string;
  agency: string;
  agency_full: string;
  name: string;
  rate_per_sqft: string;
  cap_usd: string;
  minimum_sqft: number;
  url: string;
}

export default function LawnWebScreen() {
  const [programs, setPrograms] = useState<Program[] | null>(null);
  const [warning, setWarning] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_BASE_URL}/v1/programs/rebates`)
      .then((r) => r.json())
      .then((body) => {
        setPrograms(body.programs);
        setWarning(body.warning);
      })
      .catch(() => setError('Could not load the rebate programmes.'));
  }, []);

  if (error) {
    return (
      <Screen style={styles.padded}>
        <ErrorNote message={error} />
      </Screen>
    );
  }
  if (!programs) return <Loading label="Loading rebate programmes" />;

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.warningBox}>
          <Text style={styles.warningTitle}>Apply before you dig</Text>
          <Text style={styles.warningBody}>{warning}</Text>
        </View>

        <Text style={styles.note}>
          Measuring your lawn by outlining it on satellite needs the phone app. The programmes and
          their real rates are below — a 1,000 sq ft lawn is worth $1,000–$2,000 depending on your
          utility.
        </Text>

        {programs.map((program) => (
          <Card key={program.key}>
            <Text style={type.label}>{program.agency_full}</Text>
            <Text style={styles.rate}>
              ${program.rate_per_sqft}/sq ft, up to ${Number(program.cap_usd).toLocaleString()}
            </Text>
            <Text style={styles.min}>Minimum {program.minimum_sqft} sq ft converted</Text>
            <Pressable onPress={() => Linking.openURL(program.url)}>
              <Text style={styles.link}>Open {program.agency}&apos;s application page →</Text>
            </Pressable>
          </Card>
        ))}
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg, maxWidth: 720, width: '100%', alignSelf: 'center' },
  padded: { padding: spacing.lg },
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
  note: { ...type.body, color: colors.textMuted, marginBottom: spacing.md },
  rate: { ...type.title, color: colors.water, marginTop: spacing.xs },
  min: { ...type.caption, color: colors.textMuted, marginTop: spacing.xs },
  link: { ...type.label, color: colors.accent, marginTop: spacing.md },
});
