# Checkup report — CodeTrail investigation workspace

- **Project:** CodeTrail (`Phase 1(AI)/PROJECTS/Project-4-CodeTrail/frontend/`)
- **Mode:** checkup (bare `/design` routing; no prior report existed)
- **Register:** product — an operator runs an investigation and inspects its evidence
- **Date:** 18 October 2026
- **Score:** **30 / 60**
- **Verdict:** **Block** — three HIGH escalation triggers standing at audit time

---

## Vitals

| # | Vital | Score | Status | Key finding |
|---|---|---|---|---|
| 1 | Intentionality | 5/10 | Watch | Dark slate + blue-violet accent + mono is the generic developer-tool reflex; nothing expresses "case file / provenance" |
| 2 | Readability | 5/10 | Watch | One voice (system sans) for chrome and document; no reading measure on any prose; 15px base |
| 3 | Usability | 5/10 | Watch | Core task works, but no empty state, saved runs sit under a long form, stages are a separate card |
| 4 | Responsiveness | 5/10 | Watch | Single 900px breakpoint; sub-16px inputs (iOS zoom); fixed 92px timeline column |
| 5 | Speed | 10/10 | Healthy | 24 modules, 231 kB JS (72 kB gzip), no web fonts, no layout shift observed |
| 6 | Accessibility | 0/10 | Critical | Spinner ignores `prefers-reduced-motion`; evidence sheet has no focus move/trap/restore or Escape; focus-visible treatment missing on buttons |

---

## Findings

| # | Sev | Discipline | Location | Before | After | Why |
|---|---|---|---|---|---|---|
| 1 | HIGH | Motion | `frontend/src/index.css` (`.spinner`, `@keyframes spin`) | Spinner rotates for as long as the run takes, with no reduced-motion gate | Wrap animation in `@media (prefers-reduced-motion: no-preference)`; under reduce show a static "Working" indicator | Escalation trigger: self-starting rotational motion that ignores `prefers-reduced-motion` |
| 2 | HIGH | Accessibility | `frontend/src/components/EvidenceDrawer.jsx:1-45` | `role="dialog" aria-modal="true"` but no focus move-in, no trap, no focus restore, no Escape, background not `inert` | Move focus to the sheet on open, trap Tab, close on Escape, restore focus to the originating citation, `inert` the page while open | Mouse can wander the page behind an "open" dialog while the keyboard cannot; a role promises a keyboard model it does not implement |
| 3 | HIGH | Interaction | `frontend/src/App.jsx:118-140` | Before the first run the workspace is empty; the only affordance is a form in the rail | An empty state that teaches what a run produces and offers the prepared cases as the primary action | A first-time visitor cannot tell what the product does or what to do next |
| 4 | MEDIUM | Layout | `frontend/src/index.css` (`.layout`, `.panel`, `.report`) | The report is a card inside the workspace, containing sections; status, report and stage log are three stacked sibling cards | A ruled document (title block, findings, trail, scope) beside a rail; one elevated plane only for the evidence sheet | Nested cards flatten hierarchy; the document has no spine, so scanning a long report is work |
| 5 | MEDIUM | Type | `frontend/src/index.css` (`body`, `.summary`, `h1/h2/h3`) | 26/16/13px scale, `1.5` line-height, no measure; chrome and prose share one voice | Serif document voice at 72ch measure for summary/claims; sans stays for chrome; section tags at 11px uppercase | Flat scale reads as uncommitted; full-width prose loses the line |
| 6 | MEDIUM | Accessibility | `frontend/src/index.css` (button rules) | Buttons get a hover border change; focus falls back to the UA default while inputs get a hard-coded 1px outline | One `:focus-visible` ring (2px accent, 2px offset) across buttons, links, inputs | Tab focus must be as visible as hover, and consistent between control types |
| 7 | MEDIUM | Accessibility | `frontend/src/index.css` (`input, textarea` inherit 15px) | Inputs render below 16px | Inputs at 16px on narrow screens | Escalation-adjacent: sub-16px inputs trigger iOS Safari auto-zoom on focus |
| 8 | MEDIUM | Interaction | `frontend/src/index.css` (`.case`, `button` padding `7px 12px`) | Rail buttons land near 30px tall | 40px primary controls, 36px chips, 44px row targets in the rail | Fine-pointer precision on a laptop, mis-taps on touch |
| 9 | MEDIUM | Voice | `frontend/src/index.css` tokens | Near-black chrome plus a blue-violet accent is the predictable developer-tool palette | Paper, ink, hairline rules, one teal accent, colored stamps for the three labels | The surface could be swapped into any dev tool by changing the logo |
| 10 | LOW | Writing | `frontend/src/components/ReportView.jsx` and `App.jsx` | Em dashes in UI copy ("— coverage incomplete") | Commas, colons, or a new sentence | Em dashes interrupt rather than clarify |

---

## Considered but rejected

| Location | Candidate | Rejected because |
|---|---|---|
| `index.css` (`--muted` on `--panel`) | Raise muted contrast | Measured around 6.5:1, above the 4.5:1 body threshold; no evidence of a readability failure |
| `Timeline.jsx` (92px date column) | Collapse the grid below 360px | At 320px the date column plus a readable line still fits; no reflow failure observed |
| `App.jsx` (saved-runs list) | Virtualize the list | The API caps at 100 reports and each row is a single line; no jank evidence |
| `index.css` | Add tabular figures | No numeric columns exist on the surface yet; premature |
| `App.jsx` (resume) | Confirm dialog before resume | Resume is idempotent, not destructive; undo beats confirm, and there is nothing to undo |

---

## Prescriptions

1. **Motion:** gate the spinner on `prefers-reduced-motion: no-preference`; under reduce, keep the work named and the elapsed time visible without rotation.
2. **Evidence sheet:** it is a real dialog. Focus in, trap, Escape to close, restore to the citation, background `inert`.
3. **First run:** an empty document that states what a run produces (a claim with a stamp and a citation, a trail, an unknown list) and runs a prepared case in one click.
4. **Layout and type:** rebuild the workspace as a **case file**: rail for the brief, ruled document for the report, sheet for evidence, header stamp for status.
5. **Focus and targets:** one focus-visible ring everywhere; 40px primary controls.
6. **Voice:** replace the dark blue dev-tool palette with paper, ink, hairlines, and one accent that means "interactive".

---

## Verification

**Ran:**

- `npm run build` → 24 modules transformed, 231.06 kB JS / 5.87 kB CSS (72 kB gzip)
- `npm run lint` → 0 warnings, 0 errors across 11 files
- Vite transform probes through the dev server: `/src/main.jsx`, `/src/App.jsx`, `/src/components/ReportView.jsx` all 200
- API plumbing through the UI proxy: `/health` and `/reports` both 200 with real payloads
- Source inspection of all 11 frontend files at line level (findings 1-10 cite exact locations)

**Not verified (verification gap, not a pass):**

- Rendered appearance and keyboard traversal in a real browser: no browser automation is installed in this environment (`agent-browser` is not installed), so no visual or Tab-order check was performed
- Contrast under a color-blindness simulation
- 200% zoom reflow

---

## Verdict

**Block** at audit time: three HIGH escalation triggers (1, 2, 3). Fixed in the same pass per bare `/design`
routing, together with the MEDIUM layout, type, focus, target, and voice findings. Re-audit after the
browser verification gap closes.

---

## Re-audit (browser verification, 19 October 2026)

`agent-browser` 0.39.1 with Chrome 155 was installed, and the surface was driven at 1280×900 and 375×812.

**Verified working:**

- axe-core 4.12.1: **0 violations** on the empty state (40 passes) and on a populated report (43 passes).
  The one *incomplete* item is background determination inside the scrollable saved-runs list, not a failure.
- Evidence sheet: focus moves to the dialog on open (`aria-labelledby=evidence-title`), Escape closes it,
  and focus returns to the triggering citation (`PR #4682`).
- Tab order starts with the skip link, then the prepared cases; the focus ring is visible on a case button.
- `prefers-reduced-motion: reduce` emulation: computed animation duration becomes `1e-06s`.
- 375px: the document now leads, the rail follows; no horizontal overflow.

**Found by this pass and fixed:**

- The sticky rail with an inner scrollbar clipped the question field, the Investigate button, and Saved
  runs. The rail now scrolls with the page; the primary action is visible on first paint.
- The mobile order put the whole rail before the document; the document now comes first under 1020px.
- Muted text measured 4.24:1; the token was darkened until axe passed.
- Minor: missing comma in the empty-state copy; disclosure summaries gained a +/− indicator.

**Still not exercised in the browser:** the running state and a live investigation (they require a paid
model run). Both are build-verified only.
