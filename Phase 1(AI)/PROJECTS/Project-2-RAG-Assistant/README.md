# Project 2: Eight-Thousanders RAG Assistant

A retrieval-augmented assistant over the 14 eight-thousanders, the mountains
above 8,000 m. Ask a question in plain English; it retrieves the relevant
passages and answers with citations.

The point of this project is **hybrid retrieval + reranking, not naive top-k**.
Everything is built by hand, no LangChain, and every layer is measured.

See `STEPS.md` for the full step-by-step breakdown.

## Setup

```bash
python -m venv venv
venv\Scripts\activate            # Windows (source venv/bin/activate on macOS/Linux)
pip install -r requirements.txt
copy .env.example .env           # then fill in your keys
```

## Status

The implementation now includes the pipeline from corpus ingestion through the
React interface:

- Fetching, parsing, chunking, embedding, and storing the source articles in Postgres with pgvector.
- Dense and keyword retrieval, query rewriting, reciprocal rank fusion, and cross-encoder reranking.
- Structured lookups for exact facts, plus generated answers with source references.
- A FastAPI service with blocking and streaming answer endpoints, and a React UI with a Sources panel.
- A retrieval evaluation harness over 20 labelled questions, comparing dense, hybrid, and hybrid + rerank using recall@5, MRR, and nDCG.

This is a local project; a public deployment is still ahead. The streaming UI
shows the retrieved sources, while the blocking endpoint returns the sources
selected by the model's citations. See `STEPS.md` for the build plan and how
this project extends into the later agent and monitoring work.
