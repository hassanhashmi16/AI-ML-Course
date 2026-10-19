# CodeTrail: reference repository and demo cases

**Step 1 completed:** 16 October 2026.

## Why we selected a repository

CodeTrail's product input is **a public GitHub repository link and a question**. The repository below supplies manually verified examples for development and demonstrations. Repository identity comes from each request; it is not a fixed application setting.

Before automating an investigation, we need to know what a good answer looks like. Otherwise, a convincing explanation could be completely wrong without us noticing. These cases give us two supported explanations and one question the inspected evidence cannot settle.

They are development/demo cases, not a held-out evaluation set. Later evaluation must include new questions and another repository, with saved findings reset, to check that the app generalizes.

## Repository selection

| Candidate | Evidence inspected | Decision |
|---|---|---|
| [pallets/flask](https://github.com/pallets/flask) | Context-storage PR #4682, JSON-provider PR #4692, and relevant 2.2.0 source | Selected: two distinct changes have accessible implementation and explicit rationale |
| [encode/httpx](https://github.com/encode/httpx/pull/187) | The merged `trust_env` PR, its linked issue lead, and review discussion | A useful later candidate; did not complete three cases here |
| [Starlette](https://github.com/Kludex/starlette/discussions/1729) | Discussion of middleware limitations and proposed approaches | A useful later candidate; deciding which proposal became implementation needs additional tracing |

This is a small evidence-quality check, not an exhaustive comparison of the projects.

### Reproducible snapshot

| Field | Value |
|---|---|
| Repository | `https://github.com/pallets/flask` |
| Demo ref | `2.2.0` |
| Resolved commit SHA | `b17bb9ed563ab2857c0db9a07ec4e6407404c7be` |
| Commit timestamp from GitHub metadata | `2022-08-02T00:12:09Z` |
| Checked | 16 October 2026 |

The [release page](https://github.com/pallets/flask/releases/tag/2.2.0) identifies the short commit `b17bb9e`; GitHub's [commit endpoint](https://api.github.com/repos/pallets/flask/commits/2.2.0) resolved the full SHA above. This historical snapshot contains both selected changes. It is source material to inspect, not a Flask dependency to install for CodeTrail.

Source was inspected through the `2.2.0` raw-file URLs below; the JSON-provider source was also available through its full-SHA URL. Keep the full SHA as the future collector's input. Direct SHA-addressed retrieval of some other files was unavailable through the research browser, so the checked tag-to-SHA mapping is recorded explicitly rather than claiming every canonical file URL was fetched.

## Case CT-001: why context storage changed

**Input**

```text
Repository: https://github.com/pallets/flask
Ref: b17bb9ed563ab2857c0db9a07ec4e6407404c7be
File: src/flask/ctx.py
Question: Why did Flask replace LocalStack with direct ContextVar handling
          for its application and request contexts?
```

**Evidence trail**

1. [Context implementation at the checked tag](https://raw.githubusercontent.com/pallets/flask/2.2.0/src/flask/ctx.py): inspect `AppContext.push/pop`, `RequestContext.push/pop`, and `_cv_tokens`.
2. [Context globals](https://raw.githubusercontent.com/pallets/flask/2.2.0/src/flask/globals.py): inspect `_cv_app` and `_cv_request`.
3. [PR #4682](https://github.com/pallets/flask/pull/4682), merged 8 July 2022: its timeline identifies the context refactor commits and merge `cbebdae`; its description records the reason.
4. [Release changes](https://raw.githubusercontent.com/pallets/flask/2.2.0/CHANGES.rst), the context-storage entry under Version 2.2.0, corroborates the change and links #4682.

**Short source excerpt:** “performance and memory overhead on every `push` and `pop`.” [PR #4682](https://github.com/pallets/flask/pull/4682).

**Expected finding:** the earlier mutable-list stack needed copying to preserve isolation when contexts were copied. The refactor used context-variable tokens to restore previous values, avoiding that stack-management overhead. The source demonstrates token storage and reset. Label this rationale **documented**; do not attach an unverified percentage speedup.

**What the app must do:** connect the implementation to its historical discussion. Reading only the current function is insufficient to establish the author's reason. The Werkzeug PR mentioned in the discussion is an external-repository lead; it is not necessary for this expected answer and was not used as independent evidence here.

## Case CT-002: why JSON became a provider

**Input**

```text
Repository: https://github.com/pallets/flask
Ref: b17bb9ed563ab2857c0db9a07ec4e6407404c7be
File: src/flask/json/provider.py
Question: Why was the JSONProvider interface introduced instead of relying
          on custom JSONEncoder and JSONDecoder classes?
```

**Evidence trail**

1. [Provider implementation at the pinned SHA](https://raw.githubusercontent.com/pallets/flask/b17bb9ed563ab2857c0db9a07ec4e6407404c7be/src/flask/json/provider.py): inspect `JSONProvider`, `DefaultJSONProvider`, and the old encoder/decoder deprecation paths.
2. [Merge commit `67310ab`](https://github.com/pallets/flask/commit/67310ab): its message links #4692 and the diff includes the new provider file.
3. [PR #4692](https://github.com/pallets/flask/pull/4692), merged 13 July 2022: its description explains the customization motivation and discusses the previous hooks.

**Short source excerpt:** “fully customize the JSON implementation used by a Flask application.” [PR #4692](https://github.com/pallets/flask/pull/4692).

**Expected finding:** the provider creates an application-level integration point for alternative JSON implementations, including faster serializers. Encoder/decoder customization had been an ineffective integration mechanism; per-blueprint customization also added overhead and fit the new interface poorly. Label the motivation **documented**. Code at this snapshot still includes deprecated compatibility paths; do not claim the old hooks had already been removed.

**What the app must do:** separate the design motivation from API usage and migration status. The PR also links issue #1728 and the tag's changelog points to #4688 for some JSON entries; those leads were not independently retrieved successfully here. Do not treat them as verified support or silently replace the inspected #4692 commit relationship with an assumed one.

## Case CT-003: an unsupported performance claim

**Input**

```text
Repository: https://github.com/pallets/flask
Ref: b17bb9ed563ab2857c0db9a07ec4e6407404c7be
File: src/flask/ctx.py
Question: What exact percentage improvement in end-to-end Flask request
          throughput was measured for the LocalStack refactor, and under
          which benchmark setup?
```

**Inspected scope:** the context implementation, context globals, the visible #4682 description/timeline, and its 2.2.0 changelog entry listed in CT-001. The visible PR text was checked for benchmark results and percentage figures. No end-to-end measurement and reproducible benchmark setup were established from that material. No Flask benchmark was executed.

**Expected finding:** **unknown within this scope**. Explain the qualitative motivation already documented in CT-001, then state that an exact throughput gain and benchmark setup cannot be substantiated from these inspected sources. Identify benchmark results as the missing evidence.

**Unacceptable finding:** inventing a percentage, treating removal of an overhead as a measured throughput result, or claiming that no benchmark exists anywhere in Flask's history. The linked Werkzeug investigation, other commits, and hidden or unavailable discussion content were not exhaustively searched.

This case checks whether the system recognizes the limits of its evidence. A later broader investigation may discover a real measurement; if so, revise the case's scope and reference answer rather than forcing an unknown result.

## Case CT-004: removed internals, kept compatibility (added in Step 19)

**Input**

```text
Repository: https://github.com/pallets/flask
Ref: b17bb9ed563ab2857c0db9a07ec4e6407404c7be
File: src/flask/ctx.py
Question: Was the LocalStack API removed entirely in Flask 2.2.0, or kept for compatibility?
```

**Evidence trail**

1. [PR #4682](https://github.com/pallets/flask/pull/4682), merged 8 July 2022, is titled "remove use of `LocalStack`", which can read as full removal.
2. The same description states the nuance: the `_app_ctx_stack.top` and `_request_ctx_stack.top` attributes "will no longer exist", but "currently, there is a fake object that keeps the API around... importing them or accessing them will show deprecation warnings."
3. The 2.2.0 changelog records deprecations rather than an immediate removal.

**Short source excerpt:** "Currently, there is a fake object that keeps the API around... importing them or accessing them will show deprecation warnings." (PR #4682.)

**Expected finding:** internal use of LocalStack was replaced with direct ContextVar handling, while a **deprecated compatibility shim** preserved the old attribute API during the transition. Label both halves documented. "Removed entirely" is wrong for the public API.

**What the app must do:** reconcile a change title with its body. The title states the direction; the body states the compatibility boundary. A supported answer reports both, and the removal claim is scoped to internals.

This case checks conflicting-history handling: the same change supports two readings unless the evidence is read to the end.

## How this becomes a general repository-link product

```text
User's repository link + question (+ optional path/ref)
  → validate and resolve that repository's snapshot
  → discover a bounded set of relevant files and changes
  → fetch that repository's discussions
  → retrieve, investigate, and cite its evidence
```

Cache/index namespaces and retrieval filters include the requested repository and snapshot. Flask appears in demo inputs, never in the generic reader/agent logic. Expected answers stay outside runtime retrieval and memory so the app must reconstruct its explanation from sources.

Accepting another public Python repository uses this same flow. The variable work is finding relevant files and fetching its initial evidence; results also depend on how much rationale that project recorded. Private access, huge exhaustive histories, and equally good support for every programming language require additional scope decisions.

## Step 1 check and files

- Verified the release ref's full SHA through GitHub metadata.
- Inspected the source, PR descriptions/timelines, and JSON merge diff used above.
- Recorded two supported cases and a scoped unknown, including unsuccessful leads.
- Created this reference document; application collection, indexing, and automated evaluation will be implemented in their planned steps.

```text
Project-4-CodeTrail/
  STEPS.md             # execution plan and current progress
  docs/
    demo-cases.md      # this reference corpus, questions, and expected findings
```

The next build step is the project skeleton and environment. The examples here tell us what that future application must investigate; they are not prewritten application responses.
