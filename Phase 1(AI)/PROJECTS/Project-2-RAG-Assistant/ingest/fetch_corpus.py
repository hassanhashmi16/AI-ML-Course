"""Step 2 deliverable: build the corpus.

Downloads the plain-text Wikipedia article for each of the 14 eight-thousanders
plus the "Eight-thousander" list article, and caches them under `data/raw/`.
A `manifest.json` records where each file came from, how big it is, and its hash.

Why the standard library and not `requests`: a plain HTTP GET does not need a
third-party package. Keeping the fetch step dependency-free means anyone can
rebuild the corpus with nothing installed, and the only dependency we take on is
the one we actually need. (`requests` earns its place only when we need sessions,
retries, and streaming uploads, which this does not.)

Run it from the project root:

    python -m ingest.fetch_corpus            # fetch anything missing
    python -m ingest.fetch_corpus --force    # re-fetch everything

Network behavior: a free public API is a shared resource, so we send a
descriptive User-Agent (Wikipedia requires one) and pause briefly between calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from config import PEAKS_JSON, RAW_DIR

# Wikipedia's Action API. `prop=extracts&explaintext=1` returns the article as
# plain text (no HTML tags, no wikitext markup). That is exactly what we want:
# it means Step 3's cleaning has almost nothing left to strip out.
WIKI_API = "https://en.wikipedia.org/w/api.php"

# Wikipedia's API policy requires a descriptive User-Agent so they can identify
# automated clients. A generic or missing UA may be blocked. Replace the contact
# with your own if you adapt this script.
USER_AGENT = "eight-thousanders-rag/0.1 (learning project; contact: you@example.com)"

# The list article is fetched too. It is the one page that discusses all 14 peaks
# together (records, death rates, disputed ascents), so questions like "which
# 8000er is the deadliest?" have a passage to retrieve.
LIST_TITLE = "Eight-thousander"
LIST_SLUG = "list-eight-thousanders"

# Politeness delay between requests, in seconds. 15 requests at half a second is
# nothing, but the habit is the point.
REQUEST_PAUSE_S = 0.5


def slugify(name: str) -> str:
    """Turn a peak name into a safe filename: 'Gasherbrum I' -> 'gasherbrum-i'."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def fetch_extract(title: str) -> tuple[str, str]:
    """Fetch one article's plain text.

    Returns (resolved_title, text). The resolved title matters because Wikipedia
    may redirect ('Annapurna' -> 'Annapurna Massif'), and we want to record where
    the text actually came from, not the name we happened to ask for.
    """
    params = {
        "action": "query",
        "prop": "extracts",   # ask for article text, not page metadata
        "explaintext": "1",   # plain text, not HTML
        "redirects": "1",     # follow redirects, so near-miss titles still resolve
        "format": "json",
        "titles": title,
    }
    url = f"{WIKI_API}?{urllib.parse.urlencode(params)}"

    # A Request object lets us set headers; urlopen does the actual GET.
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.load(response)  # json.load reads straight from the stream

    # The API nests results as query.pages.{pageid}. Asking for one title gives
    # exactly one page, so we can take the only value without knowing its id.
    pages = payload["query"]["pages"]
    page = next(iter(pages.values()))

    if "missing" in page:  # the title does not exist (a typo, usually)
        raise ValueError(f"no Wikipedia article for {title!r}")

    return page["title"], page.get("extract", "")


def wiki_url(resolved_title: str) -> str:
    """Build the human-readable article URL we record for provenance."""
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(
        resolved_title.replace(" ", "_")
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch and cache the eight-thousander corpus."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-fetch even if the file already exists on disk",
    )
    args = parser.parse_args()

    # Create data/raw/ if it does not exist yet (parents=True is harmless here).
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    peaks = json.loads(PEAKS_JSON.read_text(encoding="utf-8"))["peaks"]

    # The existing manifest lets a re-run reuse provenance for files it skips,
    # instead of inventing it again.
    manifest_path = RAW_DIR / "manifest.json"
    existing = {}
    if manifest_path.exists():
        existing = {
            entry["file"]: entry
            for entry in json.loads(manifest_path.read_text(encoding="utf-8"))
        }

    # Build the work list: every peak, then the list article.
    targets = [(peak["name"], peak["wiki_title"]) for peak in peaks]
    targets.append(("Eight-thousander list", LIST_TITLE))

    manifest = []
    for name, title in targets:
        slug = LIST_SLUG if title == LIST_TITLE else slugify(name)
        dest = RAW_DIR / f"{slug}.txt"

        if dest.exists() and not args.force:
            # Cached: read it back so we still compute the hash for the manifest.
            text = dest.read_text(encoding="utf-8")
            resolved = existing.get(dest.name, {}).get("title", title)
            print(f"skip   {dest.name} (cached)")
        else:
            resolved, text = fetch_extract(title)
            dest.write_text(text, encoding="utf-8")
            print(f"fetch  {dest.name}  <- {resolved}  ({len(text):,} chars)")
            time.sleep(REQUEST_PAUSE_S)  # be polite between real requests

        manifest.append(
            {
                "file": dest.name,
                "peak": name,
                "title": resolved,
                "url": wiki_url(resolved),
                "bytes": len(text.encode("utf-8")),
                "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
        )

    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    total = sum(entry["bytes"] for entry in manifest)
    print(f"\n{len(manifest)} files, {total:,} bytes total, in {RAW_DIR}")
    print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    main()
