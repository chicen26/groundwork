/**
 * The risk meter: where a zone sits on the state's own scale, animated into place.
 *
 * Four bands, because CAL FIRE publishes four answers — this is a position on a legal scale, not
 * an invented score. The needle slides to its band on mount; motion draws the eye to the one fact
 * the quick look exists to deliver.
 */

import { useEffect, useRef } from 'react';
import { Animated, StyleSheet, Text, View } from 'react-native';

import type { FhszClass } from '@/api/types';
import { useT } from '@/i18n';
import { colors, radius, spacing, type } from '@/theme';

const BANDS: { key: FhszClass; label: string; color: string }[] = [
  { key: 'non_wildland', label: 'Non-wildland', color: colors.low },
  { key: 'moderate', label: 'Moderate', color: colors.moderate },
  { key: 'high', label: 'High', color: colors.high },
  { key: 'very_high', label: 'Very high', color: colors.critical },
];

export function RiskMeter({ fhsz }: { fhsz: FhszClass }) {
  const t = useT();
  const index = BANDS.findIndex((band) => band.key === fhsz);
  const progress = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.spring(progress, {
      toValue: index < 0 ? 0 : index,
      // Animating layout position, not opacity/transform-on-native — the driver must be JS.
      useNativeDriver: false,
      friction: 8,
      tension: 40,
      delay: 250,
    }).start();
  }, [index, progress]);

  // An unknown zone has no honest place on the scale; showing a needle anyway would invent one.
  if (index < 0) return null;

  const left = progress.interpolate({
    inputRange: [0, BANDS.length - 1],
    outputRange: ['1.5%', '89.5%'], // needle is 9% wide; keep its center over the band centers
  });

  return (
    <View style={styles.wrap}>
      <View style={styles.track}>
        {BANDS.map((band, i) => (
          <View
            key={band.key}
            style={[
              styles.band,
              { backgroundColor: band.color, opacity: i === index ? 1 : 0.22 },
              i === 0 && styles.bandFirst,
              i === BANDS.length - 1 && styles.bandLast,
            ]}
          />
        ))}
        <Animated.View style={[styles.needle, { left }]} />
      </View>
      <View style={styles.labels}>
        {BANDS.map((band, i) => (
          <Text
            key={band.key}
            style={[styles.label, i === index && { color: band.color, fontWeight: '800' }]}
            numberOfLines={1}
          >
            {t(band.label)}
          </Text>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 6, marginTop: spacing.xs },
  track: {
    flexDirection: 'row',
    gap: 3,
    height: 10,
    alignItems: 'center',
  },
  band: { flex: 1, height: 8, borderRadius: 2 },
  bandFirst: { borderTopLeftRadius: radius.pill, borderBottomLeftRadius: radius.pill },
  bandLast: { borderTopRightRadius: radius.pill, borderBottomRightRadius: radius.pill },
  needle: {
    position: 'absolute',
    width: '9%',
    height: 14,
    borderRadius: radius.pill,
    borderWidth: 2.5,
    borderColor: colors.ink,
    backgroundColor: colors.surface,
  },
  labels: { flexDirection: 'row', gap: 3 },
  label: { ...type.caption, fontSize: 10.5, flex: 1, textAlign: 'center', color: colors.textMuted },
});
