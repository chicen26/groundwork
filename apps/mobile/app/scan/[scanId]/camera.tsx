/**
 * Photographing one station.
 *
 * The framing hint stays on screen while the camera is live, because a photo taken from the wrong
 * distance is the commonest way a scan produces nothing useful — and the person holding the phone
 * cannot read instructions they left on the previous screen.
 *
 * Uploads return as soon as the photo is stored. Inference is queued, so nobody stands in their
 * driveway watching a spinner.
 */

import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useRef, useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { api } from '@/api/client';
import type { Station } from '@/api/types';
import { STATION_HINTS, STATION_LABELS } from '@/api/types';
import { Button, ErrorNote, Screen } from '@/components/ui';
import { useCredentials } from '@/session';
import { colors, radius, spacing, type } from '@/theme';

export default function CameraScreen() {
  const { scanId, station } = useLocalSearchParams<{ scanId: string; station: Station }>();
  const credentials = useCredentials();
  const router = useRouter();
  const insets = useSafeAreaInsets();

  const cameraRef = useRef<CameraView>(null);
  const [permission, requestPermission] = useCameraPermissions();
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function upload(uri: string) {
    if (!scanId || !station) return;
    setUploading(true);
    setError(null);
    try {
      await api.uploadPhoto(credentials, scanId, station, uri);
      router.back();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'That photo would not upload.');
    } finally {
      setUploading(false);
    }
  }

  async function capture() {
    const photo = await cameraRef.current?.takePictureAsync();
    if (photo?.uri) await upload(photo.uri);
  }

  /** Some hazards are easier to photograph in better light, or were captured earlier. */
  async function pickFromLibrary() {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.9,
    });
    if (!result.canceled && result.assets[0]?.uri) {
      await upload(result.assets[0].uri);
    }
  }

  if (!permission) {
    return <Screen />;
  }

  if (!permission.granted) {
    return (
      <Screen style={styles.permission}>
        <Text style={type.title}>Camera access</Text>
        <Text style={styles.permissionBody}>
          Groundwork needs the camera to photograph your property. Photos stay private to your
          account, and their location metadata is stripped before they leave your phone&apos;s
          upload.
        </Text>
        <Button title="Allow camera" onPress={requestPermission} />
        <Button title="Choose from library instead" variant="secondary" onPress={pickFromLibrary} />
        <Button title="Back" variant="quiet" onPress={() => router.back()} />
      </Screen>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView ref={cameraRef} style={styles.camera} facing="back" />

      <View style={[styles.header, { paddingTop: insets.top + spacing.sm }]}>
        <Text style={styles.stationName}>{station ? STATION_LABELS[station] : 'Photograph'}</Text>
        <Text style={styles.stationHint}>{station ? STATION_HINTS[station] : ''}</Text>
      </View>

      <View style={[styles.controls, { paddingBottom: insets.bottom + spacing.lg }]}>
        {error ? <ErrorNote message={error} /> : null}

        <View style={styles.controlRow}>
          <Pressable onPress={() => router.back()} style={styles.sideButton}>
            <Text style={styles.sideButtonText}>Cancel</Text>
          </Pressable>

          <Pressable
            onPress={capture}
            disabled={uploading}
            accessibilityRole="button"
            accessibilityLabel="Take photo"
            style={[styles.shutter, uploading && styles.shutterBusy]}
          >
            <View style={styles.shutterInner} />
          </Pressable>

          <Pressable onPress={pickFromLibrary} style={styles.sideButton}>
            <Text style={styles.sideButtonText}>Library</Text>
          </Pressable>
        </View>

        <Text style={styles.uploadNote}>
          {uploading ? 'Uploading…' : 'We look at the photo after it uploads — no waiting.'}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  camera: { ...StyleSheet.absoluteFill },
  header: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    backgroundColor: 'rgba(0,0,0,0.55)',
  },
  stationName: { ...type.heading, color: '#FFF' },
  stationHint: { ...type.caption, color: 'rgba(255,255,255,0.85)', marginTop: spacing.xs },
  controls: {
    marginTop: 'auto',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    backgroundColor: 'rgba(0,0,0,0.55)',
  },
  controlRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sideButton: { padding: spacing.md, minWidth: 76 },
  sideButtonText: { ...type.label, color: '#FFF', textAlign: 'center' },
  shutter: {
    width: 74,
    height: 74,
    borderRadius: radius.pill,
    borderWidth: 4,
    borderColor: '#FFF',
    alignItems: 'center',
    justifyContent: 'center',
  },
  shutterBusy: { opacity: 0.5 },
  shutterInner: {
    width: 58,
    height: 58,
    borderRadius: radius.pill,
    backgroundColor: '#FFF',
  },
  uploadNote: {
    ...type.caption,
    color: 'rgba(255,255,255,0.8)',
    textAlign: 'center',
    marginTop: spacing.sm,
  },
  permission: { padding: spacing.lg, justifyContent: 'center', gap: spacing.md },
  permissionBody: { ...type.body, color: colors.textMuted },
});
