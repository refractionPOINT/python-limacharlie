# Organization Notes

An Organization Note is a free-form document you store in your organization to
record context that is true of the org itself: the network layout, which subnets
are production, the naming convention for servers, who owns which business unit,
the maintenance window, a link to the internal runbook.

Where an [SOP](sops.md) says *how a job should be done* and [AI Memory](memory.md)
holds *what an agent learned on its own*, an Organization Note is *reference
material a human wrote down for whoever reads it next* — an analyst opening the
web interface, or an AI agent gathering context before it acts.

Organization Notes live in the `org_notes` [Config Hive](../7-administration/config-hive/index.md),
scoped to a single organization. They are managed with the `limacharlie note`
command group.

!!! note "Not the same as case or investigation notes"
    Organization Notes are org-wide and permanent. Notes attached to a case or an
    investigation are scoped to that one incident and belong there instead.

## Record format

Each note is one Hive record. The key is the note name, and the payload has two
fields — identical in shape to an [SOP](sops.md):

| Field | Required | Purpose |
|---|---|---|
| `text` | Yes | The note itself. Free-form; markdown is the convention. |
| `description` | No | A one-line summary used to decide whether the note is relevant. |

```yaml
data:
  description: Production network layout and ownership
  text: |
    # Production Network

    ## Subnets
    - `10.10.0.0/16` — production application tier, owned by Platform.
    - `10.20.0.0/16` — corporate VPN pool, dynamic, expect churn.
    - `10.30.0.0/16` — lab; noisy by design, do not escalate on it.

    ## Naming
    - Hostnames `web-*` and `api-*` are internet-facing.
    - Hostnames `db-*` are never internet-facing — treat exposure as an incident.

    ## Maintenance window
    - Sundays 02:00–06:00 UTC. Patch-related process churn is expected then.
usr_mtd:
  enabled: true
  tags: [network, reference]
```

The only validation applied is that `text` must be non-empty — nothing about the
content is enforced. Write for the reader, which increasingly means an LLM
deciding whether this note changes what it is about to do.

### Writing an effective `description`

As with SOPs, the `description` is load-bearing. An agent lists the notes,
reads names and descriptions, and fetches in full only the ones that look
relevant. "Misc" gets skipped; "Production network layout and ownership" gets
opened.

### Limits

- Maximum record size: 1 MB per note.

Notes are meant to be read whole, so keep each one to a single subject. A dozen
focused notes beat one `everything` document that no reader can pull selectively.

!!! warning "New notes are created disabled"
    Like every Hive record, a note is created **disabled** unless you pass
    `--enabled` or set `usr_mtd.enabled: true`.

## How agents use notes

Nothing injects Organization Notes into an agent automatically. Agents that
gather org context do it in two steps, the same lazy-loading pattern used for
SOPs:

1. **List** the notes and read the names and descriptions — `limacharlie note list --brief`
   reduces each record to its `description` so the index costs almost no context.
2. **Fetch by key** the notes whose description bears on the task, then use them
   as ground truth about the environment.

Notes are also the recommended place to park longer reference documents an agent
should consult but that are not procedures — a compliance control mapping, an
asset inventory summary, a customer-specific escalation matrix.

!!! tip "Don't mirror notes into AI Memory"
    [AI Memory](memory.md) is for what an agent discovered itself. Copying an
    Organization Note into memory creates a second copy that silently goes stale;
    have the agent read the note from the hive instead.

## Permissions

| Operation | Permission |
|---|---|
| List / read notes | `org_notes.get` |
| Create / update a note | `org_notes.set` |
| Delete a note | `org_notes.del` |
| Read metadata | `org_notes.get.mtd` |
| Update metadata | `org_notes.set.mtd` |

An agent that only needs environment context should be issued `org_notes.get`
(plus `org_notes.get.mtd` if it reads tags) — read-only. Grant `org_notes.set`
only to agents expected to write documentation back, such as an agent that
maintains an inventory note between runs.

## Managing Organization Notes

### Web interface

Notes are managed under **Organization Settings → Organization Notes** in the
organization view, where you can create, edit, tag, enable, and disable them. The
editor takes markdown.

### CLI

The command group is `note` — the hive it writes to is `org_notes`.

```bash
# List every note in the organization, full bodies included.
limacharlie note list --oid <oid> --output yaml

# List just the index — each record reduced to its description.
limacharlie note list --brief --oid <oid> --output yaml

# Read one note.
limacharlie note get --key prod-network --oid <oid> --output yaml

# Create or update a note from a file, enabled in one shot.
limacharlie note set --key prod-network \
    --input-file prod-network.yaml --enabled --oid <oid>

# Or pipe the record in.
cat prod-network.yaml | limacharlie note set \
    --key prod-network --enabled --oid <oid>

# Toggle without touching the content.
limacharlie note disable --key prod-network --oid <oid>
limacharlie note enable --key prod-network --oid <oid>

# Organize with tags.
limacharlie note tag add --key prod-network -t reference --oid <oid>

# Delete.
limacharlie note delete --key prod-network --confirm --oid <oid>
```

The input file takes the same shape as the record above — a `data` block with
`text` and `description`, plus an optional `usr_mtd` block.

### REST API

Notes use the standard Hive endpoints with a hive name of `org_notes` and the
organization ID as the partition key:

```bash
# List all notes.
curl -s "https://api.limacharlie.io/v1/hive/org_notes/$OID" \
  -H "Authorization: Bearer $LC_JWT"

# Read one note.
curl -s "https://api.limacharlie.io/v1/hive/org_notes/$OID/prod-network/data" \
  -H "Authorization: Bearer $LC_JWT"

# Create or update.
curl -s -X POST \
  "https://api.limacharlie.io/v1/hive/org_notes/$OID/prod-network/data" \
  -H "Authorization: Bearer $LC_JWT" \
  --data-urlencode 'data={"text":"# Production Network\n- 10.10.0.0/16 is production.","description":"Production network layout and ownership"}' \
  --data-urlencode 'usr_mtd={"enabled":true}'
```

### Python SDK

```python
--8<-- "snippets/python/org_note_create.py"
```

Reading works the same way as any other hive:

```python
--8<-- "snippets/python/org_note_list.py"
```

## Version control

`org_notes` is one of the hives the [Git Sync](../5-integrations/extensions/limacharlie/git-sync.md)
extension can handle: enable it under the extension's `sync_hives` (pull from the
repository) or `export_hives` (push to the repository) selection and notes are
versioned alongside the rest of your configuration. Reviewing notes like code is
worth it — they are the assumptions your analysts and agents act on.

## Related

- [SOPs](sops.md) — the procedures agents follow, in the sibling `sop` hive.
- [AI Memory](memory.md) — what an agent learned and should recall later.
- [AI Skills](skills.md) — reusable instruction sets an agent invokes as capabilities.
- [Config Hive](../7-administration/config-hive/index.md) — the store notes live in.
- [Permissions](../8-reference/permissions.md) — the full permission reference.
