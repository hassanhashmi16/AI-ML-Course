# Step 10: Anthropic / OpenAI SDK

> **What it covers:** Client setup, messages format, streaming, and tool-use/function-calling — everything needed to call an LLM from code.

---

## Foundational Concepts (read this first)

### What is an SDK?

An **SDK** (Software Development Kit) is a wrapper library that makes calling an API easier. Instead of manually crafting HTTP requests, setting headers, handling JSON serialization, and parsing responses, the SDK gives you Python objects and methods.

Under the hood, the SDK still makes HTTP requests to Anthropic's or OpenAI's servers — it just hides that complexity. This means:

- Your code never leaves your machine. You send text to their servers, they run the model, they send text back.
- You need an internet connection. The model is not running locally.
- You pay per token (input + output), not per API call.

### What is an API Key?

An API key is a secret string that identifies you and authorizes your requests. Think of it like a password for your code. Every request to Anthropic or OpenAI includes this key in an HTTP header (`x-api-key` for Anthropic, `Authorization: Bearer` for OpenAI). Without it, the server rejects the request.

**Best practice:** Never hardcode API keys in source files. Use environment variables or a `.env` file:

```python
import os
api_key = os.environ["ANTHROPIC_API_KEY"]
```

### The HTTP Request/Response Model

Every call to an LLM follows the same pattern:

1. **You send a request** — a JSON payload containing your model choice, messages, and parameters.
2. **The server processes it** — the model runs inference, generating tokens one by one.
3. **You receive a response** — a JSON payload containing the generated text and metadata (token usage, stop reason, etc.).

This is a **stateless** protocol. Each request is independent. If you want a conversation, you must send the entire history with every request — there is no server-side "session" remembering previous turns. This is why the `messages` array exists: it's how you provide context.

### What is a Token?

A **token** is the atomic unit the model reads and generates — roughly ¾ of an English word, or about 4 characters. The model doesn't see letters or words; it sees tokens.

- `max_tokens`: The hard cap on how many tokens the model can generate in its response. If it hits this cap, it stops mid-word. This is a safety valve to prevent runaway costs.
- Input tokens (your messages) + output tokens (the response) = total tokens you pay for.
- Why `max_tokens` matters: without it, a model could theoretically generate forever, running up a massive bill.

### What is Temperature?

Temperature controls **randomness** in the model's output. The model generates a probability distribution over the next possible token, and temperature shapes that distribution before sampling:

- **`temperature=0.0`** — Always pick the most likely token. Deterministic. Same input → same output. Use for classification, extraction, structured data, and anything where consistency matters.
- **`temperature=1.0`** — Sample proportionally from the raw probabilities. High variability. Use for creative writing, brainstorming, etc.
- **`temperature > 1.0`** — Flatten the distribution further, making less-likely tokens more probable. Use rarely.

Most pipeline/AI-engineering tasks use `temperature=0.0` or very close to it.

---

## 10.1 — Client Setup & Authentication

### Anthropic

```bash
pip install anthropic
```

```python
import anthropic

client = anthropic.Anthropic(
    api_key="sk-ant-..."  # or set ANTHROPIC_API_KEY env var
)
```

**Get a key:** [console.anthropic.com](https://console.anthropic.com)

**Key models (as of mid-2026):**

| Model ID | Use case |
|---|---|
| `claude-haiku-4-5` | Fastest, cheapest. Good for classification, simple responses. |
| `claude-sonnet-5` | Balanced. Good default for most tasks. |
| `claude-opus-4-8` | Most intelligent. Complex reasoning, multi-step tasks. |

### OpenAI

```bash
pip install openai
```

```python
from openai import OpenAI

client = OpenAI(api_key="sk-...")  # or set OPENAI_API_KEY env var

# Minimal call
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello"}],
    max_tokens=2000,
)
print(response.choices[0].message.content)
```

Both SDKs default to reading `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` from your environment if you don't pass `api_key` explicitly.

---

## 10.2 — Messages Format (system / user / assistant)

### Why this format exists

LLMs are trained on conversation data. The `messages` array simulates a conversation history. Each message has a **role** that tells the model whose turn it is and **content** that provides the actual text.

The model reads the entire `messages` array as context, then generates the next assistant message. This is why you can (and should) include prior turns — they give the model conversational context it otherwise wouldn't have.

### Anthropic Messages API

A call requires at minimum: `model`, `max_tokens`, and `messages`.

```python
import anthropic

client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=1000,
    temperature=0.0,
    system="You are a helpful assistant who responds in pirate-speak.",  # system prompt
    messages=[
        {"role": "user", "content": "What is the capital of France?"},
        # Optional: include prior assistant responses for multi-turn
        {"role": "assistant", "content": "Arr, ye ask about France!"},
        {"role": "user", "content": "And Germany?"},
    ],
)

print(response.content[0].text)
# Access usage stats
print(response.usage.input_tokens, response.usage.output_tokens)
```

**Critical rules for `messages`:**
- Must be a list of dicts, each with `role` and `content`.
- Roles **must alternate** between `user` and `assistant`.
- Must **start with a `user` message**.
- `system` is a **separate top-level parameter** — not part of the messages array.

**Why `system` is separate in Anthropic:** The system prompt is treated differently during inference — it gets special attention weighting, making the model more likely to follow its instructions than instructions buried in a `user` message. It persists across all conversation turns without needing to be repeated.

**Common mistakes that cause errors:**
```python
# ❌ Missing role/content keys
messages=[{"Hello, how are you?"}]

# ❌ Two user messages in a row (no alternation)
messages=[
    {"role": "user", "content": "What year was Celine Dion born?"},
    {"role": "user", "content": "Tell me more about her."},
]
```

### Anthropic's Content Block Model

Anthropic responses don't return a plain string. They return a **list of content blocks**:

```python
response.content
# [{type: "text", text: "The capital is Paris."}]
# or with tool use:
# [{type: "text", text: "Let me check..."}, {type: "tool_use", ...}]
```

This matters because a single response can contain multiple types of content (text + tool calls) in one turn. You access specific blocks by type and index.

### OpenAI Chat Completions API

```python
from openai import OpenAI

client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the capital of France?"},
        {"role": "assistant", "content": "The capital of France is Paris."},
        {"role": "user", "content": "What about Germany?"},
    ],
)

print(response.choices[0].message.content)
```

**Key differences from Anthropic:**
- OpenAI puts the system prompt **inside the `messages` array** with `role: "system"`. Anthropic uses a separate `system` parameter.
- OpenAI returns `response.choices[0].message.content`; Anthropic returns `response.content[0].text`.
- OpenAI's `content` is a plain string. Anthropic's `content` is a **list of content blocks** (text, tool_use, etc.).
- OpenAI supports a `role: "developer"` (GPT-4o+) — conceptually similar to `system` but lower-priority. Anthropic has no equivalent.

### Key parameters for both SDKs

| Parameter | Purpose |
|---|---|
| `model` | Which model to call |
| `max_tokens` | Hard cap on output tokens (can cut off mid-word) |
| `temperature` | 0.0 = deterministic, ~1.0 = creative. Use 0.0 for most pipeline tasks. |
| `messages` | Conversation turns |
| `system` | (Anthropic) Instructions that persist across the conversation |

---

## 10.3 — Streaming Responses & SSE

### The Problem Streaming Solves

Without streaming, the model generates the **entire response** before sending anything back. If `max_tokens` is large (say, 4,000 tokens for a long essay), the user stares at a blank screen for several seconds, then gets everything at once. For real-time chat UIs, this is a terrible experience.

Streaming sends each token as it's generated, so the user sees text appearing character-by-character — like ChatGPT's typing effect.

### What is SSE (Server-Sent Events)?

**SSE** is a web standard where the server keeps an HTTP connection open and pushes data to the client as it becomes available, rather than closing the connection after one response.

**How it differs from regular HTTP:**
- Regular HTTP: Client sends request → Server processes → Server sends response → Connection closes.
- SSE: Client sends request → Server keeps connection open → Server sends multiple events over time → Connection closes when the stream ends.

**How SSE differs from WebSockets:**
- SSE is **one-directional** (server → client only). The client cannot send data back over the same connection.
- WebSockets are **bi-directional** (both sides can send at any time).
- SSE is simpler, uses standard HTTP, and works through proxies and firewalls more reliably.
- For LLM streaming, SSE is the right choice — you only need server → client.

**What an SSE stream looks like on the wire:**

```
event: message_start
data: {"type": "message_start", "message": {...}}

event: content_block_start
data: {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Hello"}}

event: content_block_delta
data: {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": " world"}}

event: ping
data: {"type": "ping"}

event: content_block_stop
data: {"type": "content_block_stop", "index": 0}

event: message_delta
data: {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 15}}

event: message_stop
data: {"type": "message_stop"}
```

Each line prefixed with `event:` names the event type, and `data:` carries the JSON payload. The SDKs parse this into clean Python objects so you don't deal with raw SSE.

**The `ping` event** exists because SSE connections stay open for long periods. If no data is flowing, proxies and firewalls might close the connection thinking it's dead. Pings keep it alive.

### Streaming Event Types Explained

| Event | What it means |
|---|---|
| `message_start` | A new message is beginning. Contains a skeleton `Message` object with empty content. |
| `content_block_start` | A content block is starting (text, tool_use, or thinking). Has `index` to identify it. |
| `content_block_delta` | Incremental data for the current block. For text: `text_delta`. For tool calls: `input_json_delta`. For extended thinking: `thinking_delta`. |
| `content_block_stop` | The current content block is complete. |
| `message_delta` | Top-level message changes — typically the `stop_reason` and final `usage` counts. |
| `message_stop` | The entire message is complete. No more events will come for this message. |
| `ping` | Keep-alive heartbeat. Ignore it — the SDK handles it. |

### Actually using streaming (the code)

```python
import anthropic

client = anthropic.Anthropic()

# Basic text streaming — the common case
with client.messages.stream(
    model="claude-sonnet-5",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Write a haiku about Python."}],
) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)   # flush=True so it prints immediately

# If you just want the final assembled message (avoids HTTP timeouts on large max_tokens)
with client.messages.stream(
    model="claude-sonnet-5",
    max_tokens=128000,  # large output
    messages=[{"role": "user", "content": "Write a detailed analysis..."}],
) as stream:
    message = stream.get_final_message()   # accumulates all events internally
    print(message.content[0].text)
```

### OpenAI (streaming)

```python
from openai import OpenAI

client = OpenAI()

stream = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Write a haiku about Python."}],
    stream=True,
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="", flush=True)
```

OpenAI uses the same SSE mechanism under the hood, but its SDK API is different: you iterate over chunk objects, checking `delta.content` on each.

### Error recovery for streams

If a stream is interrupted (network issue, timeout), you can resume:
- **Anthropic (Claude 4.6+):** Send a new request with a user message containing the partial response and "Continue from where you left off."
- **OpenAI:** Reconstruct the partial message and re-send the conversation.

---

## 10.4 — Tool-Use / Function-Calling

### What problem does tool use solve?

LLMs are trained on text — they can't do math reliably, can't access live data, can't query databases, can't send emails. Tool use gives the model a way to say "I need to run this function with these arguments" instead of hallucinating an answer.

The model itself never executes code. It outputs a structured request, your code executes the function, and you feed the result back. The model then incorporates that result into its final response.

### The round-trip model

```
You: "What's the weather in SF?"
     ↓
Model: "I'll call get_weather("San Francisco, CA")"  ← model outputs a tool_use block
     ↓
Your code: executes get_weather() → "15°C, partly cloudy"
     ↓
You: feed "15°C, partly cloudy" back as a tool_result
     ↓
Model: "The weather in San Francisco is 15°C and partly cloudy."
```

This is why tool use requires at least **two API calls** — the initial call (which may return a tool request) and the follow-up call (which feeds the result back). The SDK's `ToolRunner` can automate this loop for you.

### The modern Anthropic tool use flow

```python
import anthropic
import json

client = anthropic.Anthropic()

# Step 1: Define the tool schema
tools = [
    {
        "name": "get_weather",
        "description": "Get the current weather for a given location.",
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "City and state, e.g. San Francisco, CA",
                }
            },
            "required": ["location"],
        },
    }
]

# Step 2: Send the request
messages = [{"role": "user", "content": "What's the weather in San Francisco?"}]

response = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=1024,
    tools=tools,
    tool_choice={"type": "auto"},  # let Claude decide whether to call a tool
    messages=messages,
)

# Step 3: Check for tool use blocks
if response.stop_reason == "tool_use":
    for block in response.content:
        if block.type == "tool_use":
            print(f"Claude called: {block.name}")
            print(f"With args: {json.dumps(block.input)}")

            # Step 4: Execute the tool yourself
            if block.name == "get_weather":
                result = "15 degrees Celsius, partly cloudy"  # your actual logic here

            # Step 5: Append the tool result and send back
            messages.append({"role": "assistant", "content": response.content})
            messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                ],
            })

    # Step 6: Get Claude's final answer
    followup = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        tools=tools,
        messages=messages,
    )
    for block in followup.content:
        if block.type == "text":
            print(block.text)
```

### `tool_choice` options

| Value | Behavior |
|---|---|
| `{"type": "auto"}` | Claude decides whether to use a tool or reply directly. (Default) |
| `{"type": "any"}` | Claude **must** use at least one tool before replying. |
| `{"type": "tool", "name": "get_weather"}` | Force a specific tool to be called. |
| `{"type": "none"}` | Disable tool use for this turn. |

### Parallel tool calls

Claude can call multiple tools at once when they're independent (e.g., get weather for two cities simultaneously). To disable: `tool_choice={"type": "auto", "disable_parallel_tool_use": True}`.

### Tool Runner (Anthropic SDK convenience)

The SDK provides `ToolRunner` to automate the round-trip loop:

```python
from anthropic import Anthropic
from anthropic.tools import ToolRunner

client = Anthropic()
runner = ToolRunner()

tools = [
    {
        "name": "get_weather",
        "description": "Get current weather for a location.",
        "input_schema": {
            "type": "object",
            "properties": {"location": {"type": "string"}},
            "required": ["location"],
        },
    }
]

response = client.messages.create(
    model="claude-sonnet-5",
    max_tokens=1024,
    tools=tools,
    messages=[{"role": "user", "content": "What's the weather in SF?"}],
)

final_response = runner.run(response, client, tools, messages)
```

### The older XML-based format (from the tutorial)

The original tutorial uses an XML-based format where tool definitions are embedded in the system prompt. Here's the conceptual pattern:

```
System prompt explains:
  - "You can call functions using <function_calls> blocks"
  - Lists tools with <tool_description>, <parameters>, etc.
  - Uses <invoke name="func"> with <parameter name="x">value</parameter>

Claude responds with:
  <function_calls>
    <invoke name="calculator">
      <parameter name="first_operand">1984135</parameter>
      <parameter name="operator">*</parameter>
      <parameter name="second_operand">9343116</parameter>
    </invoke>
  </function_calls>

Your code parses the XML, runs the function, and returns:
  <function_results>
    <result>
      <tool_name>calculator</tool_name>
      <stdout>18536496042660</stdout>
    </result>
  </function_results>
```

**Prefer the native `tools` parameter** (JSON schema-based) for new code. The XML format is legacy — it still works but the native approach is cleaner and the model is explicitly trained for it.

### OpenAI function calling

```python
from openai import OpenAI
import json

client = OpenAI()

tools = [
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get the current weather for a given location.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "City and state, e.g. San Francisco, CA",
                    }
                },
                "required": ["location"],
            },
        },
    }
]

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "What's the weather in SF?"}],
    tools=tools,
    tool_choice="auto",
)

tool_calls = response.choices[0].message.tool_calls
if tool_calls:
    for tc in tool_calls:
        args = json.loads(tc.function.arguments)
        print(f"GPT called: {tc.function.name}({args})")

    # Execute tool, append result
    messages = [
        {"role": "user", "content": "What's the weather in SF?"},
        response.choices[0].message,  # assistant message with tool_calls
        {
            "role": "tool",
            "tool_call_id": tool_calls[0].id,
            "content": "15°C, partly cloudy",
        },
    ]

    followup = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
    )
    print(followup.choices[0].message.content)
```

**Key differences from Anthropic:**
- OpenAI uses `tool_calls` on the assistant message (nested under `.message`), Anthropic uses `tool_use` content blocks (sibling to text blocks).
- OpenAI appends tool results as a `role: "tool"` message with `tool_call_id`. Anthropic uses a `user`-role message containing `tool_result` content blocks.
- Both use JSON Schema for tool definitions.

---

## Quick-Reference: Anthropic vs. OpenAI Cheatsheet

| Concept | Anthropic | OpenAI |
|---|---|---|
| **Install** | `pip install anthropic` | `pip install openai` |
| **Client** | `anthropic.Anthropic()` | `openai.OpenAI()` |
| **API method** | `client.messages.create()` | `client.chat.completions.create()` |
| **Model param** | `model="claude-sonnet-5"` | `model="gpt-4o"` |
| **System prompt** | Separate `system=` param | `{"role": "system", ...}` in messages |
| **Messages** | `[{"role": "user", "content": "..."}]` | Same format |
| **Response text** | `response.content[0].text` | `response.choices[0].message.content` |
| **Response structure** | List of content blocks | Plain string on `.message.content` |
| **Streaming** | `client.messages.stream()` → `stream.text_stream` | `stream=True` → iterate chunks |
| **Tool defs** | `tools=[{"name":..., "input_schema":...}]` | `tools=[{"type":"function", "function":{...}}]` |
| **Tool call in response** | `block.type == "tool_use"` on `response.content` | `response.choices[0].message.tool_calls` |
| **Tool result format** | `{"type": "tool_result", "tool_use_id": id, "content": ...}` as user message | `{"role": "tool", "tool_call_id": id, "content": ...}` |
| **Multi-turn** | Roles must alternate user/assistant | Same rule + tool role allowed |

---

## What to Practice

1. Get an API key, install the SDK, and make a single `messages.create()` call.
2. Add a **system prompt** and observe how it changes the response.
3. Send a **multi-turn conversation** (user → assistant → user) in one call.
4. Write a **streaming loop** that prints tokens as they arrive — watch how the SSE events translate to incremental text.
5. Build a full **tool-use round trip**: define a tool, detect the `tool_use` block, execute your function, send back `tool_result`, get the final answer.
6. Do the same with the **OpenAI SDK** to internalize the structural differences.
