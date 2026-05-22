# Week 1 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** End of Week 1, a student can join a class with a code, type timestamped notes during a lecture, one student can record audio, and all of it persists to Postgres. No AI processing yet — that's Week 2.

**Architecture:** Monorepo with Next.js 15 (App Router, TypeScript) frontend at `:3000` and Python/FastAPI backend at `:8000`. Postgres 16 in docker-compose. Sessions are opaque tokens stored on `students` rows, set as `httpOnly` cookies, validated per-request via DB lookup. Audio uploads via multipart, written to `backend/storage/audio/` on local disk. Backend follows TDD (pytest + real Postgres test DB, transactional rollback per test). Frontend tested manually in the browser.

**Tech Stack:**
- Frontend: Next.js 15, React 19, TypeScript, Tailwind, `pnpm`
- Backend: Python 3.11+, FastAPI, SQLAlchemy 2.0, Alembic, pydantic v2, pytest, `uv`
- DB: Postgres 16 via docker-compose
- Browser audio: `MediaRecorder` API (WebM/Opus, native in Chrome/Firefox/Safari)

---

## Prerequisites (you do these once, outside the plan)

These are blockers for Task 1. Do them first.

1. **Install tooling** (if missing):
   ```bash
   # Python via uv
   curl -LsSf https://astral.sh/uv/install.sh | sh

   # Node via your usual route, then pnpm
   npm install -g pnpm

   # Docker Desktop
   # Download from docker.com/products/docker-desktop and install
   ```

2. **Sign up for NVIDIA Developer Program** at https://build.nvidia.com, generate an API key starting with `nvapi-...`. Save it somewhere — you'll need it Week 2. Not used in Week 1.

3. **Verify the NIM API works** from your Mac with the snippet in `project_plan.md` lines 213–236. If chat + embedding both return real responses, you're unblocked for Week 2. Also try one ASR call against a short audio sample — that's the riskiest endpoint, and you want to fail fast if it doesn't work. Not used in Week 1 but proves the stack before you build a week of infrastructure around it.

---

## Open Decisions (resolved, do not revisit in Week 1)

- **Auth:** Just join code + display name. Session is a `secrets.token_urlsafe(32)` cookie. No passwords, no email.
- **DB:** Local Postgres via docker-compose. Same image runs both dev and test databases.
- **Tests:** TDD on every backend endpoint (pytest). Frontend tested manually in the browser.
- **Repo:** Monorepo. `frontend/` and `backend/` are siblings under repo root.
- **Recording:** Any student in the lecture can press Record. Frontend shows a local indicator. No backend "recording active" broadcast yet — defer to Week 4 dogfooding.

---

## File Structure (created across all tasks)

```
Koherent/
├── docker-compose.yml                              # Postgres dev + test DBs
├── .gitignore
├── README.md                                       # written in Task 17
├── project_plan.md                                 # existing
├── docs/superpowers/plans/
│   └── 2026-05-21-week-1-foundation.md             # this file
├── backend/
│   ├── pyproject.toml
│   ├── .env.example
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   ├── src/koherent/
│   │   ├── __init__.py
│   │   ├── main.py                                 # FastAPI app + CORS + router mounts
│   │   ├── config.py                               # pydantic-settings
│   │   ├── db.py                                   # engine, SessionLocal, Base
│   │   ├── models.py                               # SQLAlchemy: Class, Student, Lecture, Note, AudioRecording
│   │   ├── schemas.py                              # pydantic request/response models
│   │   ├── deps.py                                 # get_db, get_current_student
│   │   ├── storage.py                              # audio disk helpers
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── classes.py                          # POST /classes, POST /classes/join
│   │       └── lectures.py                         # POST /lectures, GET /lectures/{id}, POST /lectures/{id}/notes, POST /lectures/{id}/audio
│   ├── storage/audio/                              # gitignored, written at runtime
│   └── tests/
│       ├── conftest.py                             # test DB engine + per-test rollback + client fixture
│       ├── test_health.py
│       ├── test_models.py
│       ├── test_classes.py
│       ├── test_join.py
│       ├── test_session.py
│       ├── test_lectures.py
│       ├── test_notes.py
│       └── test_audio.py
└── frontend/
    ├── package.json
    ├── tsconfig.json
    ├── next.config.ts
    ├── tailwind.config.ts
    ├── postcss.config.mjs
    ├── .env.local.example
    └── src/
        ├── app/
        │   ├── layout.tsx
        │   ├── page.tsx                            # landing
        │   ├── globals.css
        │   ├── create/page.tsx                     # prof creates class
        │   ├── join/page.tsx                       # student joins
        │   ├── class/page.tsx                      # post-join home; start lecture
        │   └── lecture/[id]/page.tsx               # in-lecture notes + recorder
        ├── lib/
        │   ├── api.ts                              # typed fetch wrappers
        │   └── recorder.ts                         # MediaRecorder helper
        └── components/
            ├── NoteEditor.tsx
            └── AudioRecorder.tsx
```

---

## Task 1: Monorepo skeleton + docker-compose Postgres

**Files:**
- Create: `docker-compose.yml`
- Create: `.gitignore`
- Create: `backend/` (directory)
- Create: `frontend/` (directory)
- Create: `backend/storage/audio/.gitkeep`

- [ ] **Step 1: Create the root `.gitignore`**

Create `.gitignore`:

```gitignore
# Python
__pycache__/
*.pyc
.venv/
.pytest_cache/
.ruff_cache/
*.egg-info/

# Node
node_modules/
.next/
out/
.turbo/

# Env files (do not commit secrets)
.env
.env.local
.env.*.local
backend/.env
frontend/.env.local

# OS / IDE
.DS_Store
.vscode/
.idea/

# Local audio uploads
backend/storage/audio/*
!backend/storage/audio/.gitkeep

# Postgres data volume
.pgdata/
```

- [ ] **Step 2: Create `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16-alpine
    container_name: koherent-postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: koherent
      POSTGRES_PASSWORD: koherent
      POSTGRES_DB: koherent
    ports:
      - "5432:5432"
    volumes:
      - ./.pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U koherent -d koherent"]
      interval: 5s
      timeout: 5s
      retries: 10
```

- [ ] **Step 3: Create directories and placeholder**

Run:
```bash
mkdir -p backend/src/koherent/routes backend/tests backend/alembic/versions backend/storage/audio frontend
touch backend/storage/audio/.gitkeep
```

- [ ] **Step 4: Start Postgres and verify it's healthy**

Run:
```bash
docker compose up -d db
sleep 3
docker compose ps
```

Expected: `koherent-postgres` shows `Up` and `(healthy)`.

Then verify a connection:
```bash
docker compose exec db psql -U koherent -d koherent -c 'SELECT version();'
```

Expected: prints a `PostgreSQL 16.x ...` line.

- [ ] **Step 5: Create the test database**

Run:
```bash
docker compose exec db psql -U koherent -d koherent -c 'CREATE DATABASE koherent_test;'
```

Expected: `CREATE DATABASE`.

- [ ] **Step 6: Commit**

```bash
git add .gitignore docker-compose.yml backend/storage/audio/.gitkeep
git commit -m "chore: bootstrap monorepo skeleton with docker-compose postgres"
```

---

## Task 2: Backend project setup (uv + pyproject.toml + first passing test)

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/.env.example`
- Create: `backend/src/koherent/__init__.py` (empty)
- Create: `backend/src/koherent/main.py`
- Create: `backend/tests/__init__.py` (empty)
- Create: `backend/tests/test_smoke.py`

- [ ] **Step 1: Create `backend/pyproject.toml`**

```toml
[project]
name = "koherent-backend"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.32",
    "sqlalchemy>=2.0.36",
    "alembic>=1.14",
    "psycopg[binary]>=3.2",
    "pydantic>=2.9",
    "pydantic-settings>=2.6",
    "python-multipart>=0.0.17",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "httpx>=0.28",
    "ruff>=0.8",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/koherent"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "-ra -q"

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 2: Create `backend/.env.example`**

```bash
DATABASE_URL=postgresql+psycopg://koherent:koherent@localhost:5432/koherent
TEST_DATABASE_URL=postgresql+psycopg://koherent:koherent@localhost:5432/koherent_test
AUDIO_STORAGE_DIR=./storage/audio
CORS_ORIGINS=http://localhost:3000
```

Also copy it for local use:
```bash
cp backend/.env.example backend/.env
```

- [ ] **Step 3: Create the FastAPI entrypoint**

Create `backend/src/koherent/__init__.py` (empty file).

Create `backend/src/koherent/main.py`:

```python
from fastapi import FastAPI

app = FastAPI(title="Koherent API", version="0.1.0")
```

- [ ] **Step 4: Install deps with `uv` and write a smoke test**

Run:
```bash
cd backend && uv sync --extra dev
```

Expected: `uv` creates `.venv/` and `uv.lock`, installs all deps.

Create `backend/tests/__init__.py` (empty file).

Create `backend/tests/test_smoke.py`:

```python
from fastapi.testclient import TestClient

from koherent.main import app


def test_app_boots():
    client = TestClient(app)
    # No routes defined yet — 404 just proves the app imports and serves
    response = client.get("/")
    assert response.status_code == 404
```

- [ ] **Step 5: Run pytest and verify it passes**

Run:
```bash
cd backend && uv run pytest
```

Expected: `1 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/uv.lock backend/.env.example backend/src backend/tests
git commit -m "feat(backend): scaffold fastapi app with uv + pytest"
```

---

## Task 3: Health endpoint (TDD)

**Files:**
- Modify: `backend/src/koherent/main.py`
- Create: `backend/tests/test_health.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from koherent.main import app


def test_health_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run and verify it fails**

Run:
```bash
cd backend && uv run pytest tests/test_health.py -v
```

Expected: FAIL — `404 Not Found` on `/health`.

- [ ] **Step 3: Implement the endpoint**

Replace `backend/src/koherent/main.py`:

```python
from fastapi import FastAPI

app = FastAPI(title="Koherent API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 4: Run and verify it passes**

Run:
```bash
cd backend && uv run pytest tests/test_health.py -v
```

Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/src/koherent/main.py backend/tests/test_health.py
git commit -m "feat(backend): add /health endpoint"
```

---

## Task 4: Config + DB layer + SQLAlchemy models + Alembic

This task bundles config, the DB layer, the model definitions, the test DB fixture, and the first Alembic migration. They're tightly coupled and each piece is useless without the others.

**Files:**
- Create: `backend/src/koherent/config.py`
- Create: `backend/src/koherent/db.py`
- Create: `backend/src/koherent/models.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_models.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/0001_initial.py`

- [ ] **Step 1: Create `config.py`**

Create `backend/src/koherent/config.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://koherent:koherent@localhost:5432/koherent"
    test_database_url: str = "postgresql+psycopg://koherent:koherent@localhost:5432/koherent_test"
    audio_storage_dir: str = "./storage/audio"
    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
```

- [ ] **Step 2: Create `db.py`**

Create `backend/src/koherent/db.py`:

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from koherent.config import settings


class Base(DeclarativeBase):
    pass


engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
```

- [ ] **Step 3: Create `models.py`**

Create `backend/src/koherent/models.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from koherent.db import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class Class(Base):
    __tablename__ = "classes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    join_code: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    owner_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    students: Mapped[list["Student"]] = relationship(back_populates="class_", cascade="all, delete-orphan")
    lectures: Mapped[list["Lecture"]] = relationship(back_populates="class_", cascade="all, delete-orphan")


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (UniqueConstraint("class_id", "display_name", name="uq_class_display_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    session_token: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    class_: Mapped[Class] = relationship(back_populates="students")


class Lecture(Base):
    __tablename__ = "lectures"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    class_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("classes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id", ondelete="SET NULL"), nullable=True
    )

    class_: Mapped[Class] = relationship(back_populates="lectures")
    notes: Mapped[list["Note"]] = relationship(back_populates="lecture", cascade="all, delete-orphan")
    audio_recordings: Mapped[list["AudioRecording"]] = relationship(
        back_populates="lecture", cascade="all, delete-orphan"
    )


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    lecture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lectures.id", ondelete="CASCADE"), nullable=False, index=True
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(String, nullable=False)
    client_timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lecture: Mapped[Lecture] = relationship(back_populates="notes")


class AudioRecording(Base):
    __tablename__ = "audio_recordings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    lecture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lectures.id", ondelete="CASCADE"), nullable=False, index=True
    )
    uploaded_by_student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id", ondelete="SET NULL"), nullable=True
    )
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lecture: Mapped[Lecture] = relationship(back_populates="audio_recordings")
```

- [ ] **Step 4: Initialize Alembic**

Run:
```bash
cd backend && uv run alembic init alembic
```

This creates `backend/alembic.ini`, `backend/alembic/env.py`, `backend/alembic/script.py.mako`, and `backend/alembic/versions/`.

- [ ] **Step 5: Wire Alembic to our metadata**

Replace `backend/alembic/env.py`:

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from koherent.config import settings
from koherent.db import Base
import koherent.models  # noqa: F401  -- import so metadata sees the tables

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 6: Generate the first migration**

Run:
```bash
cd backend && uv run alembic revision --autogenerate -m "initial schema"
```

Expected: a new file like `backend/alembic/versions/<hash>_initial_schema.py` is created. Open it and verify it includes `create_table` calls for `classes`, `students`, `lectures`, `notes`, and `audio_recordings`.

Rename the file to `0001_initial.py` for stable ordering and edit the top of the file so `revision = "0001"` and `down_revision = None`.

- [ ] **Step 7: Apply the migration to dev DB**

Run:
```bash
cd backend && uv run alembic upgrade head
```

Expected: `Running upgrade -> 0001, initial schema`.

Then verify in psql:
```bash
docker compose exec db psql -U koherent -d koherent -c '\dt'
```

Expected: lists `classes`, `students`, `lectures`, `notes`, `audio_recordings`, `alembic_version`.

- [ ] **Step 8: Create the test fixtures (`conftest.py`)**

Create `backend/tests/conftest.py`:

```python
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from koherent.config import settings
from koherent.db import Base
from koherent.deps import get_db  # created in Task 5
from koherent.main import app


@pytest.fixture(scope="session")
def _engine():
    engine = create_engine(settings.test_database_url, future=True)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture()
def db(_engine) -> Generator[Session, None, None]:
    connection = _engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection, autoflush=False, autocommit=False, future=True)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db) -> Generator[TestClient, None, None]:
    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

Note: `koherent.deps.get_db` is created in Task 5. This conftest will fail to import until then. That's intentional — the next task wires it up.

- [ ] **Step 9: Write a model-level test**

Create `backend/tests/test_models.py`:

```python
import secrets

from koherent.models import Class, Student


def test_can_persist_class_and_student(db):
    klass = Class(name="Econ 101", join_code="ABC123", owner_token=secrets.token_urlsafe(32))
    db.add(klass)
    db.flush()

    student = Student(class_id=klass.id, display_name="Alice", session_token=secrets.token_urlsafe(32))
    db.add(student)
    db.flush()

    refetched = db.get(Class, klass.id)
    assert refetched is not None
    assert refetched.name == "Econ 101"
    assert len(refetched.students) == 1
    assert refetched.students[0].display_name == "Alice"
```

This test will be runnable after Task 5 creates `deps.py`. Run it then; for now move to Task 5.

- [ ] **Step 10: Commit**

```bash
git add backend/src/koherent/config.py backend/src/koherent/db.py backend/src/koherent/models.py \
        backend/alembic.ini backend/alembic backend/tests/conftest.py backend/tests/test_models.py
git commit -m "feat(backend): add config, db, models, and initial alembic migration"
```

---

## Task 5: `get_db` dependency + verify models test passes

**Files:**
- Create: `backend/src/koherent/deps.py`

- [ ] **Step 1: Create `deps.py` with `get_db`**

Create `backend/src/koherent/deps.py`:

```python
from collections.abc import Generator

from sqlalchemy.orm import Session

from koherent.db import SessionLocal


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
```

(Note: `get_current_student` is added in Task 8 when it's first needed.)

- [ ] **Step 2: Run the models test and verify it passes**

Run:
```bash
cd backend && uv run pytest tests/test_models.py -v
```

Expected: `1 passed`. Also verify `tests/test_health.py` still passes:

```bash
cd backend && uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/src/koherent/deps.py
git commit -m "feat(backend): add get_db dependency"
```

---

## Task 6: POST /classes (create a class) — TDD

**Files:**
- Create: `backend/src/koherent/schemas.py`
- Create: `backend/src/koherent/routes/__init__.py`
- Create: `backend/src/koherent/routes/classes.py`
- Modify: `backend/src/koherent/main.py`
- Create: `backend/tests/test_classes.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_classes.py`:

```python
def test_create_class_returns_id_and_join_code(client, db):
    response = client.post("/classes", json={"name": "Econ 101"})

    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert body["name"] == "Econ 101"
    assert len(body["join_code"]) == 6
    assert body["join_code"].isalnum()
    assert body["join_code"].isupper()
    assert "owner_token" in body and len(body["owner_token"]) >= 32


def test_create_class_rejects_empty_name(client):
    response = client.post("/classes", json={"name": ""})
    assert response.status_code == 422
```

- [ ] **Step 2: Run and watch fail**

Run:
```bash
cd backend && uv run pytest tests/test_classes.py -v
```

Expected: FAIL — `404 Not Found` on POST /classes.

- [ ] **Step 3: Create `schemas.py`**

Create `backend/src/koherent/schemas.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ClassRead(BaseModel):
    id: uuid.UUID
    name: str
    join_code: str
    created_at: datetime


class ClassCreated(ClassRead):
    owner_token: str
```

- [ ] **Step 4: Create the routes package and the classes router**

Create `backend/src/koherent/routes/__init__.py` (empty file).

Create `backend/src/koherent/routes/classes.py`:

```python
import secrets
import string

from fastapi import APIRouter, Depends, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from koherent.deps import get_db
from koherent.models import Class
from koherent.schemas import ClassCreate, ClassCreated

router = APIRouter(prefix="/classes", tags=["classes"])

_JOIN_CODE_ALPHABET = string.ascii_uppercase + string.digits


def _generate_join_code() -> str:
    return "".join(secrets.choice(_JOIN_CODE_ALPHABET) for _ in range(6))


@router.post("", response_model=ClassCreated, status_code=status.HTTP_201_CREATED)
def create_class(payload: ClassCreate, db: Session = Depends(get_db)) -> Class:
    for _ in range(10):
        candidate = _generate_join_code()
        klass = Class(
            name=payload.name,
            join_code=candidate,
            owner_token=secrets.token_urlsafe(32),
        )
        db.add(klass)
        try:
            db.flush()
            db.commit()
            db.refresh(klass)
            return klass
        except IntegrityError:
            db.rollback()
            continue
    raise RuntimeError("Could not allocate a unique join code after 10 attempts")
```

- [ ] **Step 5: Mount the router in `main.py`**

Replace `backend/src/koherent/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from koherent.config import settings
from koherent.routes import classes

app = FastAPI(title="Koherent API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(classes.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 6: Run and watch pass**

Run:
```bash
cd backend && uv run pytest tests/test_classes.py -v
```

Expected: `2 passed`.

- [ ] **Step 7: Commit**

```bash
git add backend/src/koherent/schemas.py backend/src/koherent/routes backend/src/koherent/main.py backend/tests/test_classes.py
git commit -m "feat(backend): POST /classes creates a class with a join code"
```

---

## Task 7: POST /classes/join (student joins) — TDD

**Files:**
- Modify: `backend/src/koherent/schemas.py`
- Modify: `backend/src/koherent/routes/classes.py`
- Create: `backend/tests/test_join.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_join.py`:

```python
def _create_class(client, name="Econ 101") -> dict:
    response = client.post("/classes", json={"name": name})
    assert response.status_code == 201
    return response.json()


def test_join_existing_class_returns_session_and_sets_cookie(client):
    klass = _create_class(client)
    response = client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    )

    assert response.status_code == 201
    body = response.json()
    assert "student_id" in body
    assert body["display_name"] == "Alice"
    assert body["class_id"] == klass["id"]
    assert "session_token" in body and len(body["session_token"]) >= 32

    assert "koherent_session" in response.cookies
    assert response.cookies["koherent_session"] == body["session_token"]


def test_join_unknown_code_returns_404(client):
    response = client.post(
        "/classes/join", json={"join_code": "ZZZZZZ", "display_name": "Alice"}
    )
    assert response.status_code == 404


def test_join_duplicate_display_name_returns_409(client):
    klass = _create_class(client)
    payload = {"join_code": klass["join_code"], "display_name": "Alice"}
    assert client.post("/classes/join", json=payload).status_code == 201

    response = client.post("/classes/join", json=payload)
    assert response.status_code == 409
```

- [ ] **Step 2: Run and watch fail**

Run:
```bash
cd backend && uv run pytest tests/test_join.py -v
```

Expected: FAIL — `404` on POST /classes/join.

- [ ] **Step 3: Add the join schemas**

Append to `backend/src/koherent/schemas.py`:

```python
class JoinRequest(BaseModel):
    join_code: str = Field(min_length=1, max_length=16)
    display_name: str = Field(min_length=1, max_length=100)


class StudentSession(BaseModel):
    student_id: uuid.UUID
    class_id: uuid.UUID
    display_name: str
    session_token: str
```

- [ ] **Step 4: Implement the join route**

Add to `backend/src/koherent/routes/classes.py` (below the existing `create_class`):

```python
import secrets

from fastapi import HTTPException, Response
from sqlalchemy import select

from koherent.models import Student
from koherent.schemas import JoinRequest, StudentSession

SESSION_COOKIE_NAME = "koherent_session"


@router.post("/join", response_model=StudentSession, status_code=status.HTTP_201_CREATED)
def join_class(
    payload: JoinRequest, response: Response, db: Session = Depends(get_db)
) -> StudentSession:
    klass = db.scalar(select(Class).where(Class.join_code == payload.join_code.upper()))
    if klass is None:
        raise HTTPException(status_code=404, detail="Join code not found")

    existing = db.scalar(
        select(Student).where(
            Student.class_id == klass.id, Student.display_name == payload.display_name
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Display name already taken in this class")

    student = Student(
        class_id=klass.id,
        display_name=payload.display_name,
        session_token=secrets.token_urlsafe(32),
    )
    db.add(student)
    db.commit()
    db.refresh(student)

    response.set_cookie(
        SESSION_COOKIE_NAME,
        student.session_token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return StudentSession(
        student_id=student.id,
        class_id=student.class_id,
        display_name=student.display_name,
        session_token=student.session_token,
    )
```

Note: the `secrets` import is added at the top of the file as a regular import alongside the existing ones — consolidate `import secrets` to a single line at file top.

- [ ] **Step 5: Run and watch pass**

Run:
```bash
cd backend && uv run pytest tests/test_join.py -v
```

Expected: `3 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/src/koherent/schemas.py backend/src/koherent/routes/classes.py backend/tests/test_join.py
git commit -m "feat(backend): POST /classes/join issues student session"
```

---

## Task 8: `get_current_student` dependency — TDD

**Files:**
- Modify: `backend/src/koherent/deps.py`
- Create: `backend/tests/test_session.py`
- Modify: `backend/src/koherent/main.py` (temporary test-only route)

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_session.py`:

```python
def _join(client) -> dict:
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    return client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    ).json()


def test_me_returns_current_student_with_session_cookie(client):
    session = _join(client)
    response = client.get("/me")

    assert response.status_code == 200
    body = response.json()
    assert body["student_id"] == session["student_id"]
    assert body["display_name"] == "Alice"


def test_me_without_session_returns_401(client):
    response = client.get("/me", cookies={})  # explicit no cookie
    # TestClient persists cookies across requests; use a fresh request without them:
    response = client.get("/me", cookies={"koherent_session": ""})
    assert response.status_code == 401
```

Note: TestClient persists cookies. The second assertion uses an empty cookie value to simulate an unauthenticated request. If the framework version doesn't honor that, change the test to instantiate a fresh `TestClient(app)` for the unauthenticated call.

- [ ] **Step 2: Run and watch fail**

Run:
```bash
cd backend && uv run pytest tests/test_session.py -v
```

Expected: FAIL — `404` on `/me`.

- [ ] **Step 3: Add `get_current_student` to `deps.py`**

Replace `backend/src/koherent/deps.py`:

```python
from collections.abc import Generator

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from koherent.db import SessionLocal
from koherent.models import Student

SESSION_COOKIE_NAME = "koherent_session"


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_current_student(
    koherent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> Student:
    if not koherent_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    student = db.scalar(select(Student).where(Student.session_token == koherent_session))
    if student is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")
    return student
```

- [ ] **Step 4: Add a `/me` route to satisfy the test**

Edit `backend/src/koherent/main.py` and add (below the existing `/health` route):

```python
from koherent.deps import get_current_student
from koherent.models import Student
from koherent.schemas import StudentSession


@app.get("/me", response_model=StudentSession)
def me(current: Student = Depends(get_current_student)) -> StudentSession:
    return StudentSession(
        student_id=current.id,
        class_id=current.class_id,
        display_name=current.display_name,
        session_token=current.session_token,
    )
```

Consolidate the `from fastapi import ...` line at the top to include `Depends`.

- [ ] **Step 5: Run and watch pass**

Run:
```bash
cd backend && uv run pytest tests/test_session.py -v
```

Expected: `2 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/src/koherent/deps.py backend/src/koherent/main.py backend/tests/test_session.py
git commit -m "feat(backend): add get_current_student dependency and /me"
```

---

## Task 9: POST /lectures (start a lecture) — TDD

**Files:**
- Modify: `backend/src/koherent/schemas.py`
- Create: `backend/src/koherent/routes/lectures.py`
- Modify: `backend/src/koherent/main.py`
- Create: `backend/tests/test_lectures.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_lectures.py`:

```python
def _join(client) -> dict:
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    session = client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    ).json()
    return {**session, "join_code": klass["join_code"]}


def test_start_lecture_returns_id_and_started_at(client):
    _join(client)
    response = client.post("/lectures", json={"title": "Day 1: supply curves"})

    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert body["title"] == "Day 1: supply curves"
    assert "started_at" in body
    assert body["ended_at"] is None


def test_start_lecture_without_session_returns_401(client):
    response = client.post("/lectures", json={"title": "x"}, cookies={"koherent_session": ""})
    assert response.status_code == 401
```

- [ ] **Step 2: Run and watch fail**

Run:
```bash
cd backend && uv run pytest tests/test_lectures.py -v
```

Expected: FAIL — `404` on POST /lectures.

- [ ] **Step 3: Add lecture schemas**

Append to `backend/src/koherent/schemas.py`:

```python
class LectureCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)


class LectureRead(BaseModel):
    id: uuid.UUID
    class_id: uuid.UUID
    title: str | None
    started_at: datetime
    ended_at: datetime | None
```

- [ ] **Step 4: Create the lectures router**

Create `backend/src/koherent/routes/lectures.py`:

```python
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from koherent.deps import get_current_student, get_db
from koherent.models import Lecture, Student
from koherent.schemas import LectureCreate, LectureRead

router = APIRouter(prefix="/lectures", tags=["lectures"])


@router.post("", response_model=LectureRead, status_code=status.HTTP_201_CREATED)
def start_lecture(
    payload: LectureCreate,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> Lecture:
    lecture = Lecture(
        class_id=current.class_id,
        title=payload.title,
        created_by_student_id=current.id,
    )
    db.add(lecture)
    db.commit()
    db.refresh(lecture)
    return lecture
```

- [ ] **Step 5: Mount the router**

In `backend/src/koherent/main.py`, add to imports:

```python
from koherent.routes import classes, lectures
```

And below the existing `app.include_router(classes.router)`:

```python
app.include_router(lectures.router)
```

- [ ] **Step 6: Run and watch pass**

Run:
```bash
cd backend && uv run pytest tests/test_lectures.py -v
```

Expected: `2 passed`.

- [ ] **Step 7: Commit**

```bash
git add backend/src/koherent/schemas.py backend/src/koherent/routes/lectures.py backend/src/koherent/main.py backend/tests/test_lectures.py
git commit -m "feat(backend): POST /lectures starts a lecture for the current student's class"
```

---

## Task 10: POST /lectures/{id}/notes (append a note) — TDD

**Files:**
- Modify: `backend/src/koherent/schemas.py`
- Modify: `backend/src/koherent/routes/lectures.py`
- Create: `backend/tests/test_notes.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_notes.py`:

```python
def _start_lecture(client) -> dict:
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    )
    return client.post("/lectures", json={"title": "Day 1"}).json()


def test_post_note_persists_and_returns_id(client):
    lecture = _start_lecture(client)
    response = client.post(
        f"/lectures/{lecture['id']}/notes",
        json={"content": "MR = MC at the profit-maximizing output", "client_timestamp_ms": 12345},
    )
    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert body["content"] == "MR = MC at the profit-maximizing output"
    assert body["client_timestamp_ms"] == 12345


def test_post_note_to_other_class_lecture_returns_403(client):
    # Create lecture in class A as Alice
    lecture_a = _start_lecture(client)

    # Switch identity: join a NEW class as Bob, then try to post to lecture A
    klass_b = client.post("/classes", json={"name": "Hist 101"}).json()
    client.post(
        "/classes/join",
        json={"join_code": klass_b["join_code"], "display_name": "Bob"},
    )
    # Bob's cookie is now active. Posting to lecture_a should be forbidden.
    response = client.post(
        f"/lectures/{lecture_a['id']}/notes",
        json={"content": "trespass", "client_timestamp_ms": 1},
    )
    assert response.status_code == 403


def test_post_note_to_unknown_lecture_returns_404(client):
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    )
    response = client.post(
        "/lectures/00000000-0000-0000-0000-000000000000/notes",
        json={"content": "x", "client_timestamp_ms": 1},
    )
    assert response.status_code == 404
```

- [ ] **Step 2: Run and watch fail**

Run:
```bash
cd backend && uv run pytest tests/test_notes.py -v
```

Expected: FAIL — `404` on POST /lectures/{id}/notes.

- [ ] **Step 3: Add note schemas**

Append to `backend/src/koherent/schemas.py`:

```python
class NoteCreate(BaseModel):
    content: str = Field(min_length=1)
    client_timestamp_ms: int = Field(ge=0)


class NoteRead(BaseModel):
    id: uuid.UUID
    lecture_id: uuid.UUID
    student_id: uuid.UUID
    content: str
    client_timestamp_ms: int
    created_at: datetime
```

- [ ] **Step 4: Implement the note route**

Append to `backend/src/koherent/routes/lectures.py`:

```python
import uuid

from fastapi import HTTPException

from koherent.models import Note
from koherent.schemas import NoteCreate, NoteRead


def _load_lecture_for_student(lecture_id: uuid.UUID, student: Student, db: Session) -> Lecture:
    lecture = db.get(Lecture, lecture_id)
    if lecture is None:
        raise HTTPException(status_code=404, detail="Lecture not found")
    if lecture.class_id != student.class_id:
        raise HTTPException(status_code=403, detail="Not a member of this lecture's class")
    return lecture


@router.post("/{lecture_id}/notes", response_model=NoteRead, status_code=status.HTTP_201_CREATED)
def append_note(
    lecture_id: uuid.UUID,
    payload: NoteCreate,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> Note:
    lecture = _load_lecture_for_student(lecture_id, current, db)
    note = Note(
        lecture_id=lecture.id,
        student_id=current.id,
        content=payload.content,
        client_timestamp_ms=payload.client_timestamp_ms,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return note
```

Consolidate the `import uuid` at the file top alongside other imports.

- [ ] **Step 5: Run and watch pass**

Run:
```bash
cd backend && uv run pytest tests/test_notes.py -v
```

Expected: `3 passed`.

- [ ] **Step 6: Commit**

```bash
git add backend/src/koherent/schemas.py backend/src/koherent/routes/lectures.py backend/tests/test_notes.py
git commit -m "feat(backend): POST /lectures/{id}/notes appends a timestamped note"
```

---

## Task 11: POST /lectures/{id}/audio (multipart upload) — TDD

**Files:**
- Create: `backend/src/koherent/storage.py`
- Modify: `backend/src/koherent/routes/lectures.py`
- Modify: `backend/src/koherent/schemas.py`
- Create: `backend/tests/test_audio.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_audio.py`:

```python
import io


def _start_lecture(client) -> dict:
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    )
    return client.post("/lectures", json={"title": "Day 1"}).json()


def test_upload_audio_persists_file_and_row(client, tmp_path, monkeypatch):
    monkeypatch.setenv("AUDIO_STORAGE_DIR", str(tmp_path))
    # The settings instance is already loaded — patch directly:
    from koherent.config import settings

    monkeypatch.setattr(settings, "audio_storage_dir", str(tmp_path))

    lecture = _start_lecture(client)
    fake_audio = b"OggS\x00\x02fake-webm-bytes" * 100  # ~1.7 KB of bytes

    response = client.post(
        f"/lectures/{lecture['id']}/audio",
        files={"file": ("lecture.webm", io.BytesIO(fake_audio), "audio/webm")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["lecture_id"] == lecture["id"]
    assert body["mime_type"] == "audio/webm"
    assert body["size_bytes"] == len(fake_audio)

    saved = tmp_path / body["file_path"].split("/")[-1]
    assert saved.exists()
    assert saved.read_bytes() == fake_audio


def test_upload_audio_rejects_non_audio_mime(client):
    lecture = _start_lecture(client)
    response = client.post(
        f"/lectures/{lecture['id']}/audio",
        files={"file": ("evil.txt", io.BytesIO(b"hello"), "text/plain")},
    )
    assert response.status_code == 415
```

- [ ] **Step 2: Run and watch fail**

Run:
```bash
cd backend && uv run pytest tests/test_audio.py -v
```

Expected: FAIL — `404` on POST /lectures/{id}/audio.

- [ ] **Step 3: Create the storage helper**

Create `backend/src/koherent/storage.py`:

```python
import uuid
from pathlib import Path

from koherent.config import settings


def storage_root() -> Path:
    root = Path(settings.audio_storage_dir)
    root.mkdir(parents=True, exist_ok=True)
    return root


def save_audio(content: bytes, suffix: str = ".webm") -> str:
    """Write `content` to disk under the configured storage root.
    Returns a path relative to the storage root."""
    root = storage_root()
    name = f"{uuid.uuid4()}{suffix}"
    (root / name).write_bytes(content)
    return name
```

- [ ] **Step 4: Add the audio schema**

Append to `backend/src/koherent/schemas.py`:

```python
class AudioRecordingRead(BaseModel):
    id: uuid.UUID
    lecture_id: uuid.UUID
    uploaded_by_student_id: uuid.UUID | None
    file_path: str
    mime_type: str
    size_bytes: int
    created_at: datetime
```

- [ ] **Step 5: Implement the upload route**

Append to `backend/src/koherent/routes/lectures.py`:

```python
from fastapi import File, UploadFile

from koherent.models import AudioRecording
from koherent.schemas import AudioRecordingRead
from koherent.storage import save_audio

_ALLOWED_AUDIO_MIME_PREFIXES = ("audio/",)


@router.post(
    "/{lecture_id}/audio",
    response_model=AudioRecordingRead,
    status_code=status.HTTP_201_CREATED,
)
def upload_audio(
    lecture_id: uuid.UUID,
    file: UploadFile = File(...),
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> AudioRecording:
    lecture = _load_lecture_for_student(lecture_id, current, db)

    mime = file.content_type or "application/octet-stream"
    if not any(mime.startswith(p) for p in _ALLOWED_AUDIO_MIME_PREFIXES):
        raise HTTPException(status_code=415, detail=f"Unsupported media type: {mime}")

    content = file.file.read()
    suffix = ".webm" if "webm" in mime else ".bin"
    relative_path = save_audio(content, suffix=suffix)

    recording = AudioRecording(
        lecture_id=lecture.id,
        uploaded_by_student_id=current.id,
        file_path=relative_path,
        mime_type=mime,
        size_bytes=len(content),
    )
    db.add(recording)
    db.commit()
    db.refresh(recording)
    return recording
```

- [ ] **Step 6: Run and watch pass**

Run:
```bash
cd backend && uv run pytest tests/test_audio.py -v
```

Expected: `2 passed`.

Then run the full suite:
```bash
cd backend && uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/src/koherent/storage.py backend/src/koherent/schemas.py backend/src/koherent/routes/lectures.py backend/tests/test_audio.py
git commit -m "feat(backend): POST /lectures/{id}/audio uploads audio to disk"
```

---

## Task 12: GET /lectures/{id} (lecture status, for UI)

**Files:**
- Modify: `backend/src/koherent/routes/lectures.py`
- Modify: `backend/tests/test_lectures.py`

- [ ] **Step 1: Add the failing test**

Append to `backend/tests/test_lectures.py`:

```python
def test_get_lecture_returns_status(client):
    klass = client.post("/classes", json={"name": "Econ 101"}).json()
    client.post(
        "/classes/join",
        json={"join_code": klass["join_code"], "display_name": "Alice"},
    )
    lecture = client.post("/lectures", json={"title": "Day 1"}).json()

    response = client.get(f"/lectures/{lecture['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == lecture["id"]
    assert body["title"] == "Day 1"
    assert body["ended_at"] is None
    assert body["my_notes_count"] == 0
    assert body["has_audio"] is False
```

- [ ] **Step 2: Run and watch fail**

Run:
```bash
cd backend && uv run pytest tests/test_lectures.py::test_get_lecture_returns_status -v
```

Expected: FAIL — `404` or `405`.

- [ ] **Step 3: Add response schema**

Append to `backend/src/koherent/schemas.py`:

```python
class LectureStatus(LectureRead):
    my_notes_count: int
    has_audio: bool
```

- [ ] **Step 4: Add the GET route**

Append to `backend/src/koherent/routes/lectures.py`:

```python
from sqlalchemy import func, select

from koherent.schemas import LectureStatus


@router.get("/{lecture_id}", response_model=LectureStatus)
def get_lecture(
    lecture_id: uuid.UUID,
    current: Student = Depends(get_current_student),
    db: Session = Depends(get_db),
) -> LectureStatus:
    lecture = _load_lecture_for_student(lecture_id, current, db)

    my_notes_count = db.scalar(
        select(func.count(Note.id)).where(
            Note.lecture_id == lecture.id, Note.student_id == current.id
        )
    ) or 0
    has_audio = bool(
        db.scalar(
            select(func.count(AudioRecording.id)).where(AudioRecording.lecture_id == lecture.id)
        )
    )
    return LectureStatus(
        id=lecture.id,
        class_id=lecture.class_id,
        title=lecture.title,
        started_at=lecture.started_at,
        ended_at=lecture.ended_at,
        my_notes_count=my_notes_count,
        has_audio=has_audio,
    )
```

- [ ] **Step 5: Run and watch pass**

Run:
```bash
cd backend && uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/src/koherent/schemas.py backend/src/koherent/routes/lectures.py backend/tests/test_lectures.py
git commit -m "feat(backend): GET /lectures/{id} returns status for the in-lecture UI"
```

---

## Task 13: Frontend scaffold (Next.js 15 + Tailwind)

**Files:**
- Create: `frontend/` (via `pnpm create next-app`)
- Modify: `frontend/.env.local.example`

- [ ] **Step 1: Scaffold the Next.js app**

Run from the repo root:
```bash
pnpm create next-app frontend \
  --typescript --tailwind --app --eslint --src-dir --no-import-alias --use-pnpm
```

Accept defaults for any remaining prompts. This generates a complete `frontend/` directory.

- [ ] **Step 2: Add `.env.local` files**

Create `frontend/.env.local.example`:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

And:
```bash
cp frontend/.env.local.example frontend/.env.local
```

- [ ] **Step 3: Verify dev server boots**

In one terminal:
```bash
cd frontend && pnpm dev
```

Open http://localhost:3000 — you should see the default Next.js welcome page. Kill the dev server (Ctrl-C) when verified.

- [ ] **Step 4: Commit**

```bash
git add frontend
git commit -m "feat(frontend): scaffold next.js 15 app with tailwind"
```

---

## Task 14: Frontend API client (`lib/api.ts`)

**Files:**
- Create: `frontend/src/lib/api.ts`

- [ ] **Step 1: Create the API client**

Create `frontend/src/lib/api.ts`:

```typescript
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${res.statusText}: ${body}`);
  }
  return res.json() as Promise<T>;
}

export type ClassCreated = {
  id: string;
  name: string;
  join_code: string;
  owner_token: string;
  created_at: string;
};

export type StudentSession = {
  student_id: string;
  class_id: string;
  display_name: string;
  session_token: string;
};

export type LectureRead = {
  id: string;
  class_id: string;
  title: string | null;
  started_at: string;
  ended_at: string | null;
};

export type LectureStatus = LectureRead & {
  my_notes_count: number;
  has_audio: boolean;
};

export type NoteRead = {
  id: string;
  lecture_id: string;
  student_id: string;
  content: string;
  client_timestamp_ms: number;
  created_at: string;
};

export const api = {
  createClass: (name: string) =>
    request<ClassCreated>("/classes", { method: "POST", body: JSON.stringify({ name }) }),

  joinClass: (joinCode: string, displayName: string) =>
    request<StudentSession>("/classes/join", {
      method: "POST",
      body: JSON.stringify({ join_code: joinCode, display_name: displayName }),
    }),

  me: () => request<StudentSession>("/me"),

  startLecture: (title: string | null) =>
    request<LectureRead>("/lectures", { method: "POST", body: JSON.stringify({ title }) }),

  getLecture: (id: string) => request<LectureStatus>(`/lectures/${id}`),

  postNote: (lectureId: string, content: string, clientTimestampMs: number) =>
    request<NoteRead>(`/lectures/${lectureId}/notes`, {
      method: "POST",
      body: JSON.stringify({ content, client_timestamp_ms: clientTimestampMs }),
    }),

  uploadAudio: async (lectureId: string, blob: Blob) => {
    const form = new FormData();
    form.append("file", blob, "lecture.webm");
    const res = await fetch(`${BASE}/lectures/${lectureId}/audio`, {
      method: "POST",
      credentials: "include",
      body: form,
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    return res.json();
  },
};
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat(frontend): typed api client wrapping backend endpoints"
```

---

## Task 15: Landing page + create-class page

**Files:**
- Modify: `frontend/src/app/page.tsx`
- Create: `frontend/src/app/create/page.tsx`

- [ ] **Step 1: Replace the landing page**

Replace `frontend/src/app/page.tsx`:

```tsx
import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-4xl font-semibold">Koherent</h1>
      <p className="text-neutral-600">AI-native notetaking for lectures.</p>
      <div className="flex gap-4">
        <Link
          href="/create"
          className="px-4 py-2 rounded bg-black text-white hover:bg-neutral-800"
        >
          Create a class
        </Link>
        <Link
          href="/join"
          className="px-4 py-2 rounded border border-black hover:bg-neutral-100"
        >
          Join a class
        </Link>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Create the create-class page**

Create `frontend/src/app/create/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { api, type ClassCreated } from "@/lib/api";

export default function CreateClassPage() {
  const [name, setName] = useState("");
  const [klass, setKlass] = useState<ClassCreated | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      setKlass(await api.createClass(name));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  }

  if (klass) {
    return (
      <main className="min-h-screen flex flex-col items-center justify-center gap-6 p-8">
        <h1 className="text-2xl font-semibold">Class created: {klass.name}</h1>
        <p className="text-neutral-600">Share this join code with your students:</p>
        <div className="text-5xl font-mono tracking-widest border-2 border-black rounded px-6 py-4">
          {klass.join_code}
        </div>
        <p className="text-xs text-neutral-500 max-w-md text-center">
          Keep your owner token safe — you&apos;ll need it for the professor dashboard in a future
          version: <code className="break-all">{klass.owner_token}</code>
        </p>
      </main>
    );
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-2xl font-semibold">Create a class</h1>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3 w-full max-w-sm">
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="e.g. Econ 101"
          required
          className="border border-neutral-300 rounded px-3 py-2"
        />
        <button
          type="submit"
          disabled={submitting || !name}
          className="px-4 py-2 rounded bg-black text-white disabled:opacity-50"
        >
          {submitting ? "Creating…" : "Create class"}
        </button>
        {error && <p className="text-red-600 text-sm">{error}</p>}
      </form>
    </main>
  );
}
```

Note: the import uses `@/lib/api`. If `pnpm create next-app` set up the `@/*` alias (default in `tsconfig.json` from the scaffold), this works as-is. If you opted out, change to a relative import.

- [ ] **Step 3: Manual test**

Start backend and frontend in two terminals:
```bash
# terminal 1
cd backend && uv run uvicorn koherent.main:app --reload --port 8000

# terminal 2
cd frontend && pnpm dev
```

Open http://localhost:3000, click "Create a class", enter `Econ 101`, submit. You should see a 6-character uppercase join code displayed.

Verify in the DB:
```bash
docker compose exec db psql -U koherent -d koherent -c "SELECT name, join_code FROM classes;"
```

Expected: a row showing your class.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/page.tsx frontend/src/app/create/page.tsx
git commit -m "feat(frontend): landing page and create-class flow"
```

---

## Task 16: Join page + class home

**Files:**
- Create: `frontend/src/app/join/page.tsx`
- Create: `frontend/src/app/class/page.tsx`

- [ ] **Step 1: Create the join page**

Create `frontend/src/app/join/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function JoinClassPage() {
  const router = useRouter();
  const [joinCode, setJoinCode] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await api.joinClass(joinCode.toUpperCase(), displayName);
      router.push("/class");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-2xl font-semibold">Join a class</h1>
      <form onSubmit={handleSubmit} className="flex flex-col gap-3 w-full max-w-sm">
        <input
          type="text"
          value={joinCode}
          onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
          placeholder="Join code (e.g. ABC123)"
          required
          maxLength={6}
          className="border border-neutral-300 rounded px-3 py-2 font-mono tracking-widest text-center"
        />
        <input
          type="text"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="Your name"
          required
          className="border border-neutral-300 rounded px-3 py-2"
        />
        <button
          type="submit"
          disabled={submitting || !joinCode || !displayName}
          className="px-4 py-2 rounded bg-black text-white disabled:opacity-50"
        >
          {submitting ? "Joining…" : "Join class"}
        </button>
        {error && <p className="text-red-600 text-sm">{error}</p>}
      </form>
    </main>
  );
}
```

- [ ] **Step 2: Create the class home page**

Create `frontend/src/app/class/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type StudentSession } from "@/lib/api";

export default function ClassHomePage() {
  const router = useRouter();
  const [session, setSession] = useState<StudentSession | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    api
      .me()
      .then(setSession)
      .catch(() => router.push("/join"));
  }, [router]);

  async function startLecture() {
    setStarting(true);
    setError(null);
    try {
      const lecture = await api.startLecture(null);
      router.push(`/lecture/${lecture.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setStarting(false);
    }
  }

  if (!session) {
    return <main className="p-8">Loading…</main>;
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-6 p-8">
      <h1 className="text-2xl font-semibold">Welcome, {session.display_name}</h1>
      <p className="text-neutral-600">
        Ready when class begins. Press start when the lecture kicks off.
      </p>
      <button
        onClick={startLecture}
        disabled={starting}
        className="px-6 py-3 rounded bg-black text-white text-lg disabled:opacity-50"
      >
        {starting ? "Starting…" : "Start a new lecture"}
      </button>
      {error && <p className="text-red-600 text-sm">{error}</p>}
    </main>
  );
}
```

- [ ] **Step 3: Manual test**

Backend and frontend still running. In an incognito window, go to http://localhost:3000/join, enter the join code from Task 15 and a name. You should land on `/class` showing "Welcome, [your name]". Click "Start a new lecture" — you'll be redirected to `/lecture/[id]` (which won't render anything yet; the page is built in Task 17). Verify in the DB:

```bash
docker compose exec db psql -U koherent -d koherent -c "SELECT s.display_name, l.id, l.started_at FROM students s JOIN lectures l ON l.created_by_student_id = s.id;"
```

Expected: one row showing your name and the lecture ID.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/join/page.tsx frontend/src/app/class/page.tsx
git commit -m "feat(frontend): join class flow and class home page"
```

---

## Task 17: In-lecture page — notes editor with autosave + audio recorder

**Files:**
- Create: `frontend/src/lib/recorder.ts`
- Create: `frontend/src/components/NoteEditor.tsx`
- Create: `frontend/src/components/AudioRecorder.tsx`
- Create: `frontend/src/app/lecture/[id]/page.tsx`

- [ ] **Step 1: Create the recorder helper**

Create `frontend/src/lib/recorder.ts`:

```typescript
export type RecorderState = "idle" | "recording" | "stopping";

export class LectureRecorder {
  private mediaRecorder: MediaRecorder | null = null;
  private chunks: BlobPart[] = [];
  private stream: MediaStream | null = null;

  async start(): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mr = new MediaRecorder(this.stream, { mimeType: "audio/webm" });
    this.chunks = [];
    mr.ondataavailable = (e) => {
      if (e.data.size > 0) this.chunks.push(e.data);
    };
    mr.start(1000); // emit a chunk per second
    this.mediaRecorder = mr;
  }

  stop(): Promise<Blob> {
    return new Promise((resolve, reject) => {
      const mr = this.mediaRecorder;
      if (!mr) {
        reject(new Error("Recorder not started"));
        return;
      }
      mr.onstop = () => {
        const blob = new Blob(this.chunks, { type: "audio/webm" });
        this.stream?.getTracks().forEach((t) => t.stop());
        this.stream = null;
        this.mediaRecorder = null;
        resolve(blob);
      };
      mr.stop();
    });
  }
}
```

- [ ] **Step 2: Create the note editor component**

Create `frontend/src/components/NoteEditor.tsx`:

```tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";

const FLUSH_INTERVAL_MS = 5_000;

export function NoteEditor({ lectureId, startedAt }: { lectureId: string; startedAt: number }) {
  const [text, setText] = useState("");
  const [savedCount, setSavedCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const bufferRef = useRef<string>("");
  const bufferStartRef = useRef<number>(Date.now());

  useEffect(() => {
    const interval = setInterval(async () => {
      const buf = bufferRef.current;
      if (!buf.trim()) return;
      const ts = bufferStartRef.current - startedAt;
      bufferRef.current = "";
      bufferStartRef.current = Date.now();
      try {
        await api.postNote(lectureId, buf, Math.max(ts, 0));
        setSavedCount((c) => c + 1);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        // restore buffer so we retry on next tick
        bufferRef.current = buf + bufferRef.current;
      }
    }, FLUSH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [lectureId, startedAt]);

  function onChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    const next = e.target.value;
    // Whatever's been added since the last flush goes into the buffer
    const added = next.slice(text.length);
    if (added) {
      if (!bufferRef.current) bufferStartRef.current = Date.now();
      bufferRef.current += added;
    }
    setText(next);
  }

  return (
    <div className="flex flex-col gap-2">
      <textarea
        value={text}
        onChange={onChange}
        placeholder="Type your notes…"
        className="w-full min-h-[400px] border border-neutral-300 rounded p-3 font-mono text-sm leading-relaxed"
      />
      <div className="flex items-center justify-between text-xs text-neutral-500">
        <span>{savedCount} batch{savedCount === 1 ? "" : "es"} saved</span>
        {error && <span className="text-red-600">save error: {error}</span>}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create the audio recorder component**

Create `frontend/src/components/AudioRecorder.tsx`:

```tsx
"use client";

import { useRef, useState } from "react";
import { api } from "@/lib/api";
import { LectureRecorder, type RecorderState } from "@/lib/recorder";

export function AudioRecorder({ lectureId }: { lectureId: string }) {
  const recorderRef = useRef<LectureRecorder | null>(null);
  const [state, setState] = useState<RecorderState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [uploadedSize, setUploadedSize] = useState<number | null>(null);

  async function handleStart() {
    setError(null);
    try {
      const r = new LectureRecorder();
      await r.start();
      recorderRef.current = r;
      setState("recording");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleStop() {
    if (!recorderRef.current) return;
    setState("stopping");
    try {
      const blob = await recorderRef.current.stop();
      await api.uploadAudio(lectureId, blob);
      setUploadedSize(blob.size);
      setState("idle");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setState("idle");
    } finally {
      recorderRef.current = null;
    }
  }

  return (
    <div className="border border-neutral-300 rounded p-4 flex flex-col gap-3">
      <div className="flex items-center gap-3">
        {state === "idle" && (
          <button
            onClick={handleStart}
            className="px-4 py-2 rounded bg-red-600 text-white hover:bg-red-700"
          >
            Record lecture
          </button>
        )}
        {state === "recording" && (
          <>
            <span className="inline-block w-3 h-3 rounded-full bg-red-600 animate-pulse" />
            <span className="text-sm font-medium">Recording…</span>
            <button
              onClick={handleStop}
              className="ml-auto px-4 py-2 rounded bg-black text-white hover:bg-neutral-800"
            >
              Stop & upload
            </button>
          </>
        )}
        {state === "stopping" && <span className="text-sm">Uploading…</span>}
      </div>
      {uploadedSize !== null && (
        <p className="text-xs text-neutral-500">
          Uploaded {(uploadedSize / 1024).toFixed(1)} KB.
        </p>
      )}
      {error && <p className="text-red-600 text-xs">{error}</p>}
    </div>
  );
}
```

- [ ] **Step 4: Create the in-lecture page**

Create `frontend/src/app/lecture/[id]/page.tsx`:

```tsx
"use client";

import { use, useEffect, useState } from "react";
import { api, type LectureStatus } from "@/lib/api";
import { NoteEditor } from "@/components/NoteEditor";
import { AudioRecorder } from "@/components/AudioRecorder";

export default function LecturePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [status, setStatus] = useState<LectureStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getLecture(id).then(setStatus).catch((err) => setError(String(err)));
  }, [id]);

  if (error) return <main className="p-8 text-red-600">Error: {error}</main>;
  if (!status) return <main className="p-8">Loading…</main>;

  const startedAtMs = new Date(status.started_at).getTime();

  return (
    <main className="max-w-3xl mx-auto p-6 flex flex-col gap-6">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{status.title ?? "Lecture in progress"}</h1>
        <span className="text-xs text-neutral-500 font-mono">{status.id.slice(0, 8)}</span>
      </header>
      <AudioRecorder lectureId={id} />
      <NoteEditor lectureId={id} startedAt={startedAtMs} />
    </main>
  );
}
```

- [ ] **Step 5: Manual test**

With backend and frontend running, walk through:
1. Open http://localhost:3000 in a regular window, click "Create a class", name it `Test Class`, note the join code.
2. In an incognito window, http://localhost:3000/join, enter the join code and the name `Alice`.
3. Click "Start a new lecture" — you land on `/lecture/[id]`.
4. Allow microphone permission when prompted.
5. Type several sentences in the notes area. Wait ~6 seconds. The "saved" counter increments to 1.
6. Click "Record lecture", talk for ~10 seconds, click "Stop & upload". You should see "Uploaded X.X KB."
7. Verify in DB:
   ```bash
   docker compose exec db psql -U koherent -d koherent -c \
     "SELECT count(*) FROM notes; SELECT count(*), sum(size_bytes) FROM audio_recordings;"
   ```
   Expected: notes count >= 1, audio_recordings count = 1.
8. Verify the file on disk:
   ```bash
   ls -la backend/storage/audio/
   ```
   Expected: a `.webm` file ~the size shown in the UI.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/recorder.ts frontend/src/components frontend/src/app/lecture
git commit -m "feat(frontend): in-lecture page with note autosave and audio recorder"
```

---

## Task 18: End-to-end smoke + README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Run the full E2E flow with two students**

With both servers running:
1. Window A (regular): create class `Econ 101`, note the join code.
2. Window B (incognito): join as `Alice`, start a lecture, get the lecture URL.
3. Window C (private window, different browser if possible): join as `Bob` with the same join code. You'll land on `/class`. Open the same lecture URL from window B.
4. Both Alice and Bob type notes in their respective windows.
5. Alice clicks "Record lecture", speaks for 30 seconds, stops.
6. Verify:
   ```bash
   docker compose exec db psql -U koherent -d koherent -c \
     "SELECT s.display_name, count(n.id) AS notes FROM students s LEFT JOIN notes n ON n.student_id = s.id GROUP BY s.display_name;"
   docker compose exec db psql -U koherent -d koherent -c \
     "SELECT lecture_id, size_bytes, mime_type FROM audio_recordings;"
   ls -la backend/storage/audio/
   ```
   Expected: both students have notes; one audio row; one `.webm` file on disk.

If anything fails, fix it before continuing.

- [ ] **Step 2: Write the root README**

Create `README.md`:

```markdown
# Koherent

AI-native notetaking app — students take notes during lecture, the system compares notes against the lecture audio, and produces per-student feedback plus an aggregated misconception dashboard for the professor.

See [project_plan.md](./project_plan.md) for the full product spec.

## Week 1 status

Foundation is in. The MVP loop persists:
- A professor creates a class and shares the join code
- Students join with a code + display name
- Students start a lecture, type timestamped notes (autosaved every 5s)
- One student records audio via the browser; on stop the file uploads to the backend

No AI processing yet — that's Week 2.

## Local development

### Prerequisites
- Docker Desktop
- Python 3.11+ via `uv` (https://docs.astral.sh/uv/)
- Node 20+ via `pnpm`

### One-time setup

```bash
# Start Postgres
docker compose up -d db

# Backend deps
cd backend && uv sync --extra dev
cp .env.example .env

# Create the test database (one-time)
docker compose exec db psql -U koherent -d koherent -c 'CREATE DATABASE koherent_test;'

# Apply migrations
uv run alembic upgrade head

# Frontend deps
cd ../frontend && pnpm install
cp .env.local.example .env.local
```

### Run

In three terminals:

```bash
# 1. Postgres (if not already running)
docker compose up -d db

# 2. Backend
cd backend && uv run uvicorn koherent.main:app --reload --port 8000

# 3. Frontend
cd frontend && pnpm dev
```

Open http://localhost:3000.

### Tests

```bash
cd backend && uv run pytest
```

## Repository layout

- `backend/` — FastAPI + SQLAlchemy + Alembic
- `frontend/` — Next.js 15 (App Router, TypeScript, Tailwind)
- `docker-compose.yml` — Postgres 16
- `docs/superpowers/plans/` — implementation plans (TDD task-by-task)
- `project_plan.md` — product/architecture spec
```

- [ ] **Step 3: Final commit**

```bash
git add README.md
git commit -m "docs: add README with run instructions"
```

- [ ] **Step 4: Final verification — all backend tests still pass**

```bash
cd backend && uv run pytest -v
```

Expected: all tests pass. If not, fix before declaring Week 1 done.

---

## Self-Review (already run)

- **Spec coverage:** Every Week 1 checklist item from `project_plan.md` lines 167–172 is implemented except "Sign up for NVIDIA Developer Program" and "Get NIM API key" (called out as user-only Prerequisites). Goal "upload a 5-min audio clip and typed notes, persist to DB" is met by Task 17 E2E test (and Task 18 with two students).
- **Placeholders:** None — every code block is complete.
- **Type consistency:** `StudentSession`, `LectureRead`, `LectureStatus`, `NoteRead`, `AudioRecordingRead`, `ClassCreated` are used identically across backend schemas and frontend `api.ts`.

## What's deferred to Week 2+

- All AI: transcription, embedding, claim extraction, judging, dashboard — Weeks 2–3 per `project_plan.md`.
- Lecture "end" endpoint and `ended_at` updates — add when needed.
- Owner / professor dashboard auth — Week 3 when the dashboard exists.
- Recording-active broadcast to other students — Week 4 dogfooding.
- Production deployment, CI, hosted DB — out of scope for Week 1.
