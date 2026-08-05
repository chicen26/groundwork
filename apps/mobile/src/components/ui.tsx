/**
 * The small set of components every screen is built from.
 *
 * `LegalStatusBadge` is the one worth reading closely: whenever a requirement appears on screen, it
 * has to say whether it is law today, a draft, or advice. That distinction is the product's central
 * honesty claim, so it lives in a component rather than in each screen's discretion.
 */

import { ActivityIndicator, Pressable, StyleSheet, Text, View, ViewStyle } from 'react-native';

import type { FhszClass, RuleStatus } from '@/api/types';
import { FHSZ_LABELS } from '@/api/types';
import { colors, radius, shadow, spacing, type } from '@/theme';

export function Screen({ children, style }: { children?: React.ReactNode; style?: ViewStyle }) {
  return <View style={[styles.screen, style]}>{children}</View>;
}

export function Card({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Button({
  title,
  onPress,
  variant = 'primary',
  disabled,
  loading,
}: {
  title: string;
  onPress: () => void;
  variant?: 'primary' | 'secondary' | 'quiet';
  disabled?: boolean;
  loading?: boolean;
}) {
  const isPrimary = variant === 'primary';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: disabled || loading }}
      onPress={onPress}
      disabled={disabled || loading}
      style={(state) => {
        // The web adds a hover flag native platforms never set; feeling alive under the cursor
        // is half of what makes a button read as a button in a browser.
        const hovered = (state as { hovered?: boolean }).hovered ?? false;
        return [
          styles.button,
          isPrimary && styles.buttonPrimary,
          variant === 'secondary' && styles.buttonSecondary,
          variant === 'quiet' && styles.buttonQuiet,
          hovered && isPrimary && styles.buttonPrimaryHover,
          hovered && variant === 'secondary' && styles.buttonSecondaryHover,
          hovered && variant === 'quiet' && styles.buttonQuietHover,
          (disabled || loading) && styles.buttonDisabled,
          state.pressed && styles.buttonPressed,
        ];
      }}
    >
      {loading ? (
        <ActivityIndicator color={isPrimary ? colors.textInverse : colors.text} />
      ) : (
        <Text
          style={[
            styles.buttonText,
            isPrimary && styles.buttonTextPrimary,
            variant === 'quiet' && styles.buttonTextQuiet,
          ]}
        >
          {title}
        </Text>
      )}
    </Pressable>
  );
}

/**
 * Says whether a requirement is law, a draft, or advice.
 *
 * Zone 0 has not been adopted. Showing one of its items without this badge would tell a homeowner
 * they are breaking a rule that does not exist yet.
 */
export function LegalStatusBadge({ status }: { status: RuleStatus | null }) {
  if (!status) return null;

  const config: Record<RuleStatus, { label: string; bg: string; fg: string }> = {
    in_effect: {
      label: 'Required now',
      bg: colors.accentMuted,
      fg: colors.accent,
    },
    pending_adoption: {
      label: 'Proposed, not yet law',
      bg: colors.draftMuted,
      fg: colors.draft,
    },
    advisory: {
      label: 'Recommended',
      bg: colors.surfaceMuted,
      fg: colors.textMuted,
    },
  };
  const { label, bg, fg } = config[status];

  return (
    <View style={[styles.badge, { backgroundColor: bg }]}>
      <Text style={[styles.badgeText, { color: fg }]}>{label}</Text>
    </View>
  );
}

export function ZoneBadge({ fhsz }: { fhsz: FhszClass }) {
  const tone: Record<FhszClass, { fg: string; bg: string }> = {
    very_high: { fg: colors.critical, bg: '#F9E4E2' },
    high: { fg: colors.high, bg: '#F8E8DC' },
    moderate: { fg: colors.moderate, bg: '#F3EBD5' },
    non_wildland: { fg: colors.low, bg: colors.accentMuted },
    unknown: { fg: colors.textMuted, bg: colors.surfaceMuted },
  };
  const { fg, bg } = tone[fhsz];
  return (
    <View style={[styles.zoneBadge, { backgroundColor: bg }]}>
      <View style={[styles.zoneDot, { backgroundColor: fg }]} />
      <Text style={[styles.zoneBadgeText, { color: fg }]}>
        {FHSZ_LABELS[fhsz]} fire hazard zone
      </Text>
    </View>
  );
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <View style={styles.centred}>
      <ActivityIndicator color={colors.accent} />
      <Text style={styles.mutedText}>{label}</Text>
    </View>
  );
}

/**
 * An error the user can act on.
 *
 * Shows the server's own words. "Could not locate that address, place it on the map instead" tells
 * someone what to do next; a generic failure message does not.
 */
export function ErrorNote({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <View style={styles.errorNote}>
      <Text style={styles.errorText}>{message}</Text>
      {onRetry ? <Button title="Try again" variant="secondary" onPress={onRetry} /> : null}
    </View>
  );
}

/** The disclaimer, wherever a score or plan is shown. Never optional. */
export function Disclaimer({ text }: { text: string }) {
  return <Text style={styles.disclaimer}>{text}</Text>;
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.background,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radius.lg,
    padding: spacing.md + 4,
    marginBottom: spacing.md,
    ...shadow.card,
  },
  button: {
    minHeight: 54,
    borderRadius: radius.pill,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
    borderWidth: 1.5,
    borderColor: colors.border,
    backgroundColor: colors.surface,
  },
  buttonPrimary: {
    backgroundColor: colors.ink,
    borderColor: colors.ink,
    ...shadow.raised,
  },
  buttonSecondary: {
    backgroundColor: colors.surface,
    borderColor: colors.ink,
  },
  buttonQuiet: {
    backgroundColor: 'transparent',
    borderColor: 'transparent',
    minHeight: 40,
  },
  buttonPrimaryHover: { backgroundColor: colors.accent, borderColor: colors.accent },
  buttonSecondaryHover: { backgroundColor: colors.accentMuted },
  buttonQuietHover: { backgroundColor: colors.surfaceMuted },
  buttonDisabled: { opacity: 0.45 },
  buttonPressed: { opacity: 0.85, transform: [{ scale: 0.99 }] },
  buttonText: { ...type.label, fontSize: 16, color: colors.ink },
  buttonTextPrimary: { color: colors.textInverse },
  buttonTextQuiet: { color: colors.textMuted },
  badge: {
    alignSelf: 'flex-start',
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm + 4,
    paddingVertical: 4,
  },
  badgeText: { fontSize: 12, fontWeight: '700', letterSpacing: 0.2 },
  zoneBadge: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    flexShrink: 1,
    gap: 6,
    borderRadius: radius.pill,
    paddingHorizontal: spacing.sm + 4,
    paddingVertical: 5,
  },
  zoneDot: { width: 8, height: 8, borderRadius: 4 },
  zoneBadgeText: { fontSize: 13, fontWeight: '700', flexShrink: 1 },
  centred: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.sm,
  },
  mutedText: { ...type.caption, color: colors.textMuted },
  errorNote: {
    backgroundColor: '#FBEAE7',
    borderLeftWidth: 4,
    borderLeftColor: colors.critical,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
    marginBottom: spacing.md,
  },
  errorText: { ...type.body, color: colors.critical },
  disclaimer: {
    ...type.caption,
    color: colors.textMuted,
    marginTop: spacing.lg,
    marginBottom: spacing.xl,
  },
});
