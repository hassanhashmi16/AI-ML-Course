# Step 21: Document Ingestion & Parsing

> **What it covers:** PDF/DOCX/HTML extraction with layout-aware parsing, tables/figures/OCR for scanned documents, cleaning/deduplication/boilerplate removal, metadata extraction for filtering and citations, and incremental re-ingestion to keep an index fresh — everything that has to happen before chunking (Step 22) so a RAG system isn't built on garbage text.

---

## The Problem

Chunking (Step 22) assumes you already have clean, well-ordered text. In reality your corpus is PDFs with two-column layouts, scanned invoices with no text layer, tables whose cells get smeared together, and HTML full of navigation and boilerplate. If you feed that raw to a chunker and then to an embedding model, you don't get "slightly worse retrieval" — you get retrieval that is quietly broken, because the model never saw the real document, only a garbled reconstruction of it.

The specific failure: a naive PDF text extractor reads columns in the wrong order, so a paragraph becomes "headline from column A, then headline from column B, then body of column A, then body of column B" — semantically scrambled text that no chunker or retriever can recover from. The extraction step is where the damage is done, and everything downstream (chunking, embedding, retrieval, generation) inherits it. This step is about not doing that damage in the first place.

---

## Foundational Concepts

### A PDF is not text — it's a list of drawing instructions

This is the single most important mental model in the step. A PDF stores *where to draw glyphs on a page* (coordinates, fonts, sizes), not "a paragraph of text." When you open a PDF you're looking at rendered output; the text layer — if it exists at all — is a separate, optional layer that maps glyphs to Unicode. That's why extraction is hard:

- **Text is positioned, not sequential.** There's no inherent reading order. A two-column page is just glyphs at x-coordinates; "reading order" is something *you* have to reconstruct from position.
- **Scanned PDFs have no text layer at all.** They're images of pages. Extraction returns nothing until you run OCR.
- **Tables are lines and boxes**, not "rows and columns." Reconstructing a table means inferring structure from ruled lines or whitespace.

### The distinction that drives every decision: extraction vs. understanding

| Approach | What it does | When it's enough | When it breaks |
|---|---|---|---|
| **Text extraction** (`pypdf`, `PyMuPDF`, `pdfplumber`) | Pulls the text layer as strings, roughly positioned | Single-column, born-digital PDFs | Multi-column, tables, scanned pages |
| **Layout-aware parsing** (Docling, Unstructured, Marker) | Reconstructs *structure*: reading order, headings, tables, figures | Everything real — the production default | Still imperfect on complex scans/charts |
| **OCR** (Tesseract, EasyOCR) | Recognizes text from an image of a page | Scanned docs, no text layer | Stylized fonts, handwriting, low resolution |

The step is fundamentally about knowing when to move up this ladder. A single-column text PDF can be handled by `PyMuPDF` in two lines. The moment you hit a two-column layout or a table, you need a layout-aware parser; the moment you hit a scan, you need OCR.

### Garbage in is the one failure you can't fix later

Cleaning, chunking, reranking (Step 26) — none of them can recover text that was scrambled or lost at extraction. A chunker will happily chunk "column A headline + column B headline" as if it were one sentence. The embedding model will faithfully encode that nonsense. The retriever will confidently return it. The failure is invisible at every later stage, which is why it's worth getting extraction right *before* you build on top of it.

---

## 21.1 — PDF / DOCX / HTML Extraction & Layout-Aware Parsing

### The naive version, and why it scrambles

The fastest way to "get text out of a PDF" looks like this:

```python
import fitz  # PyMuPDF

doc = fitz.open("report.pdf")
for page in doc:
    print(page.get_text())
```

For a single-column document this works. But here's what `get_text()` returns for a two-column page — I'll show it compacted:

```
Revenue grew 12%   New hire attrition fell
in Q3, driven by   to 8% as retention
the enterprise     programs matured
segment...
```

Read it top-to-bottom and it's nonsense, because `get_text()` emits glyphs in the order they appear in the content stream, which for a two-column layout is roughly "left headline, right headline, left body, right body." The *meaning* is destroyed while the *words* are all still present — which is exactly what makes this failure so dangerous: nothing looks obviously wrong until a user asks a question and gets a hallucinated answer.

### The fix: layout-aware parsing reconstructs reading order

A layout-aware parser doesn't just read glyphs; it detects the page's *layout* — text blocks, columns, headings, tables, figures — and orders them the way a human would read them. Docling (the roadmap's linked tool, started by IBM Research and now an LF AI & Data project) is the current default for this. Its basic flow:

```python
from docling.document_converter import DocumentConverter

converter = DocumentConverter()
result = converter.convert("report.pdf")   # -> ConversionResult

print(result.document.export_to_markdown())
```

Reading this line by line, because it's the first example of a genuinely new mechanism:

- `DocumentConverter()` — creates the parser. This is the object that knows how to take a raw file and run the whole pipeline (format detection → layout analysis → structure → export). You make one and reuse it; it holds configuration like whether to run OCR.
- `converter.convert("report.pdf")` — runs that pipeline and returns a `ConversionResult`, *not* a string. The result carries a structured document (`result.document`) plus a status (`SUCCESS`, `FAILURE`, `PARTIAL_SUCCESS`) and any errors — a big deal for batch jobs, where you want to log failures per-file instead of crashing the whole run.
- `result.document.export_to_markdown()` — serializes the reconstructed document to Markdown. Markdown is the useful target because it *preserves structure* (headings, lists, tables, code blocks), which is exactly what the chunker in Step 22 will respect.

The output is now in reading order, with headings as `#`/`##` and tables as Markdown tables — clean, structured input for chunking.

### Why Markdown is the right output format

You could export to plain text, but then you'd throw away the structure the parser worked to recover. Markdown keeps the hierarchy: a `##` heading tells the chunker "a new section starts here," and a pipe-delimited table tells it "these cells belong together." Plain text is a lossy format; Markdown is the lossless-enough middle ground between "raw document" and "what the model needs."

### DOCX and HTML: the easy cases, with caveats

**DOCX** is the easiest real-world format, because it's already structured — a `.docx` is a zip of XML files where paragraphs, headings, and tables are explicitly tagged. Extraction is mostly "read the XML and emit Markdown," and you can do it with `python-docx` or just hand it to Docling. The one gotcha: DOCX from "print to Word" or a PDF converted to DOCX can be just as scrambled as the PDF, because the structure was already lost before you got it.

**HTML** is also structured, but noisy: navigation, sidebars, cookie banners, and repeated boilerplate are all part of the page. Extraction is easy; *isolation of the actual content* is the hard part (that's the cleaning in 21.3). For HTML, tools like `trafilatura` or readability-style extractors are often better first steps than a general document parser, because they're specifically built to strip the chrome and keep the article.

### The decision rule

| Input | First tool to reach for |
|---|---|
| Single-column, born-digital PDF | `PyMuPDF` / `pypdf` — fast, no heavy deps |
| Multi-column, tables, or anything complex | Docling (layout-aware) |
| DOCX | `python-docx` or Docling |
| HTML (web pages) | `trafilatura` / readability, then clean |
| Scanned PDF / image | OCR (21.2), then layout-aware parse |

Reach for the heavy parser when the layout matters — "use Docling when the document's *structure* is load-bearing; use plain extraction when it's just prose and you're in a hurry."

---

## 21.2 — Tables, Figures & OCR for Scanned Documents

### Tables: the thing that breaks naive extraction most

A naive extractor sees a table as cells laid out at coordinates and emits them in whatever order it stumbles across — usually reading *down a column first*, which produces `Name | Age | Alice | Bob | 30 | 25` instead of a 2×3 grid. The information is present but the relationship between cells is destroyed, which is fatal for any question like "who is 30?"

Layout-aware parsers have **table structure recognition**: they detect the table's bounding box and grid (or whitespace alignment) and reconstruct it as a real table. Docling exports tables as Markdown tables:

```markdown
| Name  | Age |
|-------|-----|
| Alice | 30  |
| Bob   | 25  |
```

That Markdown table is what you want to feed downstream — it preserves the row/column relationship that the embedding model needs to "see." The key point: **tables must be kept as tables**, not flattened to text, or the cell relationships are lost. This is a strong argument for Markdown output (21.1) over plain text.

### Figures and images

A PDF often contains figures (charts, diagrams, photos) with captions. For text-based RAG you typically *skip* the image content but *keep the caption*, because a chart's meaning is often in its caption ("Figure 3: revenue by segment"). Docling lets you export figures separately and optionally enrich them with a text description using a vision-language model (relevant to Step 84/85). For this step, the rule is: keep captions in the text, and store images separately with a reference — don't just drop them silently.

### OCR: when there's no text layer

**OCR** (Optical Character Recognition) turns an *image of text* into text. You need it when the PDF is scanned or a photo — there is no text layer to extract, so extraction returns empty. Docling integrates OCR engines (Tesseract and EasyOCR being the common two), and the config is the "hard part" worth showing:

```python
from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions, TesseractOcrOptions
)
from docling.document_converter import DocumentConverter, PdfFormatOption

pipeline_opts = PdfPipelineOptions()
pipeline_opts.do_ocr = True
pipeline_opts.ocr_options = TesseractOcrOptions()

converter = DocumentConverter(format_options={
    InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_opts),
})
result = converter.convert("scanned_invoice.pdf")
```

The judgment calls here:

- **Full-page OCR vs. selective OCR.** You *can* run OCR on every page, but it's slow and error-prone. The better approach is: extract the text layer where it exists, and only OCR pages (or regions) that have no text. This is "selective OCR" and it's the production default.
- **OCR quality is a function of input quality.** A 150-DPI scan with handwriting will produce garbage no matter the engine. Resolution, contrast, and skew matter more than engine choice.
- **OCR is the fallback, not the first resort.** If a PDF has a text layer, use it — it's usually more accurate than re-OCR'ing the rendered page.

The rule of thumb: **use OCR only when the text layer is missing, and treat its output as lower-confidence than born-digital text** — which matters when you later decide whether to cite or filter a chunk.

---

## 21.3 — Cleaning, Deduplication & Boilerplate Removal

### The problem: your "content" is full of non-content

Every real document is padded with **boilerplate**: page numbers, running headers ("Annual Report 2024"), footers with legal disclaimers, and — for HTML — navigation menus, cookie banners, and "related articles" links. If you embed this, two things go wrong: boilerplate chunks dilute retrieval (they match on words like "page" and "copyright" that appear everywhere), and deduplication fails because every page's footer is near-identical but not identical.

### Cleaning: normalize before you dedupe

Before you can spot "this chunk is a duplicate of that chunk," you have to normalize so that near-identical text becomes *actually* identical:

```python
import re

def clean_text(text: str) -> str:
    text = text.replace("\u00a0", " ")           # non-breaking space -> space
    text = re.sub(r"\s+", " ", text)             # collapse all whitespace
    text = re.sub(r"\x00", "", text)             # strip null bytes from bad PDFs
    text = re.sub(r"[\u200b\u200c\u200d]", "", text)  # zero-width chars
    return text.strip()
```

The specific offenders: non-breaking spaces, zero-width characters, and control bytes all *look* invisible but break exact-match dedupe and inflate token counts. Collapse them first.

### Boilerplate removal: two approaches

1. **Structural** (preferred) — if your parser knows what's a header/footer (Docling does), drop it at parse time using the document's structure. This is more reliable than pattern-matching.
2. **Pattern-based** — strip repeated lines: page numbers (`^\d+$`), running headers that appear on many pages, and known footer text.

The production insight: **boilerplate is best detected by repetition across pages.** A line that appears on 90% of pages is boilerplate by definition; a line that appears once is content. Compute frequency per document and drop the high-frequency, low-information lines.

### Deduplication: near-duplicates are the enemy

Exact duplicates are easy (hash them). The hard case is **near-duplicates**: two revisions of the same paragraph, or a paragraph repeated with one word changed. For RAG you usually want to collapse these, because two near-identical chunks don't add retrieval value — they just make the top-k results redundant.

| Method | What it catches | Cost |
|---|---|---|
| Exact hash (`sha256`) | Byte-identical chunks | Trivial |
| **MinHash / LSH** | Near-duplicates (Jaccard similarity above a threshold) | Low-medium |
| Embedding similarity | Semantic duplicates (same meaning, different words) | Higher, uses your embedding model (Step 20) |

For this step, start with exact-hash dedupe and add MinHash when you observe redundant retrieval results. Embedding-based dedupe is the most powerful but also the most expensive, and it overlaps with what you'll do in Step 20/26 — don't build it until you have evidence you need it.

The rule of thumb: **clean to make text comparable, then dedupe to keep the index from storing the same information twice.**

---

## 21.4 — Metadata Extraction for Filtering & Citations

### Why metadata is not a nice-to-have

A RAG answer is only trustworthy if it can point at a *source*: "this claim comes from `2024-annual-report.pdf`, page 12, section 'Risk Factors'." Without metadata, your chunks are anonymous text, and you can't (a) filter retrieval by source/date, or (b) show citations. Both are core product requirements, and both require that metadata survives from extraction all the way to the chunk.

### The fields that matter, and where they come from

| Field | Example | Source | Used for |
|---|---|---|---|
| `source` | `2024-annual-report.pdf` | Filename / document ID | Filtering, citation |
| `page` | `12` | Parser (page number) | Citation, "where did this come from" |
| `section` | `Risk Factors` | Parser (heading structure) | Filtering, context |
| `date` | `2024-03-15` | Filename / metadata / parsing | Recency filtering ("only last 2 years") |
| `content_hash` | `a1b2c3...` | Computed | Incremental re-ingestion (21.5) |

The critical design rule: **metadata must be carried alongside the text, not guessed later.** The parser knows the page number and heading; once you flatten to a bare string, that information is unrecoverable. So the ingestion pipeline should emit structured records, not strings:

```python
from dataclasses import dataclass

@dataclass
class DocumentChunk:
    text: str
    source: str
    page: int
    section: str | None
    content_hash: str
```

This is the seam where ingestion (this step) hands off to chunking (Step 22) — and the reason chunking should happen *on top of* a structured document, not on raw extracted text. (Docling even provides a `HybridChunker` that respects this structure; you'll meet chunking properly in Step 22.)

### Metadata quality is a filtering problem, not a formatting problem

If `date` is missing on 30% of documents, then "filter to last 2 years" silently drops those documents — a correctness bug, not a cosmetic one. The fix is to *validate* metadata at ingestion: require `source`, attempt to resolve `date`, and log a warning (Step 14) for any chunk that goes in without the fields your filters depend on. A filter is only as good as the completeness of the field it filters on.

---

## 21.5 — Incremental Re-Ingestion & Keeping an Index Fresh

### The problem: your corpus changes, your index doesn't

The first version of ingestion is a one-shot batch: parse everything, chunk everything, embed everything. Then someone updates one PDF — and now your index has a stale version of that document, and your RAG system confidently cites an outdated number. The naive fix ("just re-ingest everything every time") works for a handful of documents but is wasteful and slow for a corpus, and it burns money re-embedding unchanged documents.

### The fix: detect what changed, re-process only that

The mechanism is a **content hash**: a fingerprint of a document's bytes. If the hash is unchanged, the document is unchanged, and you skip it. If it changed, you re-parse, re-chunk, and re-embed *just that document*, and update (or replace) its old chunks in the index.

```python
import hashlib

def content_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()
```

The ingestion loop becomes:

```
for each file:
    h = content_hash(file)
    if h == stored_hash(file):   # unchanged
        skip
    else:
        parse + chunk + embed(file)   # changed or new
        update stored_hash(file)
        delete old chunks for this file
```

Three things make this actually correct in production:

1. **The hash must be stored alongside the chunks.** You need to know, at re-ingestion time, what the *previous* hash was to compare against. A `document_versions` table mapping `source → (hash, ingested_at)` is the standard way.
2. **Deletion matters as much as insertion.** Re-processing a changed document must *remove* the old chunks, or the index accumulates both versions and returns stale results. A stable `document_id` (or `source` + version) lets you delete-by-source before inserting the new chunks.
3. **Partial failures must not corrupt state.** If re-parsing fails midway, you want to keep serving the old version, not wipe it. The pattern: ingest to a staging state, and only atomically swap old→new after the new chunks are fully built and validated.

### Beyond byte-hash: when a file changes semantically

A byte hash catches "the file changed" but not "this chunk is now wrong because a *different* document changed" — which happens with cross-references, or when you dedupe across documents (21.3) and a removed duplicate should propagate. For this step, byte-hash-per-document is the right scope. The more advanced cases (dependency-aware invalidation, embedding-space drift) belong to the monitoring step (Step 74), not here.

The rule of thumb: **store a content hash per document and make re-ingestion idempotent — same input produces the same index state, and changed input replaces only its own old chunks.**

---

## Pitfalls

1. **Using naive text extraction on a two-column PDF.** You get scrambled reading order, and the damage is invisible until a user gets a hallucinated answer. Use layout-aware parsing when layout is load-bearing.
2. **Flattening tables to text.** Losing cell relationships makes "who is 30?" unanswerable. Keep tables as Markdown tables through to the chunker.
3. **Running OCR on everything.** Slow, error-prone, and often *worse* than the text layer that was already there. Use selective OCR — only when the text layer is missing.
4. **Dropping captions and metadata during cleaning.** Captions carry meaning; metadata carries provenance. Strip boilerplate, not structure.
5. **Deduping before cleaning.** Non-breaking spaces and zero-width chars make near-identical text look different. Normalize first, then dedupe.
6. **Emitting bare strings instead of structured records.** Once you flatten to a string you've lost page/section/source forever. Carry metadata alongside text.
7. **Re-ingesting everything on every change.** Wasteful and slow. Hash per document and re-process only what changed.
8. **Forgetting to delete old chunks on re-ingestion.** You end up with stale and current versions both in the index, and the stale one keeps winning retrieval.
9. **Treating `date` metadata as optional when you filter on it.** Missing dates silently drop documents from recency filters. Validate the fields your filters depend on.
10. **Trusting OCR output as confidently as born-digital text.** OCR errors propagate to embeddings and retrieval. Track OCR vs. native as a confidence signal.

---

## Quick Reference

| Goal | Tool / approach |
|---|---|
| Extract single-column born-digital PDF | `PyMuPDF` (`fitz`) / `pypdf` |
| Multi-column, tables, complex layout | Docling (layout-aware) |
| DOCX | `python-docx` or Docling |
| HTML (web pages) | `trafilatura` / readability extractor |
| Scanned PDF, no text layer | OCR (Tesseract / EasyOCR), selective |
| Preserve table structure | Export as Markdown tables |
| Strip boilerplate | Structural removal (parser) + frequency-based repetition |
| Normalize text | Collapse whitespace, strip zero-width/control chars |
| Dedupe exact chunks | `sha256` hash |
| Dedupe near-duplicates | MinHash / LSH |
| Carry provenance | Structured records: `text`, `source`, `page`, `section`, `date` |
| Track what changed | Per-document content hash |
| Re-ingest safely | Hash → skip unchanged → replace old chunks atomically |

---

## Theory Summary

**Extraction is where quality is decided.** Chunking, embedding, and retrieval are all downstream of extraction, and none of them can repair text that was scrambled or lost at the source. The highest-leverage place to invest in RAG quality is *before* the text becomes a string — that's the entire point of this step.

**A document is structure, not just text.** Headings, tables, captions, page numbers, and reading order are all information. The more of that structure you preserve (Markdown is the practical format for doing so), the better the downstream system can reason. Extracting "the text" while discarding "the structure" is the root cause of most broken RAG.

**The parser matters only as much as the document's complexity.** Single-column prose doesn't need a heavyweight parser; a two-column table-heavy PDF absolutely does. Match the tool to the layout, and reach for OCR only when there's genuinely no text layer — it's a fallback, not a default.

**Cleaning and deduplication are prerequisites for retrieval quality.** Normalize so text becomes comparable, then remove boilerplate and duplicates so the index doesn't store (or retrieve) the same information twice. Every redundant chunk in the index is noise competing with your real content for top-k slots.

**Metadata is what makes retrieval answerable and citable.** Anonymous text can be embedded but not filtered or sourced. Carrying `source`, `page`, `section`, and `date` through ingestion is what turns "the model says X" into "the model says X, from this document on this page" — and it's the difference between a toy and a product.

**Ingestion is a stateful process, not a one-shot.** Your corpus changes, and the index must change with it. Content hashes make change detectable, and idempotent re-ingestion makes it safe — re-process only what changed, and never leave stale chunks behind.

---

## Deliverable

**`Phase 1(AI)/STEP 21/step21-ingestion/`** — a minimal ingestion pipeline that turns raw documents into clean, deduplicated, metadata-carrying records ready for chunking:

- **`ingest.py`** — the pipeline, built around Docling:
  - `parse(path) -> list[DocumentChunk]` — uses `DocumentConverter` to extract Markdown, splits by page, and attaches `source`, `page`, `section` (from heading), and a computed `content_hash` to each chunk.
  - `clean(text) -> str` — the normalization function from 21.3 (whitespace collapse, zero-width/control stripping).
  - `dedupe(chunks) -> list[DocumentChunk]` — exact-hash dedupe on `content_hash`.
  - `reingest(path, state: dict) -> (added, skipped, removed)` — content-hash change detection: skip unchanged files, re-process changed ones, and return the list of old chunk hashes to delete.
- **`sample_report.pdf`** — a small multi-column or table-containing PDF you generate or find, used to *prove* the layout-aware parser recovers reading order that naive extraction scrambles.
- **`test_ingest.py`** — pytest tests (Step 13) asserting: `clean` normalizes non-breaking spaces, `dedupe` collapses identical chunks, `parse` attaches page/source metadata, and `reingest` skips an unchanged file. No network calls.

**Prove it:** run `parse()` on `sample_report.pdf` and show the Markdown output is in correct reading order with tables intact — then run the same file through `fitz.open().get_text()` and capture the scrambled output side by side. That before/after is the whole step in one screenshot.
