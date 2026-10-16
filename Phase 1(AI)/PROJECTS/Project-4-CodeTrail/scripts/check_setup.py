r"""Check installed integrations and settings without calling provider APIs.

Run from the project folder with:
    .\.venv\Scripts\python.exe scripts\check_setup.py --with-eval
"""

import argparse
import os
import sys
from importlib import import_module
from importlib.metadata import version
from pathlib import Path

# Running a file inside scripts/ otherwise places scripts/, rather than the
# project folder, first on Python's module search path.
PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

# Distribution names (used by installers) can differ from Python import names.
IMPORTS = {
    "pydantic": "pydantic",
    "pydantic-settings": "pydantic_settings",
    "langchain-core": "langchain_core",
    "langchain-google-genai": "langchain_google_genai",
    "langchain-text-splitters": "langchain_text_splitters",
    "langchain-qdrant": "langchain_qdrant",
    "langchain-cohere": "langchain_cohere",
    "qdrant-client": "qdrant_client",
    "fastembed": "fastembed",
    "langgraph": "langgraph.graph",
    "langgraph-checkpoint-sqlite": "langgraph.checkpoint.sqlite",
    "langsmith": "langsmith",
    "PyGithub": "github",
    "diskcache": "diskcache",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "sse-starlette": "sse_starlette",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-eval", action="store_true", help="Also import Ragas.")
    args = parser.parse_args()

    # An offline setup check should not emit evaluation usage telemetry.
    os.environ["RAGAS_DO_NOT_TRACK"] = "true"
    print(f"Python {sys.version.split()[0]}", flush=True)
    integrations = {**IMPORTS, **({"ragas": "ragas"} if args.with_eval else {})}
    for distribution, module in integrations.items():
        import_module(module)  # Import only: do not create models or download weights.
        print(f"  OK {distribution} {version(distribution)}", flush=True)

    # Import actual entry points we will use, rather than just package roots.
    from langchain_core.documents import Document
    from langchain_cohere import CohereRerank
    from langchain_qdrant import FastEmbedSparse, QdrantVectorStore
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.prebuilt import ToolNode

    document = Document(page_content="setup check", metadata={"source_id": "smoke"})
    assert document.metadata["source_id"] == "smoke"
    print("  OK reranker, sparse/store, checkpoint, and tool-executor entry points")

    # Settings load without credentials; never print secrets or dump all fields.
    from config import settings

    print(f"Settings OK: retrieve {settings.retrieve_k}, rerank {settings.rerank_k}")
    print(f"Runtime data: {settings.data_dir}")
    print("Setup check passed. No provider requests or model-weight downloads made.")


if __name__ == "__main__":
    main()
