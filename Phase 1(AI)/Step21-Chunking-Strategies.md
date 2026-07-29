# Step 21: Chunking Strategies

> **What it covers:** Why documents need to be split before embedding, the different chunking strategies, and how chunk overlap, splitter parameters, and strategy choice affect retrieval quality in a RAG system.

---

## Foundational Concepts

### The core problem: embedding models have a context window

Every embedding model has a maximum input length. OpenAI's `text-embedding-3-small` accepts up to 8191 tokens. If your document is 20,000 tokens (roughly 15,000 words), the model truncates everything past the limit. You lose the entire tail of the document.

But even if you stay under the limit, there's a second, subtler problem: **dilution.** A 1536-dimensional vector has to represent everything in the input text. If you embed a 5000-word article about "healthy breakfast ideas" that also mentions the author's cat on page 3, the embedding becomes a blurry average of breakfasts AND cats. Search for "oatmeal recipes" might return this article, but not because it's a good result — because the vector couldn't cleanly represent either topic.

**Chunking solves both problems.** Split the document into pieces, embed each piece separately, and search over the pieces. Each piece's embedding is a focused representation of one topic. The query matches whatever piece is most relevant, not a muddy average of the whole document.

### The fundamental trade-off

```
small chunks (50-100 tokens)               large chunks (1000+ tokens)
├──────────────────────────────────────────┤
high precision (specific match)            high recall (finds more)
low context (missing surrounding info)     low precision (noisy matches)
```

- **Small chunks** match queries precisely but lack context for the LLM to answer well. "What's the capital of France?" matches a chunk that says "Paris is the capital of France" — perfect. But "Why is Paris the capital?" might need surrounding historical context that's in adjacent chunks.
- **Large chunks** have more context but produce fuzzy embeddings. A chunk about "French history including how Paris became the capital" contains the answer, but its embedding is diluted with other historical facts. The query might not rank it first.

There's no universal sweet spot. The right size depends on your content, your queries, and your embedding model.

### What a "chunk" is

A chunk is just a text segment — a string of characters, usually between 100-1000 tokens, that will be independently embedded and stored in a vector database. Each chunk becomes a row in your search index:

```
doc_id | chunk_index | chunk_text                                    | embedding
───────┼─────────────┼───────────────────────────────────────────────┼─────────────────────
1      | 0           | "Paris is the capital and most populous city..." | [0.023, -0.015, ...]
1      | 1           | "The city was founded in the 3rd century BC..." | [0.031, -0.042, ...]
1      | 2           | "During the French Revolution, Paris was..."    | [-0.012, 0.021, ...]
```

When you search, the vector database returns the most similar chunks, not entire documents. The LLM then receives these chunks as context to answer the query.

### Why chunking is harder than it sounds

Most people's first instinct: "I'll just split on paragraphs." This fails because:

- Paragraphs vary wildly in length. A paragraph can be 20 words or 2000 words. The embedding quality degrades on very long paragraphs.
- Paragraphs don't always represent semantic units. A writer might end a paragraph mid-idea and continue in the next one.
- The embedding model has a fixed token limit. A chunk that exceeds it gets truncated silently.

Good chunking strategies solve these problems by respecting both structure AND size constraints. Bad chunking creates chunks that start or end mid-sentence, lose context at boundaries, and make retrieval unreliable.

---

## 14.1 — Fixed-Size Chunking

### How it works

The simplest approach: pick a number (say, 500 characters), and split the text every 500 characters. No intelligence, no structure awareness — just counting.

```python
# Conceptual example — what fixed-size chunking does
text = "Paris is the capital and most populous city of France. It is located on the Seine..."
# split every 80 characters
chunks = [text[i:i+80] for i in range(0, len(text), 80)]
```

A real implementation uses `CharacterTextSplitter` from LangChain:

```python
from langchain_text_splitters import CharacterTextSplitter

splitter = CharacterTextSplitter(
    separator=" ",          # split on spaces as fallback
    chunk_size=500,         # target size in characters
    chunk_overlap=50,       # overlap between chunks
)

chunks = splitter.split_text(your_text)
print(len(chunks))  # depends on text length
```

### What happens without overlap

Without overlap, critical information gets severed at chunk boundaries:

```
Chunk 1: "The Eiffel Tower was built for the 1889 World's Fair. It was originally"
Chunk 2: "intended as a temporary structure but became a permanent landmark."
```

If a user searches "was the Eiffel Tower intended as temporary?", chunk 1 has "originally" but not "temporary structure." Chunk 2 has "temporary structure" but no context linking it to the Eiffel Tower. Neither chunk is a perfect match. The LLM might get incomplete context.

**With overlap**, the boundary gets softened:

```
Chunk 1: "The Eiffel Tower was built for the 1889 World's Fair. It was originally"
Chunk 2: "originally intended as a temporary structure but became a permanent landmark."
```

Both chunks contain the word "originally," and chunk 2 has the full thought. The overlap ensures that no single meaningful sentence is lost entirely.

### Problems with fixed-size chunking

1. **Splits mid-word or mid-sentence.** The blind character count doesn't care about language structure.
2. **Splits mid-paragraph.** Related sentences get orphaned across chunks.
3. **Splits across code blocks, tables, or lists.** A code function or markdown table gets cut in half, making both chunks useless.
4. **Unpredictable token counts.** Characters ≠ tokens. A 500-character chunk in English might be ~125 tokens, but the same 500 characters in another language might be very different.

Measured against real documents, only about **5%** of fixed-size chunk boundaries end on a sentence-ending character (period, question mark, exclamation point). The other 95% create ragged splits.

### When to use fixed-size chunking

- **Prototyping**: you need something working in 5 minutes to test a hypothesis
- **Uniform content**: every document is roughly the same short length
- **Baseline comparison**: you want to measure whether smarter chunking actually improves results
- **Storage constraints**: you need predictable, uniform chunk sizes

Don't use it for production unless your content is unusually uniform (e.g., every document is a 2-3 sentence product description).

---

## 14.2 — Recursive & Semantic Chunking

### Recursive character splitting

Instead of blindly counting characters, recursive splitting tries to respect natural document structure by checking **multiple separators in priority order**:

1. Double newline `\n\n` (paragraph breaks) — highest priority
2. Single newline `\n` (line breaks)
3. Period-space `. ` (sentence boundaries)
4. Space ` ` (word boundaries)
5. Empty string `""` (individual characters, last resort — guaranteed to always work)

The algorithm: try separating at `\n\n`. If the resulting chunks are still too big, fall back to `\n`. If still too big, fall to `. ` and so on, until it finds a separator that produces chunks under the size limit.

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Default separators — good starting point for most text
splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    separators=["\n\n", "\n", ". ", " ", ""],
)

chunks = splitter.split_text(your_text)
```

The result: chunks that almost always end at sentence boundaries. In benchmarks, **100%** of recursive chunk boundaries landed on sentence-ending characters (vs. 5% for fixed-size), because the `". "` separator ensures the splitter cuts after a period rather than mid-sentence.

#### Custom separators for different content types

The real power of recursive splitting is that you customize separators to match your document structure:

```python
# For markdown content — prioritize heading boundaries
markdown_separators = [
    "\n## ",    # H2 heading
    "\n### ",   # H3 heading
    "\n\n",     # paragraph break
    "\n",       # line break
    ". ",       # sentence boundary
    " ",        # word boundary
    "",          # character (last resort)
]

# For code — prioritize function and class boundaries
code_separators = [
    "\n\nclass ",    # class definition
    "\n\n def ",     # function definition (indented)
    "\n\n    def ",  # function definition (4-space indent)
    "\n\n",         # paragraph break
    "\n",           # line break
    " ",            # word boundary
    "",             # character
]

# For HTML — prioritize tag boundaries
html_separators = [
    "\n<h2>", "\n<h3>", "\n<h4>",
    "\n<p>", "\n<div>",
    "\n<br>", "\n<li>",
    "\n\n", "\n", " ", "",
]
```

The separator list is ordered from "most preferred structural split" to "least preferred fallback." If your content has clear `##` headings, put `\n##` first. The splitter will try to keep sections intact before resorting to sentence-level cuts.

#### The chunk_size ceiling problem

Recursive chunking is still size-bound. If your document has a section that's 2000 characters long and `chunk_size=700`, the splitter is forced to cut through that section regardless of separator order. It will fall through to `" "` or `""` and split mid-sentence.

```python
# A 2000-character section with chunk_size=700
# The splitter tries every separator, can't keep it under 700
# Eventually falls to "" and splits at character 700
# This produces a mid-sentence cut
```

The only fix: raise `chunk_size` to accommodate your longest logical units, or use semantic chunking instead.

### Semantic chunking

Semantic chunking doesn't count characters at all. It splits based on **topic shifts** — where the meaning of the text changes.

The pipeline:

1. Split the document into individual sentences
2. Generate an embedding vector for each sentence
3. Measure cosine distance between consecutive sentences
4. When the distance exceeds a threshold, start a new chunk (because the topic likely changed)

```python
from langchain_experimental.text_splitter import SemanticChunker
from langchain_openai import OpenAIEmbeddings

embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

splitter = SemanticChunker(
    embeddings=embeddings,
    breakpoint_threshold_type="percentile",  # or "standard_deviation" or "interquartile"
    breakpoint_threshold_amount=95,           # split when distance > 95th percentile
)

chunks = splitter.split_text(your_text)
```

#### How the breakpoint threshold works

The splitter computes distances between every pair of consecutive sentence-embeddings. Then it looks for "breaks" — distances that are unusually large compared to the rest.

| Threshold type | How it finds breaks | Best for |
|---|---|---|
| **percentile** (default) | Splits at distances above the 95th percentile (or whatever you set) | General use, unknown data |
| **standard_deviation** | Splits when distance > mean + (amount × std_dev) | One big topic shift in otherwise uniform text |
| **interquartile** | Uses the middle 50% of distances; splits when a distance exceeds the robust range | Multiple shifts of different magnitudes |
| **gradient** | Looks at rate of change in distances, not raw distances | Gradual topic drift (scientific papers) |

The `percentile` method is the safest default. The `standard_deviation` method can miss moderate topic shifts because a single huge shift inflates the mean and std, making average-sized shifts look normal.

#### Semantic chunking produces variable-sized chunks

Because it splits on meaning, not character count, chunk sizes vary widely:

```
Chunk 1: "Introduction to the drug and its classification..."            (315 chars)
Chunk 2: "Full description of mechanism of action and clinical trials..." (4701 chars)
Chunk 3: "Side effects and contraindications..."                         (8405 chars)
```

If a topic takes 8000 characters to explain, semantic chunking produces one 8000-character chunk. If another topic only takes 200 characters, that's a separate chunk. This is by design — each chunk represents a coherent topic, regardless of length.

#### The cost trade-off

Semantic chunking requires calling an embedding model for every sentence in every document. For 10,000 documents averaging 500 sentences each, that's 5 million embedding calls just for chunking. This adds both cost and processing time.

**Does it improve results?** Chroma's research found semantic chunking achieved 91-92% recall vs. 85-90% for recursive splitting at 400 tokens. That 2-6% improvement may or may not be worth the cost depending on your use case. A NAACL 2025 paper found that fixed 200-word chunks matched or beat semantic chunking in retrieval and generation quality — the extra cost didn't always pay off.

**Start with recursive splitting.** Move to semantic only if:
- Your documents have complex, non-obvious topic boundaries that recursive splitting misses
- You've measured your recall and know the gap is worth closing
- The cost (in money or time) is acceptable

### LLM-based chunking (advanced)

For high-value content, you can send documents to an LLM to analyze structure and decide chunk boundaries:

```python
# Conceptual — send document sections to an LLM
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{
        "role": "system",
        "content": "Identify logical sections in this text and suggest split points."
    }, {
        "role": "user",
        "content": document_text[:8000]
    }]
)
```

The LLM understands document structure at a human level — it knows where topics shift, where definitions end and procedures begin, where arguments transition. It produces better chunks than any rule-based method.

**The cost makes this impractical for production.** Embedding every sentence (semantic chunking) is cheap compared to running an LLM on every document. Use LLM-based chunking only for:
- One-time processing of a small, high-value corpus
- Creating a gold-standard benchmark to evaluate simpler methods against
- Experimental projects where cost isn't a constraint

---

## 14.3 — Chunk Overlap

### What overlap does

Overlap is the number of characters (or tokens) repeated from the end of one chunk at the start of the next. It creates a sliding window over the text:

```
Chunk 1: [......A......B......C......]
Chunk 2:                    [C......D......E......F......]
Chunk 3:                                      [F......G......H......]
```

The overlapping region (C and F) appears in two adjacent chunks. This ensures that information near chunk boundaries isn't lost — any concept that spans the boundary exists fully in at least one chunk.

### How much overlap to use

| Overlap | When to use |
|---|---|
| **0%** | Only if your chunks are sentence-boundary-aligned (recursive, semantic). Even then, you might miss cross-chunk references. |
| **10-15%** | Default starting point. `chunk_size=500`, `overlap=50-75`. |
| **20-25%** | Dense content where concepts often span boundaries (legal documents, technical specs). |
| **>25%** | Usually wasteful — you're duplicating too much content without proportional gain. |

### Does overlap actually help?

Mixed evidence. Most industry guides recommend 10-20% overlap as a hedge against boundary fragmentation. But a January 2026 systematic analysis using SPLADE retrieval found that overlap provided **no measurable benefit** and only increased indexing cost and storage overhead.

**The practical takeaway**: use overlap when you're using fixed-size chunking (where boundary cuts are arbitrary and likely to lose information). For recursive chunking (where boundaries align with sentences), you may not need it. Test both and measure.

### The cost of overlap

Overlap increases the total number of chunks and the total tokens stored:

```
1000-character document, chunk_size=500:
  no overlap  → 2 chunks  (100% of original tokens stored)
  50 overlap  → 3 chunks  (~110% of original tokens stored)
  100 overlap → 4 chunks  (~120% of original tokens stored)
```

More chunks = more embedding API calls (cost) and more vector database storage. For small corpuses this doesn't matter. For millions of documents, a 20% overhead in storage cost is real money.

---

## 14.4 — Splitter Parameters

### chunk_size

The target size for each chunk. In LangChain, this defaults to **characters**, but some splitters (like `TokenTextSplitter`) count **tokens**.

```python
# Character-based
CharacterTextSplitter(chunk_size=500)        # 500 characters
# Token-based (uses tiktoken to count tokens)
TokenTextSplitter(chunk_size=500)            # 500 tokens
```

**Character-based vs. token-based**: a token is roughly 4 characters in English, but varies wildly. "apple" is 5 characters and 1 token. "unhappiness" is 11 characters and 2 tokens. Token-based splitting aligns with your embedding model's actual limits. Character-based is simpler but less predictable.

**Choosing chunk_size:**

| Query type | Recommended size | Reasoning |
|---|---|---|
| **Factoid** (names, dates, facts) | 256-512 tokens | Precise matching, don't need surrounding context |
| **Explanatory** (why, how, describe) | 512-1024 tokens | Need context around the answer |
| **Analytical** (compare, contrast, summarize) | 1024+ tokens | Need full section/argument to answer |
| **Mixed / unknown** | 400-512 tokens | Balanced middle ground |

### chunk_overlap

The number of characters/tokens shared between adjacent chunks. Already covered in 14.3 — but the parameter itself is straightforward:

```python
RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,  # 10% overlap
)
```

### separators (for recursive splitters)

The ordered list of separators the splitter tries, from most preferred to least. This is the highest-leverage tuning parameter for recursive chunking.

```python
# Default
separators=["\n\n", "\n", " ", ""]

# Better for well-structured markdown
separators=["\n## ", "\n### ", "\n\n", "\n", ". ", " ", ""]

# Better for dense academic text with long paragraphs
separators=["\n\n", ". ", "! ", "? ", "\n", " ", ""]
```

### length_function

How the splitter measures chunk size. By default it's `len()` (character count). You can use a token counter instead:

```python
import tiktoken

def token_len(text: str) -> int:
    encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    length_function=token_len,  # now chunk_size = 500 tokens, not characters
)
```

### The default that works for most cases

```python
from langchain_text_splitters import RecursiveCharacterTextSplitter

splitter = RecursiveCharacterTextSplitter(
    chunk_size=512,
    chunk_overlap=50,
    separators=["\n\n", "\n", ". ", " ", ""],
)
```

Start here. Tune only if your retrieval metrics show a clear problem.

---

---

## 14.5 — Text Segmentation as an NLP Problem

Chunking isn't just an engineering convenience — it's a well-studied NLP task called **topic segmentation** or **text segmentation**. CS224N at Stanford covers it as a core NLP problem alongside summarization and question-answering.

### The formal problem

Given a document D of length N (in sentences or tokens), produce a set of boundary positions B = {b₁, b₂, ..., bₖ} that divide D into K contiguous segments, each representing a coherent topic or subtopic.

This framing matters because it connects chunking to decades of NLP research, not just RAG system design. The same algorithms used for segmenting podcasts and news transcripts in the 1990s are now used for RAG chunking in 2026.

### Unsupervised approaches (no training required)

These algorithms detect topic shifts using statistical signals in the text itself. They're the academic precursors to the chunking strategies used in LangChain.

**TextTiling** (Hearst, 1997). One of the earliest and most influential topic segmentation algorithms. It works in three steps:

1. Divide the text into small blocks of token sequences (pseudo-sentences)
2. Compute lexical cohesion scores at each potential boundary by comparing word overlap between adjacent blocks
3. Where cohesion drops significantly (a "valley"), mark a topic boundary

TextTiling assumes that within a topic, vocabulary stays consistent. When the topic shifts, new vocabulary appears and old vocabulary disappears, causing a drop in lexical cohesion. All modern chunking strategies are variations on this core idea — they just use better signals (embeddings instead of raw word counts) to detect the drops.

**Limitations**: TextTiling uses bag-of-words, so "car" and "automobile" don't contribute to cohesion even though they mean the same thing. Semantic chunking solves this with embeddings.

**GraphSeg** (Glavas et al., 2016): Builds a graph where each sentence is a node, edges connect semantically related sentences. Finds maximal cliques (densely connected subgraphs) as coherent segments. This is an unsupervised precursor to the clustering-based approaches used in RAPTOR.

### Evaluation metrics from NLP research

Standard retrieval metrics (recall@k) measure whether the right chunk was found. But NLP research has its own metrics for measuring segmentation quality directly — whether the chunk boundaries themselves are correct.

**Pk score** (Beeferman et al., 1997): Slides a window of size k (half the average true segment length) across the text. For each window position, checks whether the two ends are in the same segment in both the predicted and reference segmentation. Penalizes mismatches. Lower is better (0 = perfect).

```
Reference:    [....topic A....|....topic B....|....topic C....]
Prediction:   [....topic A..|..topic B......|....topic C....]
                                        ^
                                      Penalized here — prediction split early
```

Pk's flaw: it penalizes false negatives more than false positives, and it doesn't account for multiple boundaries inside a window.

**WindowDiff** (Pevzner & Hearst, 2002): A fix for Pk. Instead of checking whether the two ends of the window are in the same segment, it compares the *number* of boundaries in the window between reference and prediction. Penalizes any mismatch. Also lower is better.

```
WindowDiff(ref, pred) = (1/N) * Σ|b_ref(i, i+k) - b_pred(i, i+k)|
```

These metrics matter when you're **evaluating chunking quality directly** — e.g., testing whether a new semantic chunking algorithm produces boundaries that match human-annotated topic shifts. For RAG systems, you usually care more about retrieval recall than boundary accuracy, but understanding Pk/WindowDiff helps you read the academic literature.

### Why this matters

Knowing that chunking is a formal NLP problem (not just a LangChain utility) helps you:
- Understand why semantic chunking works — it's a modern version of TextTiling with better features
- Read research papers that compare segmentation algorithms using Pk/WindowDiff
- Recognize that the "best" chunking strategy depends on your document structure, and NLP researchers have been studying this question for 30 years

---

## 14.6 — Hierarchical & Tree-Organized Chunking

All the strategies so far produce a flat list of chunks. But documents have hierarchy — sections contain subsections, which contain paragraphs. Hierarchical chunking preserves this structure.

### Parent-child (two-level) chunking

The simplest hierarchical approach: create two sets of chunks from the same document.

- **Small child chunks** (100-200 tokens): indexed in the vector database for search. High precision.
- **Parent chunks** (500-1000 tokens): not indexed. Retrieved only when a child chunk matches.

```
Document
├── Parent chunk 1 (section-level, not indexed)
│   ├── Child chunk A (indexed) ← query matches this
│   ├── Child chunk B (indexed)
│   └── Child chunk C (indexed)
├── Parent chunk 2 (section-level, not indexed)
│   ├── Child chunk D (indexed)
│   └── Child chunk E (indexed)
```

When a query matches a child chunk, the system returns its parent as context to the LLM. This gives precise retrieval (the child found the exact passage) with rich context (the parent provides surrounding information).

```python
# LangChain implementation
from langchain_text_splitters import RecursiveCharacterTextSplitter

parent_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
child_splitter = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=20)

# Create parent chunks
parents = parent_splitter.create_documents([full_document])

# For each parent, create children
for parent in parents:
    children = child_splitter.split_text(parent.page_content)
    # Store children in vector DB with reference to parent ID
    # On match: return parent as context
```

**Storage cost**: you still only store the children in the vector DB. The parents are stored separately (in a document store or as metadata). The total embedding cost is the same as a single-pass strategy.

### RAPTOR: Recursive Abstractive Processing for Tree-Organized Retrieval

A Stanford CS224N spin-off (Sarthi et al., ICLR 2024) that extends hierarchical chunking to multiple levels with **summarization**.

RAPTOR recursively clusters chunks and summarizes each cluster, building a tree:

```
                    Level 2 (top): summary of entire document
                   /        \
        Level 1: summary    summary        (clusters summarized)
         /    |    \        /    \
Level 0: chunk chunk chunk chunk chunk    (original text chunks)
```

The pipeline:
1. Split document into 100-token chunks (using sentence tokenizer, not regex)
2. Generate embeddings for each chunk (using SBERT or similar)
3. Cluster the embeddings (using Gaussian Mixture Models or agglomerative clustering)
4. Summarize each cluster's text using an LLM into a concise summary
5. Embed the summaries and repeat steps 3-4, building up the tree

At query time, RAPTOR retrieves from ALL levels simultaneously — matching both specific details (from leaf chunks) and high-level themes (from summary nodes). The original paper showed improvements over flat retrieval on complex, multi-topic questions.

**Key insight from a 2025 CS224N project extending RAPTOR:**
- Moving from GMMs to **agglomerative clustering** produced deeper, more balanced trees with better extractive (+1.8%) and abstractive (+1.38%) question answering
- Adding **positional embeddings** (encoding chunk index and document position) further improved results because nearby chunks are statistically more likely to belong to the same topic
- The clustering step became computationally negligible with agglomerative clustering vs. GMMs

```python
# Conceptual RAPTOR pipeline
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering

# Step 1: Create base chunks
chunks = sentence_tokenizer(document, chunk_size=100)

# Step 2: Embed each chunk
model = SentenceTransformer('all-MiniLM-L6-v2')
embeddings = model.encode(chunks)

# Step 3: Cluster (add positional info to embeddings)
pos_embeddings = add_positional_info(embeddings, chunk_indices)
clustering = AgglomerativeClustering(distance_threshold=1.5, n_clusters=None)
clusters = clustering.fit_predict(pos_embeddings)

# Step 4: Summarize each cluster with an LLM
summaries = [llm.summarize(join([chunks[i] for i in cluster]))
             for cluster in clusters]

# Step 5: Build tree recursively (embed summaries, cluster again)
```

**When to use RAPTOR:**
- Documents are long (10,000+ tokens per document)
- Queries span multiple levels of abstraction ("summarize the paper" vs. "what was the learning rate?")
- You can afford the LLM summarization cost during indexing (one-time cost)

**When NOT to use RAPTOR:**
- Short documents or uniform content (flat chunks are sufficient)
- Latency-sensitive applications (tree retrieval adds complexity)
- Cost-sensitive applications (LLM summarization adds significant indexing cost)

### Late chunking

Late chunking inverts the normal order: **embed the full document first, then split**. This means each chunk's embedding carries context from the entire document.

The key insight: a chunk that says "Its population exceeds 3.85 million" — if "Berlin" appeared three paragraphs earlier in a different chunk, standard chunking loses that connection. Late chunking preserves it because the transformer sees the full document before pooling per-chunk vectors.

```python
# Jina AI's API (the only production-ready option as of 2026)
response = requests.post(
    "https://api.jina.ai/v1/embeddings",
    json={
        "input": [
            "Berlin is the capital and largest city of Germany.",
            "Its more than 3.85 million inhabitants make it the EU's most populous city.",
        ],
        "model": "jina-embeddings-v3",
        "late_chunking": True,
    }
)
```

The second chunk's embedding now "knows" that "Its" refers to Berlin. On the NFCorpus benchmark, late chunking improved nDCG@10 by 6.5 points for longer documents.

**Limitations**: the full document must fit in the model's context window (8,192 tokens for Jina's model, roughly 10 pages). It's provider-specific — OpenAI and Gemini don't support it. A weaker embedding model with late chunking still underperforms a stronger model without it.

---

## 14.7 — Choosing a Strategy: Decision Framework & Evaluation

### The decision tree

```
Is your content primarily PDFs with tables/figures?
├── YES → Page-level chunking (Unstructured.io)
└── NO →
    Are your documents long (>5000 tokens) with multiple topics?
    ├── YES →
    │   Do queries vary from specific to broad?
    │   ├── YES → RAPTOR or parent-child chunking
    │   └── NO → Recursive + semantic, 512 tokens
    └── NO →
        Is your content short and uniform (product descriptions)?
        ├── YES → Fixed-size or sentence-based, 100-200 tokens
        └── NO →
            Start with RecursiveCharacterTextSplitter at 512 tokens
```

### Evaluating chunking quality: a practical protocol

Don't ship a chunking strategy without measuring it first. Here's the protocol:

**Step 1: Create a test set.** Gather 20-50 representative documents and 10-20 realistic queries with known correct answers.

**Step 2: Define success metrics.**

| Metric | What it measures | How to compute |
|---|---|---|
| **Recall@k** | Does the right chunk appear in top-k results? | (relevant retrieved chunks in top-k) / (total relevant chunks) |
| **Precision@k** | Are the top-k results all relevant? | (relevant retrieved chunks in top-k) / k |
| **Answer quality** | Can the LLM answer correctly given the chunk? | LLM-as-judge or human eval |

**Step 3: Test 2-3 strategies.** Always include recursive at 512 tokens as a baseline.

**Step 4: Compare.**

```python
# Minimal evaluation harness
import numpy as np
from typing import Callable

def evaluate_strategy(
    documents: list[str],
    queries: list[tuple[str, str]],  # (query, ground_truth_chunk_text)
    chunk_fn: Callable,
    embed_fn: Callable,
    k: int = 5
) -> dict:
    all_chunks = []
    for doc in documents:
        all_chunks.extend(chunk_fn(doc))

    chunk_embs = embed_fn(all_chunks)
    recalls = []

    for query, truth in queries:
        q_emb = embed_fn([query])[0]
        scores = [np.dot(q_emb, ce) for ce in chunk_embs]
        top_k_indices = np.argsort(scores)[-k:][::-1]
        top_k_texts = [all_chunks[i] for i in top_k_indices]

        # Check if truth chunk is in top-k
        recalls.append(any(truth in t for t in top_k_texts))

    return {"recall_at_k": np.mean(recalls)}
```

### The default recommendation

For 80% of projects, start here:

```python
RecursiveCharacterTextSplitter(
    chunk_size=512,
    chunk_overlap=50,
    separators=["\n\n", "\n", ". ", " ", ""],
)
```

Move to something more complex only when you've measured a clear gap. The most common mistake is over-engineering the chunking strategy before measuring whether the default actually fails on your specific data.

### Common mistakes (expanded from research)

1. **Chunking without checking content structure.** If your documents have clear `##` headings and you use the default separator list (without `\n##`), you're losing your best structural signal.

2. **Same chunk size for all query types.** Factoid queries need small chunks. Analytical queries need large chunks. If your system handles both, consider multiple chunk sizes or query routing.

3. **Ignoring token limits.** chunk_size=2000 chars with a 8192-token limit seems safe. But 2000 chars in a verbose language could be 3000+ tokens. Always check.

4. **Semantic chunking with a bad embedding model.** Using TF-IDF as the embedding for semantic chunking produces garbage — it ranks "river bank" and "savings bank" as moderately similar (shared word "bank") while missing actual topic shifts. The chunking quality is only as good as the embedding model.

5. **Not testing on your actual data.** Benchmarks from NVIDIA, Chroma, and others are useful guides, but your documents and queries are different. Test strategies on your data before committing.

6. **Assuming overlap always helps.** A January 2026 systematic analysis found overlap provided no measurable benefit and increased indexing cost. Test with and without on your data.

7. **Using sentence splitting without proper detection tools.** Libraries like NLTK correctly handle "Dr. Smith" vs sentence-ending periods. Regex-based splitting does not. The RAPTOR paper's implementation was notably improved by switching from regex to NLTK's sentence tokenizer.

---

## Theory Summary

**Chunking is the bridge between documents and retrieval.** Without it, embedding models produce blurry averages of entire documents. With it, each chunk captures a focused, retrievable unit of meaning.

**The strategy continuum:** fixed-size (fast, stupid) → recursive (fast, structure-aware) → semantic (slow, meaning-aware) → LLM-based (expensive, context-aware). The right choice depends on your content, your budget, and the accuracy you need.

**Overlap is a hedge against boundary loss.** Use it for fixed-size chunking. For recursive or semantic chunking, test whether it helps before committing to the storage cost.

**The default works for most projects.** RecursiveCharacterTextSplitter at 400-512 tokens with 10-15% overlap. Move to semantic or specialized strategies only when your metrics tell you the default isn't good enough.

**Chunking quality determines retrieval quality more than vector database choice.** A well-chunked document on SQLite with cosine similarity beats a poorly-chunked document on Pinecone with HNSW indexing. Invest your optimization effort where it matters most.

---

## Quick Reference

| Concept | Key point |
|---|---|
| **Why chunk** | Embedding models have context limits; long texts produce blurry embeddings |
| **Fixed-size** | Split by character/token count, no structure awareness |
| **Recursive** | Split by natural boundaries (paragraphs → sentences → words) |
| **Semantic** | Split where topic shifts (measured by embedding distance) |
| **LLM-based** | Split where an LLM says to — most accurate, most expensive |
| **Chunk overlap** | Repeated boundary text to prevent information loss |
| **Default strategy** | Recursive, chunk_size=512, overlap=50, `["\n\n", "\n", ". ", " ", ""]` |
| **Parent-child chunking** | Small chunks for retrieval, parent chunks for context |
| **Late chunking** | Embed full document, then split — preserves cross-chunk context |
| **Measure, don't guess** | Test strategies with recall@k on real queries before deciding |

---

## What to Practice

1. Take a 2000+ word article. Chunk it with fixed-size (chunk_size=500, no overlap). Count how many chunks end mid-sentence. Now try recursive splitting. Compare.

2. Try custom separators for different content: markdown (with `\n##`), code (with `\ndef`), academic text (with `. ` priority). See how chunk boundaries change.

3. Implement parent-child chunking: create small retrieval chunks (200 tokens) linked to parent context chunks (800 tokens). Query a test corpus. Are the results better than single-size chunks?

4. Test semantic chunking with OpenAI embeddings vs. a free alternative (HuggingFace `BAAI/bge-small-en-v1.5`). Compare chunk quality and processing time. Decide if the cost difference is worth it.

5. Evaluate your chunking strategy: create 10 test queries with known correct answers. Chunk a document with 3 different strategies. Compute recall@3 for each. Which strategy wins?
