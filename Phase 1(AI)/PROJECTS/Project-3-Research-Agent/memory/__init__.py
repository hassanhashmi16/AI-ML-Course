"""Cross-session memory: what the agent knows after the process is gone.

The context window dies with the run. Anything the agent should still know
tomorrow has to live somewhere else — that somewhere is this package. It is what
makes session 2 smarter than session 1, and it is half of Project 3's milestone
("...and remembers across sessions").

Two kinds of memory, distinguished because they behave differently:

- **Semantic** — durable facts about a subject ("solid-state energy density is
  ~500 Wh/kg"). Keyed by `(session_id, subject)` and *upserted*: new information
  on the same subject replaces the old row rather than piling up contradictions.
- **Episodic** — a log of what happened ("researched X on date Y, brief at Z").
  Append-only, because events don't get superseded — they just accumulate.

Why SQLite: it is in the standard library, needs no server, and survives process
death — which is exactly the property we need and the reason a Python dict (or a
vector store we can't inspect) would not do.
"""
