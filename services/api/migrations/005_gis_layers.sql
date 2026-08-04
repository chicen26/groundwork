-- 005: Hosted GIS boundary layers.
--
-- We host these ourselves rather than calling CAL FIRE or a county server during a request. A
-- homeowner opening the app on demo day must not depend on someone else's ArcGIS server being up
-- (governing principle 3), and point-in-polygon against a local GIST index is milliseconds.
--
-- Geometry, not geography: containment is a topological question, so the geodesic corrections
-- geography pays for buy us nothing here. Areas and distances elsewhere still use geography.

CREATE TABLE gis_layer_versions (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    layer         text NOT NULL,
    source_url    text NOT NULL,
    -- The publisher's own name for this edition, e.g. 'FHSZ LRA 2025 v1'. Shown to the user
    -- alongside their zone, because "designated Very High in Feb 2025" is a claim about a specific
    -- published map and we should be able to name it.
    source_version text NOT NULL,
    feature_count integer NOT NULL DEFAULT 0,
    imported_at   timestamptz NOT NULL DEFAULT now(),
    is_active     boolean NOT NULL DEFAULT false,

    CONSTRAINT gis_layer_versions_feature_count_non_negative CHECK (feature_count >= 0)
);

-- Exactly one active version per layer: an import promotes itself only once it has loaded
-- successfully, so a failed refresh leaves the previous map serving rather than a half-loaded one.
CREATE UNIQUE INDEX gis_layer_versions_one_active_idx
    ON gis_layer_versions (layer) WHERE is_active;

CREATE TABLE fhsz_zones (
    id             bigserial PRIMARY KEY,
    layer_version_id uuid NOT NULL REFERENCES gis_layer_versions (id) ON DELETE CASCADE,
    -- State Responsibility Area vs Local. The two are published as separate maps and a property
    -- falls under one of them; which one decides whose rules apply.
    responsibility text NOT NULL,
    fhsz           fhsz_class NOT NULL,
    geom           geometry (MultiPolygon, 4326) NOT NULL,

    CONSTRAINT fhsz_zones_responsibility_known CHECK (responsibility IN ('SRA', 'LRA', 'FRA'))
);

CREATE INDEX fhsz_zones_geom_idx ON fhsz_zones USING gist (geom);
CREATE INDEX fhsz_zones_version_idx ON fhsz_zones (layer_version_id);

CREATE TABLE fire_districts (
    id             bigserial PRIMARY KEY,
    layer_version_id uuid NOT NULL REFERENCES gis_layer_versions (id) ON DELETE CASCADE,
    name           text NOT NULL,
    agency_code    text,
    geom           geometry (MultiPolygon, 4326) NOT NULL
);

CREATE INDEX fire_districts_geom_idx ON fire_districts USING gist (geom);
CREATE INDEX fire_districts_version_idx ON fire_districts (layer_version_id);

CREATE TABLE water_utilities (
    id             bigserial PRIMARY KEY,
    layer_version_id uuid NOT NULL REFERENCES gis_layer_versions (id) ON DELETE CASCADE,
    name           text NOT NULL,
    utility_code   text,
    geom           geometry (MultiPolygon, 4326) NOT NULL
);

CREATE INDEX water_utilities_geom_idx ON water_utilities USING gist (geom);
CREATE INDEX water_utilities_version_idx ON water_utilities (layer_version_id);

-- Boundary layers are public reference data: every signed-in user resolves against the same maps,
-- and only the import job writes them. No row-level security, matching plants and programs.
GRANT SELECT ON gis_layer_versions, fhsz_zones, fire_districts, water_utilities TO groundwork_app;

-- Record which published maps produced a property's zone, so an answer stays explainable after the
-- layers are refreshed.
ALTER TABLE properties
    ADD COLUMN fhsz_source_version text,
    ADD COLUMN fhsz_responsibility text;
