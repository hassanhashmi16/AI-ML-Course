# Step 13: Embeddings & Similarity Search

> **What it covers:** What an embedding vector is, cosine similarity, embedding APIs, and the limits of pure similarity search — how "search by meaning" actually works.

---

## Foundational Concepts

### The core problem: computers don't understand meaning

A computer sees "apple" as the string `"apple"` — five characters. `"apple" == "orange"` is False. `"apple" == "Apple"` is False. There's no notion that an apple is more like an orange than it is like a car. To a computer, all strings are equally different unless we explicitly tell them otherwise.

Keyword search (what Google did in the 90s) solves this by checking for exact word matches. The query "apple fruit" finds documents containing "apple" and "fruit." But it fails when someone searches "pome" (the botanical term for apple) or "orchard harvest" — different words, same meaning.

**Embeddings solve this by converting meaning into geometry.** Every piece of text maps to a point in a high-dimensional space. Similar texts end up at nearby points. The meaning of "apple" is encoded by its position relative to "orange" (close), "fruit" (close), and "car" (far). Instead of comparing strings, we compare distances.

### What is a vector?

A vector is just a list of numbers. `[0.5, -0.2, 0.8, ...]`. That's it. If you've used NumPy or done linear algebra, you've worked with vectors. If not: think of a vector as coordinates in space. `[3, 4]` is a point 3 units right and 4 units up on a 2D grid. `[3, 4, -2]` is a point in 3D space.

An embedding vector is the same idea, but with **1536 or 3072 dimensions** instead of 2 or 3. We can't visualize 1536-dimensional space, but the math works the same as it does in 2D — distances, angles, directions all generalize.

### What is an embedding space?

Imagine a 2D space where you plot words:

```
                    fruit
                      |
             apple -- + -- orange
                      |
                    vehicle
                      |
                     car
```

Here, "apple" and "orange" are close because they're both fruits. "Car" is in a different region. "Fruit" sits between them because it's related to both. This is the intuitive idea — but real embedding spaces have thousands of dimensions and encode far more nuanced relationships.

A famous property of good embedding spaces: **vector arithmetic works**. Take the vector for "king," subtract "man," add "woman," and the nearest vector to the result is "queen." The space captures analogies.

```
king - man + woman ≈ queen
```

This isn't programmed explicitly. The model learned it from observing patterns in text during training.

### How an embedding model works (conceptually)

An embedding model is a neural network (usually a transformer) that takes text as input and outputs a vector. The training process teaches the model: "put similar texts at nearby points, different texts at distant points."

The input text passes through the transformer layers, which process each token in context of all other tokens (this is self-attention, covered in depth in Step 37). The final layer pools the token representations into a single vector. That vector is the embedding.

The specific numerical values of the embedding depend on:
- The model architecture (how many layers, how wide)
- The training data (what texts it saw during training)
- The training objective (specifically, what "similar" means — usually: do these texts appear together?)

### Why are embeddings useful?

Any task that involves measuring text relatedness:

| Task | How embeddings help |
|---|---|
| **Search** | Embed the query, find the nearest documents in embedding space |
| **Clustering** | Group texts by their positions in embedding space |
| **Classification** | Embed texts, use the vectors as features for a classifier |
| **Recommendation** | Embed users and items, recommend items nearest to the user |
| **Anomaly detection** | Flag texts that are far from all clusters |
| **Deduplication** | Find texts whose embeddings are nearly identical |

In the course roadmap, you'll use embeddings most heavily for **RAG** (Retrieval-Augmented Generation), starting Step 14.

---

## 13.1 — What an Embedding Vector Is

### The concrete output

An embedding is a list of floating-point numbers. For OpenAI's `text-embedding-3-small`, it's 1536 floats. For `text-embedding-3-large`, it's 3072. Here's what a real embedding looks like (first 10 of 1536 values):

```python
[0.0053, -0.0124, 0.0331, -0.0089, 0.0217, -0.0156, 0.0423, -0.0031, -0.0289, 0.0112, ...]
```

These numbers by themselves are meaningless to read. The meaning is in the **pattern relative to other embeddings**. Each dimension captures some latent feature the model learned — not a feature a human would name, but a statistical pattern that helps distinguish texts.

### What determines whether two embeddings are "similar"?

Two texts get similar embeddings when they:
- Use similar vocabulary ("dog" and "puppy" → close)
- Discuss similar topics ("how to bake bread" and "bread recipe" → close)
- Have similar writing style (formal vs. casual → may differ)
- Appear in similar contexts in the training data

Two texts get **different** embeddings when they:
- Discuss unrelated topics ("quantum physics" vs. "recipe for pasta")
- Express opposite sentiments (positive review vs. negative review of the same product)
- Use different language to describe the same thing ("myocardial infarction" vs. "heart attack" — depending on the model)

### Important: embeddings capture statistical patterns, not truth

An embedding model trained on Reddit comments will place "that's what she said" close to "that's a great point" because they co-occur in similar contexts. The model has no understanding that one is a joke and the other is sincere. It only knows that they appear in statistically similar environments.

This matters because: **garbage in, garbage out.** If your texts are noisy, the embeddings will be noisy. If your domain is highly specialized (medical, legal), make sure your embedding model was trained on that domain.

### The embedding pipeline

```
raw text → tokenize → transformer model → pooling → normalized vector
```

1. **Tokenize**: split text into tokens (subwords). "Embeddings are useful" → `["Em", "bed", "dings", " are", " useful"]`
2. **Transformer**: process tokens through the model, producing a vector per token
3. **Pooling**: combine token vectors into one vector (usually mean pooling or using the \[CLS\] token)
4. **Normalize**: divide by the vector's length so it has magnitude 1 (this makes cosine similarity = dot product)

Steps 2-4 are handled by the embedding API. You send text, you get a vector back.

---

## 13.2 — Cosine Similarity

### The intuition

Once every text is a point in embedding space, "how similar are these texts?" becomes "how close are these points?"

**Cosine similarity** measures the angle between two vectors. Two vectors pointing in the same direction have cosine similarity = 1. Vectors at right angles = 0. Vectors pointing opposite = -1.

In embedding space:
- Nearly all similarities are between 0 and 1 (embedding vectors point in the same general direction — positive space)
- A similarity of 0.9+ means the texts are nearly identical in meaning
- 0.7–0.9 means closely related topics
- 0.5–0.7 means somewhat related
- Below 0.3 means essentially unrelated

### The formula

```
cosine_similarity(A, B) = (A · B) / (||A|| * ||B||)
```

Where:
- `A · B` is the **dot product**: sum of `A[i] * B[i]` for all dimensions
- `||A||` is the **magnitude** (length) of A: square root of `sum(A[i]^2)`

If vectors are already normalized to length 1 (which most embedding APIs return), the denominator is 1, and cosine similarity = dot product.

### In code

```python
import numpy as np

def cosine_similarity(a: list[float], b: list[float]) -> float:
    a = np.array(a)
    b = np.array(b)
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# If vectors are pre-normalized:
def dot_product(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))

# Example with real embeddings
embedding_apple = [0.023, -0.045, 0.067, ...]  # 1536 numbers
embedding_orange = [0.031, -0.052, 0.059, ...]
embedding_car = [-0.089, 0.012, -0.076, ...]

similarity_fruit = cosine_similarity(embedding_apple, embedding_orange)   # ~0.85
similarity_different = cosine_similarity(embedding_apple, embedding_car)  # ~0.20
```

### Which distance metric to use

| Metric | What it measures | Range | Notes |
|---|---|---|---|
| **Cosine similarity** | Angle between vectors | [-1, 1] | Standard choice. Invariant to vector length. |
| **Dot product** | Cosine sim for normalized vectors | [0, 1] | Faster computation if vectors are unit-length. |
| **Euclidean distance** | Straight-line distance | [0, ∞) | Sensitive to vector length. Same ranking as cosine for normalized vectors. |
| **L2 distance** | Same as Euclidean | [0, ∞) | Used by some vector databases as the native metric. |

For retrieval, cosine similarity is the default. The embedding models from both OpenAI and Google normalize their output vectors, so dot product gives the same ranking.

### Why we use cosine (not Euclidean) for text

Euclidean distance measures absolute distance between points. A document about "dog" and a document about "puppy" might have similar direction but different lengths (the "puppy" doc might be more emphatic). Cosine similarity ignores length and measures direction only — it captures "what you're about" not "how loudly you're saying it."

In embedding space, vector direction ≈ semantics. Vector magnitude ≈ emphasis/specificity. For search, we usually care about direction.

### A concrete search example

```python
query = "healthy breakfast ideas"
documents = [
    "10 recipes for a nutritious morning meal",
    "car maintenance schedule for 2024",
    "how to cook eggs for beginners",
    "stock market analysis for today",
]

# Step 1: embed everything
query_emb = embed(query)
doc_embeddings = [embed(doc) for doc in documents]

# Step 2: compute similarities
scores = [cosine_similarity(query_emb, de) for de in doc_embeddings]

# Step 3: rank by similarity
results = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
# 1. "10 recipes for a nutritious morning meal"  → ~0.82
# 2. "how to cook eggs for beginners"              → ~0.65
# 3. "car maintenance schedule for 2024"           → ~0.15
# 4. "stock market analysis for today"             → ~0.10
```

It correctly ranks recipe docs first, even though none of them contain the words "healthy" or "breakfast." The embedding captures the semantic relationship.

---

## 13.3 — Embedding APIs

### OpenAI

```python
from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

response = client.embeddings.create(
    input="Your text string here",
    model="text-embedding-3-small",  # or "text-embedding-3-large"
)

embedding = response.data[0].embedding  # list of 1536 floats
print(len(embedding))  # 1536
```

**Supported models:**

| Model | Dimensions | Max input tokens | Relative cost |
|---|---|---|---|
| `text-embedding-3-small` | 1536 | 8191 | 1x |
| `text-embedding-3-large` | 3072 | 8191 | ~6.5x |
| `text-embedding-ada-002` | 1536 | 8191 | ~2x (legacy) |

You can reduce dimensions with the `dimensions` parameter:

```python
response = client.embeddings.create(
    input="Your text",
    model="text-embedding-3-large",
    dimensions=256,  # trade accuracy for speed/storage
)
```

Even at 256 dimensions, `text-embedding-3-large` outperforms the legacy model at 1536 dimensions.

### Google Gemini

```python
import google.generativeai as genai
import os

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

result = genai.embed_content(
    model="models/text-embedding-004",
    content="Your text here",
)
embedding = result['embedding']  # list of 768 floats
```

Google's embedding models have varying dimensions (768, 768, 256 depending on model). Check the docs for the latest model names.

### Batch processing

Most embedding APIs accept a **list** of texts in a single call. This is more efficient than one-at-a-time:

```python
# ❌ Slow — one API call per text
embeddings = [embed(t) for t in texts]

# ✅ Fast — one API call for all texts
response = client.embeddings.create(
    input=texts,  # list of strings
    model="text-embedding-3-small",
)
embeddings = [d.embedding for d in response.data]
```

OpenAI's embedding API supports up to 2048 inputs per call. The response order matches the input order.

### Async for many texts

When embedding thousands of texts, use the async client (connecting to Step 12):

```python
from openai import AsyncOpenAI
import asyncio

client = AsyncOpenAI()

async def embed_batch(texts: list[str]) -> list[list[float]]:
    response = await client.embeddings.create(
        input=texts,
        model="text-embedding-3-small",
    )
    return [d.embedding for d in response.data]

async def embed_all(texts: list[str], batch_size: int = 100) -> list[list[float]]:
    batches = [texts[i:i+batch_size] for i in range(0, len(texts), batch_size)]
    tasks = [embed_batch(batch) for batch in batches]
    results = await asyncio.gather(*tasks)
    # flatten
    return [emb for batch_result in results for emb in batch_result]
```

### Storing embeddings

Embeddings are just lists of floats. Store them wherever you store data:

```python
# Option 1: JSON
import json
embeddings_json = json.dumps(embedding)

# Option 2: NumPy (for local work)
import numpy as np
np.save("embeddings.npy", np.array(embeddings))

# Option 3: Database (you'll use pgvector in Step 15)
# INSERT INTO documents (text, embedding) VALUES ('...', '[0.01, -0.02, ...]')
```

---

## 13.4 — Limits of Pure Similarity Search

### What similarity search can't do

Embeddings measure **statistical similarity**, not logical relevance or factual correctness. This leads to several failure modes:

**1. Negation**

```python
query = "products that are NOT expired"
# Embedding might place this NEAR documents about expired products
# because the vocabulary overlaps heavily — "product" + "expired"
# The word "not" is a single token that barely shifts the embedding.
```

The model sees "expired" as the central concept. The negation can be lost in the high-dimensional noise.

**2. Synonym mismatch for rare terms**

If your query uses a rare technical term, but your documents use a common synonym, the embedding might not bridge them — depending on whether the model saw both terms in the same contexts during training. "Myocardial infarction" and "heart attack" might map to nearby but not identical vectors.

**3. Context matters at the sentence level, not the word level**

```python
doc_a = "The band played until midnight."
doc_b = "The robber was caught by the police band."
# "band" has completely different meanings here
# A good embedding model will distinguish them based on context words
# But the similarity will be higher than "band" and "elephant"
```

The same word can embed differently depending on surrounding words. This is a feature (context-aware embeddings are better) but it also means two texts about different meanings of the same word can end up moderately similar despite being about different things.

**4. No understanding of factual correctness**

```python
doc_a = "The Earth is flat."
doc_b = "The Earth is round."
# These have nearly opposite factual claims, but their embeddings
# will be highly similar — same vocabulary, same structure,
# only one word differs. Similarity ≠ correctness.
```

Embeddings capture how texts are written, not whether they're true. Two contradictory texts about the same topic will have similar embeddings.

**5. The query intent gap**

```python
query = "how to fix a leaky faucet"
# User wants step-by-step instructions
# But the nearest documents might be:
# - "reasons faucets leak" (explanation, not fix)
# - "types of faucet washers" (background knowledge)
# - "calling a plumber costs" (unrelated to DIY)
```

The embedding doesn't know whether you want instructions, explanations, or pricing. It only knows your query is "about faucets." All three results are about faucets, but only one matches the intent.

**6. The curse of dimensionality**

In 1536-dimensional space, distances behave counterintuitively:
- All points are roughly equally distant from each other in high dimensions
- The ratio of nearest to farthest distances approaches 1 as dimensions increase
- This means similarity scores become less discriminative with more dimensions
- Reducing dimensions (the `dimensions` parameter in OpenAI's API) can actually improve retrieval quality for small datasets

This is why vector databases use **approximate nearest neighbor (ANN)** search instead of brute-force comparison — exact search across millions of high-dimensional vectors is both slow and less meaningful than you'd expect.

### Mitigations: what you'll learn in later steps

| Problem | Solution (upcoming step) |
|---|---|
| Negation, query intent | Query rewriting, multi-step retrieval (Step 23) |
| Large document coverage | Chunking (Step 14) |
| Ranking quality | Reranking with a cross-encoder |
| Not factual | RAG with citations, RAGAS evaluation (Step 17) |
| Slow with many vectors | HNSW index in pgvector (Step 15) |

### When similarity search IS the right tool

- **Finding related content**: "show me articles similar to this one"
- **Deduplication**: "find near-duplicate documents in this corpus"
- **Semantic clustering**: "group these support tickets by topic"
- **Cold-start recommendations**: "recommend products with descriptions similar to the user's past purchases"
- **First-pass retrieval**: "narrow 100,000 documents to 50 candidates" (then rerank with a more expensive method)

---

## 13.5 — Sparse vs. Dense Retrieval

### The other way to search: keyword matching

Before embeddings, search worked by **keyword matching**. The dominant algorithm is **BM25** (Best Matching 25), an evolution of TF-IDF. It works like this:

- Each document is represented by a sparse vector — one dimension per unique word in the vocabulary
- The value at each dimension is the word's importance: how often it appears in this document (TF) vs. how many documents it appears in (IDF)
- A query is converted to the same sparse vector
- Relevance = overlap between query vector and document vector

A sparse vector for "the brown fox jumps" might look like:

```
{"the": 1.2, "brown": 2.1, "fox": 3.4, "jumps": 2.8, ...}
```

Most entries are zero — hence "sparse." A text with 100 words produces a vector with ~100 non-zero values out of potentially 100,000+ vocabulary dimensions.

**This is fundamentally different from embeddings.** BM25 operates on exact word matches with weighting. Embeddings operate on meaning, regardless of word overlap.

### When to use each

| Criteria | BM25 (sparse) | Embeddings (dense) |
|---|---|---|
| **Exact match required** | "Error code 404" must match "Error code 404" exactly | Embeddings might blur "404" with "500" since both are error codes |
| **Synonym handling** | Fails — "car" won't match "automobile" | Works — both map to nearby points |
| **Typo tolerance** | Fails — "teh" won't match "the" | Partial — nearby misspellings may be close |
| **Out-of-domain vocabulary** | Works fine — matches on any exact word | May fail — rare terms might not have been seen during training |
| **Speed** | Very fast — inverted index, no math | Slower — requires full vector comparison |
| **Storage** | Minimal — just token counts | Large — 1536 floats per document |
| **Training required** | No — zero training, works on raw text | Yes — needs a trained embedding model |
| **Interpretability** | High — you can see exactly which words matched | Low — "it's similar because of dimension 427" is meaningless |

### The hybrid approach (best of both)

For production search systems, the best approach is often **hybrid search**: combine BM25 score and embedding similarity score.

```python
def hybrid_score(query: str, doc: str, bm25_score: float, emb_score: float) -> float:
    # Normalize both scores to [0, 1] range, then combine
    alpha = 0.3  # weight for BM25 (tune this)
    return alpha * normalize(bm25_score) + (1 - alpha) * emb_score
```

The alpha parameter controls the blend. Alpha = 0 means pure embedding search. Alpha = 1 means pure keyword search. The right value depends on your data and use case.

**Why hybrid works:** BM25 catches exact matches and rare terms. Embeddings catch synonyms and conceptual similarity. They fail in complementary ways — BM25 misses synonyms, embeddings miss rare exact matches. Together, they cover both failure modes.

Many vector databases (including pgvector, which you'll use in Step 15) support hybrid search natively. You'll also see this pattern in production RAG systems: BM25 as a fast first pass, embeddings for reranking, or both combined.

### Why this matters for the roadmap

When you build your RAG system (Projects 2–4), you'll default to embedding search because it's the popular approach. But knowing about BM25 means you can debug cases where embedding search fails: if a query has a rare technical term that's an exact match in one document, BM25 would catch it instantly. Embeddings alone might miss it.

The best engineers know both and pick the right tool per query type.

---

## 13.6 — How Embedding Models Are Trained

### The core idea: contrastive learning

Embedding models are trained with a simple objective: **pull similar texts together, push dissimilar texts apart.** This is called contrastive learning.

The training process:
1. Take a batch of text pairs labeled as "similar" (e.g., two sentences that mean the same thing, or a query and a relevant document)
2. Add "dissimilar" pairs (random texts that don't match)
3. Compute embeddings for all texts
4. The loss function rewards the model when similar pairs have high cosine similarity and dissimilar pairs have low similarity
5. Backpropagation adjusts the model weights to make this more true next time

The result: after training on millions of pairs, the model learns to map semantically related texts to nearby points.

### What counts as "similar" during training

Different training datasets define similarity differently:

| Training data type | What "similar" means | Example |
|---|---|---|
| **Paraphrase pairs** | Two sentences with the same meaning | "The cat sat on the mat" / "A cat is sitting on the rug" |
| **Query-document pairs** | A search query and a relevant result | "cheap flights to Tokyo" / "Budget airlines for Japan travel" |
| **Next sentence** | Two sentences that appear consecutively in a document | "She opened the door. The room was dark." |
| **Translation pairs** | Same sentence in different languages | "Hello" / "Bonjour" |
| **Instruction-following** | A task description and the correct output | "Summarize this" / (the summary) |

OpenAI's text-embedding-3 models were trained on a massive dataset of all these types, plus proprietary data. Google's embedding models similarly.

### Why this matters for your understanding

Once you know this, the behavior of embeddings makes sense:

- **Why are synonyms close?** Because the training data contains sentences where "car" and "automobile" appear in similar contexts — the model learned they're interchangeable.
- **Why do negations fail?** Because "not good" and "bad" appear in very different training pairs — the model might not have seen them paired as similar.
- **Why can't you train on just your own data?** You need millions of diverse pairs. A few hundred examples won't teach the model anything useful. This is why you use pre-trained embedding models and don't train your own from scratch.
- **Why fine-tuning works?** You can take a pre-trained embedding model and fine-tune it on a small set of domain-specific pairs (legal, medical, code) to adjust the space.

### What you'll build toward

In Step 40 (LoRA/PEFT), you'll learn to fine-tune embedding models for your specific domain. For now, the pre-trained APIs are sufficient.

---

## Additional Concepts

### Normalization

Embedding vectors from most APIs are **normalized to unit length** (magnitude = 1). This means:
- Cosine similarity = dot product (the denominator is 1)
- The vector lies on the surface of a hypersphere — only direction matters
- Magnitude differences between texts are discarded entirely

Normalization is done automatically by the API. You don't need to do it yourself. But understanding it matters because:

```python
# These are equivalent for normalized vectors:
sim1 = cosine_similarity(a, b)
sim2 = np.dot(a, b)  # same result, slightly faster

# If you ever get raw (un-normalized) vectors, you must normalize:
raw_vector = [0.5, 0.3, 0.8]
norm = np.linalg.norm(raw_vector)
normalized = [v / norm for v in raw_vector]
```

If you ever build your own embedding pipeline (e.g., from an open-source model), remember to normalize the output. Most vector databases assume normalized vectors.

### Text length and embedding quality

Very short texts (a single word) produce poor embeddings — there's not enough context for the model to disambiguate meaning. Very long texts (thousands of tokens) dilute the embedding because the model averages over many topics.

The sweet spot is a paragraph or short document (50–500 tokens). For longer documents, you'll use chunking (Step 14).

### Embedding multiple segments

Some use cases embed different parts of a document separately:

```python
# For a product page:
title_emb = embed(product["title"])
description_emb = embed(product["description"])
review_emb = embed(product["top_review"])

# Combine for search (concatenate or average)
product_emb = np.concatenate([title_emb, description_emb])
```

For retrieval, the title of a document is often more useful than the full body — titles are dense with distinguishing keywords.

### Pricing and token limits

OpenAI embedding pricing is per-token (not per-call). Input tokens are what you're charged for. The models have a maximum input length of 8191 tokens. Texts longer than this get truncated (you should pre-truncate or chunk them).

Gemini pricing is also per-character. Check current pricing pages.

### Embedding for code

Code embeddings work the same way as text embeddings, and the same models can embed both. Code search embeds function bodies and query natural language into the same space:

```python
query = "function to sort a list of dictionaries by a key"
code = """
def sort_by_key(items, key):
    return sorted(items, key=lambda x: x[key])
"""
query_emb = embed(query)  # natural language
code_emb = embed(code)    # code
# These should be similar if the embedding model saw code in training
```

---

## 13.7 — Bi-Encoder vs. Cross-Encoder

### The architecture distinction

There are two fundamentally different ways to compute text similarity:

**Bi-encoder** (what embedding APIs use):
- Query and document are encoded **separately** into two vectors
- Similarity = cosine distance between the two vectors
- **Fast**: all documents can be pre-encoded. Query encoding is cheap.
- **Cheap**: O(n) comparisons for n documents (just dot products)
- **Less accurate**: the two texts never "see" each other during encoding

**Cross-encoder**:
- Query and document are fed into the model **together** as one input
- Model outputs a similarity score directly (not a vector)
- **Slow**: you must run the model once per query-document pair
- **Expensive**: O(n) model inferences for n documents (not just dot products)
- **More accurate**: the model can compare specific words and phrases across both texts

```
Bi-encoder:
  query → [encoder] → vector Q
  doc1  → [encoder] → vector D1    similarity = cos(Q, D1)
  doc2  → [encoder] → vector D2    similarity = cos(Q, D2)

Cross-encoder:
  (query + doc1) → [encoder] → score 1
  (query + doc2) → [encoder] → score 2
```

### The retrieval-reranking pattern

In production, you use both:

```python
# Step 1: Bi-encoder (fast, cheap) — narrow candidates from 100K to 50
documents = vector_db.search(query_embedding, top_k=50)

# Step 2: Cross-encoder (slow, accurate) — rerank 50 to top 5
scores = cross_encoder.predict([(query, doc.text) for doc in documents])
reranked = [doc for _, doc in sorted(zip(scores, documents), reverse=True)][:5]
```

The bi-encoder eliminates 99.95% of documents. The cross-encoder carefully ranks the remaining candidates. This is the standard pattern in every production RAG system.

### When to use which

| Scenario | Use |
|---|---|
| **First pass retrieval** (100K → 50) | Bi-encoder. Speed matters here. |
| **Final ranking** (50 → 5) | Cross-encoder. Accuracy matters here. |
| **You have < 1000 documents** | Cross-encoder only is feasible |
| **You need real-time response** | Bi-encoder only (cross-encoder adds latency) |
| **You need high accuracy** | Both — the reranking step catches bi-encoder mistakes |

### Why this matters now

In Step 14 (chunking) and Step 15 (pgvector), you'll use a bi-encoder (embedding model) for retrieval. In Step 17 (RAGAS), you'll evaluate whether your retrieval is good enough. If it isn't, a cross-encoder reranker is your first improvement — and understanding this distinction now means you'll know why and when to add it.

---

## Additional Concepts (continued)

### Embedding dimension trade-offs

The number of dimensions in your embedding vector is a system design decision with real consequences:

| Dimensions | Storage (1M docs) | Query speed | Accuracy |
|---|---|---|---|
| 256 | ~1 GB | Fastest | Good for most tasks |
| 768 | ~3 GB | Fast | Better |
| 1536 | ~6 GB | Moderate | Best (`text-3-small`) |
| 3072 | ~12 GB | Slower | Best (`text-3-large`) |

The trade-off: more dimensions capture more nuanced relationships, but storage and query cost increase linearly. In high dimensions, the "curse of dimensionality" makes the space less discriminative anyway — the 3072-dim vector isn't 2x better than the 1536-dim one.

OpenAI's `dimensions` parameter lets you truncate embeddings from the large model while preserving most of the quality. A 256-dim `text-embedding-3-large` embedding still outperforms the full 1536-dim `ada-002` embedding on benchmarks.

**Rule of thumb:** start with 1536 dimensions. Only go higher if you have >1M documents and the accuracy gain justifies the cost. Only go lower if you're storage-constrained or need very fast queries.

### Embeddings are a general concept

The same idea — represent an entity as a vector — applies everywhere in ML:

| Domain | What gets embedded | Why |
|---|---|---|
| **Text** | Words, sentences, documents | Semantic search, clustering |
| **Images** | Pixels → feature vectors | Image search, similarity |
| **Users** | User behavior history | Recommendation systems |
| **Items** | Product descriptions, metadata | Recommend similar items |
| **Graphs** | Nodes in a network | Find related entities |
| **Audio** | Raw audio → spectrogram features | Music similarity, speech search |

The math is the same across all domains. An image embedding and a text embedding are both vectors of floats. You can even map multiple modalities into the same embedding space (CLIP does this for images and text — Step 55 in Phase 3).

Understanding this now means: when you learn about text embeddings, you're learning about a general technique that applies everywhere in AI/ML.

### Out-of-distribution embeddings

Embedding models perform poorly on text that's very different from their training data:

```python
# If your documents are in a specialized domain, test your embedding first
queries = ["What is the policy on PCI DSS compliance?"]
domain_docs = ["PCI DSS requirement 3.4: render PAN unreadable..."]

emb_q = embed(queries[0])
emb_d = embed(domain_docs[0])
score = cosine_similarity(emb_q, emb_d)

# If score is < 0.5 for obviously relevant content,
# your embedding model doesn't understand this domain
```

Signs of OOD degradation:
- Relevant documents score barely higher than random
- Rare technical terms get fragmented by the tokenizer
- The model confuses domain-specific jargon with general words

**Mitigations:**
- Test your embedding model on a few known-relevant pairs before committing
- For specialized domains (legal, medical, code), use domain-specific embedding models (e.g., `gte-small` for code, `BioBERT` for biomedical)
- Consider fine-tuning if the gap is large (covered in Step 40)

### How to evaluate and choose an embedding model (MTEB)

When choosing an embedding model, you don't guess — you check the **MTEB** (Massive Text Embedding Benchmark). It's the standard leaderboard that scores embedding models across 70+ datasets covering 8 tasks:

```python
# MTEB tasks that matter for different use cases:
# Retrieval:         how well does it find relevant docs?      → use this for RAG
# STS (STS):         how well does it measure similarity?      → use this for clustering
# Classification:    how well do embeddings work as features?  → use this for ML pipelines
# Reranking:         how well does it rank candidates?         → use this for search
# Clustering:        how well do similar texts group together? → use this for analysis
# Pair Classification: how well does it compare two texts?
```

The MTEB leaderboard (available at huggingface.co/spaces/mteb/leaderboard) lets you compare models. Key things to look for:

| What to check | Why |
|---|---|
| **Retrieval score** | Most relevant for RAG systems |
| **Model size** | Larger models are slower and more expensive |
| **Max tokens** | Can it handle your document lengths? |
| **Language support** | Does it work for your language(s)? |
| **Embedding dimensions** | Higher = more storage cost |

For production, `text-embedding-3-small` is a safe default — good scores, cheap, fast, 8191 token limit. For higher accuracy, use `text-embedding-3-large`. For open-source, `gte-small` or `e5-mistral` are strong options.

### Static vs. contextual embeddings (historical context)

Older embedding models (Word2Vec, GloVe, 2013–2018) produced **static** embeddings — one vector per word, regardless of context:

```
Word2Vec: "bank" → [-0.12, 0.45, ...]  # same vector whether river or savings
```

Modern embedding models (BERT-based, 2018+) produce **contextual** embeddings — the vector depends on surrounding words:

```
BERT: "river bank" → [0.23, -0.11, ...]    # financial context
BERT: "savings bank" → [-0.08, 0.34, ...]  # financial context  
```

This is why modern embeddings handle polysemy (words with multiple meanings) correctly. The attention mechanism (covered in Step 37) lets each word's representation be influenced by every other word in the text.

**Why this matters for your understanding:**
- Static embeddings are why old search systems confused "river bank" with "savings bank"
- Contextual embeddings solved this, making semantic search actually usable
- The embedding models you call via API are all contextual — but knowing the history helps you understand why they work

**Note:** The embedding APIs you use (OpenAI, Gemini) all produce contextual embeddings. You don't need to implement this yourself. But understanding the distinction helps when debugging — if your embeddings seem wrong for polysemous terms, check if the surrounding context is sufficient.

---

## Theory Summary

**Embeddings convert meaning into geometry.** Every text becomes a point in high-dimensional space. Similarity between texts is the distance between their points. This is the fundamental abstraction: meaning-as-position.

**The space is learned, not designed.** Nobody decides that dimension 427 represents "sentiment" and dimension 809 represents "topic." The model discovers these representations statistically from data. We can measure the outputs but we don't directly control the internal structure — we trust the training process.

**Cosine similarity measures direction, not magnitude.** Two texts can have very different lengths (one is a short query, the other is a long document) but similar embeddings if they're "about" the same thing. Cosine ignores magnitude and compares direction only — which is exactly what search needs.

**Embeddings are lossy.** Converting a paragraph of text into 1536 numbers discards a lot of information. You can cluster, search, and classify with embeddings, but you cannot reconstruct the original text from them. They're a compressed semantic representation, not a full text encoder.

**Similarity ≠ relevance.** The nearest neighbor in embedding space might not be what the user wants. Embeddings find texts that are written similarly, not texts that satisfy constraints, intent, or factual criteria. This is why RAG pipelines combine embedding retrieval with an LLM — the LLM adds reasoning that pure similarity lacks.

**High-dimensional space is weird.** Points are uniformly far apart in 1536 dimensions. The difference between the nearest and farthest neighbor shrinks as dimensions grow. This is the curse of dimensionality, and it's why you need good chunking, indexing, and reranking to make retrieval work at scale.

---

## Quick Reference

| Concept | Key point |
|---|---|
| **Embedding vector** | A list of floats (1536 for `text-3-small`) representing a text's meaning |
| **How similarity works** | Similar texts → nearby points in embedding space |
| **Cosine similarity** | Measures angle between two vectors; standard for text |
| **Dot product** | Same as cosine similarity for normalized vectors |
| **Euclidean distance** | Straight-line distance; same ranking as cosine for normalized vectors |
| **OpenAI model** | `text-embedding-3-small` (1536 dims) or `-large` (3072 dims) |
| **Max input** | 8191 tokens per text for OpenAI |
| **Batch API** | Pass a list of texts; one API call vs. one-per-text |
| **Best text length** | Paragraph level, ~50–500 tokens |
| **Main failure mode** | Similarity doesn't understand negation, intent, or factual truth |

---

## What to Practice

1. Embed 5 different sentences. Compute pairwise cosine similarities. Rank them. Does the ranking match your intuition?
2. Find a pair of sentences where cosine similarity is high but the actual meaning is opposite (e.g., "The meeting is on" vs. "The meeting is off"). This demonstrates the negation problem.
3. Embed a query and 10 sample documents. Implement search: embed the query, compute dot products, return the top 3. Verify with a keyword-based baseline — which results differ?
4. Use the `dimensions` parameter to create 256-dim and 1536-dim embeddings of the same text. Compare their search results on a small test set.
5. Batch-embed 50 texts in a single API call. Time it vs. 50 individual calls. Measure the speedup.
6. Try the vector analogy: embed "king", "man", "woman", compute `king - man + woman`. Find which embedded concept is nearest to the result.
7. Embed a single word ("bank") twice — once with context ("river bank") and once with different context ("savings bank"). Compare the two embeddings. How different are they?
