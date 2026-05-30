# Decision Index

The single front door to every decision in this repo. One row per decision.
Click the ID to read the full reasoning on the relevant topic page.

See [README.md](README.md) for how this index works and how to add to it.

| ID | Decision | Date | Status | Details |
|----|----------|------|--------|---------|
| [D-001](topics/01-fastapi.md#d-001-use-fastapi-as-the-backend-web-framework) | Use FastAPI as the backend web framework | 2026-05-21 | Active | [01-fastapi](topics/01-fastapi.md) |
| [D-002](topics/01-fastapi.md#d-002-validate-all-requests-and-responses-with-pydantic-schemas) | Validate all requests/responses with Pydantic schemas | 2026-05-21 | Active | [01-fastapi](topics/01-fastapi.md) |
| [D-003](topics/01-fastapi.md#d-003-split-routes-into-routers-by-resource) | Split routes into routers by resource (`classes`, `lectures`) | 2026-05-21 | Active | [01-fastapi](topics/01-fastapi.md) |
| [D-004](topics/01-fastapi.md#d-004-use-dependency-injection-for-db-and-auth) | Use FastAPI dependency injection for DB session + auth | 2026-05-21 | Active | [01-fastapi](topics/01-fastapi.md) |
| [D-005](topics/02-sqlalchemy.md#d-005-use-the-sqlalchemy-orm-instead-of-raw-sql) | Use the SQLAlchemy ORM instead of raw SQL | 2026-05-21 | Active | [02-sqlalchemy](topics/02-sqlalchemy.md) |
| [D-006](topics/02-sqlalchemy.md#d-006-use-postgresql-as-the-database) | Use PostgreSQL as the database | 2026-05-21 | Active | [02-sqlalchemy](topics/02-sqlalchemy.md) |
| [D-007](topics/02-sqlalchemy.md#d-007-one-db-session-per-request-via-get_db) | One DB session per request, via `get_db` | 2026-05-21 | Active | [02-sqlalchemy](topics/02-sqlalchemy.md) |
| [D-008](topics/03-auth-and-sessions.md#d-008-auth-is-join-code--display-name-no-passwords) | Auth is join-code + display name (no passwords/email) | 2026-05-21 | Active | [03-auth-and-sessions](topics/03-auth-and-sessions.md) |
| [D-009](topics/03-auth-and-sessions.md#d-009-sessions-are-opaque-random-tokens-in-httponly-cookies) | Sessions are opaque random tokens in httpOnly cookies | 2026-05-21 | Active | [03-auth-and-sessions](topics/03-auth-and-sessions.md) |
| [D-010](topics/03-auth-and-sessions.md#d-010-6-char-join-codes-generated-with-collision-retry) | 6-char join codes, generated with collision-retry | 2026-05-21 | Active | [03-auth-and-sessions](topics/03-auth-and-sessions.md) |
| [D-011](topics/04-data-model.md#d-011-five-tables-class-student-lecture-note-audiorecording) | Five tables: Class, Student, Lecture, Note, AudioRecording | 2026-05-21 | Active | [04-data-model](topics/04-data-model.md) |
| [D-012](topics/04-data-model.md#d-012-uuid-primary-keys-not-auto-increment-integers) | UUID primary keys (not auto-increment integers) | 2026-05-21 | Active | [04-data-model](topics/04-data-model.md) |
| [D-013](topics/04-data-model.md#d-013-cascade-deletes-for-ownership-set-null-for-attribution) | CASCADE deletes for ownership, SET NULL for attribution | 2026-05-21 | Active | [04-data-model](topics/04-data-model.md) |
| [D-014](topics/04-data-model.md#d-014-store-a-client-timestamp-on-notes) | Store a client timestamp (ms since lecture start) on notes | 2026-05-21 | Active | [04-data-model](topics/04-data-model.md) |
| [D-015](topics/04-data-model.md#d-015-store-audio-on-local-disk-metadata-in-the-database) | Store audio files on local disk, metadata in the DB | 2026-05-21 | Active | [04-data-model](topics/04-data-model.md) |
| [D-016](topics/05-testing.md#d-016-test-driven-development-on-every-backend-endpoint) | Test-driven development (TDD) on every backend endpoint | 2026-05-21 | Active | [05-testing](topics/05-testing.md) |
| [D-017](topics/05-testing.md#d-017-test-against-real-postgres-not-sqlite-or-mocks) | Test against a real Postgres DB (not SQLite or mocks) | 2026-05-21 | Active | [05-testing](topics/05-testing.md) |
| [D-018](topics/05-testing.md#d-018-isolate-tests-with-a-rollback-per-test-transaction) | Isolate each test with a rolled-back transaction + SAVEPOINT | 2026-05-21 | Active | [05-testing](topics/05-testing.md) |
| [D-019](topics/06-config-and-migrations.md#d-019-configuration-via-environment-variables-and-pydantic-settings) | Configuration via env vars + pydantic-settings | 2026-05-21 | Active | [06-config-and-migrations](topics/06-config-and-migrations.md) |
| [D-020](topics/06-config-and-migrations.md#d-020-manage-schema-changes-with-alembic-migrations) | Manage schema changes with Alembic migrations | 2026-05-21 | Active | [06-config-and-migrations](topics/06-config-and-migrations.md) |
| [D-021](topics/06-config-and-migrations.md#d-021-run-postgres-on-host-port-5433) | Run Postgres on host port 5433 to avoid local conflicts | 2026-05-21 | Active | [06-config-and-migrations](topics/06-config-and-migrations.md) |
| [D-022](topics/06-config-and-migrations.md#d-022-use-uv-for-python-dependency-and-environment-management) | Use `uv` for Python dependency/environment management | 2026-05-21 | Active | [06-config-and-migrations](topics/06-config-and-migrations.md) |

## Status legend

- **Active** — the decision is in force.
- **Superseded by D-0YY** — replaced by a later decision; kept for history.
- **Deprecated** — no longer true, not yet replaced.
