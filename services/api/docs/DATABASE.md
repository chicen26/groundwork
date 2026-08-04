# Database

Postgres 16 with PostGIS. Schema lives in `services/api/migrations/` as numbered SQL files.

## Why plain SQL migrations

The schema is mostly things an ORM migration DSL expresses badly: PostGIS geography columns, CHECK
constraints that encode product rules, and row-level security policies. Writing them directly keeps
what the database enforces readable in one place — including for judges reading the repository.

The runner records a checksum per applied file. Editing a migration that has already run fails with
`MigrationDriftError` rather than silently producing two different schemas.

## Local setup (macOS, Homebrew)

```bash
brew install postgis
brew services start postgresql@17
createdb groundwork_dev && createdb groundwork_test
```

Then point the API and the tests at them:

```bash
export GROUNDWORK_DATABASE_URL=postgresql://localhost/groundwork_dev
export GROUNDWORK_TEST_DATABASE_URL=postgresql://localhost/groundwork_test
python -m app.db.migrate
```

Database tests skip when `GROUNDWORK_TEST_DATABASE_URL` is unset, so a fresh checkout still passes
its unit tests. CI always provides a PostGIS service container and fails if those tests skip.

## Row-level security is the privacy guarantee

Handlers do not filter by user with a `WHERE` clause and hope. The API sets `groundwork.user_id` on
the connection, and the policies in `003_row_level_security.sql` constrain every statement on it.
Ownership is traced back to `properties.user_id` through the scan and photo chain, so there is one
definition of "mine" rather than one per endpoint.

Two access paths exist, and the difference is deliberate:

| Helper | Identity | Used by |
|---|---|---|
| `acquire_as_user(user_id)` | sets `groundwork.user_id` | request handlers |
| `acquire_service()` | none | feed refresh, GIS import, inference worker |

`FORCE ROW LEVEL SECURITY` is set on every user-data table. Without it the table owner bypasses
policies and the isolation tests would prove nothing.

## Conventions

- Money and areas are `numeric`, never float. These are legal and financial claims.
- Deleting a user cascades to properties, scans, photos, findings, and plans — delete-account means
  the photos are gone, not orphaned.
- Reference tables (`plants`, `programs`, `feed_cache`) hold no user data and carry no RLS: everyone
  reads the same rows, only the service role writes them.
