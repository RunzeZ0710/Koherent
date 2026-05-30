# Koherent Engineering Wiki

This wiki is the **source of truth for every meaningful decision** made in this
repository, and a **learning resource** for the engineering behind it.

It exists for two reasons:

1. **"Why did we do it this way?"** should always have an answer. Code shows you
   *what* we did; this wiki records *why*, and what we deliberately chose **not**
   to do.
2. **Learning.** Koherent is partly a vehicle for learning software engineering.
   The topic pages teach the underlying concepts from the ground up, using our
   own code as the running example. They assume you can read code and know basic
   Python, but explain web and database fundamentals (HTTP, APIs, databases,
   cookies, sessions) from scratch.

## How the wiki is organized

```
docs/wiki/
  README.md            <- you are here: how the wiki works
  DECISIONS.md         <- the index: every decision, one line each, linked
  topics/              <- deep explainer pages, one per concept
    01-fastapi.md
    02-sqlalchemy.md
    03-auth-and-sessions.md
    04-data-model.md
    05-testing.md
    06-config-and-migrations.md
```

- **[DECISIONS.md](DECISIONS.md)** is the spine. It is a flat list of every
  decision with a stable ID (`D-001`, `D-002`, …), a one-line summary, and a
  link to the topic page where it is explained in full. Start here when you want
  to know *what* was decided. Go to the linked topic when you want to know *why*.
- **`topics/`** pages are where the teaching happens. Each page follows the same
  five-part template (below) so they are predictable to read and to write.

## The topic page template

Every topic page has these sections:

1. **The concept from zero** — plain-English explanation of the underlying idea,
   assuming no prior web/database knowledge.
2. **What we chose** — the decision(s) we made.
3. **What we rejected, and why** — the alternatives, and the trade-off that
   decided it. (This is the part most documentation skips and the part that
   teaches the most.)
4. **In our code** — pointers to the real files and functions, so the abstract
   idea connects to concrete code you can open.
5. **Decision records** — compact summaries of the decisions on this page, each
   with its `D-xxx` ID so `DECISIONS.md` can link straight to it.

## How to add a new decision (going forward)

When we make a new decision worth recording:

1. Find or create the relevant topic page under `topics/`.
2. Add a **Decision record** block at the bottom of that page with the next free
   `D-xxx` ID. Use this shape:

   ```markdown
   ### D-0XX: <short title>

   - **Date:** YYYY-MM-DD
   - **Status:** Active | Superseded by D-0YY | Deprecated
   - **Context:** what situation forced a choice
   - **Decision:** what we chose
   - **Why:** the reasoning
   - **Alternatives rejected:** what else we considered and why we passed
   ```

3. Add a one-line row to the table in [DECISIONS.md](DECISIONS.md) pointing at it.

That's the whole protocol. The index stays the single front door; the topic
pages hold the depth.

## Scope right now

This wiki currently documents **Week 1 of the backend** (the capture loop:
classes, students, lectures, notes, audio — no AI yet). Frontend and later weeks
will be added using the same framework. See
[project_plan.md](../../project_plan.md) for the product roadmap and
[docs/superpowers/plans/](../superpowers/plans/) for the task-by-task build
plans.
