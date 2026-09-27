# Step 27: LangChain & LlamaIndex

> **Covers:** LangChain core (Runnables / LCEL, chat models, output parsers), retrievers / loaders / vector-store integrations, LlamaIndex (ingestion, indexes, query engines), the framework-vs-no-framework-vs-SDK trade-off, and reading a framework's source to debug it. Everything here is *glue over the primitives you already built in Steps 20–26* — this step teaches the glue and, more importantly, when to skip it.

---

## The Problem

You now know every piece of a RAG pipeline: load a document (Step 21), chunk it (Step 22), embed it (Step 20), store and search it (Steps 24–25), and retrieve the right pieces (Step 26). But wiring those pieces together is repetitive — every project re-implements "load → split → embed → store → retrieve → prompt → generate," and the glue code is fiddly and easy to get subtly wrong. LangChain and LlamaIndex exist to turn that wiring into something declarative and reusable, so you write one expression instead of seven bespoke functions.

The catch, and the reason this step exists as its own topic: these frameworks add a layer of abstraction that *leaks*, an API that *churns*, and a vocabulary you have to learn. So the real goal isn't "memorize LangChain" — it's to understand what the framework *does* (compose primitives), what it *doesn't* do (add any new capability), and to know when the honest answer is "don't use a framework at all."

---

## Foundational Concepts

### A framework is a naming scheme over primitives you already own

Nothing in LangChain or LlamaIndex is new capability. A "retriever" is the vector search you built in Step 24. A "document loader" is Step 21's parsing. An "embedding" is Step 20. The framework's entire value is **standard interfaces + composition**: it gives every piece the same shape so they can snap together. That's it. If you keep that in mind, none of this will feel like magic — because none of it is.

### The one idea everything reduces to

Both frameworks are built on the same mental model: **a unit of work that takes an input, does one step, returns an output, and can be chained with other units.** LangChain calls this unit a **Runnable** (composed with the `|` operator). LlamaIndex calls it an **index + query engine**. Learn this one idea and you've learned the framework; the rest is vocabulary.

### Why the API churns (and why you shouldn't memorize it)

These libraries change their "correct way" constantly — LangChain especially has rewritten its recommended surface several times (chains → LCEL → agents/LangGraph → `create_agent`). That churn is the strongest argument for **not memorizing the API**. The composition *concept* is stable even when the function names move. Learn the concept here; look up the current API in the official docs when you actually build, and the churn stops mattering.

---

## 27.1 — LangChain core: Runnables, LCEL, chat models, output parsers

### Chat models and messages

LangChain's first job is a **uniform interface** across model providers, so "swap OpenAI for Anthropic" is a one-line change:

```python
from langchain.chat_models import init_chat_model

model = init_chat_model("openai:gpt-4o")   # or "anthropic:claude-sonnet-4"
response = model.invoke("Hello")           # returns an AIMessage object
```

Chat models speak in **messages**, not raw strings:

- `SystemMessage` — the instructions ("you are a helpful assistant").
- `HumanMessage` — what the user said.
- `AIMessage` — what the model said back.

Why messages and not strings? Because a conversation is a *sequence* of these, and multi-turn chat, tool calls, and agents all need to track who said what. The uniform interface is what lets the rest of the framework treat any model identically.

### Runnables and LCEL (the composition primitive)

A **Runnable** is any object that exposes `invoke()` (run once, get a result), `stream()` (get output piece by piece), and `batch()` (run over a list of inputs) — plus async versions of each. That tiny interface is the whole contract.

**LCEL** (LangChain Expression Language) lets you compose Runnables with the `|` operator — and the crucial property is that **a chain of Runnables is itself a Runnable**:

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

prompt = ChatPromptTemplate.from_template("Summarize this: {text}")
chain = prompt | model | StrOutputParser()

result = chain.invoke({"text": "..."})   # the chain has the same interface as one component
```

Let me unpack what `|` actually does, because it's the entire trick:

1. `prompt` takes the input `{"text": "..."}` and turns it into a list of messages (it fills the `{text}` slot into the template).
2. `model` takes those messages and produces an `AIMessage`.
3. `StrOutputParser` takes that `AIMessage` and extracts just the text string.

`|` means "take the output of the left, feed it as the input to the right." Because the chain exposes the *same* `invoke/stream/batch` interface as a single component, chains nest: a chain can contain a chain, and you can build arbitrarily deep pipelines from small, reusable pieces. That composability is the entire reason the framework is useful — and, as the deliverable shows, it's something you can rebuild yourself in ~60 lines of Python.

### Output parsers

An LLM returns text, but you usually want a structured object. An **output parser** is the Runnable that turns model output into a typed, validated value:

```python
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel

class Recipe(BaseModel):
    title: str
    ingredients: list[str]

parser = PydanticOutputParser(pydantic_object=Recipe)
chain = prompt | model | parser       # model text -> validated Recipe object
```

Why this matters: it's the bridge from "the LLM said some text" to "my code received a validated object it can trust." Output parsers handle the messy reality — asking the model for JSON, parsing it, and validating it against a schema — so the rest of your code gets clean data. This is the same structured-output idea you'll meet again in tool calling (Step 32).

---

## 27.2 — Retrievers, vector-store integrations, document loaders

These are the RAG-specific pieces, and the key realization is that **they're all Runnables too**, so they drop into chains exactly like a prompt or a model.

- **Document loaders** read text from a source (PDF, web page, Markdown, a database) into `Document` objects — Step 21's parsing, packaged with a uniform interface.
- **Splitters** chunk those `Document`s — Step 22, which you already did using LangChain's `RecursiveCharacterTextSplitter`.
- **Vector stores** (Chroma, FAISS, Pinecone, pgvector…) store embeddings. A vector store's `.as_retriever()` returns a **Retriever** — the abstraction for "given a query, return the relevant documents."

Putting it together, a complete RAG pipeline in LangChain is just composing the pieces you already understand:

```python
from langchain_chroma import Chroma
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

docs = TextLoader("notes.txt").load()                # 1. load
chunks = RecursiveCharacterTextSplitter(
    chunk_size=500, chunk_overlap=50
).split_documents(docs)                              # 2. split

vectorstore = Chroma.from_documents(chunks, embedding=embeddings)  # 3. embed + store
retriever = vectorstore.as_retriever(search_kwargs={"k": 5})       # 4. retriever

def format_docs(docs):
    return "\n\n".join(d.page_content for d in docs)

rag = (retriever | format_docs | prompt | model | StrOutputParser())  # 5. full RAG chain
```

The insight worth internalizing: **a retriever is just another Runnable.** You plug it into a chain exactly like a prompt or a model. "Build RAG" in LangChain is therefore not a new skill — it's "compose the primitives you already studied," with the framework handling the plumbing between them.

---

## 27.3 — LlamaIndex: ingestion, indexes, query engines

LlamaIndex covers the same ground but with a **different center of gravity**: it's *data-first* (organized around your documents and how to query them), where LangChain is *composition-first* (organized around chains and agents).

The core concepts:

- **Document → Node.** A `Document` is the source (a whole PDF, say); a `Node` is a chunk of it — like a `Document` with an ID and a reference back to its parent.
- **Ingestion pipeline** = load → parse → split → embed → store. The same steps you know, formalized into one flow.
- **Index** = the data structure over your nodes. The workhorse is `VectorStoreIndex` (dense embeddings), but there are others (`SummaryIndex` for summarization, `KeywordTableIndex` for keyword lookup).
- **Query engine** = index + retriever + response synthesizer, exposed as one `.query()` call. It takes a natural-language question and returns a synthesized answer *plus* the source chunks it used.
- **Chat engine** = a query engine with multi-turn state, for back-and-forth conversation over your data.

```python
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader

documents = SimpleDirectoryReader("./data").load_data()   # ingest
index = VectorStoreIndex.from_documents(documents)        # build the index
engine = index.as_query_engine()                          # wrap in a query engine
answer = engine.query("What is the refund policy?")       # synthesized answer + sources
```

**LangChain vs LlamaIndex, honestly:** for a basic RAG app they're near-interchangeable. The difference is *where the library's attention is*. Choose **LlamaIndex** when your app is fundamentally *about* a corpus — heavy ingestion, indexing, querying, and its deep document-parsing tooling (like LlamaParse for messy PDFs). Choose **LangChain** when your app is fundamentally *about* composition — chains, agents, swapping model providers, orchestrating many steps. The common mistake is stacking both, which just doubles the abstraction you have to learn for no benefit.

---

## 27.4 — Framework vs. no framework vs. vendor agent SDK

This is the highest-value section, because the honest answer is frequently "don't use a framework." Three ways to build the same thing:

| | Framework (LangChain/LlamaIndex) | No framework (plain SDK) | Vendor agent SDK (OpenAI/Anthropic) |
|---|---|---|---|
| What it is | Abstraction + composition layer | Direct `openai`/`anthropic` calls | First-party SDK tuned to one vendor |
| Best for | Swapping providers, complex pipelines, shared abstractions | Simple RAG, full control, minimal deps | Agents on one vendor, newest features |
| What it costs | API churn, abstraction leaks, heavy deps | More boilerplate you own | Vendor lock-in |
| You learn | Their vocabulary | The glue (which you already know) | One vendor's way |

**The honest rule of thumb:**

- For a simple retrieve-then-generate app, **no framework** is often the right call. You already know how to write loader → embed → store → retrieve → prompt, and ~50 lines of plain SDK code has zero magic to debug and zero dependency churn. No framework is the cheapest framework.
- Reach for a **framework** when you genuinely need to *swap providers* across many models, or *orchestrate* something complex — many steps, branching, agents, shared abstractions across a team.
- Reach for a **vendor agent SDK** when you're building agents on a single vendor and want its newest features without fighting an abstraction layer.

The deeper point — and the reason this step is "glue, not fundamentals" — is that **none of these add capability.** They add convenience, at a cost you should be *consciously choosing* to pay, not paying by default. The strongest engineers reach for the framework *after* they can articulate why the plain version isn't enough.

---

## 27.5 — Reading a framework's source (abstraction leaks)

Every abstraction eventually leaks: the framework does something you didn't expect, and the only way to understand it is to look underneath. The skill that separates "knows the framework" from "can debug it" is the willingness to read its source.

**What "abstraction leak" means:** the framework promises "give me a retriever, get a RAG chain," but hides the details — how the prompt is actually formatted, how the retriever calls the vector store, what default `k` is, how errors propagate. When behavior surprises you, the leak is the gap between the promise and the actual code.

**How to debug a framework (the practical loop):**

1. **Reproduce in the smallest case** — one document, one query, one step. Isolate which component misbehaves.
2. **Read the source of that component** — `print(obj)`, `inspect.getsource(obj)`, or jump to the class definition in your editor. LangChain Runnables expose their steps in a `steps` attribute; LlamaIndex components are plain Python classes.
3. **Follow the `invoke` path** — trace what `invoke()` actually calls (`invoke` → `_invoke` → the underlying model/retriever). The framework is thin; you'll hit the primitive you already know within a couple of hops.
4. **Find the default you didn't set** — most surprises are a default the framework chose for you (a `k=4`, a specific prompt template, a temperature). Once you find it, you can override it.

The point is not to memorize source code — it's to **lose the fear of it.** You already understand every primitive underneath these frameworks, so when one misbehaves, reading its source is just following a call stack down to code you recognize. That's the difference between being *dependent on* a framework and being *in control of* it.

---

## Pitfalls

1. **Reaching for a framework by default.** For simple RAG, plain SDK calls are fewer moving parts and zero abstraction to leak. No framework is the cheapest framework.
2. **Memorizing the API instead of the concept.** The function names churn; the composition idea (a chain of units, `invoke/stream/batch`, `|`) doesn't. Learn the latter.
3. **Learning the framework *instead of* the primitives.** The framework wraps Steps 20–26. If you only know LangChain and not retrieval, you can't debug what it does — and you can't build without it.
4. **Treating the two as competitors.** LangChain (composition) and LlamaIndex (data/index) overlap heavily. Pick one, don't stack both.
5. **Ignoring the vendor SDK.** For agents on a single vendor, the first-party SDK is often simpler and gets features first.
6. **Not reading source when it misbehaves.** The framework isn't magic; when it surprises you, the answer is in the source, and you already understand the primitives it's calling.

---

## Quick Reference

| Concept | One-liner |
|---|---|
| Runnable | Anything with `invoke/stream/batch`; a chain of Runnables is a Runnable |
| LCEL (`|`) | Pipe output of one Runnable into the next |
| Chat model | Uniform interface over providers; speaks in Human/AI/System messages |
| Output parser | Turns model text into a typed/validated object |
| Document loader | Reads text from a source into `Document` objects |
| Retriever | "query → relevant documents"; a vector store's `.as_retriever()` |
| Index (LlamaIndex) | Data structure over your nodes (`VectorStoreIndex`) |
| Query engine | `index → retriever → synthesize → answer`, via `.query()` |
| Abstraction leak | The gap between a framework's promise and its actual code |

---

## Theory Summary

- **Frameworks add composition, not capability.** Every primitive they wrap, you already built in Steps 20–26. The framework is glue with a vocabulary.
- **The one stable idea is the chain of units.** LangChain's `Runnable | Runnable` and LlamaIndex's `index → query engine` are the same concept: compose small steps into a pipeline.
- **Choose by the cost you're willing to pay.** Convenience (framework), control (no framework), or first-party speed (vendor SDK) — each has a real cost, and it's a decision, not a default.
- **Debugging is reading source.** Abstraction leaks are inevitable; the fix is following `invoke()` down to the primitive you already recognize, not memorizing more API.

---

## Deliverable

**`Phase 1(AI)/STEP 27/step27-framework/`**

- **`mini_lcel.py`** — a ~70-line, zero-dependency implementation of the *core idea* behind LangChain: a `Runnable` class with `invoke/stream/batch` and a `|` operator, plus example components (a prompt template, a fake LLM, a string parser) composed into a working chain. This teaches what a framework actually *does* by rebuilding the essential mechanism — and it's exactly the kind of code you'd read when debugging a real framework.

**Run it:** `python mini_lcel.py` (no dependencies).
