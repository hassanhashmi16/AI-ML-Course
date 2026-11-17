# Writing Preferences (Reference for Future Sessions)

## Purpose

Every step file is training material for becoming an AI/ML engineer who understands and can apply the subject. Prioritize depth over checkbox coverage, sound engineering practice, and a concrete learning artifact. "Depth" means explaining the concepts and their dependencies from first principles, then showing how they affect decisions. The goal is concise *teaching*: a first-time reader should be able to follow using the syllabus already covered. Professional competence is the destination; unfamiliar terminology and advanced prerequisites must be taught or explicitly placed in a later step.

## Approved example and learning level

The rewritten [Step 46: ML Fundamentals & Model Evaluation](<Phase 2(ML)/STEP 46/Step46-ML-Fundamentals-Evaluation.md>) is the preferred teaching example, approved by Hassan on 17 November 2026. Follow its progression and clarity; do not copy its length or running example into every lesson.

Before creating or rewriting a lesson, read the relevant roadmap outline and earlier lessons, especially the immediately preceding steps. Establish what has actually been taught. Knowing Python or having built LLM applications does not imply knowing model training, statistics, or other new subject vocabulary.

Within Foundational Concepts, explain where the lesson starts: what prior knowledge it uses, what is new, and which later steps develop the mathematics or implementation. For substantial lessons, include a linked lesson map and a short reading order. These should help the reader take one section at a time.

## CRITICAL: Research-first protocol

Whenever asked to create a study material `.md` file for any step:

1. **Research beyond the roadmap's linked resources.** Check official docs, top university courses (Stanford CS224N/CS336, MIT 6.S191, etc.), benchmark papers, and production best practices. Identify all genuinely important concepts for the topic.

2. **Spread research across multiple independent sources — never lean on one.** The roadmap's linked resource is a starting point, not the whole bibliography. Pull from at least 3–4 distinct sources, mixing categories: official docs, online courses (MIT Missing Semester, Harvard CS50, Coursera courses, etc.), big-university curricula, and production practice guides (e.g., Google's Shell Style Guide). Prefer sources from different institutions/organizations so one bias or gap can't dominate the file.

3. **Cross-check one external curriculum.** `github.com/rohitg00/ai-engineering-from-scratch` (MIT-licensed, `phases/<NN>-<phase>/<NN>-<lesson>/docs/en.md`) covers most of these topics in depth. Read the matching lesson before writing — not to copy, but to catch anything the roadmap outline missed.

4. **Check whether the roadmap needs a change.** Preserve the existing work. If research reveals a necessary missing subtopic or a prerequisite problem, make the smallest useful correction to `AI_Engineer_StepByStep.html` before writing the lesson. Leave a sufficient outline alone; rewriting notes does not automatically require changing the roadmap.

5. **Only then write the step `.md` file** with all concepts included upfront.

## File structure

Required sections, in this order:

1. **The problem** — 2–4 sentences. What breaks, what's impossible, or what you'd do badly *without* this topic. Motivation before mechanism. Never open with a definition.
2. **Foundational Concepts** — prior knowledge, reading order / lesson map where useful, and the basic concepts needed to follow the body. Explain each concept before its code example.
3. **The body** — one section per roadmap subtopic (15.1, 15.2, …), plus any additional concepts needed for real understanding. Use standard topic names and define new terms before relying on them.
4. **Pitfalls** — the specific ways this goes wrong in practice, and how you'd notice. Not optional; this is where most of the real value is.
5. **Quick Reference** — a lookup table.
6. **Theory Summary** — the mental model and principles to internalize. Ideas, not method names.
7. **Deliverable** — see below.

End with **Sources and further study**, including direct links supporting the material and an honest review date. Distinguish sources consulted from code or behavior actually tested.

## Topic names and video learning

Use conventional, searchable names in numbered headings and subheadings: **Cross-Validation and Hyperparameter Search**, rather than only **How do we estimate performance?** A motivating question may introduce the section, but must not replace the topic name.

At each numbered topic section, add one or a few exact **YouTube search phrases** using the established terms. Put narrow searches near the relevant subsection when a section covers several distinct concepts. Search phrases are sufficient unless specific videos are requested; do not invent video titles or present unwatched videos as verified recommendations. Videos supplement the worked examples and exercises.

## Every step ships something (CRITICAL)

The `.md` file is not the output of a step. It's the notes taken while producing the output.

Each step ends with **one named artifact committed to the repo** — a script, a module, a benchmark, a test suite, a config, a small tool. Concrete enough to name in a single line, small enough to finish in one sitting, and reusable in a later project or step. Examples: a token-counting CLI, a retrieval eval harness over 20 hand-written queries, a reusable retry/backoff decorator, a Dockerfile that actually builds.

This describes completion of the learning step, not permission to build or commit the exercise whenever notes are requested. Name the proposed artifact and distinguish an exercise to build from an artifact already created. Keep its prerequisites within the current and previously covered syllabus. A foundations lesson can evaluate supplied predictions before a later lesson implements model training.

Deliverable code is teaching material too: **comment it line-by-line (or close to it).** Every non-obvious line gets an inline comment saying what it does and why it's there, so the artifact reads like a walkthrough, not a code dump. Keep the *logic* minimal, and keep the `.md` explanation to a few lines — but inside the artifact itself, be generous with comments. A deliverable you can't reread a month later isn't reusable.

If a step genuinely has no artifact, say so explicitly and give a written exercise instead — but treat that as the exception. A phase where nothing was built is a phase that didn't happen.

## Length discipline

Teach from first principles, then compress. Every concept is explained as if the reader is meeting it for the first time — what it is, why it exists, and how it works — and *then* the prose is tightened. Concise means no padding, no fluff, no repeated examples; it does not mean reducing concepts to one-line summaries that only make sense if you already know them. A first-time reader should never have to infer what a term means from context.

Two rules hold at once:

- **Cut padding, never understanding.** Remove repetition and filler; keep the intuition and the mechanism.
- **One clear explanation beats three terse bullets.** When a concept is new, a short explanatory paragraph is better than a bullet that assumes the reader already knows it.

Bullets and tables are for reference and comparison (Quick Reference, decision tables) — not a substitute for explaining a concept in the body. A mechanically simple topic should still be short; a dense topic runs longer because there is genuinely more to teach, not because of padding. Use clear subsections and navigation for a substantial lesson. Split into separate steps only when the material genuinely needs a separate learning unit; do not trigger a roadmap renumber merely to match other files' lengths.

## Teaching structure: motivate, then name

"The Problem" section at the top motivates before any definition — the reader should feel the specific pain the concept exists to fix. Keep it tight (2–4 sentences), but don't skip it.

Each subtopic gets its own miniature version of the same shape, in this order:

1. **Motivate** — one line on what breaks or is hard without the concept.
2. **Define** — what it actually is, in plain words, assuming no prior knowledge.
3. **Show** — a minimal example or diagram that makes the definition concrete.
4. **Rule of thumb** — close with "use X when Y," which reads as usable judgment rather than trivia to memorize.

When a mechanism is genuinely new (a decorator handing an argument nobody declared, a `yield` splitting a function, a name that resolves non-obviously), explain what it does and why it's there in a sentence or two — enough that a first-time reader isn't left guessing. Later examples of the same mechanism can go back to terse code + a short note.

Teach dependencies in order. Explain inputs, answers, training, and prediction before using them to discuss evaluation; apply the same principle to other subjects. Bold and define a new term at first substantive use, expand unfamiliar acronyms, and give intuition plus a concrete example. A glossary or Quick Reference is a lookup aid after teaching, not a replacement for it. Distinguish easily confused meanings, such as a software test versus a model's test set.

Develop intuition before formal notation or library APIs. Explain each symbol, formula component, unit, and denominator when introduced, and work through the arithmetic where useful. If a derivation or implementation belongs later, explain enough for the current decision and cross-reference that later topic by name and step number. Clearly mark orientation-only material so it does not become an unexplained prerequisite.

## Examples, checkpoints, and verification

- **Use a running example.** Reuse one realistic problem across related sections so the reader can focus on the new idea. Use another example when the task changes, such as classification to regression, and explicitly identify the change.
- **Keep numbers traceable.** State sample sizes, actual outcomes, units, and assumptions. Counts and calculations must agree. Explain changes in sample size or class proportions between examples.
- **Make code followable.** Prefer complete, small runnable examples. Define inputs, imports, and variables; label conceptual sketches or dependent fragments explicitly. Avoid unrelated snippets with undeclared variables. Do not introduce a later library as an unexplained requirement.
- **Show boundaries.** Identify invented probabilities, illustrative costs, tiny samples, and simplifications. A hand-worked example demonstrates a calculation; it does not establish real model performance. Explain important edge cases without burying the basic mechanism.
- **Check understanding.** Include brief checkpoints after key concepts and a final self-check or exercise. Ask the reader to explain, calculate, or choose, then provide answers with enough reasoning to check their understanding.
- **Verify before delivery.** Run examples presented as runnable when practical, check worked arithmetic and expected outputs, and validate navigation and roadmap references. Check technical distinctions against authoritative sources. Report only checks actually performed; do not call a documentation review a tested implementation.

## Content rules

- **Explain basics from scratch.** Even if something seems obvious to an experienced dev, if it's a new concept for me, explain it. Assume I'm learning it for the first time.
- **Fundamentals first.** Theory and understanding are equally as important as code. Don't just throw code at me.
- **Explain genuinely new concepts from scratch.** If a concept is new to the reader, a one-line summary is not enough — it reads like a reference for someone who already knows it. Give the definition, the intuition for why it exists, and a minimal example. Keep it concise, but never leave a first-time reader to infer meaning from context. Only after a concept is established do later examples go back to terse code + a short note.
- **Concise depth.** Explain more in fewer words. No fluff. No padding. Every sentence should carry weight.
- **Technical accuracy.** Don't oversimplify to the point of being wrong. Use correct terminology, but explain it.
- **Real documentation.** Scrape the actual docs/sites referenced in the roadmap. Don't write from memory alone. The source material is the authority.
- **Date the volatile claims.** Library APIs, model names, pricing, and "the current standard" all move. Pin versions (`TRL v1.0`, `pgvector 0.8`) and mark time-sensitive statements as of the month written, so a file read a year later is still honestly interpretable.

## Tone

- Direct, conversational. Like a senior dev explaining to a junior who's sharp.
- Don't use emojis unless I ask.
- Don't praise me or say "great question" — just answer.
- Use analogies when they clarify (X is like Y), but don't stretch them.

## What to include

- **Section for each roadmap subtopic** (1.1, 1.2, etc.)
- **Additional concepts** that are necessary for real understanding, even if not in the roadmap
- **Decision trees or tables** comparing alternatives (when to use X vs Y)
- **Common mistakes** and pitfalls
- **Concrete examples** with realistic data

## Roadmap maintenance

The roadmap has been renumbered twice; each renumber invalidates every step number written into existing `.md` files. So:

- **Preserve structure and progress.** Change only what fixes an identified gap, prerequisite problem, or inaccuracy. Keep step numbers and completion tracking intact unless the user requests an update or a necessary structural correction requires renumbering. Writing notes does not mark a learning step complete.
- **Make prerequisites visible.** State whether a topic is an intuitive preview, a practical exercise, or a mathematical treatment. A short prerequisite note can resolve a preview-before-maths ordering without moving whole steps.
- **Prefer subtopics over new steps.** A missing concept usually belongs inside an existing step's outline, not as a new module. Only add a step when nothing existing can own it.
- **If a new step is genuinely needed**, insert it in the right pedagogical position anyway — then renumber everything downstream, rename the affected `.md` files in *descending* order, and patch cross-references in prose (leave `Step 1:` code comments alone).
- **Always validate after a renumber**: step ids sequential 1..N, badges match ids, sidebar hrefs match ids, outline `N.x` prefixes match their step, and every prose `Step N` in range.
- **Cross-reference by name and number** (`self-attention (Step 59)`), never number alone — a stale number is then still readable.

## Formatting

- Markdown, GitHub-flavored.
- Use tables for comparisons and references.
- Use code blocks with realistic examples — comments inside showing output.
- Bold key terms on first mention.
