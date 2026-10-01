-- Step 5 deliverable: the database schema for the RAG assistant.
--
-- Three tables:
--   documents  one row per source article (the 15 files from Step 2)
--   chunks     one row per chunk (the 252 pieces from Step 4). It holds BOTH the
--              embedding and the full-text vector, so a single table serves both
--              retrievers (Steps 8 and 9).
--   peaks      the structured facts from data/peaks.json (Step 12's lookup)
--
-- This file is idempotent (IF NOT EXISTS everywhere), and docker-compose mounts
-- it into Postgres's init directory, so it runs by itself the first time the
-- container is created. To apply it by hand:
--     psql "$DATABASE_URL" -f db/schema.sql

-- pgvector adds the `vector` type and the distance operators (<=>, <->, <#>).
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- documents: provenance + file-level idempotency
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS documents (
    id          bigserial PRIMARY KEY,
    source      text        NOT NULL UNIQUE,  -- the raw filename, e.g. 'k2.txt'
    peak        text,                         -- 'K2', or 'Eight-thousander list'
    title       text,                         -- resolved Wikipedia article title
    url         text,                         -- where the text actually came from
    file_hash   text,                         -- sha256 of the raw file (Step 7 decides skip/refresh)
    ingested_at timestamptz NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- chunks: the retrieval unit
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS chunks (
    id           bigserial PRIMARY KEY,
    document_id  bigint      NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index  int         NOT NULL,         -- position within its section
    section      text        NOT NULL,         -- breadcrumb, e.g. 'K2 > Climbing history'
    content      text        NOT NULL,         -- the text we embed and eventually show
    token_count  int         NOT NULL,
    content_hash text        NOT NULL,         -- sha256 of content

    -- The embedding. 768 MUST match EMBED_DIM in config.py and the model used in
    -- Step 6. Remember to adjust this if you switch to a differently sized
    -- embedding model. A mismatch is a hard error at insert time, the good kind.
    embedding    vector(768),

    -- Full-text search vector, GENERATED from content so it can never drift out
    -- of sync with it. The two-argument to_tsvector('english', ...) is deliberate:
    -- it is IMMUTABLE, which generated columns require. The one-argument form is
    -- only STABLE and Postgres rejects it here with a clear error.
    tsv          tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,

    -- One copy of a given text per document: a clean ON CONFLICT target for
    -- Steps 6/7. Scoped to the document, not global, so the same paragraph could
    -- still exist under two different peaks without one silently winning.
    UNIQUE (document_id, content_hash)
);

-- ---------------------------------------------------------------------------
-- peaks: structured facts
-- Step 12 answers exact-fact questions ("how tall is K2?") straight from here,
-- never touching the vector index. RAG is not always the right tool.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS peaks (
    id                bigserial PRIMARY KEY,
    name              text    NOT NULL UNIQUE,
    aliases           text[]  NOT NULL DEFAULT '{}',
    height_m          numeric NOT NULL,
    countries         text[]  NOT NULL DEFAULT '{}',
    mountain_range    text,
    first_ascent_year int,
    first_ascent_date date,
    first_ascenters   text[]  NOT NULL DEFAULT '{}'
);

-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------

-- HNSW graph index for approximate nearest-neighbour search (Step 25).
-- `vector_cosine_ops` binds this index to the cosine operator (<=>). Query with
-- a different operator and Postgres will NOT error: it silently ignores the
-- index and falls back to scanning every row. Correct results, zero speedup.
-- This is the classic pgvector footgun, so the operator and the index must match.
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

-- GIN index for full-text search (Step 9). Makes `tsv @@ query` fast.
CREATE INDEX IF NOT EXISTS chunks_tsv_idx
    ON chunks USING gin (tsv);

-- Makes "delete every chunk for this document, then re-insert" cheap during
-- re-ingest (Step 7).
CREATE INDEX IF NOT EXISTS chunks_document_id_idx
    ON chunks (document_id);
