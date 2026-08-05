/**
 * Sign in / create an account.
 *
 * One screen, two verbs — flipping between them keeps whatever was typed. Only reachable when
 * Supabase is configured; the welcome screen's instant-start path covers development, where an
 * account would be a gate with nothing behind it.
 */

import { useRouter } from 'expo-router';
import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
} from 'react-native';

import { BrandMark } from '@/components/BrandMark';
import { Button, Card, ErrorNote, Screen } from '@/components/ui';
import { useT } from '@/i18n';
import { useSession } from '@/session';
import { colors, radius, spacing, type } from '@/theme';

export default function SignInScreen() {
  const t = useT();
  const { signInWithPassword, signUpWithPassword } = useSession();
  const router = useRouter();

  const [mode, setMode] = useState<'signin' | 'signup'>('signin');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const ready = email.includes('@') && password.length >= 8;

  async function submit() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      if (mode === 'signin') {
        await signInWithPassword(email.trim(), password);
        router.replace('/');
      } else {
        await signUpWithPassword(email.trim(), password);
        // Supabase may require the address to be confirmed before a session exists; say so
        // instead of bouncing to a home screen that still shows the welcome hero.
        setNotice('Account created. If a confirmation email arrives, follow it, then sign in.');
        setMode('signin');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not sign in.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Screen>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}
      >
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <BrandMark size={44} flame={colors.ember} drop={colors.water} />
          <Text style={type.title}>
            {mode === 'signin' ? t('Welcome back') : t('Create your account')}
          </Text>
          <Text style={styles.sub}>
            {mode === 'signin'
              ? t('Your properties, scans, and plan are where you left them.')
              : t('Eight characters or more for the password. Your data stays yours.')}
          </Text>

          {error ? <ErrorNote message={error} /> : null}
          {notice ? <Text style={styles.notice}>{notice}</Text> : null}

          <Card style={styles.card}>
            <Text style={type.label}>{t('Email')}</Text>
            <TextInput
              style={styles.input}
              value={email}
              onChangeText={setEmail}
              placeholder="you@example.com"
              placeholderTextColor={colors.textMuted}
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="email-address"
              autoComplete="email"
            />
            <Text style={[type.label, styles.spaced]}>{t('Password')}</Text>
            <TextInput
              style={styles.input}
              value={password}
              onChangeText={setPassword}
              placeholder="••••••••"
              placeholderTextColor={colors.textMuted}
              secureTextEntry
              autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
              onSubmitEditing={() => ready && submit()}
            />
          </Card>

          <Button
            title={mode === 'signin' ? t('Sign in') : t('Create account')}
            onPress={submit}
            loading={busy}
            disabled={!ready}
          />
          <Button
            title={
              mode === 'signin' ? t('New here? Create an account') : t('Have an account? Sign in')
            }
            variant="quiet"
            onPress={() => setMode(mode === 'signin' ? 'signup' : 'signin')}
          />
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}

const styles = StyleSheet.create({
  flex: { flex: 1 },
  content: {
    padding: spacing.lg,
    paddingTop: spacing.xl,
    gap: spacing.md,
    maxWidth: 480,
    width: '100%',
    alignSelf: 'center',
  },
  sub: { ...type.body, color: colors.textMuted },
  notice: {
    ...type.body,
    color: colors.accent,
    backgroundColor: colors.accentMuted,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  card: { marginBottom: 0 },
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
});
