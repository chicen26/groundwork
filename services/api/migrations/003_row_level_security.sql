-- 003: Row-level security.
--
-- Photographs of someone's home are sensitive, and the promise on the privacy screen is that data
-- is private by default. That promise is enforced here, in the database, rather than in whichever
-- handler happens to remember a WHERE clause.
--
-- The API opens a connection, sets `groundwork.user_id` to the authenticated user, and every
-- statement on that connection is then constrained by these policies. Ownership is traced back to
-- properties.user_id through the scan/photo chain, so there is exactly one definition of "mine".

ALTER TABLE users          ENABLE ROW LEVEL SECURITY;
ALTER TABLE properties     ENABLE ROW LEVEL SECURITY;
ALTER TABLE scans          ENABLE ROW LEVEL SECURITY;
ALTER TABLE photos         ENABLE ROW LEVEL SECURITY;
ALTER TABLE findings       ENABLE ROW LEVEL SECURITY;
ALTER TABLE lawn_polygons  ENABLE ROW LEVEL SECURITY;
ALTER TABLE assessments    ENABLE ROW LEVEL SECURITY;
ALTER TABLE plans          ENABLE ROW LEVEL SECURITY;
ALTER TABLE plan_items     ENABLE ROW LEVEL SECURITY;

-- Force policies on the table owner too. Without this, the role that owns the tables silently
-- bypasses every policy below and the tests would prove nothing.
ALTER TABLE users          FORCE ROW LEVEL SECURITY;
ALTER TABLE properties     FORCE ROW LEVEL SECURITY;
ALTER TABLE scans          FORCE ROW LEVEL SECURITY;
ALTER TABLE photos         FORCE ROW LEVEL SECURITY;
ALTER TABLE findings       FORCE ROW LEVEL SECURITY;
ALTER TABLE lawn_polygons  FORCE ROW LEVEL SECURITY;
ALTER TABLE assessments    FORCE ROW LEVEL SECURITY;
ALTER TABLE plans          FORCE ROW LEVEL SECURITY;
ALTER TABLE plan_items     FORCE ROW LEVEL SECURITY;

CREATE POLICY users_self ON users
    USING (id = current_user_id())
    WITH CHECK (id = current_user_id());

CREATE POLICY properties_own ON properties
    USING (user_id = current_user_id())
    WITH CHECK (user_id = current_user_id());

CREATE POLICY scans_own ON scans
    USING (EXISTS (
        SELECT 1 FROM properties p
        WHERE p.id = scans.property_id AND p.user_id = current_user_id()
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM properties p
        WHERE p.id = scans.property_id AND p.user_id = current_user_id()
    ));

CREATE POLICY photos_own ON photos
    USING (EXISTS (
        SELECT 1 FROM scans s JOIN properties p ON p.id = s.property_id
        WHERE s.id = photos.scan_id AND p.user_id = current_user_id()
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM scans s JOIN properties p ON p.id = s.property_id
        WHERE s.id = photos.scan_id AND p.user_id = current_user_id()
    ));

CREATE POLICY findings_own ON findings
    USING (EXISTS (
        SELECT 1 FROM scans s JOIN properties p ON p.id = s.property_id
        WHERE s.id = findings.scan_id AND p.user_id = current_user_id()
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM scans s JOIN properties p ON p.id = s.property_id
        WHERE s.id = findings.scan_id AND p.user_id = current_user_id()
    ));

CREATE POLICY lawn_polygons_own ON lawn_polygons
    USING (EXISTS (
        SELECT 1 FROM properties p
        WHERE p.id = lawn_polygons.property_id AND p.user_id = current_user_id()
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM properties p
        WHERE p.id = lawn_polygons.property_id AND p.user_id = current_user_id()
    ));

CREATE POLICY assessments_own ON assessments
    USING (EXISTS (
        SELECT 1 FROM scans s JOIN properties p ON p.id = s.property_id
        WHERE s.id = assessments.scan_id AND p.user_id = current_user_id()
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM scans s JOIN properties p ON p.id = s.property_id
        WHERE s.id = assessments.scan_id AND p.user_id = current_user_id()
    ));

CREATE POLICY plans_own ON plans
    USING (EXISTS (
        SELECT 1 FROM assessments a
        JOIN scans s ON s.id = a.scan_id
        JOIN properties p ON p.id = s.property_id
        WHERE a.id = plans.assessment_id AND p.user_id = current_user_id()
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM assessments a
        JOIN scans s ON s.id = a.scan_id
        JOIN properties p ON p.id = s.property_id
        WHERE a.id = plans.assessment_id AND p.user_id = current_user_id()
    ));

CREATE POLICY plan_items_own ON plan_items
    USING (EXISTS (
        SELECT 1 FROM plans pl
        JOIN assessments a ON a.id = pl.assessment_id
        JOIN scans s ON s.id = a.scan_id
        JOIN properties p ON p.id = s.property_id
        WHERE pl.id = plan_items.plan_id AND p.user_id = current_user_id()
    ))
    WITH CHECK (EXISTS (
        SELECT 1 FROM plans pl
        JOIN assessments a ON a.id = pl.assessment_id
        JOIN scans s ON s.id = a.scan_id
        JOIN properties p ON p.id = s.property_id
        WHERE pl.id = plan_items.plan_id AND p.user_id = current_user_id()
    ));

-- Reference data (plants, programs, feed_cache) carries no user data and is intentionally left
-- without row-level security: every signed-in user reads the same rows, and only the service role
-- writes them.
