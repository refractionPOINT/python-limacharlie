# Standard Operating Procedures (SOPs)

A Standard Operating Procedure is a document you store in your organization that
tells AI agents how *your* team wants a job done. Where [AI Skills](skills.md) are
reusable capabilities an agent can invoke, [AI Memory](memory.md) is what an agent
has learned, and [Organization Notes](org-notes.md) are reference material about the
environment, an SOP is organizational policy: the escalation path for a ransomware
detection, who must approve an endpoint isolation, which hosts are never to be
touched during business hours.

SOPs are plain documents — LimaCharlie does not execute them. They are written by
humans, read by agents, and followed as instructions. That makes them the primary
way to steer agent behaviour without editing agent prompts.

SOPs live in the `sop` [Config Hive](../7-administration/config-hive/index.md),
scoped to a single organization.

## Record format

Each SOP is one Hive record. The key is the SOP name, and the payload has two
fields:

| Field | Required | Purpose |
|---|---|---|
| `text` | Yes | The procedure itself. Free-form; markdown is the convention. |
| `description` | No | A one-line summary used to decide whether the SOP applies. |

```yaml
data:
  description: Standard procedure for confirmed ransomware on an endpoint
  text: |
    # Ransomware Response

    ## Containment
    1. Isolate the affected sensor immediately — do not wait for approval.
    2. Tag the sensor `incident` and note the detection ID.

    ## Escalation
    - Page the on-call responder for any host tagged `prod`.
    - Do not power off servers; collect memory first.

    ## Out of scope
    - Never delete artifacts or detections as part of containment.
usr_mtd:
  enabled: true
  tags: [incident-response, tier-1]
```

The only validation applied is that `text` must be non-empty. Nothing else about
the content is enforced, so write for the reader — an LLM deciding what to do next.

### Writing an effective `description`

The `description` is load-bearing. Agents scan the list of SOPs and match
descriptions against the task in front of them, then fetch only the ones that look
relevant. A vague description ("IR stuff") means the SOP is never opened; a specific
one ("Standard procedure for confirmed ransomware on an endpoint") means it is.

### Limits

- Maximum record size: 1 MB per SOP.

!!! warning "New SOPs are created disabled"
    Like every Hive record, an SOP is created **disabled** unless you pass
    `--enabled` or set `usr_mtd.enabled: true`. Set it deliberately — an SOP is only
    meaningful if the agents reading it treat it as active policy.

## How agents use SOPs

Nothing injects SOPs into an agent automatically. Agents load them, on their own,
in two steps:

1. **List** the SOPs in the organization and read the names and descriptions.
2. **Fetch by key** only the SOPs whose description matches the task at hand, then
   follow the procedure.

Agents built from the LimaCharlie agent library announce the match in their
transcript — `Following SOP: <name>` — so you can audit adherence after the fact.

This means the granularity of your SOPs matters. One giant `security-policy`
document forces the agent to load everything for every task; a set of narrowly
described SOPs (`ransomware-response`, `after-hours-escalation`,
`isolation-approval`) lets it pull only what applies.

!!! note "Listing returns full records"
    `limacharlie sop list` and `GET /v1/hive/sop/{oid}` return every SOP in full,
    including `text`. Agents are instructed to read only the names and descriptions
    at that stage and re-fetch the body with `sop get`, but budget context
    accordingly if you keep many large SOPs. `limacharlie sop list --brief` reduces
    each record's data to its `description` — that is the index-only form to prefer
    when all you need is to decide what to fetch.

## Permissions

| Operation | Permission |
|---|---|
| List / read SOPs | `sop.get` |
| Create / update an SOP | `sop.set` |
| Delete an SOP | `sop.del` |
| Read metadata | `sop.get.mtd` |
| Update metadata | `sop.set.mtd` |

An agent that only needs to follow procedures should be issued `sop.get` and
`sop.get.mtd` — read-only. Grant `sop.set` only to agents that are expected to
author policy.

## Managing SOPs

### Web interface

SOPs are managed under **Organization Settings → SOPs** in the organization view,
where you can create, edit, tag, enable, and disable them. In an interactive AI
session, the `/sops` [slash command](rich-cards.md) renders the same list inline.

### CLI

```bash
# List every SOP in the organization.
limacharlie sop list --oid <oid> --output yaml

# Read one SOP.
limacharlie sop get --key ransomware-response --oid <oid> --output yaml

# Create or update an SOP from a file, enabled in one shot.
limacharlie sop set --key ransomware-response \
    --input-file ransomware-response.yaml --enabled --oid <oid>

# Or pipe the record in.
cat ransomware-response.yaml | limacharlie sop set \
    --key ransomware-response --enabled --oid <oid>

# Toggle without touching the content.
limacharlie sop disable --key ransomware-response --oid <oid>
limacharlie sop enable --key ransomware-response --oid <oid>

# Organize with tags.
limacharlie sop tag add --key ransomware-response -t incident-response --oid <oid>

# Delete.
limacharlie sop delete --key ransomware-response --confirm --oid <oid>
```

The input file takes the same shape as the record above — a `data` block with
`text` and `description`, plus an optional `usr_mtd` block.

### REST API

SOPs use the standard Hive endpoints with a hive name of `sop` and the organization
ID as the partition key:

```bash
# List all SOPs.
curl -s "https://api.limacharlie.io/v1/hive/sop/$OID" \
  -H "Authorization: Bearer $LC_JWT"

# Read one SOP.
curl -s "https://api.limacharlie.io/v1/hive/sop/$OID/ransomware-response/data" \
  -H "Authorization: Bearer $LC_JWT"

# Create or update.
curl -s -X POST \
  "https://api.limacharlie.io/v1/hive/sop/$OID/ransomware-response/data" \
  -H "Authorization: Bearer $LC_JWT" \
  --data-urlencode 'data={"text":"# Ransomware Response\n1. Isolate the sensor.","description":"Confirmed ransomware on an endpoint"}' \
  --data-urlencode 'usr_mtd={"enabled":true}'
```

### Python SDK

```python
from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.hive import Hive, HiveRecord

client = Client(oid="YOUR_OID", api_key="YOUR_API_KEY")
org = Organization(client)
sops = Hive(org, "sop")

# Create or update an SOP.
record = HiveRecord(
    "ransomware-response",
    data={
        "text": "# Ransomware Response\n1. Isolate the sensor.",
        "description": "Confirmed ransomware on an endpoint",
    },
)
record.enabled = True
record.tags = ["incident-response"]
sops.set(record)

# Read one SOP.
sop = sops.get("ransomware-response")
print(sop.data["text"])

# List every SOP.
for name, rec in sops.list().items():
    print(name, rec.data.get("description"))
```

## Related

- [AI Skills](skills.md) — reusable instruction sets an agent invokes as capabilities.
- [AI Memory](memory.md) — what an agent has learned and should recall later.
- [Organization Notes](org-notes.md) — free-form reference documents about the
  organization itself, in the sibling `org_notes` hive.
- [Config Hive](../7-administration/config-hive/index.md) — the store SOPs live in.
- [Permissions](../8-reference/permissions.md) — the full permission reference.
