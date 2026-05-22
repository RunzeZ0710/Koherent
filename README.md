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

> **Port note:** This repo runs Postgres on host port **5433** (not the default 5432) so it can coexist with another local Postgres. The container still listens on 5432 internally; only the host port mapping differs.

### One-time setup

```bash
# Start Postgres (host port 5433)
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
- `frontend/` — Next.js (App Router, TypeScript, Tailwind)
- `docker-compose.yml` — Postgres 16 (host port 5433)
- `docs/superpowers/plans/` — implementation plans (TDD task-by-task)
- `project_plan.md` — product/architecture spec
