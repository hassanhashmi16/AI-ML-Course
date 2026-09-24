-- Enable the pgvector extension. "IF NOT EXISTS" makes this safe to run twice.
-- You only need this once per database; it adds the `vector` type + operators.
CREATE EXTENSION IF NOT EXISTS vector;

-- The items table: normal relational columns plus one vector column.
-- `vector(3)` means every row stores a list of exactly 3 floats (3 dimensions).
-- In a real RAG app this would be vector(1536) or whatever your model emits.
CREATE TABLE IF NOT EXISTS items (
    id         bigserial PRIMARY KEY,   -- auto-incrementing unique id
    content    text NOT NULL,           -- the text the embedding came from
    category   text NOT NULL,           -- metadata we'll filter on later
    embedding  vector(3)                -- the embedding, stored as a float array
);

-- An HNSW index over the embedding column, using cosine distance.
-- Without this, every search scans every row (exact but O(n)).
-- With it, searches are approximate but fast. "cosine_ops" means the index
-- is only used for the <=> (cosine) operator — query with a different operator
-- and Postgres silently ignores the index.
CREATE INDEX IF NOT EXISTS items_embedding_idx
    ON items USING hnsw (embedding vector_cosine_ops);
