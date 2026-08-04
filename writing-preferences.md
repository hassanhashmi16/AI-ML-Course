# Writing Preferences (Reference for Future Sessions)

## CRITICAL: Research-first protocol

Whenever asked to create a study material `.md` file for any step:

1. **Research beyond the roadmap's linked resources.** Check official docs, top university courses (Stanford CS224N/CS336, MIT 6.S191, etc.), benchmark papers, and production best practices. Identify all genuinely important concepts for the topic.

2. **Spread research across multiple independent sources — never lean on one.** The roadmap's linked resource is a starting point, not the whole bibliography. Pull from at least 3–4 distinct sources, mixing categories: official docs, online courses (MIT Missing Semester, Harvard CS50, Coursera courses, etc.), big-university curricula, and production practice guides (e.g., Google's Shell Style Guide). Prefer sources from different institutions/organizations so one bias or gap can't dominate the file.

3. **Cross-check one external curriculum.** `github.com/rohitg00/ai-engineering-from-scratch` (MIT-licensed, `phases/<NN>-<phase>/<NN>-<lesson>/docs/en.md`) covers most of these topics in depth. Read the matching lesson before writing — not to copy, but to catch anything the roadmap outline missed.

4. **Update the roadmap HTML first.** Add any missing subtopics to `AI_Engineer_StepByStep.html` before writing the `.md` file. This keeps the roadmap comprehensive and prevents gaps from accumulating.

5. **Only then write the step `.md` file** with all concepts included upfront.

## File structure

Required sections, in this order:

1. **The problem** — 3–6 sentences. What breaks, what's impossible, or what you'd do badly *without* this topic. Motivation before mechanism. Never open with a definition.
2. **Foundational Concepts** — what the concept is and why it matters, before any code.
3. **The body** — one section per roadmap subtopic (15.1, 15.2, …), plus any additional concepts needed for real understanding.
4. **Pitfalls** — the specific ways this goes wrong in practice, and how you'd notice. Not optional; this is where most of the real value is.
5. **Quick Reference** — a lookup table.
6. **Theory Summary** — the mental model and principles to internalize. Ideas, not method names.
7. **Deliverable** — see below.

## Every step ships something (CRITICAL)

The `.md` file is not the output of a step. It's the notes taken while producing the output.

Each step ends with **one named artifact committed to the repo** — a script, a module, a benchmark, a test suite, a config, a small tool. Concrete enough to name in a single line, small enough to finish in one sitting, and reusable in a later project or step. Examples: a token-counting CLI, a retrieval eval harness over 20 hand-written queries, a reusable retry/backoff decorator, a Dockerfile that actually builds.

If a step genuinely has no artifact, say so explicitly and give a written exercise instead — but treat that as the exception. A phase where nothing was built is a phase that didn't happen.

## Length discipline

Target **250–450 lines** per step file. Hard ceiling around 600.

Longer isn't more thorough — past a point it's undigested research, and it slows the roadmap down for no retention gain. If a file is running over, the fix is compression (tables instead of prose, one good example instead of three), not deletion of concepts. If a topic genuinely needs more, that's a signal it should be two steps, and the roadmap should say so.

## Content rules

- **Explain basics from scratch.** Even if something seems obvious to an experienced dev, if it's a new concept for me, explain it. Assume I'm learning it for the first time.
- **Fundamentals first.** Theory and understanding are equally as important as code. Don't just throw code at me.
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

- **Prefer subtopics over new steps.** A missing concept usually belongs inside an existing step's outline, not as a new module. Only add a step when nothing existing can own it.
- **If a new step is genuinely needed**, insert it in the right pedagogical position anyway — then renumber everything downstream, rename the affected `.md` files in *descending* order, and patch cross-references in prose (leave `Step 1:` code comments alone).
- **Always validate after a renumber**: step ids sequential 1..N, badges match ids, sidebar hrefs match ids, outline `N.x` prefixes match their step, and every prose `Step N` in range.
- **Cross-reference by name and number** (`self-attention (Step 59)`), never number alone — a stale number is then still readable.

## Formatting

- Markdown, GitHub-flavored.
- Use tables for comparisons and references.
- Use code blocks with realistic examples — comments inside showing output.
- Bold key terms on first mention.
