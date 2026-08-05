/**
 * Settings: the account, the privacy promise, and the exit.
 *
 * Deliberately short. The one destructive action needs a typed word — a red button alone is one
 * mis-tap away from erasing somebody's photographs.
 */

import { useRouter } from 'expo-router';
import { useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput } from 'react-native';

import { api } from '@/api/client';
import { PrivacyNote } from '@/components/PrivacyNote';
import { Button, Card, ErrorNote, Screen } from '@/components/ui';
import { useCredentials, useSession } from '@/session';
import { colors, radius, spacing, type } from '@/theme';

export default function SettingsScreen() {
  const credentials = useCredentials();
  const { signOut, email, accountsEnabled } = useSession();
  const router = useRouter();

  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function leave() {
    await signOut();
    router.replace('/');
  }

  async function erase() {
    setBusy(true);
    setError(null);
    try {
      await api.deleteAccount(credentials);
      await leave();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete the account.');
      setBusy(false);
    }
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        {error ? <ErrorNote message={error} /> : null}

        <Card>
          <Text style={type.heading}>Account</Text>
          <Text style={styles.body}>
            {email ??
              (accountsEnabled
                ? 'Signed in.'
                : 'A private account on this device. No email, nothing shared.')}
          </Text>
        </Card>

        <PrivacyNote />

        <Card>
          <Text style={type.heading}>Sign out</Text>
          <Text style={styles.body}>Your properties and scans stay saved for next time.</Text>
          <Button title="Sign out" variant="secondary" onPress={leave} />
        </Card>

        <Card>
          <Text style={type.heading}>Delete everything</Text>
          <Text style={styles.body}>
            Removes your account, properties, scans, and every photo file. This cannot be undone.
            Type DELETE to confirm.
          </Text>
          <TextInput
            style={styles.input}
            value={confirm}
            onChangeText={setConfirm}
            placeholder="DELETE"
            autoCapitalize="characters"
            autoCorrect={false}
          />
          <Button
            title="Permanently delete my account"
            onPress={erase}
            disabled={confirm !== 'DELETE'}
            loading={busy}
          />
        </Card>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg },
  body: { ...type.body, color: colors.textMuted, marginVertical: spacing.sm },
  input: {
    ...type.body,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 4,
    marginBottom: spacing.sm,
    backgroundColor: colors.surface,
    color: colors.text,
  },
});
