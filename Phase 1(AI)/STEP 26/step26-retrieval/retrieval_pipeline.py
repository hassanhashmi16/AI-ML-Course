"""Step 26 deliverable: a self-contained hybrid-search + rerank + metrics demo.

Run it with no dependencies:

    python retrieval_pipeline.py

What it shows (the whole of Step 26 in one file):
  1. BM25 (sparse) finds EXACT keywords but misses synonyms ("terminate plan"
     vs "cancel subscription").
  2. Dense retrieval (a concept map standing in for real embeddings) finds
     MEANING but misses exact rare codes like "E-4021".
  3. Hybrid search (RRF fusion) combines both and beats EITHER alone.
  4. A reranker (lexical, standing in for a cross-encoder) re-orders the
     candidates for better final ranking.
  5. Metrics (recall@k, MRR, nDCG) measure each retriever SEPARATELY.

Honesty note: the "dense" retriever uses a small hand-built synonym map and the
reranker uses lexical overlap. Real systems use an embedding model (bi-encoder)
and a cross-encoder. The *pipeline structure* is identical — only the scoring
functions swap out. The map and the lexical reranker are here so the whole
thing runs with zero dependencies and still shows the real effect.
"""
import math
from collections import Counter


# ---------------------------------------------------------------------------
# A tiny synonym map. This SIMULATES what an embedding model learns: that
# "cancel" and "terminate" mean the same thing. Notice "E-4021", "error", and
# "code" are deliberately NOT in the map — that simulates a dense embedder
# treating a rare exact code as noise it can't match reliably.
# ---------------------------------------------------------------------------

SYNONYMS = {
    "cancel":       {"cancel", "terminate", "stop", "pause"},
    "subscription": {"subscription", "plan", "account"},
    "billing":      {"billing", "payment", "invoice", "fee", "charged",
                     "price", "dollars", "gateway"},
    "support":      {"support", "contact", "help"},
}


# ---------------------------------------------------------------------------
# Data: a corpus + queries with KNOWN relevant documents (ground truth).
# Index positions are part of the setup: the synonym doc (#7) and the exact-
# code docs (#9, #10) are placed far enough down that a retriever which has
# no real signal (all-zero scores) won't stumble onto them by accident.
# ---------------------------------------------------------------------------

CORPUS = [
    # 0: answers "cancel subscription" with the EXACT words
    "To cancel your subscription, go to Settings and click Cancel Plan.",
    # 1: talks about subscriptions but does NOT answer "cancel"
    "The subscription price increased to twenty dollars per month this year.",
    # 2: pure billing noise
    "Our billing system processes invoices every night.",
    # 3: more billing noise
    "The monthly fee is charged on the first of each month.",
    # 4: pricing-page noise
    "Visit the pricing page to compare available tiers.",
    # 5: upgrade noise
    "Upgrade to the premium tier for more storage.",
    # 6: retry noise
    "Payment failures are retried automatically after 24 hours.",
    # 7: answers "cancel subscription" with DIFFERENT words (synonyms)
    "To terminate your plan, contact support or use the settings page.",
    # 8: audit-log noise
    "The system logs all transaction activity for audit purposes.",
    # 9: the exact error code, first mention
    "If you see error code E-4021, restart the payment service.",
    # 10: the exact error code, second mention
    "Error E-4021 indicates a failed payment gateway connection.",
    # 11: a dense "false positive" — similar concepts but not what we asked
    "You can pause your account from the dashboard.",
]

# Query -> list of truly-relevant corpus indices (our eval ground truth).
EVAL = [
    ("how do I cancel my subscription?", [0, 7]),   # 0 exact, 7 synonyms
    ("E-4021 error", [9, 10]),                      # exact-code match
]

K = 5  # top-k size for retrieval metrics


# ---------------------------------------------------------------------------
# Shared helper: tokenize text into lowercase words.
# ---------------------------------------------------------------------------

def tokenize(text):
    """Split on whitespace and lowercase. Good enough for a demo corpus."""
    return text.lower().split()


# ---------------------------------------------------------------------------
# 1. Sparse retrieval: BM25.
# BM25 scores a doc by summing IDF(t) * term-frequency-saturation for each
# query term. It is THE standard exact-keyword matcher: rare terms (like
# "E-4021") match hard, but it has NO notion of synonyms.
# ---------------------------------------------------------------------------

class BM25:
    def __init__(self, k1=1.2, b=0.75):
        self.k1 = k1  # how much repeated terms saturate (diminishing returns)
        self.b = b    # document-length normalization strength
        self.docs = []
        self.doc_freqs = Counter()  # word -> in how many docs it appears
        self.doc_lengths = []

    def index(self, documents):
        self.docs = [tokenize(d) for d in documents]
        for words in self.docs:
            self.doc_lengths.append(len(words))
            for word in set(words):          # each term counts ONCE per doc
                self.doc_freqs[word] += 1
        self.n_docs = len(self.docs)
        self.avgdl = (sum(self.doc_lengths) / self.n_docs) or 1.0

    def _idf(self, term):
        # Inverse Document Frequency: rare terms carry more signal.
        df = self.doc_freqs[term]
        return math.log((self.n_docs - df + 0.5) / (df + 0.5) + 1)

    def score(self, query, doc_idx):
        words = self.docs[doc_idx]
        tf = Counter(words)
        dl = self.doc_lengths[doc_idx]
        total = 0.0
        for term in set(tokenize(query)):
            if term not in tf:
                continue  # term absent -> contributes nothing
            freq = tf[term]
            num = freq * (self.k1 + 1)
            den = freq + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
            total += self._idf(term) * num / den
        return total

    def search(self, query, k=K):
        """Return top-k doc indices ranked by BM25 score (descending)."""
        scored = [(i, self.score(query, i)) for i in range(self.n_docs)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [i for i, _ in scored[:k]]


# ---------------------------------------------------------------------------
# 2. Dense retrieval: concept vectors + cosine similarity.
# STAND-IN for an embedding model. It maps surface words to shared concepts
# (so "terminate" and "cancel" become the SAME dimension), then ranks docs by
# cosine similarity of their concept vectors. Unknown tokens (like "E-4021")
# contribute nothing, simulating a dense embedder missing rare exact codes.
# ---------------------------------------------------------------------------

class DenseRetriever:
    def index(self, documents):
        # Reverse map: surface word -> canonical concept.
        self.word_to_concept = {}
        for concept, words in SYNONYMS.items():
            for w in words:
                self.word_to_concept[w] = concept
        self.concepts = list(SYNONYMS.keys())
        self.doc_vecs = [self._embed(tokenize(d)) for d in documents]

    def _embed(self, words):
        # Count how many tokens map to each concept; unknown words are dropped.
        counts = Counter(self.word_to_concept[w]
                         for w in words if w in self.word_to_concept)
        return [counts.get(c, 0) for c in self.concepts]

    def _cosine(self, a, b):
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb) if na and nb else 0.0

    def search(self, query, k=K):
        qvec = self._embed(tokenize(query))
        scored = [(i, self._cosine(qvec, v)) for i, v in enumerate(self.doc_vecs)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [i for i, _ in scored[:k]]


# ---------------------------------------------------------------------------
# 3. Fusion: Reciprocal Rank Fusion (RRF).
# Fuses multiple RANKED LISTS using ONLY ranks (not raw scores), so the
# incomparable score scales of BM25 vs cosine don't matter.
# ---------------------------------------------------------------------------

def reciprocal_rank_fusion(ranked_lists, k=60):
    scores = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked):   # rank is 0-based
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    # Sort by fused score descending; ties broken by doc id for determinism.
    return [doc for doc, _ in sorted(scores.items(), key=lambda x: -x[1])]


# ---------------------------------------------------------------------------
# 4. Reranking: a lexical relevance score.
# STAND-IN for a cross-encoder. A real cross-encoder reads query+doc TOGETHER
# and outputs a relevance score; here we approximate that with term overlap,
# exact phrase match, and a boost from the retriever's initial score.
# ---------------------------------------------------------------------------

STOP = {"the", "a", "an", "to", "for", "of", "in", "on", "at", "by", "and",
        "or", "do", "does", "did", "how", "what", "is", "are", "you", "your",
        "my", "i", "it", "if", "use", "see", "our", "with", "go"}

def rerank(query, candidates):
    q_terms = [w for w in tokenize(query) if w not in STOP]
    scored = []
    for doc_id, initial_score in candidates:
        words = tokenize(CORPUS[doc_id])
        overlap = sum(1 for w in q_terms if w in words)          # shared terms
        phrase = 1.0 if query.lower() in CORPUS[doc_id].lower() else 0.0
        score = overlap * 1.0 + phrase * 3.0 + initial_score * 0.5
        scored.append((doc_id, score))
    scored.sort(key=lambda x: x[1], reverse=True)
    return [i for i, _ in scored]


# ---------------------------------------------------------------------------
# 5. Metrics: recall@k, MRR, nDCG. These measure RETRIEVAL quality only,
# separately from generation quality (faithfulness / correctness).
# ---------------------------------------------------------------------------

def recall_at_k(retrieved, relevant, k=K):
    """Fraction of relevant docs that appear in the top-k."""
    return len(set(retrieved[:k]) & set(relevant)) / len(relevant)

def mrr(retrieved, relevant, k=K):
    """Mean Reciprocal Rank: 1 / rank of the FIRST relevant result (1-based)."""
    for rank, doc in enumerate(retrieved[:k], start=1):
        if doc in relevant:
            return 1.0 / rank
    return 0.0

def ndcg(retrieved, relevant, k=K):
    """Normalized Discounted Cumulative Gain (binary relevance)."""
    def dcg(ids):
        return sum(1.0 / math.log2(i + 2) for i, d in enumerate(ids) if d in relevant)
    ideal = sorted(relevant)[:k]  # best possible ordering = relevant docs first
    idcg = dcg(ideal)
    return dcg(retrieved[:k]) / idcg if idcg else 0.0


# ---------------------------------------------------------------------------
# Main: run each retriever over the eval set and print the metrics.
# ---------------------------------------------------------------------------

def evaluate(name, retriever_fn, rerank_flag):
    recs, mrrs, ndcgs = [], [], []
    for query, relevant in EVAL:
        topk = retriever_fn(query)
        if rerank_flag:
            # Re-score the retrieved candidates (retrieve-wide, rerank-narrow).
            topk = rerank(query, [(i, 1.0 / (r + 1)) for r, i in enumerate(topk)])
        recs.append(recall_at_k(topk, relevant))
        mrrs.append(mrr(topk, relevant))
        ndcgs.append(ndcg(topk, relevant))
    n = len(EVAL)
    print(f"{name:<22} recall@{K}={sum(recs)/n:.2f}  MRR={sum(mrrs)/n:.2f}  nDCG={sum(ndcgs)/n:.2f}")


if __name__ == "__main__":
    bm25 = BM25();               bm25.index(CORPUS)
    dense = DenseRetriever();    dense.index(CORPUS)

    print("=" * 72)
    print("Retriever comparison on a tiny labeled corpus (higher is better)")
    print("=" * 72)

    # Each retriever returns top-K. Note hybrid slices [:K] to stay comparable.
    evaluate("sparse (BM25)",      lambda q: bm25.search(q), rerank_flag=False)
    evaluate("dense (concepts)",   lambda q: dense.search(q), rerank_flag=False)
    evaluate("hybrid (RRF)",       lambda q: reciprocal_rank_fusion(
                                       [bm25.search(q), dense.search(q)])[:K],
                                   rerank_flag=False)
    evaluate("hybrid + rerank",    lambda q: reciprocal_rank_fusion(
                                       [bm25.search(q), dense.search(q)])[:K],
                                   rerank_flag=True)

    # Show the actual rankings for each query so the effect is visible.
    for q, rel in EVAL:
        print()
        print(f"Query: '{q}'  (relevant docs: {rel})")
        print("  sparse :", bm25.search(q))
        print("  dense  :", dense.search(q))
        print("  hybrid :", reciprocal_rank_fusion(
            [bm25.search(q), dense.search(q)])[:K])
