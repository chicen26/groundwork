-- 001: Extensions and shared helpers.
--
-- PostGIS carries the FHSZ, fire-district, and water-utility boundary layers we host ourselves
-- (governing principle 3: GIS lookups never leave our database).

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

-- Every table with an updated_at column shares this trigger rather than repeating the logic.
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

-- The identity of the caller, as set by the API before running a user's queries.
-- Returns NULL for the service role, which bypasses row-level security by policy design.
CREATE OR REPLACE FUNCTION current_user_id() RETURNS uuid
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    raw text;
BEGIN
    raw := current_setting('groundwork.user_id', true);
    IF raw IS NULL OR raw = '' THEN
        RETURN NULL;
    END IF;
    RETURN raw::uuid;
EXCEPTION
    WHEN invalid_text_representation THEN
        RETURN NULL;
END;
$$;
