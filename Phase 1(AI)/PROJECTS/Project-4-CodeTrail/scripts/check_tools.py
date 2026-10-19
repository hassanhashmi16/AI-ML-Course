r"""Exercise Step 10: the investigator tools bound to a trusted run context.

Run from the project folder with:
    .\.venv\Scripts\python.exe scripts\check_tools.py

Builds an index containing only source files, then drives each tool and
checks it can follow a real evidence lead and make newly fetched material
searchable. No LLM calls; GitHub reads replay from the Step 5 cache.

What is verified:
  1. search_evidence returns scoped, citable results (source_ids that belong
     to this repository@snapshot).
  2. read_discussion(4682) fetches the PR + reviews, indexes them, and a
     follow-up search finds the PR -- which was deliberately absent before.
  3. list_file_history -> read_change follows a commit trail correctly.
  4. read_code returns a file with its source_id.
  5. Every tool has a description, and every output stays within its budget.
"""

import re
import sys
from pathlib import Path

# Running a file inside scripts/ otherwise places scripts/, rather than the
# project folder, first on Python's module search path.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from agent.tools import TOOL_CHAR_LIMIT, ToolContext, build_tools  # noqa: E402
from github_source.client import get_github, get_repository, resolve_ref  # noqa: E402
from github_source.collect import Collector  # noqa: E402
from ingest.index import index_records  # noqa: E402
from retrieval.clients import (  # noqa: E402
    build_embeddings,
    build_sparse_embedding,
    build_vector_store,
    collection_name,
    open_qdrant,
    reset_collection,
)

REPO = "https://github.com/pallets/flask"
EXPECTED_SHA = "b17bb9ed563ab2857c0db9a07ec4e6407404c7be"
PR_ID = "github:pallets/flask:pr:4682"


def main() -> None:
    gh = get_github()
    repo = get_repository(gh, REPO)
    snapshot = resolve_ref(gh, REPO, "2.2.0")
    assert snapshot.sha == EXPECTED_SHA

    collector = Collector(repo, snapshot)
    collection = collection_name(snapshot)
    client = open_qdrant()
    try:
        embeddings = build_embeddings()
        sparse = build_sparse_embedding()

        # Start with files only; the PR is deliberately NOT indexed yet.
        collector.add_file("src/flask/ctx.py")
        collector.add_file("src/flask/globals.py")
        records = [collector.sources[key] for key in sorted(collector.sources)]
        reset_collection(client, embeddings, collection)
        store = build_vector_store(
            client, embeddings, collection, sparse_embedding=sparse, mode="hybrid"
        )
        index_records(client, store, collection, snapshot, records, rebuild=True)

        context = ToolContext(
            repo=repo,
            snapshot=snapshot,
            collector=collector,
            client=client,
            embeddings=embeddings,
            sparse_embedding=sparse,
            store=store,
            collection=collection,
        )
        tools = {item.name: item for item in build_tools(context)}
        assert set(tools) == {
            "search_evidence",
            "read_code",
            "list_file_history",
            "read_change",
            "read_discussion",
        }
        assert all(item.description for item in tools.values()), "tools need descriptions"

        # 1) Scoped, citable search results.
        search_output = tools["search_evidence"].invoke(
            {"query": "how does Flask isolate application and request context state?", "k": 3}
        )
        source_ids = re.findall(r"source_id: (\S+)", search_output)
        assert source_ids, "search returned no citable results"
        assert all(identifier.startswith("github:pallets/flask@") for identifier in source_ids)
        assert PR_ID not in search_output, "the PR should not be indexed yet"
        print(f"PASS  search_evidence: {len(source_ids)} scoped result(s), citable source_ids")

        # 2) Newly fetched discussion becomes searchable in the same run.
        discussion = tools["read_discussion"].invoke({"number": 4682})
        assert PR_ID in discussion, "read_discussion did not return the PR record"
        follow_up = tools["search_evidence"].invoke(
            {"query": "LocalStack performance and memory overhead", "k": 5}
        )
        assert PR_ID in follow_up, "newly indexed PR is not searchable"
        print("PASS  read_discussion -> indexed -> found by a follow-up search")

        # 3) Follow a commit trail: history -> change inspection.
        history = tools["list_file_history"].invoke(
            {"path": "src/flask/ctx.py", "limit": 3}
        )
        shas = re.findall(r"- ([0-9a-f]{40}) ", history)
        assert shas, "history did not expose commit SHAs"
        change = tools["read_change"].invoke({"sha": shas[0]})
        assert "Changed files" in change and "src/flask/ctx.py" in change
        print(f"PASS  trail: list_file_history -> read_change ({shas[0][:7]})")

        # 4) A file read carries its source_id.
        code = tools["read_code"].invoke({"path": "src/flask/globals.py"})
        assert "ContextVar" in code and "source_id:" in code
        print("PASS  read_code: file text with source_id")

        # 5) Outputs stay within budget.
        outputs = [search_output, discussion, follow_up, history, change, code]
        assert all(len(item) <= TOOL_CHAR_LIMIT + 100 for item in outputs)
        print(f"PASS  outputs bounded (max {max(len(item) for item in outputs)} chars)")
    finally:
        client.close()

    print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
