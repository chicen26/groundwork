/**
 * Visual language.
 *
 * Two things drive the palette. Hazard severity has to read at a glance in bright sun, standing in
 * a yard — so those colours are saturated and high-contrast. Everything else stays quiet, because a
 * screen that shouts at a homeowner about their house is unpleasant to use and easy to distrust.
 */

export const colors = {
  background: '#FBFAF7',
  surface: '#FFFFFF',
  surfaceMuted: '#F1EFEA',
  border: '#E0DCD3',

  text: '#1C1B18',
  textMuted: '#5F5C55',
  textInverse: '#FFFFFF',

  // Fire severity. Reads in sunlight, and stays distinguishable to the most common forms of colour
  // blindness by pairing hue with a label — never colour alone.
  critical: '#B3261E',
  high: '#C5691B',
  moderate: '#8A6D1F',
  low: '#4A6B3A',

  // Water and rebate affordances, deliberately a different family from the fire palette.
  water: '#1F5F73',

  accent: '#2C5F2D',
  accentMuted: '#E3EDE1',

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
  sm: 6,
  md: 12,
  lg: 20,
  pill: 999,
} as const;

export const type = {
  display: { fontSize: 34, fontWeight: '700' as const, letterSpacing: -0.5 },
  title: { fontSize: 24, fontWeight: '700' as const, letterSpacing: -0.3 },
  heading: { fontSize: 18, fontWeight: '600' as const },
  body: { fontSize: 16, fontWeight: '400' as const, lineHeight: 23 },
  label: { fontSize: 14, fontWeight: '600' as const },
  caption: { fontSize: 13, fontWeight: '400' as const, lineHeight: 18 },
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
