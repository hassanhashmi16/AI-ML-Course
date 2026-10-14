"""Web search — the agent's door to the outside world.

Two decisions shape this file:

- **Free by default.** `ddgs` (DuckDuckGo) needs no key, so the project runs for
  anyone who clones it. If `TAVILY_API_KEY` is set, we use Tavily instead —
  better result quality, same normalized output. `config.SEARCH_PROVIDER` makes
  that choice once, so this file just reads it.
- **Compact results only: title + url + snippet.** Never page bodies. Fetching a
  page is a *separate* tool with its own budget, and splitting them lets the
  agent spend context only on pages it deliberately chose to read. Merging them
  into one "search and read everything" tool is the fastest way to blow the
  context window.

Following the registry's contract, this function returns a single string and
lets `dispatch` handle failures — if the search backend raises (rate limit,
network), that becomes an error observation the model can react to.
"""
from __future__ import annotations

import json

from config import SEARCH_K, SEARCH_PROVIDER, TAVILY_API_KEY
from tools.registry import register


def web_search(query: str, k: int = SEARCH_K) -> str:
    """Search the web, returning compact results (title, url, snippet) as JSON.

    `k` is clamped rather than rejected: a model that asks for 50 results gets
    10, not an error. Cheap argument sanitisation (Step 32.8) that keeps one bad
    number from turning into a wasted turn.
    """
    k = max(1, min(int(k), 10))

    if SEARCH_PROVIDER == "tavily":
        results = _search_tavily(query, k)
    else:
        results = _search_ddgs(query, k)

    if not results:
        # An empty result set is information, not a failure: it tells the model
        # to rephrase the query rather than retry the same one.
        return "No results found."

    # ensure_ascii=False keeps non-English characters readable (and cheaper to
    # tokenize than \uXXXX escapes).
    return json.dumps(results, ensure_ascii=False, indent=2)


def _search_ddgs(query: str, k: int) -> list[dict]:
    """DuckDuckGo backend (free, keyless). Imported lazily like Tavily."""
    from ddgs import DDGS

    # ddgs returns [{'title', 'href', 'body'}, ...]. We rename to one shape so
    # the model never sees which provider answered.
    rows = DDGS().text(query, max_results=k)
    return [
        {
            "title": row.get("title", ""),
            "url": row.get("href", ""),
            "snippet": row.get("body", ""),
        }
        for row in rows
    ]


def _search_tavily(query: str, k: int) -> list[dict]:
    """Tavily backend (used only when a key is configured).

    Tavily returns {'results': [{'title', 'url', 'content', 'score'}, ...]}.
    `content` is Tavily's snippet field, not the full page.
    """
    from tavily import TavilyClient

    client = TavilyClient(api_key=TAVILY_API_KEY)
    response = client.search(query, max_results=k)
    return [
        {
            "title": row.get("title", ""),
            "url": row.get("url", ""),
            "snippet": row.get("content", ""),
        }
        for row in response.get("results", [])
    ]


# Register with the registry so the loop can call it without importing this
# module directly. The description is written FOR THE MODEL (Step 32.5): it says
# what it returns, when to use it, and — importantly — to follow up with
# fetch_page, because that is the mistake models make here (treating snippets as
# if they were source material).
register(
    {
        "name": "web_search",
        "description": (
            "Search the web. Returns a list of results with title, url, and a short "
            "snippet. Use it to find pages worth reading — it does NOT return full "
            "page text. After searching, call fetch_page on the URLs that look most "
            "relevant to read what they actually say."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query. Be specific; include a year for time-sensitive topics.",
                },
                "k": {
                    "type": "integer",
                    "description": "How many results to return (1-10). Defaults to 5.",
                },
            },
            "required": ["query"],
        },
        "fn": web_search,
    }
)
