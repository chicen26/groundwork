/**
 * Adding a property.
 *
 * The address field completes as you type; picking a suggestion also pins the coordinates, so the
 * property can be created even if the geocoder is down. Typing only a ZIP code gets an honest
 * quick look at the area with a banner pointing at the full-address path. And when server-side
 * geocoding fails anyway, the screen says so in the geocoder's own words and offers coordinates
 * instead, rather than dead-ending someone who lives at a real address.
 */

import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
} from 'react-native';

import { ApiError, api } from '@/api/client';
import type { AddressSuggestion } from '@/api/types';
import { AddressAutocomplete } from '@/components/AddressAutocomplete';
import { Button, Card, ErrorNote, Screen } from '@/components/ui';
import { ZipQuickLookCard, useZipQuickLook } from '@/components/ZipQuickLook';
import { useCredentials } from '@/session';
import { colors, radius, spacing, type } from '@/theme';

export default function NewPropertyScreen() {
  const credentials = useCredentials();
  const router = useRouter();

  const [address, setAddress] = useState('');
  const [label, setLabel] = useState('');
  const [picked, setPicked] = useState<AddressSuggestion | null>(null);
  const [lat, setLat] = useState('');
  const [lng, setLng] = useState('');
  const [showCoordinates, setShowCoordinates] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Five digits alone is not an address — it is a question we can partly answer right here.
  const [zip, setZip] = useState<string | null>(null);
  const trimmed = address.trim();
  useEffect(() => {
    const isZip = /^\d{5}$/.test(trimmed);
    const timer = setTimeout(() => setZip(isZip ? trimmed : null), 400);
    return () => clearTimeout(timer);
  }, [trimmed]);
  const quickLook = useZipQuickLook(zip);

  async function save() {
    setSaving(true);
    setError(null);
    try {
      // Coordinates, by descending trust: ones the user typed, then ones a picked suggestion
      // carried. Either way the server skips geocoding entirely.
      const manual =
        showCoordinates && lat.trim() && lng.trim()
          ? { lat: Number(lat), lng: Number(lng) }
          : undefined;
      if (manual && (Number.isNaN(manual.lat) || Number.isNaN(manual.lng))) {
        setError('Those coordinates are not numbers. Latitude first, then longitude.');
        return;
      }
      const pinned =
        picked && picked.label === trimmed ? { lat: picked.lat, lng: picked.lng } : undefined;

      const property = await api.createProperty(credentials, {
        address: trimmed,
        label: label.trim() || undefined,
        ...(manual ?? pinned),
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

  const zipOnly = zip !== null;

  return (
    <Screen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}
      >
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          {error ? <ErrorNote message={error} /> : null}

          <Card style={styles.addressCard}>
            <Text style={type.overline}>Where is it?</Text>
            <Text style={[type.label, styles.spaced]}>Address or ZIP code</Text>
            <AddressAutocomplete
              value={address}
              onChangeText={(text) => {
                setAddress(text);
                if (picked && text.trim() !== picked.label) setPicked(null);
              }}
              onSelect={setPicked}
              placeholder="123 Diablo Road, Danville, CA"
            />
            <Text style={styles.help}>
              Start typing and pick your address, or enter just a ZIP for a quick look.
            </Text>

            <Text style={[type.label, styles.spaced]}>Name it (optional)</Text>
            <TextInput
              style={styles.input}
              value={label}
              onChangeText={setLabel}
              placeholder="Home"
              placeholderTextColor={colors.textMuted}
              autoCapitalize="words"
            />
          </Card>

          {zipOnly && quickLook.result ? (
            <ZipQuickLookCard look={quickLook.result} ctaHint="Enter your full address above" />
          ) : null}
          {zipOnly && quickLook.loading ? (
            <Text style={styles.help}>Taking a quick look at {zip}…</Text>
          ) : null}
          {zipOnly && quickLook.error ? <Text style={styles.help}>{quickLook.error}</Text> : null}

          {showCoordinates ? (
            <Card>
              <Text style={type.heading}>Place it yourself</Text>
              <Text style={styles.help}>
                We could not look that address up. Enter the coordinates instead; your phone&apos;s
                map app can copy them from a dropped pin.
              </Text>
              <TextInput
                style={styles.input}
                value={lat}
                onChangeText={setLat}
                placeholder="Latitude, e.g. 37.8216"
                placeholderTextColor={colors.textMuted}
                keyboardType="numbers-and-punctuation"
              />
              <TextInput
                style={[styles.input, styles.spaced]}
                value={lng}
                onChangeText={setLng}
                placeholder="Longitude, e.g. -121.9999"
                placeholderTextColor={colors.textMuted}
                keyboardType="numbers-and-punctuation"
              />
            </Card>
          ) : null}

          <Button
            title="Look up my zone"
            onPress={save}
            loading={saving}
            disabled={trimmed.length < 4 || zipOnly}
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
  // The suggestion dropdown overflows this card; without visible overflow it would be clipped.
  addressCard: { overflow: 'visible', zIndex: 10 },
  input: {
    ...type.body,
    borderWidth: 1.5,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 6,
    marginTop: spacing.xs,
    backgroundColor: colors.surface,
    color: colors.text,
  },
  spaced: { marginTop: spacing.md },
  help: {
    ...type.caption,
    color: colors.textMuted,
    marginVertical: spacing.sm,
  },
});
