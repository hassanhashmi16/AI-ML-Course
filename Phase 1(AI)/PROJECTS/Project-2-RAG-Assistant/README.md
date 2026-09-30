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

Step 1 (skeleton + config) is complete. See `STEPS.md` for what each later step adds.
