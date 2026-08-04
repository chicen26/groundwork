-- 002: Core data model.
--
-- Shapes worth knowing before reading:
--   * A finding is either model-produced (photo + bounding box + confidence) or checklist-produced
--     (user answered a question). The CHECK constraints below make the illegal combinations
--     unrepresentable rather than merely discouraged.
--   * Anything tied to law, money, or safety is stored as an exact numeric, never a float.
--   * Assessments are immutable snapshots: they record the rulebook version that produced them, so
--     a score can always be explained even after the rulebook advances.

-- ---------------------------------------------------------------- enumerations

CREATE TYPE fhsz_class AS ENUM ('moderate', 'high', 'very_high', 'non_wildland', 'unknown');

CREATE TYPE scan_status AS ENUM ('in_progress', 'processing', 'complete', 'abandoned');

-- The guided walk: one photo station per prompt in the scan flow.
CREATE TYPE photo_station AS ENUM (
    'front_elevation',
    'left_side',
    'right_side',
    'rear_elevation',
    'deck_porch',
    'roofline',
    'perimeter_0_5ft'
);

-- The six detector classes. Kept in the database so findings can be joined and counted in SQL;
-- kept in lockstep with ml/taxonomy.
CREATE TYPE hazard_class AS ENUM (
    'veg_touching_structure',
    'overhanging_limbs',
    'combustible_mulch_z0',
    'attached_wood_fence',
    'combustibles_under_deck',
    'dead_vegetation'
);

CREATE TYPE finding_source AS ENUM ('model', 'checklist');

CREATE TYPE finding_status AS ENUM ('open', 'confirmed', 'dismissed', 'resolved');

CREATE TYPE plan_item_kind AS ENUM ('fire', 'water');

CREATE TYPE program_type AS ENUM ('rebate', 'chipping', 'cost_share', 'inspection');

-- ---------------------------------------------------------------- users

-- Authentication lives in Supabase; this table mirrors the identity so our foreign keys stay
-- inside one database and a hard delete really does cascade.
CREATE TABLE users (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Stored lowercased by the API so the unique constraint is genuinely case-insensitive.
    email      text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------- properties

CREATE TABLE properties (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id        uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    label          text,
    address        text NOT NULL,
    -- Geography, not geometry: distances and containment on a spheroid, in metres, no projection
    -- bookkeeping at call sites.
    location       geography (Point, 4326) NOT NULL,
    fhsz           fhsz_class NOT NULL DEFAULT 'unknown',
    -- Free text rather than an enum: district and utility names come from imported boundary layers
    -- and we would rather store an unexpected name than reject a real property.
    fire_district  text,
    water_utility  text,
    geo_resolved_at timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX properties_user_id_idx ON properties (user_id);
CREATE INDEX properties_location_idx ON properties USING gist (location);

-- ---------------------------------------------------------------- scans

CREATE TABLE scans (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id  uuid NOT NULL REFERENCES properties (id) ON DELETE CASCADE,
    status       scan_status NOT NULL DEFAULT 'in_progress',
    started_at   timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT scans_completed_implies_timestamp
        CHECK ((status = 'complete') = (completed_at IS NOT NULL))
);

CREATE INDEX scans_property_id_idx ON scans (property_id);

-- ---------------------------------------------------------------- photos

CREATE TABLE photos (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id       uuid NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    station       photo_station NOT NULL,
    storage_path  text NOT NULL UNIQUE,
    width_px      integer,
    height_px     integer,
    -- Photographs of private property are sensitive. We strip EXIF on upload and record that we
    -- did; a row that claims otherwise is a bug we want to be able to find in SQL.
    exif_stripped boolean NOT NULL DEFAULT false,
    captured_at   timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT photos_dimensions_positive
        CHECK ((width_px IS NULL OR width_px > 0) AND (height_px IS NULL OR height_px > 0))
);

CREATE INDEX photos_scan_id_idx ON photos (scan_id);
-- A station can be re-shot during fix-and-verify, so this is deliberately not unique.
CREATE INDEX photos_scan_station_idx ON photos (scan_id, station);

-- ---------------------------------------------------------------- findings

CREATE TABLE findings (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id     uuid NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    photo_id    uuid REFERENCES photos (id) ON DELETE CASCADE,
    source      finding_source NOT NULL,
    status      finding_status NOT NULL DEFAULT 'open',
    hazard      hazard_class NOT NULL,

    -- Bounding box in normalized image coordinates so it survives any resize the client applies.
    bbox_x      numeric(6, 5),
    bbox_y      numeric(6, 5),
    bbox_w      numeric(6, 5),
    bbox_h      numeric(6, 5),
    confidence  numeric(4, 3),

    -- Rules this finding satisfies the trigger for, e.g. {'prc4291.z1.clearance'}.
    rule_ids    text[] NOT NULL DEFAULT '{}',
    notes       text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),

    -- A model finding always points at the pixels that produced it; a checklist finding never
    -- pretends to.
    CONSTRAINT findings_model_shape CHECK (
        source <> 'model' OR (
            photo_id IS NOT NULL
            AND bbox_x IS NOT NULL AND bbox_y IS NOT NULL
            AND bbox_w IS NOT NULL AND bbox_h IS NOT NULL
            AND confidence IS NOT NULL
        )
    ),
    CONSTRAINT findings_checklist_shape CHECK (
        source <> 'checklist' OR (
            bbox_x IS NULL AND bbox_y IS NULL AND bbox_w IS NULL AND bbox_h IS NULL
            AND confidence IS NULL
        )
    ),
    CONSTRAINT findings_bbox_within_image CHECK (
        bbox_x IS NULL OR (
            bbox_x >= 0 AND bbox_y >= 0
            AND bbox_w > 0 AND bbox_h > 0
            AND bbox_x + bbox_w <= 1 AND bbox_y + bbox_h <= 1
        )
    ),
    CONSTRAINT findings_confidence_is_a_probability
        CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1))
);

CREATE INDEX findings_scan_id_idx ON findings (scan_id);
CREATE INDEX findings_photo_id_idx ON findings (photo_id);
CREATE INDEX findings_open_idx ON findings (scan_id) WHERE status = 'open';

-- ---------------------------------------------------------------- lawn polygons

CREATE TABLE lawn_polygons (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    property_id uuid NOT NULL REFERENCES properties (id) ON DELETE CASCADE,
    label       text,
    geom        geography (Polygon, 4326) NOT NULL,
    -- Authoritative area: recomputed server-side from geom, never trusted from the client.
    area_sqft   numeric(12, 2) NOT NULL,
    computed_at timestamptz NOT NULL DEFAULT now(),
    created_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT lawn_polygons_area_positive CHECK (area_sqft > 0)
);

CREATE INDEX lawn_polygons_property_id_idx ON lawn_polygons (property_id);

-- ---------------------------------------------------------------- assessments

CREATE TABLE assessments (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    scan_id          uuid NOT NULL REFERENCES scans (id) ON DELETE CASCADE,
    score            integer NOT NULL,
    rulebook_version text NOT NULL,
    -- Per-rule contributions, so the score screen can show its work.
    breakdown        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at       timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT assessments_score_range CHECK (score BETWEEN 0 AND 100)
);

CREATE INDEX assessments_scan_id_idx ON assessments (scan_id);

-- ---------------------------------------------------------------- plans

CREATE TABLE plans (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    assessment_id uuid NOT NULL UNIQUE REFERENCES assessments (id) ON DELETE CASCADE,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE programs (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    agency     text NOT NULL,
    name       text NOT NULL,
    type       program_type NOT NULL,
    -- Rebate rates, caps, and eligibility rules live here as data; the calculators read them.
    config     jsonb NOT NULL DEFAULT '{}'::jsonb,
    url        text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT programs_agency_name_unique UNIQUE (agency, name)
);

CREATE TABLE plan_items (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id     uuid NOT NULL REFERENCES plans (id) ON DELETE CASCADE,
    rank        integer NOT NULL,
    kind        plan_item_kind NOT NULL,
    rule_id     text,
    finding_id  uuid REFERENCES findings (id) ON DELETE SET NULL,
    program_id  uuid REFERENCES programs (id) ON DELETE SET NULL,
    title       text NOT NULL,
    detail      text,
    citation    text,
    effort_hours    numeric(5, 1),
    cost_est_usd    numeric(10, 2),
    savings_est_usd numeric(10, 2),
    done_at     timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT plan_items_rank_positive CHECK (rank > 0),
    CONSTRAINT plan_items_rank_unique UNIQUE (plan_id, rank) DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT plan_items_money_non_negative CHECK (
        (cost_est_usd IS NULL OR cost_est_usd >= 0)
        AND (savings_est_usd IS NULL OR savings_est_usd >= 0)
    )
);

CREATE INDEX plan_items_plan_id_idx ON plan_items (plan_id);

-- ---------------------------------------------------------------- reference data

-- Plants and programs are reference data: readable by every signed-in user, writable only by the
-- service role. No user data lives here, so no row-level security below.
CREATE TABLE plants (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    common_name    text NOT NULL,
    scientific_name text NOT NULL UNIQUE,
    -- WUCOLS V region-appropriate water need: very low / low / moderate / high.
    wucols_rating  text,
    fire_notes     text,
    native         boolean NOT NULL DEFAULT false,
    -- Which defensible-space zones this plant may be placed in, e.g. {'5_30ft','30ft_plus'}.
    zones_allowed  text[] NOT NULL DEFAULT '{}',
    sun            text,
    sources        text[] NOT NULL DEFAULT '{}',
    created_at     timestamptz NOT NULL DEFAULT now(),
    updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX plants_native_idx ON plants (native);

-- Third-party feeds are fetched by a scheduled job and served from here, so no user request ever
-- waits on an external service (governing principle 3).
CREATE TABLE feed_cache (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source     text NOT NULL,
    cache_key  text NOT NULL DEFAULT '',
    payload    jsonb NOT NULL,
    fetched_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz,

    CONSTRAINT feed_cache_source_key_unique UNIQUE (source, cache_key)
);

-- ---------------------------------------------------------------- updated_at triggers

CREATE TRIGGER users_set_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER properties_set_updated_at BEFORE UPDATE ON properties
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER scans_set_updated_at BEFORE UPDATE ON scans
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER findings_set_updated_at BEFORE UPDATE ON findings
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER programs_set_updated_at BEFORE UPDATE ON programs
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
CREATE TRIGGER plants_set_updated_at BEFORE UPDATE ON plants
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();
