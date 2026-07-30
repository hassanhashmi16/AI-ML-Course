# Project Workflow

## The process

1. **Before writing any code**, the project is broken down into tiny, discrete steps.
2. These steps are saved in a **new markdown file** inside the project folder (e.g., `Project-1-Meeting-Summarizer/STEPS.md`). This file is the permanent reference — steps won't get lost in chat history.
3. After each step, the **folder structure and architecture** is explained — what files exist, how they connect, and why they're organized that way. This is as important as the code itself.
4. The STEPS file can be as detailed as needed since it's saved persistently.
5. Each step is executed **one at a time** — you manually tell me to proceed to the next.
6. After writing the code for a step, I explain the **general idea and structure** of what was just built — system-level thinking, not in-depth code analysis.

## What each step looks like

```
## Step N: [Single Task Name]

**What:** One sentence describing the task.

**Why:** Engineering reasoning. Why this approach? What problem does it solve?
What alternatives exist? What trade-offs are we making?

**How:** The approach. What files change? What's the data flow?
What's the input and output of this piece?

(code here)

**Structure:** Brief explanation of how this piece fits into the overall
system — architecture, data flow, design decisions.
```

## Step sizing rule

A step is small enough that:
- The explanation fits in a few paragraphs
- The code change is under ~30 lines
- You can see exactly how it fits into the bigger picture

## Thoroughness rule (CRITICAL)

Before finalizing the MD file for any step, I must:

1. **Research beyond the linked resource.** Check the official docs, related tutorials, and what the topic covers in top university courses (Stanford CS224N, MIT 6.S191, etc.) to identify all genuinely important concepts for the topic.

2. **Add everything important upfront — in one go.** Not the minimum, not incrementally when asked. Every concept a competent AI/ML engineer should know about this topic. Then stop and ask if there's anything else the user wants.

3. **The standard:** Would a graduate from a top ML program or an engineer at a leading AI company be expected to know this? If yes, it belongs in the file. The distinction isn't "is this interesting?" — it's "would lack of this knowledge cause a real gap in my ability to build, debug, or design systems?"

4. **Cover system design implications, not just definitions.** For each concept: how does this affect decisions about architecture, trade-offs, performance, and failure modes in real systems?

5. **If genuinely unsure whether something belongs, add it anyway with a note.** Better to include and let the user trim than to omit and leave a gap.

## The system design mindset

Every decision, ask:
- **Why this approach and not another?** (trade-offs)
- **What happens at the boundaries?** (edge cases, errors)
- **What's the simplest version that works?** (avoid over-engineering)
