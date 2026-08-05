/**
 * Visual language.
 *
 * The palette is drawn from the product's own subject: evergreen for the plan, ember for fire,
 * river-teal for water, on warm paper. Hazard severity still has to read at a glance in bright
 * sun, standing in a yard — those colours stay saturated and high-contrast — while everything
 * else is calm, deep, and warm, because a screen that shouts at a homeowner about their house is
 * unpleasant to use and easy to distrust.
 *
 * Type is the brand: Fraunces, a warm soft serif, for anything display-sized — it reads like a
 * seed catalogue, not a dashboard — with the system sans for body text, where legibility on a
 * phone in a yard beats character. Custom families carry their own weight, so the display styles
 * set no fontWeight (Android would fake one badly).
 */

import { Platform, type TextStyle, type ViewStyle } from 'react-native';

export const fonts = {
  display: 'Fraunces_600SemiBold',
  displayBold: 'Fraunces_700Bold',
  displayBlack: 'Fraunces_900Black',
} as const;

export const colors = {
  // Cool sage-white, not beige: the light of a nursery greenhouse rather than old paper. Surfaces
  // are pure white so cards read crisp against it, the way current product sites carry color in
  // accents over a quiet, slightly-green field.
  background: '#F2F6EF',
  surface: '#FFFFFF',
  surfaceMuted: '#E7EEE2',
  border: '#DBE4D5',

  text: '#18201A',
  textMuted: '#5D685C',
  textInverse: '#F7FAF4',

  // The brand family: deep evergreen ink, a brighter leaf for accents on dark, warm ember, water.
  ink: '#22311F',
  inkDeep: '#16220F',
  leaf: '#9DC183',
  ember: '#C75B39',
  emberMuted: '#F7E4DA',

  // The dark hero surface and everything that has to read on it.
  heroTop: '#131F0E',
  heroBottom: '#2A3D20',
  cream: '#F5F1E6',
  creamMuted: 'rgba(245, 241, 230, 0.68)',
  creamFaint: 'rgba(245, 241, 230, 0.14)',
  emberBright: '#E2794E',
  waterBright: '#8FC3CE',

  // Fire severity. Reads in sunlight, and stays distinguishable to the most common forms of colour
  // blindness by pairing hue with a label — never colour alone.
  critical: '#B3261E',
  high: '#C05621',
  moderate: '#8A6D1F',
  low: '#4A6B3A',

  // Water and rebate affordances, deliberately a different family from the fire palette.
  water: '#146678',
  waterMuted: '#DDEEF2',

  accent: '#2C5A33',
  accentMuted: '#DEEDDA',

  // Draft regulations get their own treatment so "not law yet" is visible, not buried in a caption.
  draft: '#5B5391',
  draftMuted: '#ECEAF6',
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;

export const radius = {
  sm: 10,
  md: 16,
  lg: 24,
  pill: 999,
} as const;

export const type = {
  display: { fontSize: 42, fontFamily: fonts.display, letterSpacing: -0.8, lineHeight: 48 },
  title: { fontSize: 27, fontFamily: fonts.display, letterSpacing: -0.4, lineHeight: 33 },
  heading: { fontSize: 19, fontFamily: fonts.display, letterSpacing: -0.1, lineHeight: 25 },
  body: { fontSize: 16, fontWeight: '400' as const, lineHeight: 24 },
  label: { fontSize: 14, fontWeight: '600' as const },
  caption: { fontSize: 13, fontWeight: '400' as const, lineHeight: 18 },
  // Small-caps section markers: the quiet way to structure a screen without drawing boxes.
  overline: {
    fontSize: 12,
    fontWeight: '700' as const,
    letterSpacing: 1.4,
    textTransform: 'uppercase' as const,
  },
} as const satisfies Record<string, TextStyle>;

/**
 * Elevation. One soft, warm shadow — never a hard grey web-default — and `elevation` for Android.
 * On web the same tokens render via boxShadow, which react-native-web synthesises from these.
 */
export const shadow = {
  card: Platform.select<ViewStyle>({
    default: {
      shadowColor: '#22301F',
      shadowOffset: { width: 0, height: 6 },
      shadowOpacity: 0.07,
      shadowRadius: 16,
      elevation: 3,
    },
  }) as ViewStyle,
  raised: Platform.select<ViewStyle>({
    default: {
      shadowColor: '#22301F',
      shadowOffset: { width: 0, height: 10 },
      shadowOpacity: 0.13,
      shadowRadius: 24,
      elevation: 6,
    },
  }) as ViewStyle,
} as const;

export function severityColor(severity: string | null | undefined): string {
  switch (severity) {
    case 'critical':
      return colors.critical;
    case 'high':
      return colors.high;
    case 'moderate':
      return colors.moderate;
    default:
      return colors.low;
  }
}

/** Score bands. Deliberately not a smooth gradient: a band is easier to act on than a hue. */
export function scoreColor(score: number): string {
  if (score >= 80) return colors.low;
  if (score >= 60) return colors.moderate;
  if (score >= 40) return colors.high;
  return colors.critical;
}
