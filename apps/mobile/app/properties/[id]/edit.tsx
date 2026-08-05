/**
 * Edit a property: rename, move, or remove it.
 *
 * Moving re-runs the whole zone lookup, because a moved property is a different property as far as
 * the law is concerned — the screen says so rather than silently changing someone's obligations.
 */

import { useLocalSearchParams, useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput } from 'react-native';

import { api } from '@/api/client';
import { Button, Card, ErrorNote, Screen } from '@/components/ui';
import { useCredentials } from '@/session';
import { colors, radius, spacing, type } from '@/theme';

export default function EditPropertyScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const credentials = useCredentials();
  const router = useRouter();

  const [label, setLabel] = useState('');
  const [address, setAddress] = useState('');
  const [initialAddress, setInitialAddress] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);

  useEffect(() => {
    if (!id) return;
    api
      .getProperty(credentials, id)
      .then((p) => {
        setLabel(p.label ?? '');
        setAddress(p.address);
        setInitialAddress(p.address);
      })
      .catch((e: Error) => setError(e.message));
  }, [credentials, id]);

  async function save() {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      const moved = address.trim() !== initialAddress;
      await api.updateProperty(credentials, id, {
        label: label.trim() || undefined,
        ...(moved ? { address: address.trim() } : {}),
      });
      router.back();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save.');
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!id) return;
    setBusy(true);
    try {
      await api.deleteProperty(credentials, id);
      router.replace('/');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not delete.');
      setBusy(false);
    }
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        {error ? <ErrorNote message={error} /> : null}

        <Card>
          <Text style={type.label}>Name</Text>
          <TextInput
            style={styles.input}
            value={label}
            onChangeText={setLabel}
            placeholder="Home"
          />

          <Text style={[type.label, styles.spaced]}>Address</Text>
          <TextInput
            style={styles.input}
            value={address}
            onChangeText={setAddress}
            autoCapitalize="words"
            autoCorrect={false}
          />
          {address.trim() !== initialAddress ? (
            <Text style={styles.note}>
              Changing the address looks up the fire zone again; the rules that apply can change
              with it.
            </Text>
          ) : null}

          <Button title="Save" onPress={save} loading={busy} />
        </Card>

        <Card>
          <Text style={type.heading}>Remove this property</Text>
          <Text style={styles.note}>Deletes its scans and photo files too. Cannot be undone.</Text>
          {confirmingDelete ? (
            <Button title="Yes, delete it all" onPress={remove} loading={busy} />
          ) : (
            <Button
              title="Delete property"
              variant="secondary"
              onPress={() => setConfirmingDelete(true)}
            />
          )}
        </Card>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg },
  input: {
    ...type.body,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 4,
    marginTop: spacing.xs,
    marginBottom: spacing.sm,
    backgroundColor: colors.surface,
    color: colors.text,
  },
  spaced: { marginTop: spacing.sm },
  note: { ...type.caption, color: colors.textMuted, marginVertical: spacing.sm },
});
