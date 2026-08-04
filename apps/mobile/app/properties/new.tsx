/**
 * Adding a property.
 *
 * The address is geocoded server-side. When that fails — the geocoder is down, or the address is
 * new enough not to be in the Census file — the screen says so in the geocoder's own words and
 * offers coordinates instead, rather than dead-ending someone who lives at a real address.
 */

import { useRouter } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, StyleSheet, Text, TextInput } from 'react-native';

import { ApiError, api } from '@/api/client';
import { Button, Card, ErrorNote, Screen } from '@/components/ui';
import { useCredentials } from '@/session';
import { colors, radius, spacing, type } from '@/theme';

export default function NewPropertyScreen() {
  const credentials = useCredentials();
  const router = useRouter();

  const [address, setAddress] = useState('');
  const [label, setLabel] = useState('');
  const [lat, setLat] = useState('');
  const [lng, setLng] = useState('');
  const [showCoordinates, setShowCoordinates] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const coordinates =
        showCoordinates && lat.trim() && lng.trim()
          ? { lat: Number(lat), lng: Number(lng) }
          : undefined;

      if (coordinates && (Number.isNaN(coordinates.lat) || Number.isNaN(coordinates.lng))) {
        setError('Those coordinates are not numbers. Latitude first, then longitude.');
        return;
      }

      const property = await api.createProperty(credentials, {
        address: address.trim(),
        label: label.trim() || undefined,
        ...coordinates,
      });
      router.replace(`/properties/${property.id}`);
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Could not save that property.';
      setError(message);
      // A geocoding failure is the one case where there is a next step, so offer it directly.
      if (e instanceof ApiError && e.status === 422) {
        setShowCoordinates(true);
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <Screen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}
      >
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          {error ? <ErrorNote message={error} /> : null}

          <Card>
            <Text style={type.label}>Address</Text>
            <TextInput
              style={styles.input}
              value={address}
              onChangeText={setAddress}
              placeholder="123 Diablo Road, Danville, CA"
              autoCapitalize="words"
              autoCorrect={false}
              returnKeyType="next"
            />

            <Text style={[type.label, styles.spaced]}>Name it (optional)</Text>
            <TextInput
              style={styles.input}
              value={label}
              onChangeText={setLabel}
              placeholder="Home"
              autoCapitalize="words"
            />
          </Card>

          {showCoordinates ? (
            <Card>
              <Text style={type.heading}>Place it yourself</Text>
              <Text style={styles.help}>
                We could not look that address up. Enter the coordinates instead — your phone&apos;s
                map app can copy them from a dropped pin.
              </Text>
              <TextInput
                style={styles.input}
                value={lat}
                onChangeText={setLat}
                placeholder="Latitude, e.g. 37.8216"
                keyboardType="numbers-and-punctuation"
              />
              <TextInput
                style={[styles.input, styles.spaced]}
                value={lng}
                onChangeText={setLng}
                placeholder="Longitude, e.g. -121.9999"
                keyboardType="numbers-and-punctuation"
              />
            </Card>
          ) : null}

          <Button
            title="Look up my zone"
            onPress={save}
            loading={saving}
            disabled={address.trim().length < 4}
          />

          {!showCoordinates ? (
            <Button
              title="Enter coordinates instead"
              variant="quiet"
              onPress={() => setShowCoordinates(true)}
            />
          ) : null}
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: { padding: spacing.lg, gap: spacing.sm },
  input: {
    ...type.body,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 4,
    marginTop: spacing.xs,
    backgroundColor: colors.surface,
    color: colors.text,
  },
  spaced: { marginTop: spacing.md },
  help: { ...type.caption, color: colors.textMuted, marginVertical: spacing.sm },
});
