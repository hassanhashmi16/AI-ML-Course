"""The model call — the one place the agent talks to Gemini.

Everything about *talking to the model* lives here, and nothing about *driving
the loop*: this module builds the request, sends it, and returns a parsed reply.
It does not mutate state and it does not execute tools. That boundary is
deliberate — `loop.py` is the only file that decides what happens next, so the
control flow stays readable in one place.

Three jobs:

1. **Translate** the normalized transcript in `state["messages"]` into the SDK's
   content types. Note the trap documented in `_to_contents`: Gemini accepts only
   `user` and `model` roles, so a tool *result* is sent back as a **user** turn
   carrying a `function_response` part.
2. **Attach the tool menu.** `get_schemas()` from the registry becomes the
   request's `tools=[...]` — this is the moment the model learns what it can do.
3. **Parse the reply** into something the loop can act on: either a tool call or
   final text, plus the token count for the run's budget.

The system prompt is also here, because it is part of "how we talk to the
model" — it defines *what the agent is*. Memory, by contrast, is per-run
context, so it arrives as a normal user message instead (Step 10).
"""
from __future__ import annotations

import base64
from typing import TypedDict

from google import genai
from google.genai import types

from agent.state import AgentState, Message
from config import GEMINI_API_KEY, GEN_MODEL
from tools.registry import get_schemas

SYSTEM_PROMPT = """You are a research assistant. You research one topic on the \
open web and produce a single cited briefing document.

Work in this order:
1. Plan: decide what you need to find out. If the topic is broad, break it into a \
few specific questions and answer them one at a time.
2. Search: use web_search to find candidate pages. Be specific; add a year for \
anything time-sensitive.
3. Read: use fetch_page on the most promising result. A snippet is not evidence — \
read the page before relying on anything it says.
4. Record: after reading a page that answered part of the question, call save_note \
with a one-sentence fact and the URL it came from. Save notes as you go; do not \
batch them at the end.
5. Finish: once your notes cover the topic, call write_brief. That ends the run.

Rules:
- Call one tool per turn, and wait for its result before deciding the next step.
- Never state a fact you did not read on a page. If a page fails to load, choose \
another result instead of retrying it.
- Do not fetch the same URL twice.
- Every claim in the brief must trace back to a note you saved.
- If the conversation says what you already know from earlier sessions, you may \
build on it — but prefer fresh sources for anything time-sensitive.
"""


class ModelReply(TypedDict, total=False):
    """A parsed model turn: text, a tool call, or (rarely) both, plus token counts."""
    text: str
    tool_name: str
    tool_args: dict
    # Totals drive the budget; the split exists for tracing, where the GenAI
    # convention wants input and output counted separately (`gen_ai.usage.*`).
    tokens: int
    input_tokens: int
    output_tokens: int
    # Base64 of the SDK's `bytes` signature. Base64 rather than raw bytes so the
    # value survives JSON when the loop puts it into the checkpoint.
    thought_signature: str


# The client is created on first use, not at import. Importing this module
# should never require an API key — tests and tooling can import it freely —
# and a missing key should fail with a clear message at the moment of use.
_client: genai.Client | None = None


def _client_instance() -> genai.Client:
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Copy .env.example to .env and paste your key in."
            )
        _client = genai.Client(
            api_key=GEMINI_API_KEY,
            http_options=types.HttpOptions(
                # Retry transient server errors. Hosted models return 503
                # ("currently experiencing high demand") intermittently — the
                # same request can fail and then succeed seconds later. Without
                # backoff, one unlucky moment kills a run that has already spent
                # tokens; with it, the run rides through. 429 is included
                # because rate limits are the same kind of "not now" signal.
                retry_options=types.HttpRetryOptions(
                    attempts=5,
                    initial_delay=2.0,   # first retry after 2s
                    max_delay=30.0,      # never wait longer than 30s between tries
                    http_status_codes=[429, 500, 502, 503, 504],
                )
            ),
        )
    return _client


def call_model(state: AgentState) -> ModelReply:
    """Send the transcript so far, return the model's next move.

    Read-only with respect to `state`: the loop owns all mutation, so there is
    exactly one place where the transcript changes.
    """
    response = _client_instance().models.generate_content(
        model=GEN_MODEL,
        contents=_to_contents(state["messages"]),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=_tool_declarations(),
            # Low temperature: this is extraction and synthesis, not creative
            # writing. Determinism is a feature here.
            temperature=0.3,
        ),
    )
    return _parse(response)


def _tool_declarations() -> list[types.Tool]:
    """Turn registry schemas into the SDK's tool declarations.

    We pass `parameters_json_schema` (a plain JSON-schema dict) rather than
    building `types.Schema` objects by hand — the registry already speaks
    JSON schema, which is the same format every model provider expects.
    """
    declarations = [
        types.FunctionDeclaration(
            name=spec["name"],
            description=spec["description"],
            parameters_json_schema=spec["parameters"],
        )
        for spec in get_schemas()
    ]
    # No tools registered -> an empty list, which is the SDK's "no tools" case.
    return [types.Tool(function_declarations=declarations)] if declarations else []


def _to_contents(messages: list[Message]) -> list[types.Content]:
    """Convert our normalized transcript into the SDK's content list.

    The one non-obvious mapping: Gemini's `Content.role` accepts only "user" and
    "model". A tool result therefore goes back as a **user** turn carrying a
    `function_response` part — not as a "tool" role, which the API rejects. Our
    state keeps the clearer "tool" role; the translation happens here, at the
    boundary, which is what keeps state readable.
    """
    contents: list[types.Content] = []

    for message in messages:
        role = message.get("role", "user")

        if role == "tool":
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_function_response(
                            # The response must be named after the call it answers,
                            # so the model can pair result with request.
                            name=message.get("tool_name", ""),
                            # Responses must be an object, so the string result is
                            # wrapped under "result".
                            response={"result": message.get("tool_result", "")},
                        )
                    ],
                )
            )
        elif role == "model" and message.get("tool_name"):
            # The replayed call must carry the signature Gemini returned with it
            # (`thought_signature`), or the API rejects the whole request with
            # 400 INVALID_ARGUMENT. It is opaque — we never read it, only hand
            # it back — and it arrives base64-encoded because state is JSON.
            signature = message.get("thought_signature") or ""
            contents.append(
                types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                name=message["tool_name"],
                                args=message.get("tool_args") or {},
                            ),
                            thought_signature=base64.b64decode(signature) if signature else None,
                        )
                    ],
                )
            )
        else:
            text = message.get("text", "")
            if not text:
                continue  # the API rejects empty parts; skip rather than send ""
            # Anything that isn't a tool exchange is plain text. "system" never
            # appears here: the system prompt travels in the request config.
            contents.append(
                types.Content(role=role, parts=[types.Part.from_text(text=text)])
            )

    return contents


def _parse(response: types.GenerateContentResponse) -> ModelReply:
    """Extract the first tool call, or the text, from the response.

    The caller takes the first tool call (`tool_calls`: list[dict]) and appends
    any text alongside it. The loop processes one tool per turn, which the
    system prompt asks for; a multi-call response would have its extra calls
    dropped, and the model would simply re-request them.
    """
    usage = getattr(response, "usage_metadata", None)
    tokens = (usage.total_token_count or 0) if usage else 0
    input_tokens = (usage.prompt_token_count or 0) if usage else 0
    output_tokens = (usage.candidates_token_count or 0) if usage else 0

    texts: list[str] = []
    for candidate in response.candidates or []:
        for part in candidate.content.parts or []:
            if getattr(part, "function_call", None):
                reply = ModelReply(
                    text="\n".join(texts).strip(),
                    tool_name=part.function_call.name or "",
                    tool_args=dict(part.function_call.args or {}),
                    tokens=tokens,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                signature = getattr(part, "thought_signature", None)
                if signature:
                    # bytes -> base64 str, so the loop can put it in state and
                    # the checkpoint can serialize it.
                    reply["thought_signature"] = base64.b64encode(signature).decode("ascii")
                return reply
            text = getattr(part, "text", None)
            if text:
                texts.append(text)

    return ModelReply(
        text="\n".join(texts).strip(),
        tokens=tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
