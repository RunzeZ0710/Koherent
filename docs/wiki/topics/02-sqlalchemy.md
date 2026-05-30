# 02 — SQLAlchemy (talking to the database)

> **Decisions on this page:** [D-005](#d-005-use-the-sqlalchemy-orm-instead-of-raw-sql),
> [D-006](#d-006-use-postgresql-as-the-database),
> [D-007](#d-007-one-db-session-per-request-via-get_db)

---

## 1. The concept from zero

### What is a database?

The backend needs to *remember* things between requests — which classes exist,
who joined them, what notes were typed. If it kept that only in the program's
memory, everything would vanish the moment the program restarted. A **database**
is a separate program whose entire job is to store data durably (on disk) and
let other programs query and update it reliably, even with many requests
happening at once.

We use a **relational database**, which organizes data into **tables**. A table
is like a spreadsheet:

- Each **row** is one record (one class, one student, one note).
- Each **column** is a field of that record (a class's `name`, its `join_code`).
- Tables can **reference each other**: a `students` row stores the `id` of the
  `classes` row it belongs to. That reference is called a **foreign key**, and
  it's what makes the database "relational." (More on this in
  [04-data-model](04-data-model.md).)

### What is SQL?

You talk to a relational database in a language called **SQL** (Structured Query
Language). For example, "get the class whose join code is ABC123" is:

```sql
SELECT * FROM classes WHERE join_code = 'ABC123';
```

SQL is powerful and universal, but writing it as raw strings inside your Python
has two annoyances: (1) you're constantly translating between database rows and
Python objects by hand, and (2) building query strings from user input is a
classic source of a serious security bug called **SQL injection** (where a
malicious value smuggles in extra SQL).

### What is an ORM?

An **ORM** (Object-Relational Mapper) is a library that lets you work with
database rows as ordinary Python objects, and writes the SQL for you. You define
a Python class `Class`; the ORM maps it to the `classes` table. You create
`Class(name="Econ 101")` and call `db.add(...)`; the ORM generates the
`INSERT` statement. You write a query in Python; the ORM compiles it to safe,
parameterized SQL (which closes the injection hole automatically).

**SQLAlchemy** is the ORM we use. It's the de-facto standard for Python.

---

## 2. What we chose

**[D-005] We use the SQLAlchemy ORM rather than writing raw SQL.** Our tables
are defined as Python classes in
[`backend/src/koherent/models.py`](../../../backend/src/koherent/models.py).
Here's the `Class` table, lightly trimmed:

```python
class Class(Base):
    __tablename__ = "classes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    join_code: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    owner_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

Each `mapped_column` is a column in the `classes` table, and the annotations
describe its type and constraints (`unique=True` means no two rows can share
that value; `nullable=False` means it's required; `index=True` makes lookups by
that column fast). Reading this class top-to-bottom *is* reading the table's
schema.

Working with rows then looks like normal Python. Creating a class
([`routes/classes.py`](../../../backend/src/koherent/routes/classes.py)):

```python
klass = Class(name=payload.name, join_code=candidate, owner_token=secrets.token_urlsafe(32))
db.add(klass)
db.commit()
```

Looking one up by join code ([`routes/classes.py`](../../../backend/src/koherent/routes/classes.py)):

```python
klass = db.scalar(select(Class).where(Class.join_code == payload.join_code.upper()))
```

No SQL strings; SQLAlchemy turns `select(Class).where(...)` into safe SQL.

**[D-006] The database is PostgreSQL** ("Postgres"), running in a Docker
container (see [06-config-and-migrations](06-config-and-migrations.md)).
SQLAlchemy is the ORM (the Python-side abstraction); Postgres is the actual
storage engine underneath it.

**[D-007] We use one database session per HTTP request.** A **session** is
SQLAlchemy's workspace for a unit of work: it tracks the objects you've added or
changed and flushes them to the database, and it wraps your changes in a
**transaction** (an all-or-nothing batch — if something fails partway, nothing
is half-written). We open a fresh session at the start of each request and close
it at the end, via the `get_db` dependency in
[`backend/src/koherent/deps.py`](../../../backend/src/koherent/deps.py):

```python
def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
```

The `try/finally` guarantees the session is closed even if the handler raises an
error — no leaked connections. Every endpoint that needs the database receives
this session through `Depends(get_db)` (see
[01-fastapi → D-004](01-fastapi.md#d-004-use-dependency-injection-for-db-and-auth)).

### Engine vs. session (the two-layer picture)

In [`backend/src/koherent/db.py`](../../../backend/src/koherent/db.py):

```python
engine = create_engine(settings.database_url, future=True)
SessionLocal = sessionmaker(bind=engine, ...)
```

- The **engine** is the long-lived, app-wide object that manages the actual
  connections to Postgres (it pools and reuses them). You create it once.
- A **session** is short-lived and per-request; it borrows a connection from the
  engine to do its work, then returns it. `SessionLocal()` is the factory that
  produces one.

The `Base` class in the same file is the common parent every model inherits
from; it's how SQLAlchemy keeps a registry of all our tables (which Alembic and
the tests both rely on — see [05-testing](05-testing.md) and
[06-config-and-migrations](06-config-and-migrations.md)).

---

## 3. What we rejected, and why

- **Raw SQL strings.** More control and zero abstraction, but you hand-map rows
  to objects everywhere, and you must be meticulous about parameterization to
  avoid SQL injection. For a CRUD-shaped app like Week 1, the ORM removes a
  whole category of busywork and bugs.
- **SQLite instead of Postgres.** SQLite is a zero-setup file-based database and
  is genuinely great for tiny apps. We passed for two reasons: (1) it lacks
  features we use, notably a native `UUID` column type and proper concurrent
  writes; and (2) we want our **tests to run against the same engine as
  production** so "passes in tests" actually means something (see
  [05-testing → D-017](05-testing.md#d-017-test-against-real-postgres-not-sqlite-or-mocks)).
  Developing on SQLite and deploying on Postgres is a well-known source of
  "worked on my machine" surprises.
- **A "NoSQL" document store (e.g. MongoDB).** Our data is highly relational —
  students belong to classes, notes belong to lectures and students. Relational
  tables with foreign keys model that naturally and let the database *enforce*
  the relationships. A document store would push that integrity work back into
  our application code.
- **A heavier all-in-one framework's built-in ORM (e.g. Django ORM).** That
  would have meant adopting Django wholesale, which we already declined in
  [01-fastapi → D-001](01-fastapi.md#d-001-use-fastapi-as-the-backend-web-framework).
  SQLAlchemy is framework-agnostic and pairs cleanly with FastAPI.

---

## 4. In our code

| Thing | Where |
|-------|-------|
| Engine, `SessionLocal` factory, `Base` | [`backend/src/koherent/db.py`](../../../backend/src/koherent/db.py) |
| Table/model definitions | [`backend/src/koherent/models.py`](../../../backend/src/koherent/models.py) |
| Per-request session dependency (`get_db`) | [`backend/src/koherent/deps.py`](../../../backend/src/koherent/deps.py) |
| Example writes/queries | [`backend/src/koherent/routes/classes.py`](../../../backend/src/koherent/routes/classes.py), [`routes/lectures.py`](../../../backend/src/koherent/routes/lectures.py) |
| The database connection string | [`backend/src/koherent/config.py`](../../../backend/src/koherent/config.py) |

The full table-by-table breakdown — relationships, keys, cascade behavior — is
its own topic: [04-data-model](04-data-model.md).

---

## 5. Decision records

### D-005: Use the SQLAlchemy ORM instead of raw SQL

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** The backend must persist and query relational data from Python.
- **Decision:** Use SQLAlchemy's ORM; define tables as Python classes; build
  queries with SQLAlchemy expressions rather than SQL strings.
- **Why:** Work with rows as Python objects; SQLAlchemy generates safe,
  parameterized SQL (eliminating SQL-injection risk); the model classes double
  as living schema documentation.
- **Alternatives rejected:** Raw SQL (repetitive row↔object mapping, injection
  risk); a different framework's bundled ORM (would force adopting that whole
  framework).

### D-006: Use PostgreSQL as the database

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** We need a durable, concurrent, feature-complete relational store.
- **Decision:** Use PostgreSQL 16, run locally via docker-compose.
- **Why:** Native `UUID` type, real concurrency, and a feature set we won't
  outgrow; running the same engine in dev, test, and (eventually) production
  avoids environment-specific surprises.
- **Alternatives rejected:** SQLite (missing features; engine mismatch with
  production); a NoSQL document store (our data is relational and benefits from
  DB-enforced integrity).

### D-007: One DB session per request, via `get_db`

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** Database work needs a session with a clear, safe lifecycle, and
  many endpoints need one.
- **Decision:** Open a fresh `SessionLocal()` per request in the `get_db`
  dependency and always close it in a `finally`; inject it with `Depends`.
- **Why:** Guarantees cleanup even on errors (no leaked connections); scopes a
  transaction to a request; and makes the session swappable in tests (the test
  suite overrides `get_db`).
- **Alternatives rejected:** A single shared global session (not safe under
  concurrency); per-handler manual session management (repetitive, leak-prone).
