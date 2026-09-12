# Command Line Interface

The [LimaCharlie Python SDK](../6-developer-guide/sdks/python-sdk.md) ships a `limacharlie ai` command group that covers the full AI Sessions lifecycle from the terminal: creating sessions from an `ai_agent` Hive template with per-run overrides, listing and inspecting sessions, attaching to a live session over WebSocket, and terminating.

These commands are available in the `cli-v2` release line of the CLI and talk to the same endpoints documented on the [API Reference](api-reference.md) page. Authentication reuses your existing LimaCharlie credentials — no separate AI Sessions token is required.

!!! note
    The CLI is complementary to the [web console](user-sessions.md). Anything you can do from the console (other than file upload/download, which is not yet wired into the CLI) you can do from the CLI.

## Installation

```bash
pip install limacharlie
```

Then authenticate as described in the [CLI overview](../6-developer-guide/sdk-overview.md#authentication).

## Two session ownership models

The AI Sessions backend exposes two distinct kinds of session, each with its own creation command, lifecycle group, and WebSocket auth model. They are independent: a session created in one model is not visible from the other model's commands.

| | **Org-owned session** | **User-owned session** |
|---|---|---|
| Started by | `ai start-session --definition <hive-record>` (or a DR rule) | `ai chat [PROMPT]` |
| Owner | The organization (`OwnerOID`) | The authenticated user (`OwnerUID`) |
| Anthropic credential | `anthropic_secret` from the `ai_agent` Hive record | The user's stored credential, set up via [`ai auth claude`](#limacharlie-ai-auth-claude) |
| Lifecycle commands | [`ai session list/get/history/terminate`](#limacharlie-ai-session-list) | [`ai chats list/get/history/terminate`](#limacharlie-ai-chats) |
| `ai session attach` mode | Read-only by design — the org WS endpoint is the only one available, so `--interactive` auto-falls back to read-only | Owner-interactive — `--interactive` actually sends prompts |

Use **org sessions** for automation: scheduled runs, DR-rule triggers, ad-hoc invocations of an `ai_agent` Hive record. Use **user sessions** for an interactive Claude chat in your terminal that bills against your own Claude credential.

## `limacharlie ai session list`

List AI sessions for the current organization.

```bash
limacharlie ai session list
limacharlie ai session list --status running
limacharlie ai session list --status ended --limit 10
```

Options:

| Flag | Description |
|---|---|
| `--status` | Filter by status: `running`, `starting`, `ended`. |
| `--limit` | Maximum results per page (1 – 200, default 50). |
| `--cursor` | Pagination cursor from a previous response. |

The `initial_prompt` field is truncated in the list view. Use `ai session get --id <SESSION_ID> --full-prompt` to see the full prompt.

## `limacharlie ai session get`

Fetch a single session's metadata (status, model, token usage, cost, trigger info, end reason).

```bash
limacharlie ai session get --id <SESSION_ID>
limacharlie ai session get --id <SESSION_ID> --full-prompt
```

## `limacharlie ai session history`

Retrieve the full conversation log of a session (user prompts, assistant responses, tool calls, tool results).

```bash
limacharlie ai session history --id <SESSION_ID>
limacharlie ai session history --id <SESSION_ID> --raw
```

Internal system bootstrap messages (credential diagnostics, `claude_md_loaded`, MCP config debug, etc.) are filtered out by default — same set hidden from the live stream by [`ai session attach`](#default-noise-filter). Pass `--raw` to include them.

## `limacharlie ai session terminate`

Terminate a running session. Requires the `ai_agent.set` permission.

```bash
limacharlie ai session terminate --id <SESSION_ID>
```

## `limacharlie ai session attach`

Open a WebSocket to a running session and stream its messages live. With `--interactive` the terminal becomes a chat: stdin lines are sent to the agent as prompts and approval requests are surfaced as y/n prompts.

```bash
# Tail a running session (pretty output).
limacharlie ai session attach --id <SESSION_ID>

# Interactive chat with the agent.
limacharlie ai session attach --id <SESSION_ID> --interactive

# Read-only view of an org session you did not start.
limacharlie ai session attach --id <SESSION_ID> --read-only

# Raw JSON frames, one per line — pipe-friendly.
limacharlie ai session attach --id <SESSION_ID> --raw | jq .
```

### Flags

| Flag | Description |
|---|---|
| `--id` | **Required.** Session ID to attach to. |
| `--interactive`, `-i` | Send stdin lines as prompts; surface approval/question messages interactively. |
| `--read-only` | Use the org-scoped read-only WebSocket (`/v1/ws/org/sessions/{id}`). Requires `ai_agent.get` on the session's owning org. Send operations are blocked client-side. |
| `--no-history` | Don't render the history block on connect; just show new messages. |
| `--raw` | Print each WebSocket frame as a single JSON line instead of colour-coded formatting. |
| `--verbose`, `-v` | Show the full firehose: plumbing `system[subtype]` messages (`init_received`, `model_set`, `hook_started`, …), `session_status` pings, `usage_delta` frames, and full ISO timestamps instead of the default `HH:MM:SS`. See [Default noise filter](#default-noise-filter). |

### Endpoint selection and fallback

Two WebSocket endpoints exist on the AI Sessions service:

- `/v1/ws/sessions/{id}` — owner-interactive. The authenticated user must own the session; write messages (prompts, approvals, interrupts) are accepted.
- `/v1/ws/org/sessions/{id}` — org-scoped, read-only. Requires `ai_agent.get` on the session's owning org. No write messages accepted.

By default the CLI connects to the owner endpoint. If the server returns 403 (the session is owned by your organization rather than by you personally — for example any session created via `ai start-session`), the CLI transparently falls back to the org-scoped read-only endpoint and prints a notice. Pass `--read-only` to connect directly to the org endpoint and skip the 403 round trip.

!!! tip "When `--interactive` actually accepts your input"
    `ai session attach --interactive` only sends prompts when the owner endpoint accepts you. That happens for **user-owned** sessions (created via [`ai chat`](#limacharlie-ai-chat) or the web UI under your identity). For **org-owned** sessions (created via `ai start-session` and any DR-rule-triggered run), the org endpoint is the only path the backend exposes, and it is read-only by design — the CLI auto-falls back and prints a notice. Use [`ai chat`](#limacharlie-ai-chat) when you want a real terminal chat.

### Interactive controls

When `--interactive` is set:

- **Typed line + Enter** → sent as a `prompt` message.
- `/interrupt` → sends a WebSocket `interrupt` message, cancelling the agent's current turn.
- `/quit` → closes the WebSocket and exits.
- **Ctrl+C** → clean disconnect.
- **Tool approval requests** → interactive `Approve? [y/n/session]` prompt. Choosing `session` auto-approves matching invocations for the rest of the session.
- **`ask_user_question` messages** → if the question has options, you get a numbered menu; otherwise a free-text prompt.

### Output format

Notices (connection status, read-only fallback, errors) go to **stderr**; session messages go to **stdout**. When stdout is a TTY, messages are colour-coded by type:

| Type | Colour | Form |
|---|---|---|
| `user` | green bold | `user:` + indented text |
| `assistant` | cyan bold | `assistant:` + indented text |
| `tool_use` | yellow | `tool_use NAME (id): {input}` |
| `tool_result` | dim yellow | `tool_result (id):` + content (truncated at 4 KB) |
| `system` | dim | `system[subtype]: ...` |
| `result` | blue | `result: <summary>` |
| `error` | red bold (stderr) | `error [code]: message` |
| `session_end` | red bold | `session ended: <reason>` — stream then exits |
| `tool_approval_request` (non-interactive) | yellow bold | `approval requested for NAME: {input}` |
| `ask_user_question` (non-interactive) | magenta bold | `question: <text>` |

Timestamps are abbreviated to `HH:MM:SS` by default; pass `--verbose` to preserve the full ISO-8601 value the server sent.

With `--raw` each frame is a single JSON object per line, making it easy to post-process:

```bash
limacharlie ai session attach --id $SID --raw \
  | jq -c 'select(.type=="tool_use") | .payload'
```

### Default noise filter

The AI Sessions runner emits a number of housekeeping frames at the start of every session and between tool calls. Without filtering they overwhelm the live stream — the interesting assistant turns get buried between dozens of `system[credential_diagnostics]:` / `system[model_set]:` / `session_status: {...}` / empty `assistant:` headers. The pretty renderer therefore hides the following frames by default:

- **Plumbing message types** — `session_status` (startup/status pings), `usage_delta` (per-API-call token tallies), `sdk_session_id`.
- **Plumbing `system` subtypes** — every bootstrap event emitted by the bridge (`credential_diagnostics`, `init_received`, `claude_md_loaded`, `mcp_config_debug`, `mcp_servers_set`, `model_set`, `max_turns_set`, `max_budget_set`, `task_budget_set`, `one_shot_mode_set`, `permission_mode_set`, `tools_configured`, `system_prompt_set`, `oid_added_to_system_prompt`, `ttl_added_to_system_prompt`, `plugins_resolved`, `autoinit_loaded`, `autoinit_error`, `resuming_sdk_session`, `user_mcp_servers_loaded`, `mcp_servers_loaded`, `session_patterns_loaded`, `unknown_plugin`, `claude_md_error`, …) plus Claude SDK hook events (`hook_started`, `hook_response`, `hook_matched`).
- **Empty frames** — `assistant` turns that carry only a `tool_use` block (the accompanying `tool_use` message already renders the call), `user` frames that wrap a `tool_result` (same — the `tool_result` message already renders the output), and `result` pings with no human-readable summary.

This filter applies to both the initial history block and the live stream. Pass `--verbose` / `-v` to disable it and see every frame; `--raw` bypasses the renderer entirely and prints untouched JSON. The same noise set is used by [`ai session history`](#limacharlie-ai-session-history) and [`ai chats history`](#limacharlie-ai-chats); `--raw` on those commands includes the filtered frames.

## `limacharlie ai start-session`

Start a new AI session by reusing an `ai_agent` Hive record as a **template** and overriding individual fields for this run.

The Hive record named by `--definition` supplies the default session configuration: prompt, model, credentials (as `hive://secret/` references), tool permissions, MCP servers, environment, budgets, and so on. Any `--option` flag listed below replaces the matching field from the template; everything else is used as-is.

This lets you reuse one `ai_agent` definition as a starting point and vary only the parts you need per-run — swap the prompt, cap the budget, change the model, add an environment variable, restrict tools — without maintaining a copy of the definition per variant.

### Override semantics

- **Scalars and lists** — replace the template value when the flag is passed. Omitted flags leave the template intact.
- **Environment** — merges the template's `environment` with `--env KEY=VALUE` flags. On key collision the CLI value wins.
- **MCP servers** — always come from the template (not overridable from the CLI).
- **`hive://secret/<name>` references** — valid in any override value, not just in the template. They are resolved before the request is sent, so secrets never appear in `argv`.

### Examples

Start a session from a definition with no overrides:

```bash
limacharlie ai start-session --definition my-security-analyst
```

Reuse the template but swap the prompt and tag the session for auditing:

```bash
limacharlie ai start-session --definition my-agent \
  --prompt "Investigate this specific alert" \
  --name "Alert investigation"
```

Cap budget and pick a specific model on top of the template:

```bash
limacharlie ai start-session --definition my-agent \
  --model claude-sonnet-4-6 \
  --max-budget-usd 2.50
```

Add an env var (merged with the template's environment):

```bash
limacharlie ai start-session --definition my-agent \
  --env SLACK_WEBHOOK=hive://secret/slack-webhook
```

Restrict tools and force `one_shot` off for this run only:

```bash
limacharlie ai start-session --definition my-agent \
  --allowed-tools Read,Grep --denied-tools Bash,Write --no-one-shot
```

Pipe the result into `jq` to grab the new session ID and attach to it (read-only — these are org-owned sessions; for an interactive terminal chat use [`ai chat`](#limacharlie-ai-chat) instead):

```bash
SID=$(limacharlie ai start-session --definition my-agent \
        --output json | jq -r '.session_id')
limacharlie ai session attach --id "$SID"
```

### Flags

#### Session metadata

| Flag | Description |
|---|---|
| `--definition` | **Required.** Name of the `ai_agent` Hive record to use as template. |
| `--prompt` | Replace the prompt from the definition. |
| `--name` | Replace the session name. |
| `--idempotent-key` | Deduplication key — if an active session for this key exists, it is returned instead of creating a new one. |
| `--data` | JSON dictionary appended to the prompt as YAML event data (for standalone runs that have no D&R event). |

**Profile fields** — scalars and lists replace the template value when provided:

| Flag | Maps to `ProfileContent` field |
|---|---|
| `--model` | `model` |
| `--max-turns` | `max_turns` |
| `--max-budget-usd` | `max_budget_usd` |
| `--task-budget-tokens` | `task_budget_tokens` |
| `--ttl-seconds` | `ttl_seconds` |
| `--one-shot` / `--no-one-shot` | `one_shot` |
| `--permission-mode` | `permission_mode` (`acceptEdits`, `plan`, `bypassPermissions`) |
| `--allowed-tools` | `allowed_tools` (comma-separated) |
| `--denied-tools` | `denied_tools` (comma-separated) |
| `--plugin` (repeatable) | `plugins` |

**Environment** — merged with the template's environment (override wins on key collisions):

| Flag | Description |
|---|---|
| `--env KEY=VALUE` (repeatable) | Environment variable for the session. `VALUE` may be a literal or `hive://secret/<name>`. |

**Credentials** — replace the corresponding `*_secret` field on the template:

| Flag | Description |
|---|---|
| `--anthropic-key` | Literal Anthropic API key or `hive://secret/<name>`. |
| `--provider` | Replace the template's AI provider (`anthropic`, `openai`, `google`, `openrouter`). The server owns the list of accepted values. |
| `--credential KEY=VALUE` (repeatable) | Credential entry for the chosen provider (for example `api_key=hive://secret/my-key`). Replaces the template's credentials. `VALUE` may be a literal or `hive://secret/<name>`. |
| `--lc-api-key` | Literal LimaCharlie API key or `hive://secret/<name>`. |
| `--lc-uid` | Literal User ID or `hive://secret/<name>`. |

### Output

The command prints the server's session-creation response. With `--output json`:

```json
{
  "session_id": "abc-123",
  "status": "starting",
  "created_at": "2026-04-17T18:05:02Z"
}
```

Use the returned `session_id` with `ai session attach`, `ai session get`, or `ai session terminate`.

## `limacharlie ai auth claude`

Manage the per-user Anthropic credential that backs [`ai chat`](#limacharlie-ai-chat). Org-owned sessions started via `ai start-session` ignore these and use the `anthropic_secret` field from the `ai_agent` Hive record instead — there is no need to run `auth claude` for those.

Credentials for other AI providers (OpenAI, Google Gemini, OpenRouter) are managed in the web application under **User Settings → AI Terminal** or via the [credentials API](providers.md#via-the-api).

The credential is stored server-side and bound to the authenticated UID. It can be either a Claude Max OAuth token (browser flow) or a raw Anthropic API key.

```bash
limacharlie ai auth claude status
limacharlie ai auth claude login
limacharlie ai auth claude set-key --key "$ANTHROPIC_API_KEY"
limacharlie ai auth claude set-key --key hive://secret/anthropic-key
echo "$ANTHROPIC_API_KEY" | limacharlie ai auth claude set-key --key-from-stdin
limacharlie ai auth claude logout
```

### Subcommands

| Command | Description |
|---|---|
| `status` | Returns `has_credentials`, `credential_type` (`oauth_token` or `apikey`), and `created_at`. |
| `login` | Runs the browser OAuth flow: starts a server-side OAuth session, polls until Claude returns the URL, prints it to the terminal, and prompts for the authorization code. |
| `set-key` | Stores a raw Anthropic API key. Accepts `--key <VALUE>` (literal or `hive://secret/<name>`) or `--key-from-stdin` for piping. The two are mutually exclusive. |
| `logout` | Deletes the stored credential. |

Errors:

- *"No Claude credentials registered for this user"* — `ai chat` raises this when `status.has_credentials` is `false`. Run `auth claude login` or `auth claude set-key` and retry.
- The browser OAuth flow has a 5-minute server-side TTL; if you take longer than that to paste the code back, restart with `auth claude login`.

## `limacharlie ai chat`

Start a fresh **user-owned** AI session and drop into an interactive WebSocket chat. The session is owned by the authenticated user, billed against the credential stored via [`ai auth claude`](#limacharlie-ai-auth-claude), and attaches over the owner endpoint so prompts can flow both directions.

The opening prompt comes from the optional `PROMPT` argument; further turns come from interactive stdin once the session is attached. Stdin is **not** consumed as the opening prompt — supply that via the argument so multi-line piping is not silently glued into one message.

```bash
# Start a chat with an opening prompt.
limacharlie ai chat "What sensors pinged in the last hour?"

# Start a chat with overrides — caps and a specific model.
limacharlie ai chat --model claude-sonnet-4-6 --max-budget-usd 0.50

# Start a chat with no opening prompt; first message comes from stdin in the
# interactive loop that runs after attach.
limacharlie ai chat
```

`ai chat` runs three steps before handing the terminal to the chat loop:

1. Calls [`ai auth claude status`](#limacharlie-ai-auth-claude) and exits non-zero with instructions if no credential is stored.
2. Calls `POST /v1/register` (idempotent — safe to run on every invocation).
3. Calls `POST /v1/sessions` with the override flags below, then attaches via [`ai session attach`](#limacharlie-ai-session-attach) in interactive mode.

### Flags

| Flag | Description |
|---|---|
| *(positional)* `PROMPT` | Optional opening prompt sent as the first message after attach. |
| `--name` | Session name (display only). |
| `--model` | Anthropic model (e.g. `claude-sonnet-4-6`). |
| `--max-turns` | Maximum agent turns before auto-stop. |
| `--max-budget-usd` | Hard USD cost cap for the session. |
| `--task-budget-tokens` | Per-task token budget. |
| `--permission-mode` | `acceptEdits`, `plan`, or `bypassPermissions`. |
| `--allowed-tools` | Comma-separated list of allowed tool names. |
| `--denied-tools` | Comma-separated list of denied tool names. |
| `--plugin` (repeatable) | Plugin names to enable. |
| `--idempotent-key` | Deduplication key for session creation. |
| `--verbose`, `-v` | Disable the [default noise filter](#default-noise-filter) and use full ISO timestamps — same flag as on `ai session attach`. |

The flag set is intentionally narrower than [`ai start-session`](#limacharlie-ai-start-session): there is no `--definition` (chat sessions are blank, not template-derived), no environment merge, and no credential-override flags (`--anthropic-key` / `--lc-api-key` / `--lc-uid`) since the session uses the per-user credential set via `auth claude` and runs without an attached LC service identity.

### Interactive controls

Identical to [`ai session attach --interactive`](#interactive-controls): stdin lines become prompts, `/interrupt` cancels the agent's current turn, `/quit` detaches, Ctrl+C disconnects. Tool approval requests and `ask_user_question` messages are surfaced as in-line prompts.

### Re-attaching to an in-progress chat

`ai chat` always creates a new session. To reconnect to one you already started, use [`ai session attach --interactive --id <SESSION_ID>`](#limacharlie-ai-session-attach) — it works against user-owned sessions just like the in-process attach loop, since you own them and the owner endpoint accepts you.

## `limacharlie ai chats`

Lifecycle management for user-owned sessions — the counterpart to the [`ai session`](#limacharlie-ai-session-list) group. Same subcommand shape (`list`, `get`, `history`, `terminate`), routed to the user-scoped REST endpoints (`/v1/sessions/*`) instead of the org-scoped ones (`/v1/org/sessions/*`).

```bash
limacharlie ai chats list
limacharlie ai chats list --status running
limacharlie ai chats get --id <SESSION_ID>
limacharlie ai chats get --id <SESSION_ID> --full-prompt
limacharlie ai chats history --id <SESSION_ID>
limacharlie ai chats history --id <SESSION_ID> --raw
limacharlie ai chats terminate --id <SESSION_ID>
```

| Subcommand | Org equivalent | Notes |
|---|---|---|
| `chats list` | `session list` | Lists sessions where you are the owning UID. Same `--status`, `--limit`, `--cursor` flags. |
| `chats get` | `session get` | Same `--full-prompt` toggle. |
| `chats history` | `session history` | Same internal-system-message filter; same `--raw` to disable it. |
| `chats terminate` | `session terminate` | Calls `DELETE /v1/sessions/{id}` (user-scoped). |

Sessions you create with `ai chat` will appear in `chats list`. Sessions you create with `ai start-session` (or that DR rules trigger) will appear in `session list`. The two sets do not overlap; a `chats get --id <org-session-id>` returns "not found" rather than the org session, and vice versa.

## Related pages

- [User Sessions](user-sessions.md) — concepts, session states, profiles, the web UI.
- [D&R-Driven Sessions](dr-sessions.md) — triggering the same `ai_agent` records automatically from Detection & Response rules.
- [Tool Permissions & Profiles](tool-permissions.md) — reference for `--allowed-tools`, `--denied-tools`, and `--permission-mode`.
- [API Reference](api-reference.md) — the REST and WebSocket endpoints the CLI wraps.
