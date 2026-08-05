-- 007: Supabase owns identity; our users table is a mirror.
--
-- Once tokens come from Supabase, the id in the `sub` claim is the identity, and Supabase holds the
-- email, the password, and the verification state. Our row exists so foreign keys have something to
-- point at and so a delete cascades — it does not need to duplicate the email, and duplicating it
-- would mean two records that can disagree.
--
-- So email becomes optional. A row is created on first use from the token's subject alone.

ALTER TABLE users ALTER COLUMN email DROP NOT NULL;

-- The unique index stays, but must now tolerate many NULLs, which Postgres already allows: NULLs
-- are not equal to each other. Made explicit here so the intent is not mistaken for an oversight.
COMMENT ON COLUMN users.email IS
    'Optional mirror of the Supabase email. Supabase is the source of truth; a row with a NULL email
     is a normal signed-in user whose email we simply have not copied.';
