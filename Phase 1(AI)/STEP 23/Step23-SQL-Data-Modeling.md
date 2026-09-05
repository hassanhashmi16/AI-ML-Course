# Step 23: SQL & Relational Data Modeling

> **What it covers:** SELECT/WHERE/JOIN/GROUP BY, schema design and normalization, indexes and EXPLAIN (why a query is slow), transactions and migrations (Alembic), and talking to Postgres from Python (psycopg / SQLAlchemy) — the layer Step 24's pgvector and Step 26's retrieval assume you already have.

---

## The Problem

Step 24 drops you into Postgres assuming you can already write a JOIN from memory and read an `EXPLAIN` plan. If you can't, two specific things break. First, you can't design the document/chunk schema that every RAG system needs — so you end up with chunks duplicated across rows, no way to filter by source, and queries that get slower as the corpus grows. Second, you can't debug why a retrieval query takes 2 seconds instead of 20 milliseconds, because "it's slow" isn't actionable until you can read what the planner actually did.

The deeper issue is that "I know SQL" and "I can model data for retrieval" are different skills. A database course teaches you the former. This step is the bridge to the latter: the specific schema shapes, index choices, and transaction patterns that show up over and over in AI systems, not just generic tables of customers and orders.

---

## Foundational Concepts

### The database is the source of truth; the vector index is a cache

This is the mental model that separates engineers who build RAG from engineers who understand it. Your Postgres tables hold the *actual* documents and chunks — the durable, queryable, filterable source of truth. The vector index (Step 24) is a *derived* structure that makes similarity search fast, but it's disposable: you can drop it and rebuild it from the tables without losing anything. This matters because it tells you where to put your effort: model the relational data correctly first, and the vector search becomes a thin layer on top.

### A table is a contract, not just a place to dump data

Every column has a type, every row has a key, and every relationship is either explicit (a foreign key) or it doesn't exist. When you treat a table as a place to "just store stuff" — a `text` column for everything, no keys, no constraints — you get back exactly the mess that makes queries slow and bugs impossible to find. The schema is where you encode the *rules* of your data, and those rules are what let the database optimize queries and reject bad writes.

### Why Postgres specifically

Postgres is the default for this course because it's the only major database that's both a fully-featured relational store *and* an extension platform — pgvector (Step 24) is just a Postgres extension, which means your documents, chunks, and their vectors all live in one place with one query language and one set of transactions. You don't have to sync two systems. The SQL you learn here carries over to any relational DB, but the Postgres-specific parts (JSONB, `EXPLAIN`, transactional DDL) are what make it the right default.

---

## 23.1 — SELECT / WHERE / JOIN / GROUP BY

### The four verbs that do 90% of the work

```sql
SELECT   -- which columns
FROM     -- which table(s)
WHERE    -- which rows
GROUP BY -- how to aggregate
```

`SELECT` picks columns, `WHERE` filters rows, `JOIN` combines tables on a shared key, and `GROUP BY` collapses rows into groups for aggregation (`COUNT`, `SUM`, `AVG`, `MAX`). The order they *execute* is not the order they're *written* — that's the key thing that trips people up. The logical order is `FROM` → `WHERE` → `GROUP BY` → `SELECT`, which is why you can't reference a `SELECT` alias in `WHERE` but you can in `GROUP BY`/`ORDER BY`.

### JOINs: the part worth actually recalling

A **JOIN** matches rows from two tables on a condition, usually a foreign key. The types:

| Type | Returns | When |
|---|---|---|
| `INNER JOIN` | Rows with a match in *both* tables | The default; "give me chunks and their documents" |
| `LEFT JOIN` | All left rows, matched right rows or `NULL` | "all documents, even ones with no chunks yet" |
| `RIGHT JOIN` | All right rows, matched left rows or `NULL` | Rare; usually rewritten as a LEFT JOIN |
| `FULL OUTER JOIN` | All rows from both, `NULL` where no match | Finding orphans in either direction |
| `CROSS JOIN` | Every combination | Almost never what you want — it's a bug unless intentional |

The one that actually matters for RAG: `LEFT JOIN` when you want "documents even if some have no chunks." An `INNER JOIN` silently drops documents with zero chunks, which is usually wrong for an ingestion pipeline that's mid-run.

### GROUP BY and aggregation

```sql
SELECT source, COUNT(*) AS chunk_count
FROM chunks
GROUP BY source
HAVING COUNT(*) > 1;      -- only groups with more than one chunk
```

The subtlety: `WHERE` filters *rows before* grouping, `HAVING` filters *groups after* grouping. You can't use `WHERE` to filter on `COUNT(*)` because the count doesn't exist yet at row-filter time. This is a one-line distinction that people get wrong constantly.

### Why you don't need a SQL course to recall this part

You said you've done a database course, so this section is the recall trigger, not the lesson. If you can write a `JOIN` + `GROUP BY` that answers "how many chunks per source, for sources with more than 5 chunks," you have everything here. The *new* part is what these queries look like in the retrieval context — and that's the rest of the step.

---

## 23.2 — Schema Design, Keys & Normalization

### The document/chunk schema: the one you'll actually build

RAG systems converge on the same shape, and it's worth memorizing because you'll recreate it in Step 24:

```sql
CREATE TABLE documents (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT NOT NULL,          -- filename or URL
    content_hash TEXT NOT NULL,          -- from Step 21's incremental re-ingestion
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata    JSONB                    -- flexible per-document fields
);

CREATE TABLE chunks (
    id          BIGSERIAL PRIMARY KEY,
    document_id BIGINT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,        -- position within the document
    text        TEXT NOT NULL,
    section     TEXT,                    -- heading this chunk came from (Step 21)
    UNIQUE (document_id, chunk_index)    -- no duplicate positions
);
```

Reading this schema, the design decisions are the lesson:

- **`documents` and `chunks` are separate tables, not one.** A document has many chunks (one-to-many). Putting the document metadata on every chunk row would duplicate it thousands of times and make "update the source name" a mass update.
- **`document_id` is a foreign key with `ON DELETE CASCADE`.** Delete a document and its chunks go automatically — no orphan chunks. This is the relational database doing your cleanup for you.
- **`UNIQUE (document_id, chunk_index)`** enforces that a document can't have two chunks at position 3. This is a *constraint*, and constraints are how the DB catches bugs your code misses.
- **`metadata JSONB`** holds the flexible stuff (date, author, tags) without forcing a schema migration every time you add a field. JSONB is Postgres-specific and it's the right call for metadata that varies per document.

### Keys: primary vs. foreign, and why they're non-negotiable

A **primary key** uniquely identifies a row (`id BIGSERIAL`). A **foreign key** is a column that references another table's primary key (`document_id REFERENCES documents(id)`). The foreign key is what makes `documents` and `chunks` *related* rather than just "two tables that happen to exist." Without it, nothing stops you from inserting a chunk with a `document_id` that doesn't exist — an orphan that will silently disappear from every `JOIN`.

### Normalization: the rule, and when to break it

**Normalization** means storing each fact once and referencing it everywhere else, instead of copying it. The classic example: don't store `author_name` on every `chunk`; store it once on `documents` and `JOIN` to get it. Benefits: no inconsistency (change it in one place), no duplication (smaller, faster).

The levels (1NF, 2NF, 3NF) matter less than the *judgment*: normalize by default, **denormalize deliberately** when a query is hot and a JOIN is the bottleneck. The classic RAG denormalization is copying `source` onto the `chunks` table so you can filter chunks by source without a JOIN. That's fine — but it's a decision you make *knowing* you're trading consistency for speed, not an accident.

### The rule of thumb

**Normalize until a real query is slow, then denormalize that one query's path and document the trade-off.** Most people either over-normalize (never finish) or under-normalize (duplicate everywhere and fight inconsistency bugs). The schema above is the sweet spot for retrieval: normalized where it matters (documents vs. chunks), denormalized where it helps (chunks carry `section` so you don't JOIN back for it).

---

## 23.3 — Indexes & EXPLAIN (Why a Query Is Slow)

### The problem: a query that worked on 1,000 rows dies on 1,000,000

You add a `WHERE source = '...'` clause, and it's fine — until the corpus grows and that same query goes from 5ms to 2 seconds. Why? Because without an index, Postgres has to read *every single row* (a **sequential scan**) and check the condition one by one. The query didn't get slower because Postgres got worse; it got slower because the *amount of work* grew linearly with the data, and an index is the thing that turns linear into logarithmic.

### What an index actually is

An **index** is a sorted data structure (a B-tree, by default) that maps column values to row locations, so Postgres can jump straight to "the rows where `source = 'foo'`" instead of scanning everything. It's the same idea as a book's index: find "Chapter 3" in the index in O(log n), flip to the exact page, instead of reading the whole book.

```sql
CREATE INDEX idx_chunks_source ON chunks (source);
```

Now `WHERE source = '...'` uses the index. The cost: every `INSERT`/`UPDATE` must also update the index, so writes get slightly slower. Indexes are a *read/write trade-off* — free reads you pay for with writes.

### EXPLAIN: reading what the planner decided

Postgres doesn't just run your query; it first *plans* it, choosing the cheapest strategy based on table statistics. `EXPLAIN` shows that plan without running it:

```sql
EXPLAIN SELECT * FROM chunks WHERE source = 'annual-report.pdf';
```

```
Seq Scan on chunks  (cost=0.00..445.00 rows=10000 width=244)
  Filter: (source = 'annual-report.pdf'::text)
```

Reading this line by line, because it's the skill that separates "my query is slow" from "I can see why":

- **`Seq Scan`** — Postgres chose to read every row in order. This is the smoking gun for "why is this slow": a sequential scan on a big table is always the thing you're trying to avoid.
- **`cost=0.00..445.00`** — the planner's *estimated* cost in arbitrary units (disk-page fetches, by convention). The first number is startup cost, the second is total cost. Don't read these as milliseconds; read them as *relative* — 445 vs. 8 tells you one plan is ~50x cheaper.
- **`rows=10000`** — the planner's estimate of how many rows this node will output. If this is wildly off from reality, your table statistics are stale (fix with `ANALYZE`).
- **`Filter:`** — the `WHERE` clause being applied. It's attached to the Seq Scan, which means Postgres is checking the condition on every one of the 10,000 rows it reads. That's the waste.

Now add the index and re-check:

```sql
EXPLAIN SELECT * FROM chunks WHERE source = 'annual-report.pdf';
```

```
Index Scan using idx_chunks_source on chunks  (cost=0.29..8.30 rows=1 width=244)
  Index Cond: (source = 'annual-report.pdf'::text)
```

The node changed from `Seq Scan` to `Index Scan`, and the cost dropped from 445 to 8. That's the entire "why is my query slow" toolkit in two screenshots: see `Seq Scan`, add an index, see `Index Scan`.

### EXPLAIN ANALYZE: the version that actually runs the query

`EXPLAIN` estimates; `EXPLAIN ANALYZE` runs the query and shows *actual* row counts and times alongside the estimates:

```sql
EXPLAIN ANALYZE SELECT * FROM chunks WHERE source = 'annual-report.pdf';
```

```
Seq Scan on chunks  (cost=0.00..445.00 rows=10000 width=244)
                    (actual time=0.030..1.995 rows=10000 loops=1)
```

The mismatch is the diagnostic gold: if `rows=10000` (estimate) but `actual ... rows=10000` matches, fine. If the estimate says `rows=1` but actual is `rows=9000`, Postgres is making decisions on bad statistics — the query is slow because the planner is misinformed, not because your SQL is wrong. Fix with `ANALYZE chunks;`.

### The four things to look for in a slow query

| Symptom in EXPLAIN | Meaning | Fix |
|---|---|---|
| `Seq Scan` on a big table | No usable index | Add one on the `WHERE` column |
| Estimate wildly off from `actual` | Stale statistics | `ANALYZE` the table |
| `Sort` node near the top | Sorting a big result | Index on the `ORDER BY` column |
| `Nested Loop` with many `loops` | Join doing per-row lookups | Often fixed by an index on the join key |

### The rule of thumb

**Don't index preemptively; index in response to a real slow query you can see in EXPLAIN.** Every index costs write speed, so a table with 10 indexes is a table that's slow to write to. Add an index when `EXPLAIN ANALYZE` shows you a sequential scan on a query that matters, then confirm it actually helped.

---

## 23.4 — Transactions & Migrations (Alembic)

### Transactions: all-or-nothing, and why ingestion needs them

A **transaction** is a set of operations that either all succeed or all fail — there's no in-between state. In Postgres you get this with `BEGIN` / `COMMIT` / `ROLLBACK`:

```sql
BEGIN;
UPDATE documents SET content_hash = 'new-hash' WHERE id = 42;
DELETE FROM chunks WHERE document_id = 42;
INSERT INTO chunks (document_id, chunk_index, text) VALUES (42, 1, 'new text');
COMMIT;
```

If any statement fails, `ROLLBACK` undoes all of them. Why this matters for RAG specifically: **re-ingesting a document is a multi-step operation** (update the hash, delete old chunks, insert new chunks). Without a transaction, a crash halfway through leaves the index in a broken state — document hash says "updated" but chunks are half-old, half-new. With a transaction, it's atomic: either the re-ingestion fully happened or it didn't happen at all. This is the *same* atomic-swap idea from Step 21's incremental re-ingestion, but now the database is enforcing it instead of you hoping your code gets the ordering right.

### The ACID properties, in one breath

**Atomicity** (all-or-nothing), **Consistency** (constraints stay valid), **Isolation** (concurrent transactions don't see each other's half-done work), **Durability** (committed data survives a crash). You don't need to recite them; you need to *rely* on them. When you wonder "what if two ingestion jobs run at once?", the answer is "use a transaction and let isolation handle it."

### Isolation levels: the one thing to know

Concurrent transactions can conflict. The default isolation in Postgres (`READ COMMITTED`) means each statement sees only committed data, which is usually enough. The case that bites in ingestion: two jobs both read the same document's old hash, both decide it's changed, both re-ingest. The fix is usually not a fancy isolation level — it's a unique constraint or a `SELECT ... FOR UPDATE` to lock the row. Don't reach for `SERIALIZABLE` until you've hit a real concurrency bug and understood *why* the default isn't enough.

### Migrations: schema changes, versioned

Your schema isn't static — you'll add a `section` column, then a `metadata` column, then change a type. A **migration** is a versioned, ordered script that changes the schema, so every environment (your laptop, CI, production) applies the same changes in the same order and ends up in the same state. **Alembic** (built on SQLAlchemy) is the standard tool for this in Python. As of September 2026, Alembic is at 1.19.x.

The workflow:

```bash
alembic init alembic              # one-time setup
alembic revision -m "add section column"   # generate a migration file
# edit the upgrade()/downgrade() functions
alembic upgrade head              # apply migrations
alembic downgrade -1              # roll back one step
```

Each migration has an `upgrade()` (forward) and `downgrade()` (rollback):

```python
def upgrade():
    op.add_column("chunks", sa.Column("section", sa.Text))

def downgrade():
    op.drop_column("chunks", "section")
```

The key concept: **migrations are code, and they're the only way to change a schema that's already deployed.** You never `ALTER TABLE` by hand on a live database, because then your schema and your migration history disagree, and the next `alembic upgrade` fails in ways that are miserable to untangle. The migration file is the source of truth for "what the schema is and how it got there."

---

## 23.5 — Talking to Postgres from Python (psycopg / SQLAlchemy)

### Two layers, and why both exist

There are two ways to talk to Postgres from Python, at two different levels of abstraction:

- **psycopg** (now psycopg 3, as of 2026) is the **driver** — the low-level library that speaks the Postgres wire protocol. You write SQL strings and it executes them. Fast, explicit, no magic.
- **SQLAlchemy** (2.0.x as of September 2026) is an **ORM/toolkit** layered on top of a driver. You work with Python objects and it generates SQL for you. More structure, less repetitive code, a learning curve.

The confusion is thinking they're competitors. They're not — SQLAlchemy *uses* psycopg (or another driver) underneath. The real choice is "raw SQL via psycopg" vs. "objects via SQLAlchemy."

### psycopg 3: raw SQL, explicit control

```python
import psycopg

conn = psycopg.connect("postgresql://user:pass@localhost/dbname")

with conn.cursor() as cur:
    cur.execute(
        "SELECT text FROM chunks WHERE source = %s",
        ("annual-report.pdf",),
    )
    rows = cur.fetchall()

conn.close()
```

The critical detail: **`%s` is a parameter placeholder, not string formatting.** You pass the value separately, and psycopg sends it safely, so a malicious `source` value can't inject SQL. Never do `f"... WHERE source = '{source}'"` — that's the SQL injection vulnerability, and it's how databases get owned. The parameterized version is both safer and faster (Postgres can cache the plan).

### SQLAlchemy 2.0: objects and the Session

SQLAlchemy's modern style (2.0+) uses typed `Mapped` columns. The `documents`/`chunks` schema from 23.2 becomes:

```python
from sqlalchemy import ForeignKey, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, Session

class Base(DeclarativeBase):
    pass

class Document(Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(Text, unique=True)
    content_hash: Mapped[str] = mapped_column(Text)
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document")

class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    chunk_index: Mapped[int] = mapped_column()
    text: Mapped[str] = mapped_column(Text)
    document: Mapped[Document] = relationship(back_populates="chunks")

engine = create_engine("postgresql+psycopg://user:pass@localhost/dbname")
Base.metadata.create_all(engine)
```

The two new mechanisms worth understanding, because they're the "magic" part:

- **`Mapped[int]`** — this is a type annotation that SQLAlchemy reads to know the column's type (`int` → `INTEGER`, `str` → `TEXT`). You're declaring the schema in Python types, and SQLAlchemy generates the matching SQL.
- **`relationship()`** — this doesn't create a column; it creates a *Python-side link*. `Document.chunks` lets you write `doc.chunks` and SQLAlchemy automatically queries the chunks with that `document_id`. The actual relationship is still the `ForeignKey` on `Chunk`; `relationship()` is just the convenient object access on top.

Then the Session handles the transaction and persistence:

```python
with Session(engine) as session:
    doc = session.get(Document, 42)
    print(len(doc.chunks))           # lazy-loads the chunks
    doc.content_hash = "new-hash"
    session.commit()                  # one transaction, atomic
```

### psycopg vs. SQLAlchemy: the honest trade-off

| | psycopg (raw SQL) | SQLAlchemy (ORM) |
|---|---|---|
| **Best for** | Precise queries, bulk loads, when you know exactly what SQL you want | Apps with many models and CRUD, when you want objects not rows |
| **Control** | Total — you write every query | High — but it generates SQL, so you must learn its patterns |
| **Magic** | None | Considerable (lazy loading, relationships, unit-of-work) |
| **Learning curve** | Low (you already know SQL) | Steeper (the ORM has its own model) |

For RAG specifically, the common pattern is **SQLAlchemy for the app layer** (documents, chunks, CRUD) and **raw SQL or SQLAlchemy Core for the hot retrieval queries** (where you want to see and control the exact `EXPLAIN` plan). Don't feel forced to pick one exclusively — SQLAlchemy can run raw SQL strings too (`session.execute(text(...))`), which gives you the best of both.

### The rule of thumb

**Use psycopg when the SQL is the point; use SQLAlchemy when the objects are the point.** A one-off data-loading script is psycopg. A FastAPI app with documents/chunks/users that persists and queries all of them is SQLAlchemy. When you need to optimize a query to the millisecond, drop to raw SQL in either case.

---

## Pitfalls

1. **Filtering on `COUNT(*)` in `WHERE`.** Aggregates don't exist at row-filter time — that's what `HAVING` is for. `WHERE COUNT(*) > 1` is a syntax error you'll hit once and never forget.
2. **Using `INNER JOIN` when you need `LEFT JOIN`.** It silently drops documents with no chunks, which corrupts "how many chunks does each source have" reports.
3. **String-formatting SQL instead of parameterizing.** `f"WHERE source = '{s}'"` is the injection vulnerability. Use `%s` placeholders (psycopg) or SQLAlchemy's bound params.
4. **Indexing nothing, or indexing everything.** No indexes = sequential scans at scale; too many indexes = slow writes. Index in response to a real `EXPLAIN` finding.
5. **Reading `EXPLAIN` cost as milliseconds.** It's a relative cost in arbitrary units. Use it to compare plans, not to predict wall-clock time.
6. **Trusting stale statistics.** A plan based on `rows=10000` when actual is `rows=2` is a misinformed planner. `ANALYZE` the table.
7. **Re-ingesting without a transaction.** A crash mid-way leaves old and new chunks mixed. Wrap the hash-update + delete + insert in one transaction.
8. **Hand-editing the schema instead of writing a migration.** Now your DB and your migration history disagree, and the next `alembic upgrade` breaks. Migrations only.
9. **Storing flexible metadata in fixed columns.** Every new metadata field becomes a migration. Use `JSONB` for the stuff that varies per document.
10. **Forgetting the foreign key.** No FK means orphans and broken JOINs. The constraint is what makes the relationship real, not just conventional.

---

## Quick Reference

| Goal | SQL / tool |
|---|---|
| Pick columns, filter rows | `SELECT ... FROM ... WHERE` |
| Combine two tables | `JOIN ... ON a.id = b.id` |
| Keep all left rows | `LEFT JOIN` |
| Aggregate | `GROUP BY` + `COUNT/SUM/AVG` |
| Filter after aggregation | `HAVING` (not `WHERE`) |
| Unique row id | `PRIMARY KEY` |
| Reference another table | `FOREIGN KEY ... REFERENCES` |
| Cascade deletes | `ON DELETE CASCADE` |
| Flexible per-row fields | `JSONB` |
| See the query plan | `EXPLAIN` / `EXPLAIN ANALYZE` |
| Spot the slow plan | `Seq Scan` on a big table |
| Refresh stale stats | `ANALYZE table` |
| Speed up a filter | `CREATE INDEX ... ON ... (col)` |
| Atomic multi-statement change | `BEGIN; ... COMMIT;` |
| Undo a change | `ROLLBACK` |
| Version the schema | Alembic (`revision`, `upgrade head`) |
| Raw SQL from Python | `psycopg` + `%s` params |
| ORM / objects | SQLAlchemy 2.0 (`Mapped`, `Session`) |
| Postgres URL | `postgresql+psycopg://user:pass@host/db` |

---

## Theory Summary

**The relational schema is the source of truth; everything else is derived.** Documents and chunks are real rows with keys and constraints; the vector index and the retrieval layer are views *on top of* that truth. Get the schema right and you can rebuild any derived structure; get it wrong and every layer above inherits the mess.

**Constraints are the database doing your job for you.** A foreign key prevents orphans, a `UNIQUE` prevents duplicates, a `NOT NULL` prevents missing data. Every constraint you don't write is a bug class you've opted to catch in application code instead — which is strictly worse, because application code races and forgets.

**Slow queries are diagnosed, not guessed.** `EXPLAIN` shows you exactly what the planner chose and why; `EXPLAIN ANALYZE` shows you what actually happened. The fix is usually "add an index on the column you filter on," but the *discipline* is "look at the plan first, then act." Anyone who tunes a query without reading the plan is guessing.

**Transactions make multi-step operations atomic.** Re-ingesting a document is delete-then-insert; without a transaction that's a corruptible state. The database gives you all-or-nothing for free — the only mistake is not using it.

**The ORM is a convenience, not a replacement for knowing SQL.** SQLAlchemy generates SQL you still need to be able to read and debug. When it emits a slow query, you're back in `EXPLAIN` land. The people who suffer with ORMs are the ones who never learned what's underneath; the people who thrive are the ones who can drop to raw SQL the moment the abstraction leaks.

---

## Deliverable

**`Phase 1(AI)/STEP 23/step23-sql/`** — a working document/chunk schema with a demonstrated performance fix, runnable against a local Postgres:

- **`schema.sql`** — the `documents` + `chunks` tables from 23.2, with primary keys, the foreign key with `ON DELETE CASCADE`, the `UNIQUE (document_id, chunk_index)` constraint, and a `JSONB` metadata column.
- **`seed.py`** — a script that connects via psycopg, inserts a handful of documents and chunks (parameterized, no string formatting), and seeds enough rows that a sequential scan is visible.
- **`queries.sql`** — three queries: (1) chunks per source with `GROUP BY` + `HAVING`, (2) a `LEFT JOIN` showing documents with zero chunks, (3) a filter query that's deliberately slow *before* you add an index.
- **`slow_query_fix.md`** — the before/after: paste the `EXPLAIN ANALYZE` output showing `Seq Scan`, create the index, paste the new `Index Scan` plan, and note the cost change. This is the proof you can read a plan, not just run a query.
- **`models.py`** — the same schema as SQLAlchemy 2.0 models, so you can see the ORM mapping next to the raw SQL.

**Prove it:** run `seed.py` against a local Postgres, run the slow query, capture `EXPLAIN ANALYZE`, add the index, and capture the plan again. The `cost` number should drop by an order of magnitude or more — that screenshot is the step.
