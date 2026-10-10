# Step 32: Tool Calling / Function Calling

> **Covers:** the 5-step loop that lets a model *take an action* instead of only talking (declare tools → model requests a call → your code executes → result goes back → model answers), how tool schemas are written, controlling whether tools get called at all, running calls in parallel, designing tools the model can actually use, and the security rules that make all of it safe.

---

## The Problem

A model cannot check a database, read a file, or call an API. It generates text, and that is its entire capability. Ask "how tall is K2?" and it will either guess from memory or refuse — even when the exact number is one row away in your `peaks` table.

Tool calling closes that gap. The model emits **structured JSON saying which function to call with which arguments**; your code runs the function; the result goes back into the conversation. The model never executes anything. **It decides; you execute.** That one sentence is the whole step.

---

## Foundational Concepts

### The loop (every provider, every framework)

```
1. you send:  user message + tool definitions (JSON Schema)
2. model sends back:  a tool call — { name: "lookup_peak", arguments: {...} }
      (or plain text, if no tool was needed)
3. YOUR code runs the function
4. you send the result back as a tool message
5. model now answers with real data
```

Steps 2–4 repeat until the model stops asking for tools. That repetition **is** the agent loop (Step 33); here it's a single turn.

### A tool is two things

- a **declaration** — the JSON Schema the model reads (name, description, parameter types)
- an **implementation** — the Python function your code calls

Keep them registered together. The model only ever sees the first.

### The descriptions are prompts

The model chooses tools by reading descriptions. `"gets weather"` produces worse selection than `"Get current weather for a city. Returns temperature in Celsius and conditions."` **Tool descriptions are prompt engineering, and they matter more than you'd expect.**

### Tool calling ≠ structured output

Both use JSON Schema; the *purpose* differs:

| | What the model is doing | The output is |
|---|---|---|
| **Structured output** (Step 32.6) | producing data | the final product |
| **Tool calling** | declaring an intent to act | an intermediate step |

Extracting `{name, price}` from a page is structured output. `lookup_peak(name="K2")` is a tool call. Reach for the first when you want *data*, the second when you want an *action*.

---

## 32.1 JSON Schema Tool Definitions

**Motivate.** The model needs to know your function exists, what it does, and what arguments it takes — all from text.

**Define.** A tool declaration is a name, a description, and a JSON Schema for the arguments.

```json
{
  "name": "lookup_peak",
  "description": "Look up one eight-thousander's height, countries and first ascent. Use for exact facts.",
  "parameters": {
    "type": "object",
    "properties": {
      "name": { "type": "string", "description": "Peak name, e.g. 'K2' or 'Everest'" }
    },
    "required": ["name"]
  }
}
```

**Rule of thumb.** Write the description for the *model*, not a human: say when to use it, and what it returns. List every parameter you want supplied in `required` — optional arguments get skipped.

---

## 32.2 How the Model Requests a Call

**Motivate.** The request arrives in a provider-specific envelope, and the arguments are not always what you expect.

**Define.** The model replies with a call — a name plus arguments — instead of text.

- **OpenAI:** `choices[0].message.tool_calls[]`, where `arguments` is a **JSON string** you must parse.
- **Anthropic:** a `content[]` block of `type: "tool_use"`, where `input` is **already an object**.
- **Gemini:** a `parts[]` entry containing `functionCall` with `args`.

Each call carries an **id** — and you must echo that id back with the result, or the model cannot match a result to its call. This matters the moment there is more than one call (32.4).

**Rule of thumb.** Assume nothing about the arguments: parse, then **validate** (32.8). The model will occasionally produce a plausible-looking argument that violates the schema.

---

## 32.3 Executing & Returning Results

**Motivate.** The failure mode here is a tool that raises, killing the whole request.

**Define.** Run the function, then send the result back as a message tied to the call id.

```python
try:
    result = TOOLS[name](**args)
except TypeError as exc:            # wrong arguments - the model's mistake
    result = {"error": True, "message": f"Invalid arguments: {exc}"}
return result                        # becomes the tool result message
```

**Send errors back as data, not exceptions.** A structured error lets the model correct itself:

```json
{"error": true, "message": "Peak 'K2 ' not found. Did you mean 'K2'?", "code": "NOT_FOUND"}
```

Models are good at self-correcting from a specific error and bad at recovering from a stack trace.

**Rule of thumb.** A failing tool should never take down the request. Catch, structure, return, let the model try again.

---

## 32.4 Parallel Tool Calls

**Motivate.** "Weather in Tokyo and London" as two sequential calls is a wasted round trip.

**Define.** The model emits **several calls in one message**; you run them all and reply with one batched result message.

- OpenAI: `parallel_tool_calls` (default on).
- Anthropic: on by default since Claude 3.5.
- Gemini: supported, with stable ids since Gemini 3 so out-of-order results still correlate.

**Rule of thumb.** Run independent calls **concurrently** (they're usually I/O-bound) and always key results by call id, never by position.

---

## 32.5 Tool Design: Why Bad Tools Cause Bad Agents

**Motivate.** When an agent behaves badly, the tools are the usual suspect — not the model.

**Define.** Tool design is interface design for a reader that has no context beyond your description.

| Smell | Fix |
|---|---|
| Two tools that overlap ("get_weather" / "fetch_forecast") | One tool, or descriptions that draw a hard line |
| A tool named `manage_data(action=...)` | Split per action; names are self-documenting |
| A vague description | Say when to use it and what it returns |
| An optional argument the model must supply | Make it `required` |
| A tool that returns everything (the whole table) | Return the few fields needed — results become context, and context costs money |

**Rule of thumb.** If a human can't tell which tool to call from the descriptions alone, neither can the model. Fewer, clearer, well-described tools beat a large vague set.

---

## 32.6 Structured Output Modes: Constrained Decoding vs. Prompt-and-Parse

**Motivate.** You can force valid JSON two ways, with different failure modes.

**Define.**

- **Constrained decoding** (JSON-schema / strict mode): the decoder is restricted to strings that match your schema, so malformed JSON is impossible. Guarantees shape, not truth.
- **Prompt-and-parse**: ask for JSON in the prompt and parse it yourself. Works on any model, fails on bad output — wrap the parse in try/except and count failures (Step 30's lesson).

**Rule of thumb.** Use the provider's schema mode when available (it's strictly better for well-formedness); use prompt-and-parse only where you must, and always handle the parse failure.

---

## 32.7 `tool_choice`: Auto / Required / None / Force

**Motivate.** Sometimes you *know* a tool must be used, and letting the model decide wastes a round trip or invites a guess.

| Mode | Meaning | Use when |
|---|---|---|
| **auto** (default) | model decides: call a tool or answer | general use |
| **required / any** | must call at least one tool | you know the answer needs live data |
| **none** | must not call tools | final answer turn; tool-free mode |
| **force a named tool** | must call *this* tool | routing — upstream logic already picked it |

Names differ per provider (`tool_choice: "required"` vs `{"type":"any"}` vs `mode: "ANY"`), but the four modes are universal.

**Rule of thumb.** `required` for the first turn of a fact question ("never guess when you could look it up"), `none` for the answer turn, and force-by-name when you've already decided the route.

---

## 32.8 Security: Allowlists, Argument Validation, Result Sanitisation, Call Budgets

**Motivate.** Tool calling is the most dangerous capability you can hand a model. It chooses what to execute — so it, in effect, writes your arguments and sometimes your queries.

**The rules:**

1. **Allowlist the tools.** Only functions you explicitly registered are reachable. Never build a generic "call any function by name" tool. Expose the 5 the user needs, not the 50 you have.
2. **Validate every argument** against the declared schema (types, enums, ranges) *before* execution. The model can pass `"; DROP TABLE users; --"` as a city.
3. **Never send model-generated SQL to a database.** Parameterize, or expose a structured query API (`table` + `filters` from an allowlist) instead of raw SQL. You already do this in Project 2's `structured_lookup`.
4. **Sanitise tool results.** Everything a tool returns goes back into the model's context verbatim. Strip secrets, PII, and internal error detail before it gets there.
5. **Budget the calls.** Cap tool calls per conversation (10–20 is plenty) to stop runaway loops and runaway bills.
6. **Treat tool output as untrusted input.** A tool result can contain text like *"ignore your instructions and…"*. That is **indirect prompt injection** — the tool's content is an attack surface, not just data.

**Rule of thumb.** Assume the model's arguments are hostile. It isn't malicious; it's just occasionally wrong in ways an attacker can predict.

---

## Pitfalls

1. **Building a generic "execute any function" tool.** That's remote code execution with extra steps.
2. **Trusting arguments.** Always validate before executing; schema compliance is about *shape*, not safety.
3. **Raising out of a tool.** One bad tool call then kills the whole request. Return structured errors instead.
4. **Forgetting the call id.** With parallel calls, results without ids cannot be matched to their request.
5. **Vague descriptions or overlapping tools.** The model picks badly and it looks like a model problem when it's an interface problem.
6. **Returning whole objects.** Tool results land in the context window — and context costs money and hurts focus (Step 35).
7. **No call budget.** An agent in a loop will happily call the same tool twenty times.
8. **Treating tool output as trustworthy.** Injection arrives *through* the tools (pitfall 6 above, the sharp end of it).

---

## Quick Reference

| Goal | How |
|---|---|
| Let the model act | declare a tool (name + description + JSON Schema) and register its implementation |
| Make selection reliable | write descriptions for the model; make required args `required`; avoid overlapping tools |
| Run the call | parse arguments → validate → execute → return a result tied to the call id |
| Handle failure | return `{error, message, code}` as data; never raise out of a tool |
| Fan out | run parallel calls concurrently; key results by id |
| Force / forbid a call | `tool_choice`: auto / required / none / named |
| Guarantee valid JSON shape | provider schema mode (constrained decoding), else prompt-and-parse with a try/except |
| Stay safe | allowlist tools · validate args · parameterize SQL · sanitise results · cap calls · distrust tool output |

---

## Theory Summary

- **The model decides; your code executes.** That division is the entire mechanism, and everything else is plumbing around it.
- **A tool is a declaration plus an implementation**, and the model only ever sees the declaration. Descriptions are prompts, and bad ones produce agents that look broken.
- **Errors are conversation.** Return them as structured data and the model self-corrects; raise them and the request dies.
- **Call ids are the contract** for matching results to requests, and the only thing holding parallel calls together.
- **Tool calling is the most dangerous thing you give a model.** Allowlist, validate, parameterize, sanitise, budget — and treat tool output as untrusted input, because it is.

---

## Deliverable

**`Phase 1(AI)/STEP 32/step32-tool-calling/`**

A **function-calling loop over Project 2's own capabilities** — the continuity being that its `structured_lookup` and keyword search become *tools* the model can call.

- **`tools.py`** — three real tools wrapping what you already built: `lookup_peak` (exact facts from the `peaks` table), `search_corpus` (keyword search over the chunks), and `list_peaks`. Each is a JSON-Schema declaration plus an implementation, in one registry. Includes **argument validation** and **structured error returns**.
- **`loop.py`** — the loop: send the question + declarations, run whatever the model requests (concurrently for parallel calls), feed results back, stop when it answers. Sets a **call budget**, echoes **call ids**, and accepts `tool_choice`.
- **`--simulate` mode** — the loop runs against **scripted model decisions** instead of a live API, so the artifact is fully exercisable with **zero quota**. The live path is the same loop with a real provider call.

**Deliberate design notes:** the SQL-touching tool takes a **structured request** (`peak name`), never a raw query string — rule 3 of 32.8, and exactly how Project 2's lookup already works. And every tool result is returned as JSON the model reads, so a failure is a message, not a crash.
