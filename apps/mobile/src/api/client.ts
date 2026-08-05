/**
 * The API client.
 *
 * One place that knows how to reach the backend and how to carry the caller's identity, so no
 * screen builds a URL or a header by hand. Errors arrive as `ApiError` with the server's own
 * message, because "could not locate that address, place it on the map instead" is far more use to
 * a homeowner than "Request failed".
 */

import Constants from 'expo-constants';
import { Platform } from 'react-native';

import type {
  AddressSuggestion,
  AlertStrip,
  Assessment,
  Finding,
  LawnMeasurement,
  LocalResource,
  Property,
  Question,
  ScanSummary,
  Station,
  ZipQuickLook,
} from './types';

/**
 * Where the backend lives.
 *
 * In the browser the answer is derived from the page's own address: whatever host served the app
 * is the host running the API, so a laptop at localhost and a phone on the LAN both work without
 * editing config — a hardcoded IP here is exactly how the web build once broke. Native builds
 * cannot do that trick and read app.json, so a dev build, a tunnel, and demo day can each point
 * somewhere different without a code change.
 */
export const API_BASE_URL: string =
  Platform.OS === 'web' && typeof window !== 'undefined'
    ? ((Constants.expoConfig?.extra?.webApiBaseUrl as string | undefined) ??
      `${window.location.protocol}//${window.location.hostname}:8000`)
    : ((Constants.expoConfig?.extra?.apiBaseUrl as string | undefined) ?? 'http://127.0.0.1:8000');

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }

  /** True when the request itself was fine but we could not act on it — worth showing verbatim. */
  get isActionable(): boolean {
    return this.status === 422 || this.status === 404;
  }
}

/**
 * How identity is carried: a Supabase bearer token when accounts are configured, or the
 * development header the backend accepts until they are. Screens never see the difference.
 */
export type Credentials = { userId: string; token?: string };

function headersFor(credentials: Credentials, extra: Record<string, string> = {}) {
  return credentials.token
    ? { Authorization: `Bearer ${credentials.token}`, ...extra }
    : { 'X-Groundwork-User': credentials.userId, ...extra };
}

/**
 * fetch, with its one useless failure mode translated.
 *
 * When the server cannot be reached at all, fetch rejects with the browser's "Failed to fetch" —
 * words that tell a homeowner nothing. Turn that into a sentence with a next step; every other
 * error keeps the server's own message via `unwrap`.
 */
async function reach(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch {
    throw new ApiError(
      0,
      'Could not reach the Groundwork server. Check your connection and try again in a moment.',
    );
  }
}

async function unwrap<T>(response: Response): Promise<T> {
  if (response.ok) {
    return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
  }

  // FastAPI puts the useful text in `detail`, sometimes as a validation array.
  let message = `Request failed (${response.status})`;
  try {
    const body = await response.json();
    if (typeof body?.detail === 'string') {
      message = body.detail;
    } else if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
      message = body.detail[0].msg;
    }
  } catch {
    // A non-JSON error body is not worth failing over; the status carries enough.
  }
  throw new ApiError(response.status, message);
}

async function request<T>(
  path: string,
  credentials: Credentials,
  init: RequestInit = {},
): Promise<T> {
  const response = await reach(`${API_BASE_URL}/v1${path}`, {
    ...init,
    headers: headersFor(credentials, {
      ...(init.body && !(init.body instanceof FormData)
        ? { 'Content-Type': 'application/json' }
        : {}),
      ...((init.headers as Record<string, string>) ?? {}),
    }),
  });
  return unwrap<T>(response);
}

export const api = {
  health(): Promise<{ status: string; rulebook_version: string }> {
    return reach(`${API_BASE_URL}/v1/health`).then((r) =>
      unwrap<{ status: string; rulebook_version: string }>(r),
    );
  },

  /**
   * Address completions while typing. Failure means an empty list — a dropdown that stays closed —
   * never an error surfaced mid-keystroke.
   */
  async suggestAddresses(q: string): Promise<AddressSuggestion[]> {
    try {
      const response = await fetch(`${API_BASE_URL}/v1/geo/suggest?q=${encodeURIComponent(q)}`);
      return response.ok ? ((await response.json()) as AddressSuggestion[]) : [];
    } catch {
      return [];
    }
  },

  /** The rough picture at a ZIP's center point, for people who have not typed an address yet. */
  zipQuickLook(zip: string): Promise<ZipQuickLook> {
    return reach(`${API_BASE_URL}/v1/geo/quick-look?zip=${encodeURIComponent(zip)}`).then((r) =>
      unwrap<ZipQuickLook>(r),
    );
  },

  listProperties(credentials: Credentials): Promise<Property[]> {
    return request<Property[]>('/properties', credentials);
  },

  getProperty(credentials: Credentials, id: string): Promise<Property> {
    return request<Property>(`/properties/${id}`, credentials);
  },

  createProperty(
    credentials: Credentials,
    body: { address: string; label?: string; lat?: number; lng?: number },
  ): Promise<Property> {
    return request<Property>('/properties', credentials, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  startScan(credentials: Credentials, propertyId: string): Promise<ScanSummary> {
    return request<ScanSummary>(`/properties/${propertyId}/scans`, credentials, { method: 'POST' });
  },

  getScan(credentials: Credentials, scanId: string): Promise<ScanSummary> {
    return request<ScanSummary>(`/scans/${scanId}`, credentials);
  },

  /**
   * Upload one station photograph.
   *
   * Returns as soon as the photo is stored — inference is queued, not awaited, so the walk never
   * stalls behind a model.
   */
  async uploadPhoto(
    credentials: Credentials,
    scanId: string,
    station: Station,
    photoUri: string,
  ): Promise<{ photo_id: string }> {
    const form = new FormData();
    form.append('station', station);
    // React Native's FormData takes this shape for a local file; the cast is the standard escape
    // hatch, since the DOM's File type does not apply here.
    form.append('file', {
      uri: photoUri,
      name: `${station}.jpg`,
      type: 'image/jpeg',
    } as unknown as Blob);

    const response = await reach(`${API_BASE_URL}/v1/scans/${scanId}/photos`, {
      method: 'POST',
      headers: headersFor(credentials),
      body: form,
    });
    return unwrap<{ photo_id: string }>(response);
  },

  photoUrl(scanId: string, photoId: string): string {
    return `${API_BASE_URL}/v1/photos/${photoId}/content`;
  },

  listFindings(credentials: Credentials, scanId: string): Promise<Finding[]> {
    return request<Finding[]>(`/scans/${scanId}/findings`, credentials);
  },

  setFindingStatus(
    credentials: Credentials,
    findingId: string,
    status: 'confirmed' | 'dismissed' | 'resolved' | 'open',
  ): Promise<Finding> {
    return request<Finding>(`/findings/${findingId}/status`, credentials, {
      method: 'POST',
      body: JSON.stringify({ status }),
    });
  },

  getChecklist(credentials: Credentials): Promise<Question[]> {
    return request<Question[]>('/checklist', credentials);
  },

  submitChecklist(
    credentials: Credentials,
    scanId: string,
    answers: { question_id: string; hazard_present: boolean }[],
  ): Promise<ScanSummary> {
    return request<ScanSummary>(`/scans/${scanId}/checklist`, credentials, {
      method: 'PUT',
      body: JSON.stringify({ answers }),
    });
  },

  assess(credentials: Credentials, scanId: string): Promise<Assessment> {
    return request<Assessment>(`/scans/${scanId}/assess`, credentials, {
      method: 'POST',
    });
  },

  getAssessment(credentials: Credentials, assessmentId: string): Promise<Assessment> {
    return request<Assessment>(`/assessments/${assessmentId}`, credentials);
  },

  completePlanItem(credentials: Credentials, itemId: string): Promise<void> {
    return request<void>(`/plan-items/${itemId}/complete`, credentials, {
      method: 'POST',
    });
  },

  /** Send the drawn outline; the server measures it. The area decides money, so it is not ours. */
  measureLawn(
    credentials: Credentials,
    propertyId: string,
    geojson: object,
    options: { label?: string; tier_key?: string } = {},
  ): Promise<LawnMeasurement> {
    return request<LawnMeasurement>(`/properties/${propertyId}/lawn`, credentials, {
      method: 'POST',
      body: JSON.stringify({ geojson, ...options }),
    });
  },

  listLawns(credentials: Credentials, propertyId: string): Promise<LawnMeasurement[]> {
    return request<LawnMeasurement[]>(`/properties/${propertyId}/lawn`, credentials);
  },

  resourcesForProperty(credentials: Credentials, propertyId: string): Promise<LocalResource[]> {
    return request<LocalResource[]>(`/resources/for-property/${propertyId}`, credentials);
  },

  /** Cached only. A failure here must never block a screen. */
  alerts(lat: number, lng: number): Promise<AlertStrip> {
    return fetch(`${API_BASE_URL}/v1/feeds/alerts?lat=${lat}&lng=${lng}`).then((r) =>
      unwrap<AlertStrip>(r),
    );
  },

  reportUrl(assessmentId: string): string {
    return `${API_BASE_URL}/v1/assessments/${assessmentId}/report`;
  },

  updateProperty(
    credentials: Credentials,
    propertyId: string,
    body: { label?: string; address?: string; lat?: number; lng?: number },
  ): Promise<Property> {
    return request<Property>(`/properties/${propertyId}`, credentials, {
      method: 'PATCH',
      body: JSON.stringify(body),
    });
  },

  deleteProperty(credentials: Credentials, propertyId: string): Promise<void> {
    return request<void>(`/properties/${propertyId}`, credentials, { method: 'DELETE' });
  },

  deleteAccount(credentials: Credentials): Promise<void> {
    return request<void>('/account', credentials, {
      method: 'DELETE',
      body: JSON.stringify({ confirm: 'DELETE' }),
    });
  },
};
