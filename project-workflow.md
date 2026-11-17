# Project Workflow

## Scope and teaching reference

Use [writing-preferences.md](writing-preferences.md) for all course study material and teaching explanations. Its approved Step 46 example establishes the preferred style: check the covered syllabus, explain dependencies and new terms before using them, use standard topic names and YouTube search phrases, and teach through consistent worked examples and checkpoints.

The small implementation steps below govern building projects. They do not impose a 30-line limit on study documents or require pausing between sections while writing a requested lesson. A request for notes authorizes the notes and necessary roadmap corrections; the proposed learning exercise remains for the learner to complete unless building it is also requested.

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

2. **Cover the necessary concepts upfront.** Include what is needed to understand and apply the current topic, rather than waiting for the learner to discover gaps. Teach dependencies in order. Explain where later mathematics, algorithms, or implementation are developed instead of assuming those prerequisites or inserting an unexplained advanced-topic list.

3. **The standard:** Would lack of this knowledge cause a real gap in understanding, building, debugging, or designing the system? If yes, ensure it has a clear place in the course. Teach it here if the current topic depends on it; otherwise cross-reference the appropriate later step. Aim for professional understanding through a beginner-accessible progression.

4. **Cover system design implications, not just definitions.** For each concept: how does this affect decisions about architecture, trade-offs, performance, and failure modes in real systems?

5. **Resolve scope against the syllabus.** Put essential foundations before the concepts that need them, label brief previews, and keep detailed future material in its appropriate step. Preserve the roadmap unless a specific gap or prerequisite issue requires a correction. Before delivering, check example code, arithmetic, expected outputs, and references as appropriate; do not mark the step complete merely because its notes are written.

## The system design mindset

Every decision, ask:
- **Why this approach and not another?** (trade-offs)
- **What happens at the boundaries?** (edge cases, errors)
- **What's the simplest version that works?** (avoid over-engineering)
