/**
 * The context strip.
 *
 * One line, no map, nothing operational. It renders only when we have current information and there
 * is something to say — an unavailable feed shows nothing at all rather than an "all clear" nobody
 * verified.
 *
 * A failure here is swallowed on purpose. The weather is context; it must never stop someone
 * scanning their yard.
 */

import { useEffect, useState } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import type { AlertStrip as Strip } from '@/api/types';
import { colors, radius, spacing, type } from '@/theme';

export function AlertStrip({ lat, lng }: { lat: number; lng: number }) {
  const [strip, setStrip] = useState<Strip | null>(null);

  useEffect(() => {
    let active = true;
    api
      .alerts(lat, lng)
      .then((result) => {
        if (active) setStrip(result);
      })
      .catch(() => {
        // Context only. If the feed is unreachable the strip simply does not appear.
      });
    return () => {
      active = false;
    };
  }, [lat, lng]);

  // No data, or nothing worth saying. Both render nothing — an empty strip would read as an
  // all-clear we have not earned.
  if (!strip?.available || (!strip.red_flag && strip.events.length === 0)) {
    return null;
  }

  return (
    <View style={[styles.strip, strip.red_flag && styles.stripRedFlag]}>
      <Text style={[styles.headline, strip.red_flag && styles.headlineRedFlag]}>
        {strip.headline ?? strip.events.join(' · ')}
      </Text>
      <Text style={styles.note}>{strip.note}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  strip: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.sm,
    padding: spacing.sm + 2,
    marginBottom: spacing.md,
  },
  stripRedFlag: {
    backgroundColor: '#FDECEA',
    borderLeftWidth: 4,
    borderLeftColor: colors.critical,
  },
  headline: { ...type.label, color: colors.text },
  headlineRedFlag: { color: colors.critical },
  note: { ...type.caption, color: colors.textMuted, marginTop: 2 },
});
