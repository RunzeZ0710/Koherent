# 06 — Configuration, Migrations & Tooling

> **Decisions on this page:** [D-019](#d-019-configuration-via-environment-variables-and-pydantic-settings),
> [D-020](#d-020-manage-schema-changes-with-alembic-migrations),
> [D-021](#d-021-run-postgres-on-host-port-5433),
> [D-022](#d-022-use-uv-for-python-dependency-and-environment-management)

This page covers the "operational" decisions — how the app is configured, how the
database schema evolves over time, and the tools that run it all.

---

## 1. The concepts from zero

### What is "configuration" and why not just hardcode it?

Some values change depending on *where* the app runs: the database address, which
frontend origin to trust, where to store audio. On your laptop the database is
`localhost`; on a real server it's somewhere else. If those values are hardcoded
in the source, you'd have to edit code to run it anywhere else — and you'd risk
committing secrets (like a real database password) into git.

The standard fix is **environment variables**: named values supplied by the
environment the program runs in, *outside* the code. Conventionally they're kept
in a local file named `.env` that is **never committed** (ours is gitignored). A
committed `.env.example` documents which variables exist, without real secrets.

### What is a database migration?

Your database schema (the tables and columns) changes over time — Week 2 will add
tables for transcripts and feedback. But the database already holds data you
can't just throw away. A **migration** is a versioned, ordered script that makes
one specific change to the schema (e.g. "add a `transcript` table"). Migrations
are checked into git and applied in sequence, so *every* copy of the database —
yours, a teammate's, production — can be brought to the exact same structure by
replaying them. It's version control, but for your database's shape. Our
migration tool is **Alembic** (the companion project to SQLAlchemy).

### What is `uv`, Docker, pyproject.toml?

- **`uv`** is a fast Python package manager. It reads the project's declared
  dependencies, installs them into an isolated virtual environment (`.venv`), and
  runs commands inside it (`uv run pytest`). It also pins exact versions in a
  lockfile so everyone gets identical packages.
- **Docker / docker-compose** runs Postgres in a *container* — a pre-packaged,
  isolated copy of the database software — so you don't have to install and
  configure Postgres on your machine by hand. `docker compose up -d db` starts
  it.
- **`pyproject.toml`** is the single standard file declaring the backend's
  dependencies and tool settings (pytest, ruff). See
  [`backend/pyproject.toml`](../../../backend/pyproject.toml).

---

## 2. What we chose

**[D-019] Configuration comes from environment variables, parsed by
pydantic-settings.** All settings are declared in one typed class in
[`backend/src/koherent/config.py`](../../../backend/src/koherent/config.py):

```python
class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://koherent:koherent@localhost:5433/koherent"
    test_database_url: str = "postgresql+psycopg://koherent:koherent@localhost:5433/koherent_test"
    audio_storage_dir: str = "./storage/audio"
    cors_origins: str = "http://localhost:3002"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
```

This gives us one obvious place to see every knob, with **types** (the same
Pydantic validation idea from
[01-fastapi → D-002](01-fastapi.md#d-002-validate-all-requests-and-responses-with-pydantic-schemas))
and sensible **defaults**. Each value can be overridden by an environment
variable or the `.env` file without touching code. Everything else in the
codebase imports the single `settings` object rather than reading the
environment directly — so there's exactly one source of truth. (The
`cors_origin_list` property splits the comma-separated origins into the list
FastAPI's CORS middleware wants — see
[01-fastapi → §4](01-fastapi.md#4-in-our-code).)

**[D-020] Schema changes are managed with Alembic migrations.** The schema isn't
created ad hoc; it's defined by an ordered chain of migration files under
[`backend/alembic/versions/`](../../../backend/alembic/versions/). Week 1 has
one: `0001_initial` (the five tables). You apply migrations with:

```bash
cd backend && uv run alembic upgrade head   # bring the DB up to the latest version
```

Alembic is wired to our models: its `env.py` imports our `Base` metadata, so it
can compare "what the models say the schema should be" against "what the database
currently is" and **autogenerate** a migration for the difference. That's how
we'll add Week 2's tables — change the models, autogenerate a `0002_…` migration,
review it, and `upgrade`. Crucially, applying the same ordered migrations to any
database produces an identical schema, which is exactly what keeps dev, test, and
production in sync.

> Note: the *test* database is built directly from the models
> (`Base.metadata.create_all`, see [05-testing](05-testing.md)) for speed, while
> the *dev* database is built by applying migrations. Both arrive at the same
> schema because both derive from the same models.

**[D-021] Postgres is exposed on host port 5433, not the default 5432.** A
PostgreSQL server normally listens on port 5432. Many machines already have a
Postgres running there. To avoid a clash, our
[`docker-compose.yml`](../../../docker-compose.yml) maps the container's internal
5432 to **5433** on your machine, and the connection strings in `config.py` use
`localhost:5433`. (Inside the container it's still 5432; only the host-side port
differs.) This is purely a local-conflict-avoidance choice — it's why the
connection URLs look slightly non-standard.

**[D-022] Python dependencies and environment are managed with `uv`.** The
backend's deps are declared in
[`backend/pyproject.toml`](../../../backend/pyproject.toml) and installed with
`uv sync --extra dev`. Commands run through `uv run …`, which executes them inside
the project's isolated virtual environment. A lockfile pins exact versions so the
environment is reproducible.

---

## 3. What we rejected, and why

- **Hardcoding config in source.** Can't relocate the app without editing code,
  and tempts committing secrets to git. Env vars + a gitignored `.env` keep
  config external and secrets out of history.
- **Reading `os.environ` scattered through the code.** Works, but you lose a
  single inventory of settings, type-checking, and defaults. One typed
  `Settings` object centralizes all three.
- **Creating/altering tables by hand (running SQL directly).** Fast once, but
  there's no record of the change, no way to replay it elsewhere, and no
  ordering — different databases drift apart. Migrations are versioned and
  repeatable.
- **`create_all()` in production instead of migrations.** SQLAlchemy can build
  the whole schema from the models in one shot, and we use that for the *test*
  DB. But it can't *evolve* an existing schema (it won't alter or drop columns on
  populated tables), so it's unsafe once real data exists. Migrations are the
  grown-up tool for a living database.
- **`pip` + `requirements.txt` + manual venvs.** The older Python workflow. It
  works but is slower and easier to get into inconsistent states; `uv` is fast
  and gives reproducible installs from a lockfile.
- **Installing Postgres directly on the machine.** More setup, more
  machine-specific drift. A Docker container is disposable and identical for
  everyone.

---

## 4. In our code

| Thing | Where |
|-------|-------|
| Typed settings + defaults | [`backend/src/koherent/config.py`](../../../backend/src/koherent/config.py) |
| Documented env vars (no secrets) | `backend/.env.example` |
| Migration scripts | [`backend/alembic/versions/`](../../../backend/alembic/versions/) |
| Alembic ↔ models wiring | `backend/alembic/env.py` |
| Postgres container + port mapping | [`docker-compose.yml`](../../../docker-compose.yml) |
| Dependencies + tool config | [`backend/pyproject.toml`](../../../backend/pyproject.toml) |
| Run instructions | [`README.md`](../../../README.md) |

---

## 5. Decision records

### D-019: Configuration via environment variables and pydantic-settings

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** Some values differ per environment and some are secret; they
  shouldn't live in source.
- **Decision:** Declare all config in a typed `Settings(BaseSettings)` class with
  defaults, loaded from environment variables / a gitignored `.env`; import the
  single `settings` object everywhere.
- **Why:** One typed, defaulted inventory of every knob; secrets stay out of git;
  values overridable per environment without code changes.
- **Alternatives rejected:** Hardcoding (inflexible, leaks secrets); scattered
  `os.environ` reads (no central inventory, no types/defaults).

### D-020: Manage schema changes with Alembic migrations

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** The schema will keep changing while the database holds data that
  must be preserved, across multiple environments.
- **Decision:** Define the schema as an ordered chain of Alembic migrations
  (autogenerated from the SQLAlchemy models, then reviewed); apply with
  `alembic upgrade`.
- **Why:** Versioned, ordered, repeatable schema evolution keeps every database
  identical and preserves data; autogeneration from models is low-effort.
- **Alternatives rejected:** Hand-run SQL (no record, no ordering, drift);
  `create_all()` in production (can't safely evolve a populated schema).

### D-021: Run Postgres on host port 5433

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** The default Postgres port 5432 is often already taken on a
  developer's machine.
- **Decision:** Map the container's 5432 to host port 5433; use `localhost:5433`
  in the connection strings.
- **Why:** Avoids conflicts with any pre-existing local Postgres so the project
  runs without interfering with other work.
- **Alternatives rejected:** Default 5432 (risk of clashing with an existing
  server).

### D-022: Use `uv` for Python dependency and environment management

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** The backend needs reproducible dependency installs and an isolated
  environment.
- **Decision:** Declare deps in `pyproject.toml`, install with `uv sync`, run
  commands via `uv run`; pin versions in a lockfile.
- **Why:** Fast, reproducible installs and an isolated venv with minimal
  ceremony.
- **Alternatives rejected:** `pip` + `requirements.txt` + manual venvs (slower,
  easier to get inconsistent).
