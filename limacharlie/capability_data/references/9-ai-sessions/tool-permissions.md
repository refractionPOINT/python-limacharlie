# Tool Permissions & Profiles

Every AI Session runs a Claude Agent SDK process inside a managed sandbox. What that agent is actually allowed to do — which built-in Claude Code tools it can call, which shell commands it can run, which MCP servers it can reach — is controlled by three fields that appear in both **user Profiles** and **`ai_agent` Hive records**:

- `allowed_tools`
- `denied_tools`
- `permission_mode`

These three settings map directly to the corresponding options on `ClaudeAgentOptions` in the Claude Agent SDK, so the matching semantics are exactly those documented in the upstream [Claude Code permissions reference](https://code.claude.com/docs/en/permissions). This page explains how LimaCharlie surfaces them, the full tool-name grammar, and how the bridge evaluates patterns at tool-call time.

## Where these fields live

The same three fields show up in every place an AI Session can be configured:

| Location | Who owns it | Used by |
|---|---|---|
| **User Profile** (`POST /v1/profiles`) | The authenticated LimaCharlie user | [User Sessions](user-sessions.md) created via the web UI or the [CLI](cli.md) `ai chat`. |
| **`ai_agent` Hive record** | The organization | [D&R-driven sessions](dr-sessions.md) and CLI `ai start-session --definition <name>` runs. |
| **Inline `profile:` block** in a D&R `start ai agent` action | The organization | One-off overrides inside a specific D&R rule. |
| **Per-session `allowed_tools` / `denied_tools`** in `POST /v1/sessions` | The authenticated user | Per-session override on top of the chosen Profile. |

The field names and semantics are identical across all four surfaces — a `denied_tools: [Write]` rule means the same thing whether it sits in a user's default Profile or in an `ai_agent` record triggered by a detection.

## Tool-name grammar

Entries in `allowed_tools` and `denied_tools` are **tool-name patterns**, not free-form strings. Three shapes are recognised.

### 1. Bare built-in tool name

A bare identifier matches the entire Claude Code tool of that name. Common built-ins are:

| Name | What it does |
|---|---|
| `Read` | Read a file from the session workspace. |
| `Write` | Create or overwrite a file. |
| `Edit` | Apply a targeted edit to an existing file. |
| `Bash` | Run a shell command. |
| `Grep` | Search file contents. |
| `Glob` | Match files by pattern. |
| `WebFetch` | Fetch an HTTP(S) URL. |
| `WebSearch` | Run a web search. |
| `TodoWrite` | Update the in-session task list. |
| `Task` | Spawn a subagent. |
| `AskUserQuestion` | Ask the human-in-the-loop a structured question. In interactive sessions the question is surfaced to the attached client (browser chat UI or `ai session attach --interactive`); `one_shot` / unattended sessions time out on these after five minutes. |

!!! note
    The authoritative list of built-in tools is the one published by the Claude Code CLI — LimaCharlie does not add or remove tools from that set. Bare names are case-sensitive.

### 2. Scoped Bash pattern — `Bash(prefix:*)`

The `Bash` tool accepts a scoping specifier that restricts which commands are covered. Only the `prefix:*` form is recognised, mirroring the official Claude Code CLI syntax:

```text
Bash(git:*)            # any command starting with "git "
Bash(npm install:*)    # any command starting with "npm install "
Bash(kubectl get:*)    # read-only kubectl verbs
```

**Common pre-processing.** Whether a pattern lives in `allowed_tools` or in `denied_tools`, it is evaluated by LimaCharlie's hardened matcher (not by the upstream Claude Code literal-prefix one). Before any matching happens the bridge normalises every Bash command the same way:

- The command is split on shell stage operators (`|`, `||`, `&`, `&&`, `;`, `|&`) and on real newlines.
- Process wrappers (`timeout`, `time`, `nice`, `nohup`, `stdbuf`, bare `xargs`) and leading `VAR=value` env assignments are stripped iteratively from the front of each stage, so `nohup timeout 30 DEBUG=1 npm test` reduces to `npm test` before matching.
- Redirection operators (`>`, `>>`, `<`, `>&`, `&>`, fd-duplications) stay attached to their command — they are **not** stage separators.
- Matching is a literal prefix on the stripped stage: either the stage equals the prefix exactly or it starts with `prefix + " "`. There is no flag-value allowlist and no alias resolution.

**Allow semantics.** For an `allowed_tools` match to fire, **every** pipeline stage must be covered by some allow pattern. `Bash(git:*)` alone does **not** approve `git status && rm -rf /` — the `rm -rf /` stage is uncovered, so the command falls through to `permission_mode`.

**Deny semantics.** For a `denied_tools` match to fire, **any** pipeline stage matching **any** deny pattern is enough to block the whole call. `Bash(rm:*)` in `denied_tools` catches both `rm -rf /` and the mixed-case `ls && rm -rf /` — deny is the mirror of allow, so the two sides can't be played against each other by splicing wrappers and compound operators.

**Dangerous constructs fall through to `permission_mode`.** Command substitution, process substitution, backticks, and subshell/brace grouping (`` ` ``, `$(...)`, `<(...)`, `>(...)`, `(...)`, `{...}`) smuggle commands past both sides of the matcher. Neither allow nor deny fires automatically on a stage that contains them — the call takes the `permission_mode` fallback path instead, which for interactive sessions means a re-prompt. In particular, `cat $(rm -rf /)` is **not** auto-approved by `Bash(cat:*)`, and is **not** auto-denied by `Bash(rm:*)` either; it prompts.

**Bare tool name.** A bare `Bash` entry (no `(prefix:*)` specifier) means "every Bash invocation" — in `allowed_tools` it short-circuits to auto-approve all shell commands, in `denied_tools` it blocks all of them. The same applies to every other tool name: a bare `Read` or `WebFetch` matches every invocation of that tool.

**Deny wins.** When a call matches both lists, deny is checked first and the call is blocked.

**Shared with session-scoped approvals.** The interactive `session` answer in the approval prompt seeds patterns into the same allow-pattern set, so everything above applies identically to those runtime-added rules. Autonomous org-owned sessions and interactive user sessions share a single matcher implementation.

### 3. MCP tool pattern

MCP server tools are exposed to Claude under a mangled name of the form `mcp__<server_name>__<tool_name>`. You can deny or allow them with either the full name or a scoped pattern.

```yaml
# Allow every tool exposed by the VirusTotal MCP server
allowed_tools:
  - mcp__virustotal

# Deny one specific tool from the VirusTotal MCP server
denied_tools:
  - mcp__virustotal__upload_file
```

The `<server_name>` segment is whatever the MCP server registers itself as when the session starts — the same identifier that appears as the key in the `mcp_servers` map of the Profile or `ai_agent` record. Use that exact name in your pattern.

## `allowed_tools` vs `denied_tools`

Both lists are seeded into the bridge's own pattern sets at session start and evaluated by the same hardened matcher described above. For every tool call:

1. **Deny check first.** If any `denied_tools` pattern matches under the deny semantics, the call is blocked and Claude receives a deny result. Deny always wins.
2. **Allow check second.** Otherwise, if the call is fully covered by an `allowed_tools` pattern under the allow semantics, it is auto-approved without a prompt.
3. **Fallback on no match.** If neither list matches, `permission_mode` decides what happens: `acceptEdits` auto-approves file-edit tools and prompts the user for everything else, `plan` keeps the session read-only, and `bypassPermissions` auto-approves the call.
4. **Both lists empty.** Nothing is pre-authorised and nothing is pre-blocked; every tool call falls through to `permission_mode`.

> A practical mental model: `allowed_tools` is the positive intent ("these are the things this agent should be able to do without asking"), `denied_tools` is the backstop ("even if a looser allow rule would cover it, never let the agent do this"). For unattended D&R-driven agents, a tight `allowed_tools` plus `permission_mode: bypassPermissions` replaces the interactive approval flow entirely.

## `permission_mode`

`permission_mode` controls what happens **when a tool call is not auto-approved by the lists above**. Three values are valid:

| Value | Behaviour |
|---|---|
| `acceptEdits` (default) | File-editing tools (`Write`, `Edit`, `NotebookEdit`, `MultiEdit`) are auto-approved; every other tool call triggers an approval prompt. Best for human-in-the-loop user sessions. |
| `plan` | Claude is kept in plan-only mode: it can read and reason but cannot execute any mutating tool without explicit approval. Useful for review/preview flows. |
| `bypassPermissions` | All tool calls are auto-approved (subject to `denied_tools` still taking effect). Required for unattended D&R-driven agents — without it, tool calls with no user to answer the prompt will time out after 5 minutes and the session will fail. |

The runner defaults `permission_mode` to `acceptEdits` when the field is omitted. For D&R agents that need to execute tools without a human, explicitly set `permission_mode: bypassPermissions` in the `ai_agent` record or the inline profile.

## Session-scoped approvals (interactive sessions)

In user sessions that go through the approval prompt, the operator can answer `session` instead of `y` or `n`. That choice stores a **session-scoped pattern** derived from the actual tool call — typically a `Bash(<prefix>:*)` for shell commands, or the plain tool name for everything else — and auto-approves future matching calls for the rest of the session without asking again.

Session-scoped patterns share a single pattern store with the Profile-supplied `allowed_tools`, so they share the hardened matcher and all its guarantees. These patterns are ephemeral: they vanish when the session ends and are never promoted into the Profile automatically — to persist a session's configuration, snapshot it with `POST /v1/sessions/{sessionId}/capture-profile` (see the [capture-profile endpoint](api-reference.md#profiles)).

## Defaults shipped to new users

The first time a user registers for AI Sessions, two profiles are provisioned automatically:

- **Default** — a read-only safe baseline. `permission_mode: acceptEdits`, no `denied_tools`, and `allowed_tools` limited to:

    ```text
    Read
    Bash(cat:*) Bash(head:*) Bash(tail:*) Bash(less:*)
    Bash(grep:*) Bash(sed:*) Bash(awk:*) Bash(jq:*)
    Bash(ls:*)  Bash(find:*) Bash(wc:*)
    ```

- **Full Permissions** — `permission_mode: bypassPermissions`, both lists empty. Lets Claude use any tool without prompting; use only when you're comfortable granting that blast radius.

The Default profile is marked `is_default: true` and is what the web UI starts with unless the user picks another one. The Default profile cannot be deleted; you can edit it, mark another profile as default, or create additional profiles up to the 10-per-user limit.

## Examples

### Read-only investigation profile

Good baseline for interactive triage — Claude can inspect workspace files and common read-only shell utilities, but never writes or edits, and any non-read tool still requires an approval prompt.

```json
{
  "name": "Investigation (read-only)",
  "permission_mode": "acceptEdits",
  "allowed_tools": [
    "Read", "Grep", "Glob",
    "Bash(cat:*)", "Bash(head:*)", "Bash(tail:*)",
    "Bash(grep:*)", "Bash(jq:*)", "Bash(ls:*)", "Bash(find:*)"
  ],
  "denied_tools": ["Write", "Edit", "NotebookEdit"]
}
```

### Unattended D&R triage agent

An `ai_agent` Hive record meant to run without a human. `bypassPermissions` is required so tool calls don't block on approval; `denied_tools` still prevents the agent from writing or from reaching arbitrary URLs even though `allowed_tools` is empty.

```yaml
ai_agent:
  triage-agent:
    data:
      prompt: |
        Investigate the triggering detection and produce a structured report.
      anthropic_secret: hive://secret/anthropic-key
      lc_api_key_secret: hive://secret/lc-api-key
      permission_mode: bypassPermissions
      one_shot: true
      denied_tools:
        - Write
        - Edit
        - WebFetch
```

### Scoping MCP tools to a single server

Let the agent call the VirusTotal MCP server for enrichment, but nothing else — and specifically block the one tool that would submit local files to the service. Any other MCP server the session inherits is still subject to the normal approval flow (or denied outright under `permission_mode: plan`).

```yaml
allowed_tools:
  - mcp__virustotal
denied_tools:
  - mcp__virustotal__upload_file
```

### Blocking destructive Bash verbs

Deny a specific prefix even when the rest of Bash is open. The deny-side matcher shares allow's wrapper-stripping and pipeline-splitting, so a single pattern catches both bare and compound forms.

```yaml
allowed_tools: ["Bash"]
denied_tools:
  - "Bash(rm:*)"
  - "Bash(mv:*)"
  - "Bash(kubectl delete:*)"
```

- `rm -rf /` → blocked by `Bash(rm:*)`.
- `ls && rm -rf /` → blocked too: the `rm -rf /` stage matches `Bash(rm:*)` and deny fires on any matching stage.
- `timeout 30 kubectl delete pod xyz` → blocked: the `timeout 30` wrapper is stripped before matching.
- `cat $(rm file)` → does **not** auto-deny, but does **not** auto-approve either; the dangerous construct routes the call back through `permission_mode` (a re-prompt in interactive sessions).

## Where to go next

- [User Sessions](user-sessions.md#session-profiles) — creating and managing Profiles via the API and UI.
- [D&R-Driven Sessions](dr-sessions.md#session-profiles) — attaching these fields to an `ai_agent` Hive record or to an inline `profile:` block on a `start ai agent` action.
- [Command Line Interface](cli.md#limacharlie-ai-start-session) — per-run overrides for `--allowed-tools`, `--denied-tools`, and `--permission-mode` when starting a session from a Hive template.
- [API Reference](api-reference.md#profiles) — the REST shape of the Profile resource.
- [Claude Code permissions (upstream)](https://code.claude.com/docs/en/permissions) — the source of truth for the pattern grammar.
