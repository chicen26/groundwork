/**
 * Who is signed in.
 *
 * Today that is a locally generated user id sent in the development header, which is what the
 * backend accepts while Supabase auth is unconfigured. The shape of this context is the shape the
 * real thing will have — screens ask for `credentials` and never learn how identity is carried —
 * so swapping in a bearer token is a change to this file alone.
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import type { Credentials } from './api/client';

const STORAGE_KEY = 'groundwork.session.userId';

interface SessionValue {
  credentials: Credentials | null;
  loading: boolean;
  signIn: (userId: string) => Promise<void>;
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
  const [userId, setUserId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Restore rather than re-issue: a new id would orphan every property the user already added.
    AsyncStorage.getItem(STORAGE_KEY)
      .then((stored) => setUserId(stored))
      .catch(() => setUserId(null))
      .finally(() => setLoading(false));
  }, []);

  const signIn = useCallback(async (id: string) => {
    await AsyncStorage.setItem(STORAGE_KEY, id);
    setUserId(id);
  }, []);

  const signOut = useCallback(async () => {
    await AsyncStorage.removeItem(STORAGE_KEY);
    setUserId(null);
  }, []);

  const value = useMemo<SessionValue>(
    () => ({
      credentials: userId ? { userId } : null,
      loading,
      signIn,
      signOut,
    }),
    [userId, loading, signIn, signOut],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
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
