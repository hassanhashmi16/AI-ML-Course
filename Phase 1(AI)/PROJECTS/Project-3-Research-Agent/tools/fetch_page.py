"""Page fetching — reads one URL and returns its main article text.

Why this is a separate tool from `web_search`: searching and reading are two
different budget decisions. Search returns compact snippets, so the agent can
scan many options cheaply; fetching spends real context, so it should be a
deliberate act on a page the agent chose to read.

Why extract at all: a raw HTML page is mostly markup — navigation, cookie
banners, scripts, footers. Feeding that to the model burns tokens on noise and
buries the actual content. `trafilatura` does readability-style extraction and
returns just the article body. This is Step 21's discipline ("garbage in breaks
everything downstream") applied to live pages instead of a fixed corpus.

Like every tool here, this function raises on failure and lets the registry turn
that into an error observation — no try/except.
"""
from __future__ import annotations

import httpx
import trafilatura

from config import FETCH_TIMEOUT_SECONDS, MAX_PAGE_CHARS
from tools.registry import register

# Some sites reject requests from unknown clients (403) or serve them a
# stripped page. A plain browser User-Agent is the difference between "works on
# most of the web" and "works on the handful of sites that don't care".
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch_page(url: str) -> str:
    """Fetch a URL and return its extracted article text, capped in length.

    Output starts with a `URL:` line so the page's address is in the model's
    context next to its content — which is what lets it later write a note with
    an accurate `source_url` (Step 6) and cite it in the brief (Step 7).
    """
    # Only http(s). Without this check a model could try file:// or other
    # schemes, which is an easy way to read local files by accident. Cheap
    # guard, real consequence (Step 32.8: validate arguments at the boundary).
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"only http(s) URLs are supported (got {url!r})")

    response = httpx.get(
        url,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,     # most real links redirect; without this they 3xx
        timeout=FETCH_TIMEOUT_SECONDS,
    )
    # Raises on 4xx/5xx, which the registry turns into a readable error string.
    response.raise_for_status()

    # include_comments=False: comment sections are user-generated noise, not
    # article content. include_tables=True: tables often hold the facts we want.
    text = trafilatura.extract(
        response.text,
        url=url,
        include_comments=False,
        include_tables=True,
    )

    if not text or len(text.strip()) < 200:
        # Extraction failure is a normal outcome (JS-rendered pages, PDFs, login
        # walls). Say so plainly: the model's correct move is to pick another
        # URL, not to retry this one.
        return (
            f"URL: {url}\n"
            "No extractable article text on this page. It may be JavaScript-rendered, "
            "a PDF, or mostly navigation. Try a different URL."
        )

    if len(text) > MAX_PAGE_CHARS:
        # Cap before the text enters the transcript. The tail of a long article
        # is rarely what the agent needed, and the cap is what keeps one greedy
        # fetch from crowding out the rest of the run's context.
        text = text[:MAX_PAGE_CHARS] + "\n[...truncated]"

    return f"URL: {url}\n\n{text}"


register(
    {
        "name": "fetch_page",
        "description": (
            "Fetch one web page and return its main article text (markup and navigation "
            "stripped). Use it after web_search to actually read a promising result. "
            "Long pages are truncated. If it reports no extractable text, do not retry "
            "the same URL — pick another result instead."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The full http(s) URL of the page to read.",
                }
            },
            "required": ["url"],
        },
        "fn": fetch_page,
    }
)
