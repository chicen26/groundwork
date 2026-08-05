/**
 * Who is signed in.
 *
 * Two modes, decided by configuration rather than code paths downstream:
 *
 * * **Account mode** — when app.json carries a Supabase URL and anon key, identity is a real
 *   Supabase session: email + password, a bearer token the backend verifies against the public
 *   JWKS, refresh handled by the client library.
 * * **Device mode** — with no Supabase configured, identity is a locally generated user id sent
 *   in the development header, which is what the backend accepts while auth is unconfigured.
 *
 * Screens ask for `credentials` and never learn how identity is carried, so the difference lives
 * in this file alone.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { type SupabaseClient, createClient } from '@supabase/supabase-js';
import Constants from 'expo-constants';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import type { Credentials } from './api/client';

const STORAGE_KEY = 'groundwork.session.userId';

const supabaseUrl = Constants.expoConfig?.extra?.supabaseUrl as string | undefined;
const supabaseAnonKey = Constants.expoConfig?.extra?.supabaseAnonKey as string | undefined;

/** The Supabase client, or null when the project is not configured — device mode. */
export const supabase: SupabaseClient | null =
  supabaseUrl && supabaseAnonKey
    ? createClient(supabaseUrl, supabaseAnonKey, {
        auth: {
          storage: AsyncStorage,
          autoRefreshToken: true,
          persistSession: true,
          // Deep-link handling is not wired up; leaving this on would make the web build try to
          // parse every URL for tokens.
          detectSessionInUrl: false,
        },
      })
    : null;

interface SessionValue {
  credentials: Credentials | null;
  loading: boolean;
  /** True when real accounts exist — the welcome screen routes to sign-in instead of instant-start. */
  accountsEnabled: boolean;
  /** The signed-in email, when account mode knows one. */
  email: string | null;
  signIn: (userId: string) => Promise<void>;
  signInWithPassword: (email: string, password: string) => Promise<void>;
  signUpWithPassword: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const SessionContext = createContext<SessionValue | null>(null);

/** RFC 4122 v4, from the platform's crypto rather than Math.random. */
function newUserId(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [credentials, setCredentials] = useState<Credentials | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (supabase) {
      // Account mode: the library owns persistence and refresh; we mirror its session.
      const { data: subscription } = supabase.auth.onAuthStateChange((_event, session) => {
        setCredentials(session ? { userId: session.user.id, token: session.access_token } : null);
        setEmail(session?.user.email ?? null);
        setLoading(false);
      });
      supabase.auth.getSession().then(({ data }) => {
        setCredentials(
          data.session ? { userId: data.session.user.id, token: data.session.access_token } : null,
        );
        setEmail(data.session?.user.email ?? null);
        setLoading(false);
      });
      return () => subscription.subscription.unsubscribe();
    }

    // Device mode. Restore rather than re-issue: a new id would orphan every property the user
    // already added.
    AsyncStorage.getItem(STORAGE_KEY)
      .then((stored) => setCredentials(stored ? { userId: stored } : null))
      .catch(() => setCredentials(null))
      .finally(() => setLoading(false));
    return undefined;
  }, []);

  const signIn = useCallback(async (id: string) => {
    await AsyncStorage.setItem(STORAGE_KEY, id);
    setCredentials({ userId: id });
  }, []);

  const signInWithPassword = useCallback(async (address: string, password: string) => {
    if (!supabase) throw new Error('accounts are not configured');
    const { error } = await supabase.auth.signInWithPassword({ email: address, password });
    if (error) throw new Error(error.message);
  }, []);

  const signUpWithPassword = useCallback(async (address: string, password: string) => {
    if (!supabase) throw new Error('accounts are not configured');
    const { error } = await supabase.auth.signUp({ email: address, password });
    if (error) throw new Error(error.message);
  }, []);

  const signOut = useCallback(async () => {
    if (supabase) await supabase.auth.signOut();
    await AsyncStorage.removeItem(STORAGE_KEY);
    setCredentials(null);
    setEmail(null);
  }, []);

  const value = useMemo<SessionValue>(
    () => ({
      credentials,
      loading,
      accountsEnabled: supabase !== null,
      email,
      signIn,
      signInWithPassword,
      signUpWithPassword,
      signOut,
    }),
    [credentials, loading, email, signIn, signInWithPassword, signUpWithPassword, signOut],
  );

  // Nothing renders until we know who this is: a deep link into a signed-in screen must not
  // mount before the stored session has been read, or it throws on a race it cannot see.
  return (
    <SessionContext.Provider value={value}>{loading ? null : children}</SessionContext.Provider>
  );
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) {
    throw new Error('useSession must be used inside a SessionProvider');
  }
  return value;
}

/**
 * Credentials for a screen that only renders when signed in.
 *
 * Throws rather than returning null so a screen cannot silently make unauthenticated requests and
 * render an empty state that looks like "you have no properties".
 */
export function useCredentials(): Credentials {
  const { credentials } = useSession();
  if (!credentials) {
    throw new Error('this screen requires a signed-in session');
  }
  return credentials;
}

export { newUserId };
