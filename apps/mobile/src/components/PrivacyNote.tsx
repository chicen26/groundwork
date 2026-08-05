/**
 * The privacy promise, in one breath, wherever data is being handed over.
 *
 * Each line here is backed by a test on the backend, which is the only reason it is allowed to
 * appear: metadata stripping (test_storage), private serving (test_scan_flow), hard delete
 * (test_account_deletion). A privacy note the code cannot prove would be decoration.
 */

import { StyleSheet, Text, View } from 'react-native';

import { useT } from '@/i18n';
import { colors, radius, spacing, type } from '@/theme';

export function PrivacyNote() {
  const t = useT();
  return (
    <View style={styles.note}>
      <Text style={styles.title}>🔒 {t('Your data stays yours')}</Text>
      <Text style={styles.body}>
        {t(
          'Photos are visible only to you, location data is stripped from them before upload, and deleting a property or your account erases the actual files, not just the records.',
        )}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  note: {
    backgroundColor: colors.surfaceMuted,
    borderRadius: radius.sm,
    padding: spacing.sm + 2,
    marginVertical: spacing.md,
  },
  title: { ...type.label, color: colors.text },
  body: { ...type.caption, color: colors.textMuted, marginTop: 2 },
});
