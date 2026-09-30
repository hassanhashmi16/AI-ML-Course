"""Central configuration for the Eight-Thousanders RAG assistant.

Every tunable value lives here and nowhere else. The rest of the codebase
imports from this module, so changing the embedding model, the chunk size, or
the retrieval depth is a one-line edit instead of a hunt across files.

Why a dedicated config file: sprinkling constants into whichever module happens
to use them is how projects rot, and it makes "which k did that run use?" a
question with no single answer. One source of truth fixes both.

This is the *only* file that reads secrets from the environment.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load variables from a local .env file into the process environment.
# `override=False` means a variable already set in the real environment (CI,
# Docker) wins over the .env file. That is the behavior you want in production.
load_dotenv(override=False)


# ---------------------------------------------------------------------------
# Paths
# Anchored to this file's location rather than the current working directory,
# so the code behaves the same whether you run it from the project root or from
# a subfolder. `BASE_DIR` is the Project-2-RAG-Assistant/ directory itself.
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
RAW_DIR = DATA_DIR / "raw"             # cached article text, one file per peak
PEAKS_JSON = DATA_DIR / "peaks.json"   # structured facts for the 14 peaks
DB_DIR = BASE_DIR / "db"


# ---------------------------------------------------------------------------
# Secrets / connection
# Read once, here. No other module calls os.getenv for these. Defaults are
# empty strings rather than exceptions so that early steps that don't need a
# given key still import cleanly.
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/ragdb"
)


# ---------------------------------------------------------------------------
# Models
# Pin exact names. Library defaults move under you, and a silent model change
# is the hardest kind of bug to notice: the code still runs and answers just
# get quietly worse. Verify these names against the current docs before relying
# on them (names pinned as of September 2026).
# ---------------------------------------------------------------------------
GEMINI_MODEL = "gemini-2.0-flash"          # generation; matches Project 1
EMBED_MODEL = "models/text-embedding-004"  # Gemini embeddings (768-dim)
EMBED_DIM = 768                            # MUST match vector(N) in db/schema.sql
COHERE_RERANK_MODEL = "rerank-v3.5"        # hosted cross-encoder reranker


# ---------------------------------------------------------------------------
# Chunking
# Sized in tokens, not characters. Tokens are what the embedding model and the
# LLM actually count, and for English roughly 1 token ≈ 4 characters.
# ---------------------------------------------------------------------------
CHUNK_TOKENS = 500
CHUNK_OVERLAP_TOKENS = 75  # ~15%. Lets a sentence split across chunks be found.


# ---------------------------------------------------------------------------
# Retrieval
# The core quality/latency knobs. Retrieve wide, rerank narrow: each retriever
# returns RETRIEVE_K candidates, RRF fuses them, and the reranker cuts down to
# RERANK_K chunks before anything reaches the LLM.
# ---------------------------------------------------------------------------
RETRIEVE_K = 20  # candidates from each retriever (dense and sparse)
RERANK_K = 5     # chunks that actually reach the generator
