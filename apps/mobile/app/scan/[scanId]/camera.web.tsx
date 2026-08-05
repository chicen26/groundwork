/**
 * Web fallback for a station photograph: a file picker instead of a live camera.
 *
 * On the web, expo-image-picker is a plain file input, which is exactly right — people testing from
 * a laptop usually have the photos already. The framing hint still shows, because a photo taken
 * from the wrong distance is still the commonest way a scan produces nothing useful.
 */

import * as ImagePicker from 'expo-image-picker';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useState } from 'react';
import { ScrollView, StyleSheet, Text } from 'react-native';

import { api } from '@/api/client';
import type { Station } from '@/api/types';
import { STATION_HINTS, STATION_LABELS } from '@/api/types';
import { Button, Card, ErrorNote, Screen } from '@/components/ui';
import { useCredentials } from '@/session';
import { colors, spacing, type } from '@/theme';

export default function CameraWebScreen() {
  const { scanId, station } = useLocalSearchParams<{ scanId: string; station: Station }>();
  const credentials = useCredentials();
  const router = useRouter();

  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function pick() {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.9,
    });
    if (result.canceled || !result.assets[0]?.uri || !scanId || !station) return;

    setUploading(true);
    setError(null);
    try {
      await api.uploadPhoto(credentials, scanId, station, result.assets[0].uri);
      router.back();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'That photo would not upload.');
    } finally {
      setUploading(false);
    }
  }

  return (
    <Screen>
      <ScrollView contentContainerStyle={styles.content}>
        {error ? <ErrorNote message={error} /> : null}
        <Card>
          <Text style={type.title}>{station ? STATION_LABELS[station] : 'Photograph'}</Text>
          <Text style={styles.hint}>{station ? STATION_HINTS[station] : ''}</Text>
          <Text style={styles.note}>
            On the web you upload a photo you already have; the live camera is in the phone app.
            Location data is stripped from the file on upload either way.
          </Text>
          <Button title="Choose a photo" onPress={pick} loading={uploading} />
          <Button title="Back" variant="quiet" onPress={() => router.back()} />
        </Card>
      </ScrollView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: { padding: spacing.lg, maxWidth: 720, width: '100%', alignSelf: 'center' },
  hint: { ...type.body, color: colors.textMuted, marginTop: spacing.sm },
  note: { ...type.caption, color: colors.textMuted, marginVertical: spacing.md },
});
