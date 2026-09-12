# AI Memory

AI Memory is a per-agent key/value store for content that should outlive a single AI Session. Where [Skills](skills.md) capture *how* an agent works, memory captures *what it has learned* — facts about the environment, prior decisions, ongoing investigations, anything the agent should be able to recall the next time it runs.

Each agent owns one record, keyed by an agent identifier you pick. Inside that record, individual memories are addressed by filesystem-style names (`notes/today`, `cases/INC-123/timeline`, `runtime/last-seen-host`, …). Writes are partial: setting a single named memory does not require reading the rest of the record back, and concurrent writes against different memory names on the same agent do not need to coordinate.

## How writes merge

Memory uses a server-side partial-merge model so agents can update one entry at a time without round-tripping the whole record:

- **Set** with `{"<name>": "<content>"}` replaces just that entry. Other memories on the agent are preserved.
- **Set** with `{"<name>": null}` drops just that entry. Other memories are preserved.
- **Delete the whole record** to remove every memory for an agent in one call.

This means an agent can take notes incrementally throughout a session — `progress/step-1`, `progress/step-2` — without ever fetching the full record, and two agents (or two parallel turns) writing to disjoint memory names will not clobber each other.

## Naming rules

Memory names follow filesystem conventions:

- Relative paths only — no leading `/`.
- Forward slashes only — no `\`.
- Canonical form — `./` and `../` segments are rejected.
- No traversal above the record root.
- Maximum 256 characters per name.

Use the path structure to keep memories organised (`runtime/`, `notes/`, `cases/<id>/…`) — the store does not care about the segments, but a consistent layout makes it easier to enumerate or selectively wipe.

## Limits

- Memories per agent record: 1024
- Memory name length: 256 characters
- Total record size: 10 MB

## Permissions

| Operation | Permission |
|---|---|
| List / get | `ai_memory.get` |
| Create / update / drop | `ai_memory.set` |
| Delete a whole agent record | `ai_memory.del` |
| Read metadata | `ai_memory.get.mtd` |
| Update metadata | `ai_memory.set.mtd` |

## Managing memory

### CLI

The `ai-memory` command group draws a clear line between operating on one memory entry (`get`, `set`, `delete`, with both `--key` and `--memory-name`) and operating on the whole agent record (`list-records`, `delete-record`).

```bash
# Enumerate every agent that has memory stored.
limacharlie ai-memory list-records

# List the memory entries on one agent.
limacharlie ai-memory list --key triage-bot

# Read one memory entry.
limacharlie ai-memory get --key triage-bot --memory-name notes/today

# Write or replace one memory entry (other memories preserved).
limacharlie ai-memory set --key triage-bot \
    --memory-name notes/today --content "wrote the cli wrapper"

# Pipe content from a file or another command.
cat findings.md | limacharlie ai-memory set \
    --key triage-bot --memory-name cases/INC-123/timeline

# Drop one memory entry (other memories preserved).
limacharlie ai-memory delete --key triage-bot \
    --memory-name notes/today --confirm

# Drop every memory the agent has stored.
limacharlie ai-memory delete-record --key triage-bot --confirm
```

### REST API

Memory lives in the `ai_memory` Hive. To set or drop one entry without disturbing the others, send only that entry under the `memories` field — the merge happens server-side:

```bash
# Set one memory (other memories preserved).
curl -s -X POST \
  "https://api.limacharlie.io/v1/hive/ai_memory/$OID/triage-bot/data" \
  -H "Authorization: Bearer $LC_JWT" \
  --data-urlencode 'data={"memories":{"notes/today":"wrote the cli wrapper"}}'

# Drop one memory (other memories preserved).
curl -s -X POST \
  "https://api.limacharlie.io/v1/hive/ai_memory/$OID/triage-bot/data" \
  -H "Authorization: Bearer $LC_JWT" \
  --data-urlencode 'data={"memories":{"notes/today":null}}'
```

Reading the record returns every memory under `data.memories`.

### Python SDK

The `AiMemory` client wraps the partial-merge semantics so callers can operate on one entry at a time:

```python
from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.ai_memory import AiMemory

client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
org = Organization(client)
am = AiMemory(org)

# Write or replace one memory.
am.set("triage-bot", "notes/today", "wrote the cli wrapper")

# Read one memory.
content = am.get("triage-bot", "notes/today")

# Update many entries in one call (None drops the entry).
am.set_many("triage-bot", {
    "progress/step-1": "done",
    "progress/step-2": "in flight",
    "notes/today": None,
})

# Drop one memory; everything else on the agent is preserved.
am.delete("triage-bot", "progress/step-1")

# Wipe the agent record entirely.
am.delete_record("triage-bot")
```

## Profile memory bank

AI Memory (above) is an **org-scoped, per-agent** store managed through the
`ai_memory` Hive. There is a second, distinct kind of memory: the **profile memory
bank**, which is **per-user and lifecycle-coupled to a [profile](user-sessions.md#session-profiles)**.

When a session is launched from a profile, the bank's markdown files are mounted
into the session workspace at `/workspace/.memory/<path>`, and edits the agent makes
there during the session are synced back to the profile. It's useful for notes,
runbooks, and reference material you want available in every session that uses a
given profile, editable both by hand and by the agent.

| | AI Memory (`ai_memory`) | Profile memory bank |
|---|---|---|
| Scope | Organization, per agent | A single user's profile |
| Managed via | CLI / API / SDK (Hive) | Profile management, mounted into the session |
| Mounted in session | No (the agent reads/writes via tools) | Yes, at `/workspace/.memory/` |
| Limits | 1024 entries, 256-char names, 10 MB total | 100 entries, 64 KiB per entry, 5 MiB total |

The bank is excluded from hibernation archives and re-mounted fresh on every start,
so changes made through profile management while a session is dormant take effect on
the next resume.

## Related

- [AI Skills](skills.md) — companion store for reusable instruction sets.
- [User Sessions](user-sessions.md) — interactive sessions that may write to and read from memory.
- [D&R-Driven Sessions](dr-sessions.md) — automated sessions that can persist findings across runs.
