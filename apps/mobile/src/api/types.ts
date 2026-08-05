/**
 * The shapes the API returns.
 *
 * Hand-written rather than generated, and deliberately narrow: the client only declares what the
 * screens actually read. Fields the backend adds later are simply ignored until a screen wants
 * them.
 */

export type FhszClass = 'moderate' | 'high' | 'very_high' | 'non_wildland' | 'unknown';

export type RuleStatus = 'in_effect' | 'pending_adoption' | 'advisory';

export type Station =
  | 'front_elevation'
  | 'left_side'
  | 'right_side'
  | 'rear_elevation'
  | 'deck_porch'
  | 'roofline'
  | 'perimeter_0_5ft';

export interface GeoSummary {
  fhsz: FhszClass;
  fhsz_responsibility: string | null;
  /** The published map the zone came from. Shown with the zone, never omitted. */
  fhsz_source_version: string | null;
  fire_district: string | null;
  water_utility: string | null;
  /** Layers we could not determine. Surfaced honestly rather than rendered as blanks. */
  unresolved: string[];
}

/** One line in the address dropdown. Selecting it supplies both the text and the pin. */
export interface AddressSuggestion {
  label: string;
  lat: number;
  lng: number;
}

/** What a ZIP alone can tell you. Always approximate, and the UI must say so. */
export interface ZipQuickLook {
  zip: string;
  place: string | null;
  state_code: string | null;
  lat: number;
  lng: number;
  fhsz: FhszClass;
  fhsz_source_version: string | null;
  fire_district: string | null;
  water_utility: string | null;
  unresolved: string[];
  approximate: boolean;
}

/** Aggregate impact across all accounts. Totals only; no per-user data. */
export interface ImpactStats {
  properties: number;
  assessments: number;
  plan_items_done: number;
  hazards_addressed: number;
  lawn_sqft_measured: number;
  annual_gallons_saved: number;
  rebate_dollars_identified: number;
}

export interface Property {
  id: string;
  address: string;
  label: string | null;
  lat: number;
  lng: number;
  geo: GeoSummary;
}

export interface ScanSummary {
  id: string;
  property_id: string;
  status: 'in_progress' | 'processing' | 'complete' | 'abandoned';
  stations_photographed: Station[];
  stations_remaining: Station[];
  questions_answered: number;
  questions_total: number;
  open_findings: number;
  photos_pending_inference: number;
}

export interface BoundingBox {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Finding {
  id: string;
  photo_id: string | null;
  hazard: string;
  source: 'model' | 'checklist';
  status: 'open' | 'confirmed' | 'dismissed' | 'resolved';
  confidence: number | null;
  bbox: BoundingBox | null;
  model_version: string | null;
  /** True when the detection is too uncertain to state as fact. Never render these as findings. */
  needs_confirmation: boolean;
}

export interface Question {
  id: string;
  prompt: string;
  help_text: string;
  zone: string;
  station: Station;
}

export interface PlanItem {
  id: string;
  rank: number;
  title: string;
  detail: string;
  citation: string;
  zone: string | null;
  severity: string | null;
  rule_status: RuleStatus | null;
  /** Present on rules that are not law yet. Must be shown wherever the item is shown. */
  caveat: string | null;
  effort_hours: number | null;
  cost_est_usd: number | null;
  score_if_done: number | null;
  done: boolean;
}

export interface BreakdownRule {
  rule_id: string;
  title: string;
  citation: string;
  authority: string;
  status: RuleStatus;
  zone: string;
  severity: string;
  weight: number;
  met: boolean;
  weight_lost: number;
  caveat: string;
}

export interface Assessment {
  id: string;
  scan_id: string;
  score: number;
  rulebook_version: string;
  breakdown: {
    formula: string;
    applicable_weight: number;
    met_weight: number;
    rules: BreakdownRule[];
  };
  disclaimer: string;
  plan: PlanItem[];
}

export const STATION_LABELS: Record<Station, string> = {
  front_elevation: 'Front of the house',
  left_side: 'Left side',
  right_side: 'Right side',
  rear_elevation: 'Back of the house',
  deck_porch: 'Deck or porch',
  roofline: 'Roof and gutters',
  perimeter_0_5ft: 'First five feet',
};

/** What to frame at each station, shown live over the camera. */
export const STATION_HINTS: Record<Station, string> = {
  front_elevation: 'Stand back far enough to get the whole front, roof edge to ground.',
  left_side: 'Walk the side. Include where the wall meets the ground and any vents.',
  right_side: 'Same on this side: wall, ground line, and vents.',
  rear_elevation: 'The back of the house, including anything stacked against it.',
  deck_porch: 'Crouch to show the space underneath, not just the deck surface.',
  roofline: 'Aim up at the roof edge, gutters, and any limbs above them.',
  perimeter_0_5ft: 'Close up on the strip right against the wall: mulch, plants, fencing.',
};

export const FHSZ_LABELS: Record<FhszClass, string> = {
  very_high: 'Very High',
  high: 'High',
  moderate: 'Moderate',
  non_wildland: 'Non-Wildland',
  unknown: 'Not determined',
};

export const HAZARD_LABELS: Record<string, string> = {
  dead_vegetation: 'Dead vegetation',
  veg_touching_structure: 'Vegetation touching the house',
  overhanging_limbs: 'Overhanging limbs',
  combustible_mulch_z0: 'Combustible mulch in the first five feet',
  attached_wood_fence: 'Wooden fence attached to the house',
  combustibles_under_deck: 'Combustibles under the deck',
};

// ---------------------------------------------------------------- water

export interface RebateEstimate {
  program_key: string;
  agency: string;
  program_name: string;
  tier_label: string | null;
  rate_per_sqft: string;
  /** What the rate alone would pay, before the cap. Shown when the cap bites. */
  uncapped_usd: string;
  amount_usd: string;
  capped: boolean;
  cap_usd: string;
  eligible: boolean;
  /** Present when eligible is false. Always shown — never a bare zero. */
  ineligible_reason: string | null;
  url: string;
  warning: string;
}

export interface LawnMeasurement {
  id: string;
  label: string | null;
  area_sqft: string;
  annual_gallons_saved: string;
  savings_basis: string;
  rebates: RebateEstimate[];
  warning: string;
  utility: string | null;
  /** True when the utility could not be determined and every programme is shown. */
  showing_all_programs: boolean;
}

// ---------------------------------------------------------------- resources

export interface LocalResource {
  key: string;
  agency: string;
  name: string;
  type: string;
  summary: string;
  url: string;
  phone: string | null;
  disclaimer: string | null;
  external_only: boolean;
  universal: boolean;
}

// ---------------------------------------------------------------- context strip

export interface AlertStrip {
  /** False means we do not know — never render it as "no warnings". */
  available: boolean;
  red_flag: boolean;
  events: string[];
  headline: string | null;
  fetched_at: string | null;
  note: string;
}
