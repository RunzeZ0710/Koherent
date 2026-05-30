# 04 — The Data Model (our tables and how they relate)

> **Decisions on this page:** [D-011](#d-011-five-tables-class-student-lecture-note-audiorecording),
> [D-012](#d-012-uuid-primary-keys-not-auto-increment-integers),
> [D-013](#d-013-cascade-deletes-for-ownership-set-null-for-attribution),
> [D-014](#d-014-store-a-client-timestamp-on-notes),
> [D-015](#d-015-store-audio-on-local-disk-metadata-in-the-database)

This page assumes you've read [02-sqlalchemy](02-sqlalchemy.md) (what a table, a
row, and a foreign key are). Here we cover *our specific* tables and the choices
baked into them. All of it lives in
[`backend/src/koherent/models.py`](../../../backend/src/koherent/models.py).

---

## 1. The shape, from zero

Koherent's data is a small hierarchy. In plain English:

- A **Class** is a course (e.g. "Econ 101"). It has a join code.
- A **Student** belongs to one class (they joined it with the code).
- A **Lecture** is one session of a class (e.g. "Day 1: supply curves").
- A **Note** is one chunk of typed notes, written by a student during a lecture.
- An **AudioRecording** is one audio file captured during a lecture.

As a diagram (each `──<` means "one to many"):

```
Class ──< Student
  │
  └────< Lecture ──< Note
            │
            └───────< AudioRecording
```

Read it as: one class has many students and many lectures; one lecture has many
notes and many audio recordings. A note also points back to the student who
wrote it.

### What is a "key"?

- A **primary key** is the column that uniquely identifies a row — its ID. Every
  table here has an `id`.
- A **foreign key** is a column holding the primary key of a row in *another*
  table, creating the link. `Student.class_id` holds the `id` of a `Class`. The
  database enforces that this must point at a real class — you can't create a
  student in a class that doesn't exist. That enforcement is called
  **referential integrity**, and getting the database to guarantee it (rather
  than hoping the app does) is a big part of why relational databases are
  trusted with important data.

---

## 2. What we chose

**[D-011] Five tables: `Class`, `Student`, `Lecture`, `Note`,
`AudioRecording`.** They map one-to-one to the real-world nouns above. Each is a
SQLAlchemy model class. The relationships are declared on both sides so you can
navigate them in Python — e.g. from a `Class` you can read `klass.students`, and
from a `Student` you can read `student.class_`:

```python
class Class(Base):
    ...
    students: Mapped[list["Student"]] = relationship(back_populates="class_", cascade="all, delete-orphan")
    lectures: Mapped[list["Lecture"]] = relationship(back_populates="class_", cascade="all, delete-orphan")

class Student(Base):
    ...
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("classes.id", ondelete="CASCADE"), ...)
    class_: Mapped[Class] = relationship(back_populates="students")
```

(The attribute is `class_` with a trailing underscore because `class` is a
reserved keyword in Python.)

There's also one **uniqueness rule across two columns** on `Student`:

```python
__table_args__ = (UniqueConstraint("class_id", "display_name", name="uq_class_display_name"),)
```

This says a display name must be unique *within a class* — two "Alice"s can't
join the same Econ 101, but an "Alice" in Econ 101 and an "Alice" in Hist 101 are
fine. This is what lets the join handler return a clean `409 Conflict` for a
duplicate name (there's a test for it).

**[D-012] Primary keys are UUIDs, not auto-incrementing integers.** A **UUID** is
a 128-bit random identifier like `f47ac10b-58cc-4372-a567-0e02b2c3d479`. The
common alternative is to let the database number rows `1, 2, 3, …`. We chose
UUIDs:

```python
def _uuid() -> uuid.UUID:
    return uuid.uuid4()

id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
```

Why it matters here: IDs in this app travel in URLs the browser sees
(`/lectures/<id>`). Sequential integer IDs leak information and invite
guessing — if your lecture is `/lectures/41`, someone can try `/lectures/42` and
probe other people's data. (Our authorization checks would still block them, but
"don't make the IDs guessable in the first place" is good defense-in-depth.)
Sequential IDs also reveal volume — a competitor seeing `class #1,203` learns how
many classes exist. UUIDs are unguessable and reveal nothing.

**[D-013] Deletes cascade for *ownership*, but null out for *attribution*.**
Foreign keys declare what happens when the thing they point to is deleted, and we
use two different rules deliberately:

- **`ondelete="CASCADE"`** — "if the parent is deleted, delete me too." Used for
  ownership relationships: delete a `Class` and its `Student`s, `Lecture`s,
  `Note`s, and `AudioRecording`s should all go with it. They have no meaning
  without their parent.
- **`ondelete="SET NULL"`** — "if the referenced row is deleted, just blank out
  my reference to it, but keep me." Used for *attribution* fields:
  `Lecture.created_by_student_id` and `AudioRecording.uploaded_by_student_id`.
  If the student who started a lecture is removed, the **lecture itself should
  survive** (other students' notes hang off it!) — we just forget who started
  it. (Those columns are therefore `nullable=True`.)

The distinction is the lesson: "X belongs to Y" and "X was done by Y" call for
different delete behavior. Cascading a lecture away because the one student who
started it left would be data loss.

**[D-014] Notes store a client-side timestamp (milliseconds since the lecture
started), separate from the server's `created_at`.**

```python
content: Mapped[str] = mapped_column(String, nullable=False)
client_timestamp_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)
created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), ...)
```

There are two notions of "when" for a note, and we keep both:

- `created_at` — when the **server** saved the row. Reliable wall-clock time,
  but it's the *save* time, which can lag behind typing (notes autosave in 5-second
  batches, and the network adds delay).
- `client_timestamp_ms` — how far into the lecture the student was *when they
  typed it*, measured by the browser. This is the one that matters for the Week 2
  AI feature: to compare a student's notes against the lecture transcript, we
  need to line them up on the *lecture's* timeline ("at minute 12, the professor
  said X and Alice wrote Y"). Server save-time can't give us that alignment;
  lecture-relative time can.

`BigInteger` is used because milliseconds add up fast and could exceed a normal
integer's range over a long session.

**[D-015] Audio files live on local disk; only their metadata lives in the
database.** The `AudioRecording` row stores a `file_path`, `mime_type`,
`size_bytes` (and an optional `duration_seconds`), but **not the audio bytes
themselves.** The bytes are written to disk by
[`backend/src/koherent/storage.py`](../../../backend/src/koherent/storage.py):

```python
def save_audio(content: bytes, suffix: str = ".webm") -> str:
    root = storage_root()                 # ./storage/audio, created if missing
    name = f"{uuid.uuid4()}{suffix}"      # random filename, no collisions
    (root / name).write_bytes(content)
    return name                           # store this relative path in the DB row
```

Databases are bad at being file servers — stuffing large binary blobs into them
bloats backups and slows everything down. The standard pattern is: **files on a
filesystem (or, later, cloud object storage like S3); a row in the database
pointing at them.** Storing only a *relative* path (the filename) is deliberate
too — it means we can move the storage directory or swap to S3 later without
rewriting every saved path. The filename itself is a fresh UUID, so two uploads
can never clobber each other.

---

## 3. What we rejected, and why

- **Auto-increment integer keys.** Simpler and slightly smaller, but guessable
  and information-leaking in URLs (see
  [D-012](#d-012-uuid-primary-keys-not-auto-increment-integers)). UUIDs cost a
  little space and readability for meaningfully better privacy and safety.
- **CASCADE everywhere (including attribution).** Would mean deleting one student
  could vaporize a whole lecture and everyone else's notes. Using `SET NULL` for
  "who did this" fields preserves the data and just forgets the actor.
- **Relying only on `created_at` for note timing.** It records when the server
  *saved* the note, which drifts from when it was *typed* due to batched autosave
  and network latency — useless for aligning notes to the lecture timeline. The
  client timestamp is purpose-built for that.
- **Storing audio bytes in the database (a BLOB column).** Bloats the DB and its
  backups, and databases aren't optimized to stream files. Disk + a metadata row
  is the conventional, scalable split.
- **A single flat "events" table instead of typed tables.** Would be more
  flexible but would push all the structure and integrity rules into application
  code. Distinct tables with foreign keys let the database enforce correctness.

---

## 4. In our code

| Table | Purpose | Key fields |
|-------|---------|-----------|
| `Class` | A course | `name`, `join_code` (unique), `owner_token` (unique) |
| `Student` | A member of a class | `class_id` (FK), `display_name`, `session_token` (unique); unique `(class_id, display_name)` |
| `Lecture` | One session of a class | `class_id` (FK), `title?`, `started_at`, `ended_at?`, `created_by_student_id?` (FK, SET NULL) |
| `Note` | A typed note chunk | `lecture_id` (FK), `student_id` (FK), `content`, `client_timestamp_ms` |
| `AudioRecording` | A captured audio file | `lecture_id` (FK), `uploaded_by_student_id?` (FK, SET NULL), `file_path`, `mime_type`, `size_bytes`, `duration_seconds?` |

All defined in [`backend/src/koherent/models.py`](../../../backend/src/koherent/models.py).
Disk writes in [`storage.py`](../../../backend/src/koherent/storage.py). The
authorization check that a lecture belongs to the caller's class
(`_load_lecture_for_student`) lives in
[`routes/lectures.py`](../../../backend/src/koherent/routes/lectures.py) and is
what enforces the relationships at request time.

---

## 5. Decision records

### D-011: Five tables (Class, Student, Lecture, Note, AudioRecording)

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** We need to model courses, their members, sessions, and the notes
  and audio captured in them.
- **Decision:** One table per real-world noun, linked by foreign keys, with a
  cross-column unique constraint making display names unique within a class.
- **Why:** Tables map cleanly to the domain; foreign keys let the DB enforce the
  relationships; the unique constraint gives a clean duplicate-name error.
- **Alternatives rejected:** A single flexible "events" table (pushes integrity
  into app code).

### D-012: UUID primary keys (not auto-increment integers)

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** Row IDs appear in browser-visible URLs.
- **Decision:** Use random UUIDs as primary keys.
- **Why:** Unguessable (defense-in-depth against probing other rows) and reveal
  no volume information; sequential integers leak both.
- **Alternatives rejected:** Auto-increment integers (guessable, leak counts).

### D-013: CASCADE deletes for ownership, SET NULL for attribution

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** Deleting a row shouldn't silently destroy unrelated data, but
  truly-owned children should go with their parent.
- **Decision:** `ondelete=CASCADE` on ownership FKs (class→students/lectures,
  lecture→notes/audio); `ondelete=SET NULL` on attribution FKs
  (`created_by_student_id`, `uploaded_by_student_id`), which are nullable.
- **Why:** Owned children are meaningless without their parent; attribution
  fields shouldn't drag the whole record away when an actor is removed.
- **Alternatives rejected:** CASCADE everywhere (deleting a student could erase a
  shared lecture and others' notes).

### D-014: Store a client timestamp on notes

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** Week 2 must align student notes to the lecture transcript on the
  lecture's timeline.
- **Decision:** Store `client_timestamp_ms` (ms since lecture start, from the
  browser) in addition to the server `created_at`.
- **Why:** `created_at` is save-time, skewed by batched autosave and network
  latency; lecture-relative client time is what enables transcript alignment.
- **Alternatives rejected:** Relying on `created_at` alone (wrong timeline,
  unreliable for alignment).

### D-015: Store audio on local disk, metadata in the database

- **Date:** 2026-05-21
- **Status:** Active
- **Context:** Audio recordings are large binary files.
- **Decision:** Write bytes to `./storage/audio/<uuid>.webm`; store a relative
  `file_path` plus `mime_type`/`size_bytes` in an `AudioRecording` row.
- **Why:** Databases handle large blobs poorly (backup bloat, slow); files on
  disk with a DB pointer is the standard, scalable split; relative paths and
  UUID filenames make later migration to cloud storage and collision-free
  uploads easy.
- **Alternatives rejected:** Storing audio bytes in a DB BLOB column (bloats and
  slows the database).
