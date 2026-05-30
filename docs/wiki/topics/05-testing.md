# 05 — Testing (TDD, real Postgres, isolated tests)

> **Decisions on this page:** [D-016](#d-016-test-driven-development-on-every-backend-endpoint),
> [D-017](#d-017-test-against-real-postgres-not-sqlite-or-mocks),
> [D-018](#d-018-isolate-tests-with-a-rollback-per-test-transaction)

---

## 1. The concept from zero

### What is an automated test?

An **automated test** is just code that runs your other code and checks the
result is what you expect. Instead of manually clicking through the app to see if
"create a class" works, you write a function that calls the endpoint and asserts
the response is correct. Then a **test runner** runs all such functions at once
and reports pass/fail. Ours is **pytest**, the standard Python test runner.

A backend test in this project reads almost like the English description of the
behavior. From
[`backend/tests/test_classes.py`](../../../backend/tests/test_classes.py):

```python
def test_create_class_returns_id_and_join_code(client, db):
    response = client.post("/classes", json={"name": "Econ 101"})

    assert response.status_code == 201
    body = response.json()
    assert len(body["join_code"]) == 6
    assert body["join_code"].isalnum()
```

`client` is a fake HTTP client that calls our app in-process (no real network
needed); `assert` statements state what must be true. If any assertion is false,
the test fails.

### Why bother?

Two payoffs. First, **confidence**: when a test suite passes, you know the
behaviors it covers still work — so you can change code without manually
re-checking everything. Second, **a safety net for change**: the real value
shows up next week, when adding the AI pipeline could accidentally break the note
endpoint. The test catches it instantly instead of in a demo.

### What is TDD?

**Test-Driven Development** flips the usual order. Instead of write-code-then-
maybe-test, you:

1. **Red** — write a test for the behavior you want. Run it; it *fails* (the
   feature doesn't exist yet). This proves the test actually checks something.
2. **Green** — write the minimum code to make it pass.
3. **Refactor** — clean up, with the test guarding you.

Writing the test first forces you to decide what the endpoint *should do* —
its inputs, outputs, and error cases — before you're deep in implementation
details. The plan for Week 1 was built this way: each endpoint's task literally
says "write the failing test, watch it fail, then implement."

---

## 2. What we chose

**[D-016] Every backend endpoint is developed with TDD.** The test files mirror
the features one-to-one:

| Test file | Covers |
|-----------|--------|
| [`test_health.py`](../../../backend/tests/test_health.py) | `/health` liveness |
| [`test_models.py`](../../../backend/tests/test_models.py) | models persist and relate correctly |
| [`test_classes.py`](../../../backend/tests/test_classes.py) | `POST /classes` (incl. empty-name `422`) |
| [`test_join.py`](../../../backend/tests/test_join.py) | join: success, unknown code `404`, duplicate name `409`, cookie set |
| [`test_session.py`](../../../backend/tests/test_session.py) | `/me`, and `401` without a session |
| [`test_lectures.py`](../../../backend/tests/test_lectures.py) | start lecture, `401` without session, `GET` status |
| [`test_notes.py`](../../../backend/tests/test_notes.py) | post note, cross-class `403`, unknown lecture `404` |
| [`test_audio.py`](../../../backend/tests/test_audio.py) | upload audio (file written), non-audio mime `415` |

Note how many tests check the **error** cases (`401`, `403`, `404`, `409`,
`415`, `422`), not just the happy path. The error behavior *is* the contract —
"you can't post to another class's lecture" is a rule worth a permanent test.

To run them:

```bash
cd backend && uv run pytest
```

**[D-017] Tests run against a real PostgreSQL database**, not a substitute. There
is a dedicated `koherent_test` database (separate from the dev database), pointed
at by `test_database_url` in
[`config.py`](../../../backend/src/koherent/config.py). The reason is a principle
worth internalizing: **test against what you actually run in production.** If we
tested against SQLite (a different engine) for speed, a test passing wouldn't
guarantee the code works on Postgres — the two differ in types (we use Postgres's
native `UUID`), constraint behavior, and SQL dialect. A green test would be a
false reassurance. Using the real engine means green means green. (This is the
test-side reason we also chose Postgres in
[02-sqlalchemy → D-006](02-sqlalchemy.md#d-006-use-postgresql-as-the-database).)

**[D-018] Each test is fully isolated by running inside a transaction that is
rolled back afterward.** This solves a problem every test suite hits: tests share
one database, so one test's data can pollute the next, making results depend on
order. The fix used here is a clean trick in
[`backend/tests/conftest.py`](../../../backend/tests/conftest.py)
(`conftest.py` is pytest's special file for shared test setup, called
**fixtures**):

- Before each test: open a connection and **begin a transaction**.
- Run the test inside it. The test can write rows, and the route handlers can
  even call `commit()` — but...
- After each test: **roll the whole transaction back.** Every change vanishes, so
  the next test starts from a pristine database.

The wrinkle: our route handlers *do* call `db.commit()`, and a normal commit
would permanently save data, defeating the rollback. The fixture handles this
with a **SAVEPOINT** (a nested, named checkpoint inside a transaction). A handler
calling `commit()` releases the savepoint instead of committing for real, and a
small event listener immediately opens a new savepoint so the next `commit()`
works too. The outer transaction — which is never really committed — is rolled
back at the end, erasing everything. The code, with its own explanatory comment:

```python
@pytest.fixture()
def db(_engine):
    """Uses the SQLAlchemy 'join an external transaction' pattern: the outer
    transaction is rolled back at teardown, and any session.commit() inside a
    route handler releases a SAVEPOINT (started by begin_nested) rather than
    committing to the test DB."""
    connection = _engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, ...)
    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):
        nonlocal nested
        if trans.nested and not trans._parent.nested:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()   # <- undoes everything the test did
        connection.close()
```

The other half is the `client` fixture, which makes the app-under-test use *this*
isolated session instead of a real one. It does that with FastAPI's dependency
override (recall `get_db` from
[02-sqlalchemy → D-007](02-sqlalchemy.md#d-007-one-db-session-per-request-via-get_db)):

```python
@pytest.fixture()
def client(db):
    def _override_get_db():
        yield db
    app.dependency_overrides[get_db] = _override_get_db   # swap real session for the test one
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
```

This is exactly the payoff of dependency injection
([01-fastapi → D-004](01-fastapi.md#d-004-use-dependency-injection-for-db-and-auth)):
because the app *asks* for its DB session rather than constructing it, the tests
can hand it a transaction-wrapped one without changing a single line of
application code.

---

## 3. What we rejected, and why

- **No tests / manual testing only (for the backend).** Fine for a throwaway
  script, but the whole point of Week 1 is to be a stable foundation the AI
  pipeline builds on. Manual testing doesn't scale and won't catch a regression
  introduced three weeks later. (The *frontend* is deliberately manual-tested for
  now — UI is more awkward to test and changes shape fast early on; that's a
  conscious, revisitable trade.)
- **Testing against SQLite for speed.** Faster and zero-setup, but a different
  engine than production — a pass wouldn't prove the code works on Postgres. See
  [D-017](#d-017-test-against-real-postgres-not-sqlite-or-mocks).
- **Mocking the database entirely** (replacing it with fake in-memory objects).
  Fastest of all, but then you're testing your mocks, not your real SQL,
  constraints, or relationships. The cross-class `403` and duplicate-name `409`
  tests are only meaningful against a real database enforcing real rules.
- **Recreating the whole schema (drop/create all tables) before every single
  test.** Correct, but slow. The rollback-per-test approach gives the same
  isolation far faster — the schema is built once per test session, and each
  test just rolls back its own changes.

---

## 4. In our code

| Thing | Where |
|-------|-------|
| Shared fixtures: isolated `db`, overridden `client`, schema setup | [`backend/tests/conftest.py`](../../../backend/tests/conftest.py) |
| The test files | [`backend/tests/`](../../../backend/tests/) (table above) |
| Test DB connection string | [`backend/src/koherent/config.py`](../../../backend/src/koherent/config.py) (`test_database_url`) |
| Test runner config (pytest) | [`backend/pyproject.toml`](../../../backend/pyproject.toml) (`[tool.pytest.ini_options]`) |

Run everything with `cd backend && uv run pytest`. (More on `uv` and config in
[06-config-and-migrations](06-config-and-migrations.md).)

---

## 5. Decision records

### D-016: Test-driven development on every backend endpoint

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** Week 1 is the foundation later weeks build on; regressions must be
  caught automatically.
- **Decision:** Write a failing test for each endpoint's behavior (happy path and
  error cases) before implementing it; keep the suite green.
- **Why:** Forces a clear spec of inputs/outputs/errors up front; provides a
  regression safety net for the upcoming AI work; error-case tests pin down the
  API contract.
- **Alternatives rejected:** No tests / manual-only (doesn't scale, misses later
  regressions).

### D-017: Test against real Postgres (not SQLite or mocks)

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** A passing test should guarantee the code works where it really
  runs.
- **Decision:** Run the suite against a dedicated `koherent_test` PostgreSQL
  database — the same engine as dev/production.
- **Why:** SQLite and mocks differ from Postgres in types, constraints, and SQL;
  testing on them yields false confidence. Real engine ⇒ green means green.
- **Alternatives rejected:** SQLite (engine mismatch); full DB mocking (tests the
  mocks, not real SQL/constraints).

### D-018: Isolate tests with a rollback-per-test transaction

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** Tests share one database and must not pollute each other, even
  though route handlers call `commit()`.
- **Decision:** Wrap each test in an outer transaction rolled back at teardown;
  use a SAVEPOINT (`begin_nested` + an `after_transaction_end` listener) so
  handler `commit()`s release the savepoint instead of persisting; override
  `get_db` so the app uses this session.
- **Why:** Gives perfect per-test isolation and order-independence without the
  cost of rebuilding the schema each test; works transparently with code that
  commits.
- **Alternatives rejected:** Drop/create all tables per test (correct but slow);
  hoping tests don't collide (flaky, order-dependent).
