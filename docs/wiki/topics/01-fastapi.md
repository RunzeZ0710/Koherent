# 01 — FastAPI (the backend web framework)

> **Decisions on this page:** [D-001](#d-001-use-fastapi-as-the-backend-web-framework),
> [D-002](#d-002-validate-all-requests-and-responses-with-pydantic-schemas),
> [D-003](#d-003-split-routes-into-routers-by-resource),
> [D-004](#d-004-use-dependency-injection-for-db-and-auth)

---

## 1. The concept from zero

### What is a "backend"?

Koherent has two halves:

- The **frontend** is what runs in the student's web browser — the pages, the
  text box they type notes into, the Record button. It's the part a person sees
  and clicks.
- The **backend** is a program running on a server (for now, your laptop) that
  the frontend talks to over the network. It holds the real data, enforces the
  rules ("you can't post a note to a class you didn't join"), and talks to the
  database.

They are separate programs. They communicate by sending messages over the
network.

### What is an HTTP request?

When the browser needs something from the backend, it sends an **HTTP request**.
An HTTP request is, at heart, just a formatted block of text sent over the
network. It has:

- A **method** — the verb describing intent. The common ones:
  - `GET` = "give me something" (read, no side effects)
  - `POST` = "here's some data, create/do something" (write)
- A **path** — which resource, e.g. `/classes` or `/lectures/123/notes`
- Optional **headers** — metadata, e.g. "the body is JSON", or a cookie
- An optional **body** — the payload, usually **JSON** (a text format for
  structured data, like `{"name": "Econ 101"}`)

The backend sends back an **HTTP response**: a **status code** (a number — `200`
means OK, `201` means "created", `404` means "not found", `401` means "not
authenticated"), optional headers, and usually a JSON body.

So the whole conversation for "create a class" looks like:

```
Browser  ──►  POST /classes   body: {"name": "Econ 101"}
Backend  ◄──  201 Created      body: {"id": "...", "join_code": "ABC123", ...}
```

### What is an API?

An **API** (Application Programming Interface) is just the agreed-upon set of
those request/response shapes. "When you `POST /classes` with a `name`, you get
back an `id` and a `join_code`." The collection of all such endpoints *is* our
API. The frontend is written against this contract.

### What is a web framework, and what is FastAPI?

Writing code to literally read bytes off a network socket, parse the HTTP text,
figure out the method and path, and format a response by hand is tedious and
error-prone. A **web framework** does all that plumbing for you. You write
ordinary functions; the framework calls the right one when a matching request
arrives, hands you the parsed data, and turns your return value into a response.

**FastAPI** is the Python web framework we use for the backend. The name is its
pitch: it's *fast* to write and *fast* to run. Its defining feature is that it
uses Python's **type hints** to do a lot of work automatically — validation,
documentation, and editor autocomplete — which we lean on heavily (see §2).

---

## 2. What we chose

**[D-001] FastAPI is our backend web framework.** Every endpoint
(`POST /classes`, `GET /lectures/{id}`, etc.) is a Python function decorated to
tell FastAPI which method+path triggers it.

Here is the simplest endpoint in the codebase — the health check in
[`backend/src/koherent/main.py`](../../../backend/src/koherent/main.py):

```python
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

`@app.get("/health")` says "run this function on `GET /health`". The returned
dict becomes the JSON response `{"status": "ok"}` with status `200`. That's the
whole model: **a URL maps to a Python function.**

**[D-002] We validate every request and response with Pydantic schemas.**
Pydantic is a data-validation library that ships with FastAPI. You declare the
*shape* of your data as a class, and FastAPI enforces it automatically. From
[`backend/src/koherent/schemas.py`](../../../backend/src/koherent/schemas.py):

```python
class ClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
```

When `POST /classes` declares its input as `ClassCreate`, FastAPI will:

- parse the incoming JSON,
- check `name` is a string between 1 and 200 characters,
- and if it's wrong (missing, empty, too long, not a string), **reject the
  request with a `422` error before our code ever runs.**

That's why our route handler can just trust `payload.name` exists and is valid —
the validation happened at the door. There's a test that proves an empty name
gets a `422` (`test_create_class_rejects_empty_name`).

The same idea runs in reverse for responses. `response_model=ClassCreated` tells
FastAPI exactly which fields to put in the reply — so we can't accidentally leak
a field we didn't mean to.

**[D-003] Routes are split into "routers" by resource.** Rather than one giant
file with every endpoint, related endpoints are grouped:

- [`routes/classes.py`](../../../backend/src/koherent/routes/classes.py) —
  `POST /classes`, `POST /classes/join`
- [`routes/lectures.py`](../../../backend/src/koherent/routes/lectures.py) —
  `POST /lectures`, `GET /lectures/{id}`, `POST /lectures/{id}/notes`,
  `POST /lectures/{id}/audio`

Each file creates an `APIRouter` with a shared URL prefix, and `main.py` mounts
them:

```python
app.include_router(classes.router)
app.include_router(lectures.router)
```

**[D-004] We use FastAPI's "dependency injection" for shared setup.** This
sounds fancy; it just means: instead of every handler writing the same setup
code (open a database connection; figure out who the logged-in student is), we
write that once as a function, and *declare* in the handler's signature that we
need it. FastAPI runs it and passes the result in. From
[`routes/lectures.py`](../../../backend/src/koherent/routes/lectures.py):

```python
def start_lecture(
    payload: LectureCreate,
    current: Student = Depends(get_current_student),  # who is calling?
    db: Session = Depends(get_db),                    # a DB session
) -> Lecture:
    ...
```

The `Depends(...)` markers tell FastAPI: "before running this, call
`get_current_student` and `get_db`, and hand me the results as `current` and
`db`." If `get_current_student` raises a `401` (no valid session), the handler
never runs. This keeps auth and DB wiring out of the business logic — see
[03-auth-and-sessions](03-auth-and-sessions.md) and
[02-sqlalchemy](02-sqlalchemy.md).

---

## 3. What we rejected, and why

- **Flask / Django (the other big Python frameworks).** Flask is older and
  minimal but doesn't give you typed validation or auto-generated API docs out
  of the box — you'd bolt on extra libraries to get what FastAPI includes.
  Django is a heavyweight "batteries-included" framework built around its own
  ORM and server-rendered HTML templates; it's excellent for traditional
  websites but heavy for a JSON API that has a separate JavaScript frontend.
  FastAPI is purpose-built for exactly our shape: a typed JSON API consumed by a
  separate frontend.
- **A non-Python backend (Node/Express, Go, etc.).** Python wins here for a
  project-specific reason: **Week 2 is an AI pipeline** (speech-to-text,
  embeddings, clustering), and that ecosystem is overwhelmingly Python. Keeping
  the backend in Python means the AI work lives in the same language and process
  as everything else. See [project_plan.md](../../../project_plan.md).
- **No validation layer (trusting incoming JSON).** Tempting for speed, but it
  pushes every "what if this field is missing/garbage?" check into your business
  logic, where it's easy to forget one. Pydantic makes invalid requests fail
  loudly and uniformly at the boundary. Cheap insurance.
- **Manually opening a DB connection inside each handler.** Works, but you
  repeat the open/close dance everywhere and it's easy to leak a connection if
  you forget to close it on an error path. Dependency injection centralizes it.

---

## 4. In our code

| Thing | Where |
|-------|-------|
| App creation, CORS, router mounting, `/health`, `/me` | [`backend/src/koherent/main.py`](../../../backend/src/koherent/main.py) |
| Request/response shapes (Pydantic) | [`backend/src/koherent/schemas.py`](../../../backend/src/koherent/schemas.py) |
| `classes`/`join` endpoints | [`backend/src/koherent/routes/classes.py`](../../../backend/src/koherent/routes/classes.py) |
| `lectures`/`notes`/`audio` endpoints | [`backend/src/koherent/routes/lectures.py`](../../../backend/src/koherent/routes/lectures.py) |
| Injected dependencies (`get_db`, `get_current_student`) | [`backend/src/koherent/deps.py`](../../../backend/src/koherent/deps.py) |

**A note on CORS.** In `main.py` you'll see `CORSMiddleware`. Browsers have a
security rule that a page served from one origin (e.g. `localhost:3002`, our
frontend) is **not** allowed to call a different origin (`localhost:8000`, our
backend) unless the backend explicitly permits it. CORS (Cross-Origin Resource
Sharing) is that permission. We allow our frontend origin and
`allow_credentials=True` so the session cookie is allowed to ride along. The
allowed origin is configured, not hardcoded — see
[06-config-and-migrations](06-config-and-migrations.md).

**Free bonus: interactive API docs.** Because every endpoint is typed, FastAPI
auto-generates a live, clickable documentation page. With the backend running,
open <http://localhost:8000/docs> to see every endpoint and try it in the
browser. We didn't write that; the type hints earned it.

---

## 5. Decision records

### D-001: Use FastAPI as the backend web framework

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** We need a backend that exposes a JSON API to a separate
  JavaScript frontend, in a language that won't fight us when the Week 2 AI
  pipeline lands.
- **Decision:** Use FastAPI (Python) for all backend HTTP endpoints.
- **Why:** Purpose-built for typed JSON APIs; automatic request validation and
  interactive docs from type hints; Python keeps us in the same ecosystem as the
  upcoming AI work.
- **Alternatives rejected:** Flask (less built-in, more assembly required);
  Django (heavy, template-oriented); Node/Go (would split the codebase away from
  the Python AI stack).

### D-002: Validate all requests and responses with Pydantic schemas

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** Incoming JSON from the network is untrusted and can be malformed.
- **Decision:** Define a Pydantic model for every request body and use
  `response_model` for every reply.
- **Why:** Invalid input is rejected uniformly at the boundary (`422`) before
  business logic runs; responses can't accidentally leak unintended fields;
  the schema doubles as documentation.
- **Alternatives rejected:** Trusting raw JSON and hand-checking fields inside
  handlers (easy to forget a check; scatters validation everywhere).

### D-003: Split routes into routers by resource

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** A single endpoints file grows unwieldy and mixes unrelated
  concerns.
- **Decision:** Group endpoints into `APIRouter`s per resource (`classes`,
  `lectures`) and mount them in `main.py`.
- **Why:** Smaller, focused files; clear ownership of URL prefixes; easier to
  navigate and test.
- **Alternatives rejected:** One monolithic routes file (harder to read as the
  API grows).

### D-004: Use dependency injection for DB and auth

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** Every authenticated endpoint needs a DB session and the current
  student; repeating that setup invites bugs.
- **Decision:** Express shared setup as dependency functions (`get_db`,
  `get_current_student`) and request them via `Depends(...)`.
- **Why:** Centralizes wiring and lifecycle (open/close, auth checks); keeps
  business logic clean; makes tests able to swap the real DB session for a test
  one (see [05-testing](05-testing.md)).
- **Alternatives rejected:** Manually constructing the session and decoding the
  cookie inside each handler (repetitive, leak-prone, untestable in isolation).
