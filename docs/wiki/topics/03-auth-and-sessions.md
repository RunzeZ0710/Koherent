# 03 — Authentication & Sessions

> **Decisions on this page:** [D-008](#d-008-auth-is-join-code--display-name-no-passwords),
> [D-009](#d-009-sessions-are-opaque-random-tokens-in-httponly-cookies),
> [D-010](#d-010-6-char-join-codes-generated-with-collision-retry)

---

## 1. The concept from zero

### Authentication vs. authorization

Two related-but-different ideas, and it helps to keep them straight:

- **Authentication** ("authn") = *who are you?* Proving identity.
- **Authorization** ("authz") = *are you allowed to do this?* Checking
  permissions.

A student joins a class and proves "I'm Alice in Econ 101" (authentication).
When Alice tries to post a note to a lecture, we check that the lecture belongs
to her class (authorization). This page is mostly about authentication; the
authorization checks live with the data model in
[04-data-model](04-data-model.md) and the route handlers.

### The core problem: HTTP forgets you

HTTP is **stateless**. Each request stands alone — the backend doesn't
inherently know that the request asking to post a note is "the same person" who
joined the class a minute ago. Every request arrives as a stranger.

To create the experience of being "logged in," we need something the browser can
attach to *every* request that says "it's still me." That something is a
**session token**.

### What is a cookie?

A **cookie** is a small piece of text the backend asks the browser to store and
then automatically send back on every subsequent request to that site. The flow:

1. You join a class. The backend replies with a `Set-Cookie` header containing
   your session token.
2. The browser saves it.
3. On every later request, the browser automatically includes that cookie.
4. The backend reads the cookie, looks up who it belongs to, and now knows it's
   you.

That's how "logged in" works under the hood: a cookie carrying a token, replayed
on each request.

### Why "httpOnly" matters

A cookie can be marked **httpOnly**, which means JavaScript running in the page
*cannot read it* — only the browser, sending it over HTTP, can. This is a defense
against **XSS** (cross-site scripting), where an attacker manages to run
malicious JavaScript in your page. If the session token lived somewhere
JavaScript could read (like `localStorage`), that script could steal it. An
httpOnly cookie is invisible to such script.

---

## 2. What we chose

**[D-008] Authentication is just a join code + a display name. No passwords, no
email, no accounts.** To get in, a student enters the 6-character class code and
types a name. That's the entire signup/login flow.

This is a deliberate scoping decision. Koherent's job is to capture notes during
a class everyone is physically attending; it is not a system guarding sensitive
personal data. Real accounts (email verification, password hashing, reset
flows, "forgot password" emails) are a large amount of engineering and a large
attack surface. For the product we're building this week, they'd be pure
overhead. We can always add real auth later if the product needs it.

**[D-009] A session is an opaque random token, stored on the student's row and
set as an httpOnly cookie.** When a student joins
([`routes/classes.py`](../../../backend/src/koherent/routes/classes.py)):

```python
student = Student(
    class_id=klass.id,
    display_name=payload.display_name,
    session_token=secrets.token_urlsafe(32),   # the opaque token
)
db.add(student)
db.commit()

response.set_cookie(
    SESSION_COOKIE_NAME,          # "koherent_session"
    student.session_token,
    httponly=True,                # JS can't read it
    samesite="lax",               # basic CSRF mitigation
    max_age=60 * 60 * 24 * 30,    # 30 days
)
```

Two terms worth unpacking:

- **"Opaque token"** means the token carries no information itself — it's just 32
  bytes of randomness from `secrets.token_urlsafe(32)`. (`secrets` is Python's
  *cryptographically secure* random generator, the right tool for anything
  security-related — unlike the ordinary `random` module, which is predictable.)
  To find out who a token belongs to, you look it up in the database. There's
  nothing to forge or decode because there's nothing encoded in it.
- **`samesite="lax"`** is a mitigation against **CSRF** (cross-site request
  forgery), where another website tries to make your browser fire authenticated
  requests at us using your cookie. `lax` tells the browser not to send our
  cookie on cross-site requests in the risky cases.

On each later request, the `get_current_student` dependency in
[`backend/src/koherent/deps.py`](../../../backend/src/koherent/deps.py) reads the
cookie and resolves it to a `Student`:

```python
def get_current_student(
    koherent_session: str | None = Cookie(default=None, alias=SESSION_COOKIE_NAME),
    db: Session = Depends(get_db),
) -> Student:
    if not koherent_session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    student = db.scalar(select(Student).where(Student.session_token == koherent_session))
    if student is None:
        raise HTTPException(status_code=401, detail="Invalid session")
    return student
```

No cookie → `401`. A cookie that matches no student → `401`. Otherwise you get
back the `Student`, and the endpoint proceeds knowing exactly who's calling. Any
endpoint that wants "must be logged in" simply lists
`Depends(get_current_student)` in its signature (see
[01-fastapi → D-004](01-fastapi.md#d-004-use-dependency-injection-for-db-and-auth)),
and there are tests asserting these endpoints return `401` with no/blank cookie.

> **Note on the session token in the response body.** The join/`/me` responses
> currently also include `session_token` in the JSON, not just the cookie. The
> httpOnly cookie is what actually authenticates requests; the body field is
> redundant and a candidate to remove later. Recorded here so the decision to
> tighten it is a conscious one, not a surprise.

**[D-010] Join codes are 6 characters of A–Z + 0–9, generated with a
collision-retry loop.** From
[`routes/classes.py`](../../../backend/src/koherent/routes/classes.py):

```python
_JOIN_CODE_ALPHABET = string.ascii_uppercase + string.digits

def _generate_join_code() -> str:
    return "".join(secrets.choice(_JOIN_CODE_ALPHABET) for _ in range(6))
```

Because join codes must be **unique** (the column is `unique=True`), two classes
could in principle roll the same code. Rather than hope that never happens, the
create handler tries up to 10 times: generate a code, attempt the insert, and if
the database rejects it for violating uniqueness (`IntegrityError`), roll back
and try a new code.

```python
for _ in range(10):
    candidate = _generate_join_code()
    klass = Class(name=payload.name, join_code=candidate, owner_token=secrets.token_urlsafe(32))
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

The important subtlety: we let the **database** be the referee on uniqueness, not
a "does this code already exist?" check in Python. Checking-then-inserting has a
race condition (two requests could both check "free!" and then both insert). The
database's unique constraint can't be raced — exactly one insert wins, the other
gets an `IntegrityError`, and we retry. This is a small but real example of
pushing correctness down to where it can actually be guaranteed.

---

## 3. What we rejected, and why

- **Full accounts with email + password.** The standard approach for real apps,
  but it's a lot of machinery (secure password hashing, email verification,
  reset flows) and a much bigger security responsibility. For an in-class capture
  tool with a hard project deadline, it's scope we don't need yet.
  ([D-008](#d-008-auth-is-join-code--display-name-no-passwords) is explicitly a
  "buy it later if needed" call.)
- **JWTs (JSON Web Tokens) instead of opaque DB-backed tokens.** A JWT is a
  *self-contained* signed token that encodes the user's identity, so the server
  can verify it without a database lookup. Great at large scale, but it brings
  real complexity: you can't easily revoke a JWT before it expires, and you have
  to manage signing keys. Our opaque tokens are trivially revocable (delete the
  row / clear the column) and dead simple to reason about. At our scale, a DB
  lookup per request is nothing.
- **Storing the token in `localStorage` instead of an httpOnly cookie.** Common
  in single-page apps, but `localStorage` is readable by any JavaScript on the
  page, so an XSS bug means a stolen session. An httpOnly cookie keeps the token
  out of JavaScript's reach. We also get automatic per-request sending for free.
- **Check-then-insert for join-code uniqueness.** Has a race condition under
  concurrent requests. Letting the DB's unique constraint reject duplicates and
  retrying is race-free. (See [D-010](#d-010-6-char-join-codes-generated-with-collision-retry).)
- **Longer or shorter join codes.** 6 characters of a 36-symbol alphabet is ~2.2
  billion combinations — plenty to keep collisions rare for a classroom-scale
  app, while staying short enough to read aloud and type. Shorter would collide
  often; longer would be annoying to enter.

---

## 4. In our code

| Thing | Where |
|-------|-------|
| Issue session on join, set cookie, generate join code | [`backend/src/koherent/routes/classes.py`](../../../backend/src/koherent/routes/classes.py) |
| Resolve cookie → current student (`get_current_student`) | [`backend/src/koherent/deps.py`](../../../backend/src/koherent/deps.py) |
| `/me` (who am I?) endpoint | [`backend/src/koherent/main.py`](../../../backend/src/koherent/main.py) |
| `session_token` / `owner_token` columns | [`backend/src/koherent/models.py`](../../../backend/src/koherent/models.py) |
| Session/auth tests | [`backend/tests/test_session.py`](../../../backend/tests/test_session.py), [`test_join.py`](../../../backend/tests/test_join.py) |

> **`owner_token` vs `session_token`.** A `Class` also gets an `owner_token` when
> created — that's the professor's future key to the (not-yet-built) professor
> dashboard. It's stored and returned now so it exists from day one, but nothing
> consumes it yet. `session_token` is the student-side session described above.

---

## 5. Decision records

### D-008: Auth is join code + display name (no passwords)

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** Students need to identify themselves to a class, but the app
  guards low-sensitivity, in-class data and has a tight build timeline.
- **Decision:** "Sign in" is entering a class join code plus a display name. No
  email, no password, no account recovery.
- **Why:** Minimal friction for students; avoids the large engineering and
  security burden of real account management for data that doesn't warrant it
  yet; can be upgraded later.
- **Alternatives rejected:** Email+password accounts (heavy, big security
  surface, unnecessary now).

### D-009: Sessions are opaque random tokens in httpOnly cookies

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** HTTP is stateless; we need to recognize a returning student on
  every request, safely.
- **Decision:** On join, generate a `secrets.token_urlsafe(32)` token, store it
  on the student row, and set it as an `httpOnly`, `SameSite=Lax`, 30-day
  cookie. Each request resolves the cookie to a student via DB lookup.
- **Why:** Opaque tokens carry no forgeable data and are trivially revocable;
  httpOnly keeps them out of reach of page JavaScript (XSS defense); SameSite=Lax
  mitigates CSRF; DB lookup per request is cheap at our scale.
- **Alternatives rejected:** JWTs (hard to revoke, key management overhead);
  `localStorage` tokens (readable by JS, XSS-exposed).

### D-010: 6-char join codes, generated with collision-retry

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** Join codes must be unique, short enough to read aloud and type,
  and safe under concurrent class creation.
- **Decision:** Generate 6 characters from `[A-Z0-9]` with `secrets.choice`;
  enforce uniqueness with a DB constraint; on `IntegrityError`, roll back and
  retry (up to 10 times).
- **Why:** ~2.2B combinations keeps collisions rare while staying human-friendly;
  letting the DB constraint arbitrate uniqueness is race-free, unlike a
  check-then-insert in application code.
- **Alternatives rejected:** Check-then-insert (race condition); shorter codes
  (frequent collisions); longer codes (hard to enter).
