/**
 * The ZIP quick look: what five digits can tell you, honestly framed.
 *
 * A ZIP centroid is one point standing in for square miles, so the card leads with the area name,
 * places the zone on the state's own risk scale, adds any live weather context, and carries a
 * banner saying a full address gets the real answer. The banner is not decoration — without it
 * this card would be quietly claiming a property-level result it does not have.
 */

import { useEffect, useRef, useState } from 'react';
import { Animated, StyleSheet, Text, View } from 'react-native';

import { api } from '@/api/client';
import type { FhszClass, ZipQuickLook } from '@/api/types';
import { AlertStrip } from '@/components/AlertStrip';
import { MiniMap } from '@/components/MiniMap';
import { RiskMeter } from '@/components/RiskMeter';
import { ZoneBadge } from '@/components/ui';
import { colors, radius, spacing, type } from '@/theme';

export function useZipQuickLook(zip: string | null) {
  const [result, setResult] = useState<ZipQuickLook | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSeq = useRef(0);

  useEffect(() => {
    if (!zip) {
      setResult(null);
      setError(null);
      setLoading(false);
      return;
    }
    const seq = ++requestSeq.current;
    setLoading(true);
    setError(null);
    api
      .zipQuickLook(zip)
      .then((look) => {
        if (seq === requestSeq.current) setResult(look);
      })
      .catch((e: Error) => {
        if (seq === requestSeq.current) setError(e.message);
      })
      .finally(() => {
        if (seq === requestSeq.current) setLoading(false);
      });
  }, [zip]);

  return { result, loading, error };
}

/** What each answer means for the person reading it — the sentence behind the badge. */
const ZONE_MEANING: Record<FhszClass, string> = {
  very_high:
    'Homes here carry the strictest defensible-space obligations in state law, and insurers pay close attention to this zone.',
  high: 'State law requires defensible space around homes here, and new draft rules would tighten the first five feet.',
  moderate:
    'Defensible-space law applies in this zone. Good preparation here is cheaper than in the higher zones.',
  non_wildland:
    'No mapped wildfire hazard zone at this point — water-wise landscaping and rebates are likely the bigger win.',
  unknown:
    'This point is outside the maps we host. A full address may still resolve — or sit outside California.',
};

export function ZipQuickLookCard({
  look,
  ctaHint,
}: {
  look: ZipQuickLook;
  /** What "more" looks like from where this card is shown, e.g. "Enter your full address above". */
  ctaHint: string;
}) {
  const place = look.place ? `${look.place}${look.state_code ? `, ${look.state_code}` : ''}` : null;

  // Arrive, don't appear: the card is the payoff of typing a ZIP, and easing it in reads as the
  // product thinking rather than a layout jump.
  const entrance = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(entrance, { toValue: 1, duration: 420, useNativeDriver: true }).start();
  }, [entrance]);

  return (
    <Animated.View
      style={[
        styles.card,
        {
          opacity: entrance,
          transform: [
            { translateY: entrance.interpolate({ inputRange: [0, 1], outputRange: [16, 0] }) },
          ],
        },
      ]}
    >
      <Text style={type.overline}>Quick look · ZIP {look.zip}</Text>
      {place ? <Text style={styles.place}>{place}</Text> : null}

      <MiniMap lat={look.lat} lng={look.lng} />

      <View style={styles.badgeRow}>
        <ZoneBadge fhsz={look.fhsz} />
      </View>

      <RiskMeter fhsz={look.fhsz} />

      <Text style={styles.meaning}>{ZONE_MEANING[look.fhsz]}</Text>
      {look.fhsz_source_version ? (
        <Text style={styles.source}>At this ZIP’s center point · {look.fhsz_source_version}</Text>
      ) : null}

      {/* Live weather context for the area, when the cached feeds have something to say. */}
      <AlertStrip lat={look.lat} lng={look.lng} />

      <View style={styles.factRow}>
        <Fact label="Fire district" value={look.fire_district} />
        <Fact label="Water utility" value={look.water_utility} />
      </View>

      <View style={styles.banner}>
        <Text style={styles.bannerBadge}>Approximate</Text>
        <Text style={styles.bannerText}>
          This is a rough snapshot of the area, not your property. {ctaHint} for your exact zone,
          local rules, and the rebates that apply to you.
        </Text>
      </View>
    </Animated.View>
  );
}

function Fact({ label, value }: { label: string; value: string | null }) {
  return (
    <View style={styles.fact}>
      <Text style={styles.factLabel}>{label}</Text>
      <Text style={value ? styles.factValue : styles.factUnknown}>
        {value ?? 'Needs your address'}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md + 4,
    gap: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
  },
  place: { ...type.title, color: colors.text },
  badgeRow: { flexDirection: 'row', marginTop: spacing.xs },
  meaning: { ...type.body, fontSize: 15, lineHeight: 22, color: colors.text },
  source: { ...type.caption, color: colors.textMuted },
  factRow: { flexDirection: 'row', gap: spacing.md, marginTop: spacing.xs },
  fact: { flex: 1, gap: 2 },
  factLabel: { ...type.caption, fontWeight: '600', color: colors.textMuted },
  factValue: { ...type.body, color: colors.text },
  factUnknown: { ...type.body, color: colors.textMuted, fontStyle: 'italic' },
  banner: {
    alignItems: 'flex-start',
    gap: spacing.sm,
    backgroundColor: colors.emberMuted,
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.sm,
  },
  bannerBadge: {
    ...type.overline,
    color: colors.ember,
    backgroundColor: colors.surface,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    overflow: 'hidden',
  },
  bannerText: { ...type.caption, color: colors.text },
});
