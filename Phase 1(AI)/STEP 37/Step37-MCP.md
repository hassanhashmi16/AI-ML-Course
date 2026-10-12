# Step 37: MCP (Model Context Protocol)

> **Covers:** the three server primitives (tools, resources, prompts) and the client primitive (elicitation); the host/client/server split; the two transports (stdio, Streamable HTTP) and why the old SSE transport is legacy; connecting a real client end to end; writing your own server with the Python SDK; the security model that makes MCP different from a library call — tool poisoning, confused deputy, rug pulls — and OAuth authorization; plus registries, gateways, and when a plain tool schema beats MCP entirely.

---

## The Problem

You have a tool that works. Now three different apps want it: your CLI, your IDE, and a chat app you built. Today you write it three times, once per app, because each has its own tool-calling format and its own config file.

This is the problem USB-C solved for hardware. Before it, every device had its own plug; the *device* worked fine, but connecting it was the chore.

MCP is that plug for AI tools. Write the tool once as a **server**; any MCP-speaking app can use it. And Step 36's problem reappears in a nicer form: every tool you connect costs tokens in the model's context, forever — so "which servers do I connect?" is a budget question too (Step 35.1).

---

## Foundational Concepts

### It's RPC, not a library

MCP is a **wire protocol**: JSON-RPC 2.0 messages over some transport. A server is a *process* (or a URL) that answers requests. That is why it is language-agnostic — a Python client talks to a TypeScript server as easily as to another Python one.

Same universality idea as tool schemas (Step 32): one agreed format, so anything can speak to anything. But now the standardisation is across **apps and processes**, not just across models.

### Host, client, server

Three words that blur together, so get them straight:

| Term | What it is | Example |
|---|---|---|
| **Host** | the AI application you use | Command Code, VS Code, Claude Desktop |
| **Client** | the piece *inside the host* holding one connection | one object per connected server |
| **Server** | the program providing the capability | a Postgres server, a GitHub server |

**One host, one client per server.** Connect three servers and the host runs three clients, each with its own dedicated connection and lifecycle.

### Discovery, then use

Every MCP interaction runs the same way: the client asks what the server can do, then uses it.

```
client → server/discover   → supported versions, capabilities, identity
client → tools/list        → [{name, description, inputSchema}, ...]
client → tools/call        → { name: "weather_current", arguments: {...} }
```

Discovery is why a server can add a tool tomorrow and clients pick it up with no code change. It is also why **an MCP server is a trust boundary** — that `description` text goes straight into your model's context. Hold that thought for 37.6.

### Stateless by design

As of protocol version `2026-07-28`, MCP is **stateless**: every request carries its own protocol version and capabilities in a `_meta` field. There is no hidden session state to drift out of sync, which makes servers easy to scale horizontally and easy to reason about.

---

## 37.1 Tools, Resources, Prompts (and Elicitation)

**Motivate.** "Give the model a capability" is really three different things, and conflating them causes trouble.

**Define.** Servers expose **three** primitives:

| Primitive | What it is | Who decides to use it | Example |
|---|---|---|---|
| **Tools** | executable functions | **the model** | `query_database(sql)` |
| **Resources** | data the app can read into context | **the app / user** | the DB schema, a file |
| **Prompts** | reusable interaction templates | **the user** | a "review this PR" template |

The distinction that matters: **tools are model-controlled, resources are app-controlled.** A resource is not something the model decides to fetch — it is context *you* attach. Confusing the two is how people end up exposing a 2 MB log file as a "tool result".

Each primitive has `*/list` methods and, where it applies, `*/get` or `tools/call`. A single server routinely exposes all three: a database server might offer query tools, a schema *resource*, and a few-shot *prompt*.

**Clients expose one primitive back:**

- **Elicitation** (`elicitation/create`) — the server can ask the *user* for more input, or for confirmation before a destructive action. This is a server reaching through the host to the human, and it is how "are you sure?" is implemented at the protocol level.

**Knowing what's deprecated matters here**, because this changed recently:

- **Sampling** — servers requesting an LLM completion through the client — is **deprecated** as of `2026-07-28`. New servers should call a provider API directly. It was designed for model-independence; in practice it mostly obscured which model was running.
- **Logging** is deprecated too: write to `stderr`, or emit OpenTelemetry (Step 31).

**Rule of thumb.** Model decides → tool. You decide → resource. Human decides → prompt. If unsure, ask *who should be choosing*.

---

## 37.2 Server vs. Client Architecture

**Motivate.** You need to know which side of the wire you are writing, and what shape the other side expects.

**Define.** MCP has two layers, and mixing them up makes the docs confusing:

| Layer | What it defines |
|---|---|
| **Data layer** | JSON-RPC 2.0 messages: discovery, primitives, notifications |
| **Transport layer** | how those messages travel: stdio or Streamable HTTP, plus authorization |

The data layer is identical regardless of transport — that is the design win.

**Connection count is the practical part:**

| Transport | Typical shape |
|---|---|
| **stdio** (local process) | one server serves **one** client |
| **Streamable HTTP** (remote) | one server serves **many** clients |

A local stdio server launched by your IDE is private to your session. A hosted HTTP server is shared infrastructure — which is exactly why it is the one that needs authentication (37.6).

**Notifications** let a server push changes: `notifications/tools/list_changed`. They are **opt-in** (the client opens a `subscriptions/listen` stream with a filter) and explicitly **best-effort** — so a correct client still polls. Never build correctness on a notification arriving.

**Rule of thumb.** Local and single-user → stdio. Remote, shared, multi-tenant → Streamable HTTP with auth. Decide that first; the primitives are identical either way.

---

## 37.3 Transports: stdio vs. Streamable HTTP

**Motivate.** Same protocol, very different operational realities — and the older remote transport has been replaced.

**Define.**

| | **stdio** | **Streamable HTTP** |
|---|---|---|
| How it travels | the server's stdin/stdout | HTTP POST, optional SSE stream |
| Runs where | same machine, child process | anywhere, over the network |
| Lifetime | tied to the host process | independent, long-lived |
| Auth | the OS (file permissions, env) | bearer tokens, API keys, headers — **OAuth recommended** |
| Scale | one client each | many clients |
| Debugging | easy: it is a local command | needs a network-visible endpoint |

**The rename to know about:** the original remote transport was **HTTP + SSE**. It has been replaced by **Streamable HTTP**, which uses an ordinary POST and only upgrades to Server-Sent Events when it actually needs to stream. Follow an older tutorial and you will build the deprecated one.

**Show.** One server, two transports, and no change to the tool code:

```python
# stdio: the host launches this process and talks over its pipes
mcp.run(transport="stdio")

# http: the same server, listening on a port instead
mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)
```

**Rule of thumb.** Default to **stdio** — it needs no port, no TLS, and no auth story, because the OS already provides all three. Move to Streamable HTTP only when the server must outlive the host or serve several clients.

---

## 37.4 Connecting a Client to a Server

**Motivate.** This is the part you will actually do this week, so it should be two commands.

**Define.** In Command Code, MCP management is `cmd mcp ...`, with exactly two shapes:

```bash
# remote (HTTP)
cmd mcp add --transport http notion https://mcp.notion.com/mcp

# local (stdio, the default; `--` separates the name from the command)
cmd mcp add playwright -- npx -y @playwright/mcp@latest
```

Then verify, and authenticate if it needs it:

```bash
cmd mcp list            # all configured servers
cmd mcp get notion      # one server's details
cmd mcp auth notion     # OAuth -- opens a browser
/mcp                    # in-session menu: status, tool counts, connect/remove
```

**Where the config lives** — three scopes with a precedence order:

| Scope | File | Use for |
|---|---|---|
| `local` (**default**) | `~/.commandcode/projects/<slug>/mcp.json` | private, this project only |
| `project` | `.mcp.json` in the repo | **commit it** — shared with the team |
| `user` | `~/.commandcode/mcp.json` | private, every project |

Precedence is `local` → `project` → `user`. Secrets are handled for you: OAuth client secrets are stripped out of the committable `.mcp.json` and kept in `~/.commandcode/mcp-tokens.json`.

**What you get:** the server's tools appear alongside the built-in ones, named `mcp__<server>__<tool>` — so `mcp__notion__search_page` is unambiguous about where it came from.

**Rule of thumb.** `--scope project` for anything the team needs; leave it `local` if the server needs *your* credentials.

---

## 37.5 Writing Your Own MCP Server

**Motivate.** You have an internal API, a database, or a script the model should be able to call. Wrapping it should not be a project.

**Define.** The Python SDK's `FastMCP` turns ordinary functions into tools — **type hints and the docstring become the JSON Schema**.

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("peaks")

@mcp.tool()
def lookup_peak(name: str) -> dict:
    """Return height, range and first-ascent date for an eight-thousander.

    Args:
        name: the mountain's common name, e.g. "K2".
    """
    return PEAKS[name]      # schema + description come from the signature and docstring

@mcp.resource("peaks://list")
def peak_list() -> str:
    """The 14 peaks as text -- a RESOURCE, so the app decides to read it."""
    return "\n".join(PEAKS)

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

That is a complete, working server. Three things to notice:

1. **The docstring is the tool description** — which means it is *also* the text the model reads to decide. Write it for the model (Step 32), not for a human skimming source.
2. **`@mcp.resource` vs `@mcp.tool`** is the 37.1 distinction in decorator form.
3. **Test the server before wiring it into an app.** The **MCP Inspector** connects to a server and lets you call its tools by hand. Debugging a server *through* a host is miserable; debug it directly.

Connecting it afterwards is the same `cmd mcp add` from 37.4.

**Rule of thumb.** Wrap a **narrow** capability, not an escape hatch. `lookup_peak(name)` is a tool; `run_sql(query)` is a loaded gun — see below.

---

## 37.6 MCP Security: Tool Poisoning, Confused Deputy, OAuth

**Motivate.** This is what makes MCP *different* from calling a library, and it is the part most tutorials skip entirely.

**Define: the new trust boundary.** An MCP server controls **text that lands in your model's context**. A tool `description` is not documentation — the model reads it, and it can carry instructions. So installing a server is closer to installing a *dependency with write access to your prompt* than to adding a function.

**The attacks, named:**

| Attack | Mechanism | What you would see |
|---|---|---|
| **Tool poisoning** | instructions hidden in a tool's **description** — invisible in the UI, visible to the model | the agent does something you never asked for |
| **Indirect prompt injection** | hidden instructions inside **tool results** | the agent follows instructions that came from fetched *data* |
| **Confused deputy** | the attacker's server has no privileges, but *your agent does* — so it gets the agent to use them | a low-privilege server exfiltrates via a high-privilege one |
| **Rug pull** | a tool's definition **changes after you approved it** | behaviour differs from what you reviewed |
| **Tool shadowing** | a server defines a tool that impersonates another server's | you call the wrong one |

Two deserve an extra sentence:

- **Tool poisoning is invisible.** The description sits in a settings list you will never re-read, and is read by the model on every single turn. Invariant Labs documented this in 2025; OWASP now has a page for it.
- **Confused deputy is the subtle one**, and it is not really an MCP bug — it is a classic privilege problem. The fix is not "trust less"; it is **not giving one agent credentials for everything at once**.

**The authorization layer.** The spec recommends **OAuth for HTTP transports**, and Command Code implements **OAuth 2.0 Authorization Code with PKCE** — a browser login once, with tokens stored and refreshed automatically:

```bash
cmd mcp auth my-server           # browser flow; tokens stored, auto-refreshed
cmd mcp auth --status my-server  # is it authenticated?
cmd mcp auth --clear my-server   # revoke
```

**Defences that actually hold:**

- **Least privilege, per server.** Each server gets its own scoped credentials, not one god-token.
- **Review tool descriptions before installing** — and re-review on update. That is the rug-pull defence.
- **Require approval for destructive tools.** Command Code hides MCP tools entirely in plan mode, precisely because it *cannot verify* that a remote tool is read-only; hiding the schema beats letting the model find out the hard way.
- **Sandbox local servers**, and pin versions.
- **Keep credentials in the host's store**, not in a committed `.mcp.json` — which is why the client secret is stripped out.

**Rule of thumb.** Treat every MCP server as **untrusted code that writes to your prompt**. For each one ask: what could this be made to do, using the credentials *my agent* holds?

---

## 37.7 Registries, Gateways, and When a Plain Tool Schema Beats MCP

**Motivate.** "Just install a server" does not answer *where do I find one*, *how do I trust it*, or *do I even need this*.

**Define: registries** are discovery for servers. The official **MCP Registry** (`registry.modelcontextprotocol.io`) is a metadata repository backed by Anthropic, GitHub, Microsoft and others, with a REST API clients can query and **namespace ownership proven by DNS verification** — so `com.example/weather` can only be published by whoever controls `example.com`. That is the closest thing to a trust signal MCP has: *who* published it, verifiably.

**Define: gateways** are a single endpoint fronting many servers. Instead of your host holding ten connections, it holds one to a gateway that routes, authenticates centrally, and applies policy. They solve a real problem: **N servers means N trust decisions and N tool-schema loads** in your context.

**And the honest question — do you need MCP at all?**

| | Plain tool schema | MCP |
|---|---|---|
| Wiring | a function in your app | a process or URL, plus config |
| Reuse | that app only | **any MCP host** |
| Auth | your app's problem | OAuth in the protocol |
| Cost | you load only what you need | every connected server's tools load into context |
| Best for | *your* app's *own* tools | **someone else's** system |

The rule is the one from Step 36: **own the part that's the point, outsource the rest.** If the tool is yours and your app is the only consumer, a function is simpler and cheaper — MCP is a protocol, and protocols cost you a process, a config, and a trust decision.

Reach for MCP when the answer to "who else needs this?" is not "nobody". That is literally what it was designed for.

**Rule of thumb.** MCP for **foreign** systems and **shared** tools; a plain function for your own app's internals. And when you connect many servers, use a gateway plus **progressive tool discovery** rather than loading every tool up front — Step 35.1's budget again, and the difference between an agent that works and one drowning in its own tool list.

---

## Pitfalls

1. **Confusing tools with resources.** Tools are model-chosen; resources are app-chosen. Exposing data as a tool makes it something the model can decide to fetch.
2. **Building the deprecated SSE transport.** It is **Streamable HTTP** now; older tutorials will point you the wrong way.
3. **Using `sampling` in new code.** Deprecated as of `2026-07-28` — call the provider directly.
4. **Trusting tool descriptions.** They are model input, not documentation.
5. **One credential for every server.** That is the confused deputy, handed over voluntarily.
6. **Never re-reviewing a server after install.** The rug-pull defence *is* re-review.
7. **Assuming notifications are reliable.** Best-effort by spec; poll as well.
8. **Committing secrets to `.mcp.json`.** Use the project scope for config and leave secrets in the host's store.
9. **Connecting ten servers "just in case".** Every tool schema costs tokens on every request, forever.
10. **Reaching for MCP for your own app's internals.** A function was fine; you just added a process, a config, and a trust boundary.

---

## Quick Reference

| Goal | How |
|---|---|
| Add a remote server | `cmd mcp add --transport http <name> <url>` |
| Add a local server | `cmd mcp add <name> -- <command> [args...]` |
| Share with the team | `cmd mcp add --scope project ...` → commit `.mcp.json` |
| Authenticate (OAuth) | `cmd mcp auth <server>`, or `/mcp` in a session |
| Inspect | `cmd mcp list`, `cmd mcp get <name>`, `/mcp` |
| See provided tools | they appear as `mcp__<server>__<tool>` |
| Write a server | `FastMCP("name")` + `@mcp.tool()`; **docstring = description** |
| Debug a server directly | the **MCP Inspector** |
| Local transport | `mcp.run(transport="stdio")` |
| Remote transport | `mcp.run(transport="streamable-http", port=...)` |
| Which primitive? | model decides → tool; you decide → resource; user decides → prompt |
| Ask the user mid-call | **elicitation** (`elicitation/create`) |
| Discover capabilities | `server/discover`, `tools/list` |
| MCP or not? | foreign/shared system → MCP; your own app's tool → a function |

---

## Theory Summary

- **MCP is a wire protocol (JSON-RPC 2.0), not a library.** That is what makes it language- and app-agnostic.
- **Host, client, server.** One client per server, living inside the host.
- **Three server primitives, split by who decides.** Tools = the model, resources = the app, prompts = the user. Elicitation is the client primitive that lets a server ask a human.
- **Two transports: stdio and Streamable HTTP.** HTTP+SSE is legacy. The data layer is identical either way.
- **Discovery is what makes it dynamic** — and what puts foreign text into your model's context.
- **An MCP server is a trust boundary.** Tool descriptions are model input; tool results can carry injected instructions.
- **Design for the attacks.** Least privilege per server, re-review on update, approval for destructive tools.
- **Registries give discovery, DNS gives provenance, gateways give one endpoint instead of ten.**
- **MCP is for foreign and shared systems.** For your own app's internals a function is cheaper and safer.
- **Every connected server costs context, forever.** Same budget as everything else.

---

## Deliverable

**`Phase 1(AI)/STEP 37/step37-mcp/`**

A **working MCP server** exposing Project 2's own capabilities, plus a client-side check — so you go from "I read about MCP" to a server any host can point at.

- **`server.py`** — an MCP server for the eight-thousanders data, on `FastMCP`, demonstrating all three primitives deliberately:
  - **tool** — `lookup_peak(name)`, `list_peaks(above_meters=None)`: model-chosen, narrow, docstrings written *for the model*;
  - **resource** — `peaks://list`: the same data, but app-chosen, so 37.1's distinction is visible in one file;
  - **prompt** — a `compare_peaks` template, showing the user-controlled primitive;
  - runs on **stdio** by default with a `--http` flag, so 37.3 is one flag apart rather than two files;
  - reuses Project 2's `peaks.json` and its `lookup_peak` / `list_peaks` logic — because that is the point: the *same* capability, now reachable by any MCP host.
- **`inspect.py`** — a tiny client that spawns the server over stdio, calls `server/discover`, prints the discovered capabilities and tool schemas, then calls one tool. This makes 37.2's discovery flow concrete rather than theoretical, and it runs with **zero API quota** because no model is involved — MCP is just RPC.
- **`SECURITY.md`** — a five-line checklist from 37.6, applied to *this* server: what its credentials are, which tools are destructive, why its descriptions are safe to expose, and what a poisoned version would have to do to be dangerous.

**Design notes:** `inspect.py` is the deliberate teaching move. It removes the model from the loop and shows MCP for what it is: a protocol between two processes. Once you have seen `tools/list` output by hand, an agent "magically using a tool" stops being magic. And the security file is short on purpose — writing it for your *own* tiny server is what makes the threat model stick in a way that reading about tool poisoning never does.
