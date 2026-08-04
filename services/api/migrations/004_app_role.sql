-- 004: The unprivileged role that request handlers run as.
--
-- Row-level security has a sharp edge: Postgres never applies policies to a superuser, and applies
-- them to the table owner only when FORCE ROW LEVEL SECURITY is set. If the API connected as the
-- owner or a superuser, every policy in migration 003 would be decoration and our isolation tests
-- would pass while proving nothing.
--
-- So handlers run as `groundwork_app`: no superuser, owns nothing, holds exactly the table
-- privileges it needs. Migrations, GIS imports, and the inference worker keep using the owning
-- role, which is why those paths are explicitly separated in app/db/pool.py.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'groundwork_app') THEN
        -- NOLOGIN: this is a privilege set, not an account. Deployments create a login role and
        -- grant it membership, so credentials can be rotated without touching the schema.
        CREATE ROLE groundwork_app NOLOGIN;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO groundwork_app;

-- User data: full read/write, constrained by the policies in 003.
GRANT SELECT, INSERT, UPDATE, DELETE ON
    users, properties, scans, photos, findings, lawn_polygons, assessments, plans, plan_items
    TO groundwork_app;

-- Reference data: readable by everyone signed in, written only by the service role.
GRANT SELECT ON plants, programs, feed_cache TO groundwork_app;

-- Deliberately not granted: schema_migrations. The application has no business reading or writing
-- its own migration history.
