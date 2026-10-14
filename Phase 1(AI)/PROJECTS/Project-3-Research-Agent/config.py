"""Central configuration for the Research Briefing Agent.

Every tunable value lives here and nowhere else. The rest of the codebase
imports from this module, so changing the model, the agent's step budget, or
where the database lives is a one-line edit instead of a hunt across files.

Why a dedicated config file: constants sprinkled into whichever module happens
to use them is how projects rot, and it turns "which step budget did that run
use?" into a question with no single answer. One source of truth fixes both.

This is the *only* file in the project that reads secrets from the environment.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Load variables from a local .env file into the process environment.
# `override=False` means a variable already set in the real environment (CI, a
# shell export) wins over the .env file. That is the behavior you want in
# production: the machine's real config beats a developer's local convenience.
load_dotenv(override=False)


# ---------------------------------------------------------------------------
# Paths
# Anchored to this file's location rather than the current working directory,
# so the code behaves the same whether you run it from the project root or from
# a subfolder. `BASE_DIR` is the Project-3-Research-Agent/ directory itself.
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"            # runtime state lives here
DB_PATH = DATA_DIR / "agent.db"         # SQLite: checkpoints + memory in one file
BRIEFS_DIR = BASE_DIR / "briefs"        # generated Markdown briefs


# ---------------------------------------------------------------------------
# Secrets
# Read once, here. No other module calls os.getenv for these. Defaults are
# empty strings rather than exceptions so that early steps which don't need a
# given key still import cleanly.
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Optional. When present, the agent searches via Tavily instead of DuckDuckGo.
# Left empty by default so the project runs with no extra signup (see below).
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")


# ---------------------------------------------------------------------------
# Models
# Pin exact names. Library defaults move under you, and a silent model change is
# the hardest bug to notice: the code still runs and answers just get quietly
# worse. This mirrors Project 2's model, which is already working with your key
# (names pinned as of October 2026).
# ---------------------------------------------------------------------------
GEN_MODEL = "gemini-3.6-flash"  # the tool-calling / generation model


# ---------------------------------------------------------------------------
# Search
# Which search backend to use, decided by what credentials exist rather than by
# a second setting the user could get out of sync. No Tavily key -> free,
# keyless DuckDuckGo. This "configure by presence" trick keeps one less thing to
# forget when setting up the project.
# ---------------------------------------------------------------------------
SEARCH_PROVIDER = "tavily" if TAVILY_API_KEY else "ddgs"
SEARCH_K = 5  # results returned per search; more results = more context spent


# ---------------------------------------------------------------------------
# Page fetching
# A single web page can be enormous, and every fetched character competes for
# the model's context window. Cap what we pull and what we keep.
# ---------------------------------------------------------------------------
FETCH_TIMEOUT_SECONDS = 15.0  # don't let one slow site stall the whole run
MAX_PAGE_CHARS = 8000         # truncate extracted text before it reaches the model


# ---------------------------------------------------------------------------
# Tools
# A single tool result can be arbitrarily large (a fat page, a long search
# dump). The registry truncates anything past this before it re-enters the
# context window — the "result sanitisation" half of Step 32.8, applied in one
# place so no individual tool has to remember to do it.
# ---------------------------------------------------------------------------
MAX_TOOL_RESULT_CHARS = 6000


# ---------------------------------------------------------------------------
# Agent budget
# These are the guardrails from Step 12. Defined here, enforced in policy.py.
# An agent with no ceiling is an agent that can loop forever and burn money.
# ---------------------------------------------------------------------------
MAX_STEPS = 25            # hard cap on model<->tool turns before we stop
TOKEN_BUDGET = 120_000    # rough ceiling on tokens spent across a single run


# ---------------------------------------------------------------------------
# Memory
# Cross-session memory (Step 8). Stored in the same SQLite file as checkpoints,
# in its own table. TOP_K caps how many remembered facts are loaded into context
# at the start of a run, so memory helps the agent without flooding it.
# ---------------------------------------------------------------------------
MEMORY_TOP_K = 5
