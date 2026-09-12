# AI Triage

--8<-- "includes/email-security-beta.md"

Email Security produces an explainable verdict for every message. AI triage is the
optional second pass: an agent that reads a message the way an analyst would, pivots on
what else it can find, writes a conclusion with the evidence behind it, and — when you
allow it — acts.

Triage is **not** a mailsec feature with a toggle. There is no `enable_triage` button and
no triage "mode". It is an ordinary [AI Sessions](../9-ai-sessions/index.md) agent that
watches Email Security events and works under a LimaCharlie API key. Email Security
provides the raw material an agent needs; the agent, its triggers, its credentials and its
permissions are a recipe **you** assemble. That decoupling is deliberate: it buys you full
freedom — bring your own model and provider, start from the reviewed reference and edit its
prompt, or write your own agent against the same events and API.

Nothing on this page is installed for you. This is the recipe, worked end to end, plus a
reference bundle you copy.

!!! important "What the agent may do is a permission, not a setting"
    The agent authenticates with a LimaCharlie API key, and that key either carries
    `mailsec.act` or it does not.

    A **passive** agent — one that investigates and explains but never moves mail — is
    simply an agent whose key lacks `mailsec.act`. If it tries to act anyway, the API
    refuses server-side and writes an audit row; the agent cannot talk its way past it.
    **Do not rely on the prompt for this.** A prompt is a request, not a control.

## The two halves: substrate vs recipe

Email Security ships the substrate. You assemble the agent on top of it. Keeping the line
clear is the whole idea, so here it is explicitly.

| Email Security provides (the substrate) | You assemble (the recipe) |
|---|---|
| The events an agent triggers on, on the `edr` D&R target: `EMAIL_MESSAGE`, `EMAIL_VERDICT`, `EMAIL_USER_REPORT`, `EMAIL_ACTION`. Note `EMAIL_VERDICT` fires for **every** verdict decision, including the engine's own at ingest (`revision/seq: 0`) — a trigger meant for overrides only should say `revision/seq` is greater than `0` | The `ai_agent` record — the agent's playbook, model, and session limits |
| The read/act API and its `limacharlie mailsec ...` CLI the agent drives as tools: message and report reads, sender profiles, `similar`/`campaign` pivots, report resolution, the typed actions, and the verdict write-back | The trigger rules that decide **when** the agent runs |
| The permission model that decides what any agent may **do**, per credential, server-side, audited | The credentials: an AI provider key and a LimaCharlie API key at whatever permission ceiling you choose |
| The `submit_to_triage` automation action — the one place mailsec says "this message warrants a look" | Whether the agent may act at all, and what it costs |

The benefit of doing it this way is that the agent is a normal API client. You can run its
playbook by hand to see exactly what it does, reason about its access with the same tools
you use for every other integration, and swap any part of it without waiting on a product
release.

## Before you start

1. The org is subscribed to `ext-email-security` and has at least one connected mail
   provider ingesting mail. See [Connecting Providers](providers.md).
2. You have an AI provider credential (Anthropic, OpenAI, Google, Bedrock, Vertex, …)
   available to store as a [Hive Secret](../7-administration/config-hive/secrets.md). See
   [AI Sessions providers](../9-ai-sessions/providers.md).
3. AI Sessions is available in the org — the `start ai agent` response action and the
   `ai_agent` Hive record are the platform mechanisms triage is built from. See
   [D&R-Driven AI Sessions](../9-ai-sessions/dr-sessions.md).
4. You have decided whether this agent may act. Start passive; that is the recommendation,
   and the rest of this page assumes you can widen later.

All commands use `$OID` for the organization id. Set it once:

```bash
export OID="c1ffedc0-ffee-4a1e-b1a5-abc123def456"
```

## Step 1 — Store the AI provider credential

The agent runs on a model, and the model needs a key. Store it as a secret so the agent
record references it rather than embedding it:

```bash
echo '{"secret": "<your-anthropic-api-key>"}' | \
  limacharlie hive set --hive-name secret --key mailsec-triage-anthropic \
  --oid "$OID" --enabled
```

This example uses Anthropic; any [supported provider](../9-ai-sessions/providers.md) works.
The provider and model are yours to choose — mailsec neither supplies nor meters them.

## Step 2 — Create the LimaCharlie API key the agent will use

The key's permissions are the agent's ceiling, and they are the *only* thing that makes an
agent passive or active. Create the key, then store it as a secret too.

=== "Passive (recommended to start)"

    A passive agent investigates and explains. It reads the queue, the parsed message
    model, sender history, campaigns and the audit trail, and it writes a conclusion — but
    it cannot move mail. If it tries, the API returns a refusal and audits the attempt.

    ```bash
    limacharlie api-key create --oid "$OID" \
      --name mailsec-triage \
      --permissions "mailsec.get,ai_agent.operate"
    ```

    - `mailsec.get` — read reports, the parsed message model, sender profiles, `similar`
      and campaign pivots, and the action audit trail.
    - `ai_agent.operate` — the platform guardrail that lets a key be driven by an AI agent
      at all. Without it the agent cannot start.

=== "Active (grant later, once you trust it)"

    An active agent may additionally remediate: quarantine, trash, banner, move-to-spam,
    restore, act on a whole campaign, and write a `mode: ai` verdict. Every action passes
    through the same choke point as a human's — your `alert_only` / `enforce` policy
    applies, and an audit row names the agent as the actor.

    ```bash
    limacharlie api-key create --oid "$OID" \
      --name mailsec-triage \
      --permissions "mailsec.get,ai_agent.operate,mailsec.act"
    ```

    - `mailsec.act` — the write tier: move mail and write the `mode: ai` verdict.
    - Add `mailsec.set` as well if you also want the agent to **resolve user reports**
      (close a report with a disposition). Omit it and the agent investigates reports but
      leaves them open for a human.

!!! warning "Raw EML is deliberately withheld"
    Do not grant `mailsec.get.eml` to this agent. The playbook is grounded in the parsed
    message model and indexed evidence, which is enough to triage. Raw message bytes are a
    separate privileged workflow — every use takes the original mail out of your tenant and
    is written to the access audit with a justification — and the reference agent is built
    to work without them.

Store the key value as a secret so the agent record can reference it:

```bash
echo '{"secret": "<the-api-key-value>"}' | \
  limacharlie hive set --hive-name secret --key mailsec-triage-key \
  --oid "$OID" --enabled
```

## Step 3 — Install the agent record

The agent is an `ai_agent` Hive record: the playbook, the model, the session limits, and
references to the two secrets from Steps 1 and 2. Copy the reviewed reference from the
public [`lc-ai`](https://github.com/refractionPOINT/lc-ai/tree/master/ai-agents/triage/mailsec-triage)
bundle (`ai-agents/triage/mailsec-triage`) — it ships the agent and all three triggers as
one reviewable unit — and wire in your credentials.

The record has the following shape. The `prompt` below is abbreviated: copy the full
playbook from the reference, which walks the agent through resolving the work item,
gathering bounded corroborating evidence, remediating only when the credential permits it,
and finishing with an auditable result.

```yaml
# mailsec-triage-agent.yaml
lc_api_key_secret: hive://secret/mailsec-triage-key
anthropic_secret: hive://secret/mailsec-triage-anthropic

name: "Email triage: {{ .msg_uuid }}{{ .report_id }}"
prompt: |
  You are an email security analyst triaging one LimaCharlie Email Security
  message or user report. You receive trigger data containing oid and either
  msg_uuid or report_id. Always pass --oid <oid> and --output yaml.
  # ... copy the full reference playbook here ...

data:
  oid: routing.oid
debounce_key: "mailsec-triage-{{ .msg_uuid }}{{ .report_id }}"

plugins:
  - lc-essentials

max_turns: 20
max_budget_usd: 0.50
ttl_seconds: 180
one_shot: true
permission_mode: bypassPermissions
```

```bash
limacharlie hive set --hive-name ai_agent --key mailsec-triage \
  --input-file mailsec-triage-agent.yaml --oid "$OID" --enabled
```

What the non-obvious fields buy you:

| Field | Why it is there |
|---|---|
| `lc_api_key_secret` | The key from Step 2 — the agent's permission ceiling. Passive or active is decided here, not in the prompt. |
| `anthropic_secret` | The provider key from Step 1. To run on a different provider, reference that provider's credential instead — see [AI Sessions providers](../9-ai-sessions/providers.md). |
| `plugins: [lc-essentials]` | Puts the `limacharlie` CLI in the session. Without it the agent has no way to reach anything. |
| `max_budget_usd` | A per-run ceiling enforced by AI Sessions. This is the real cost control — a run that reaches it stops. There is no separate Email Security budget to keep in sync. |
| `max_turns`, `ttl_seconds` | Bound how long a single run can go round and how long it can live. |
| `debounce_key` | One session per work item. A redelivered notification or a second rule firing on the same message queues behind the first instead of paying twice for the same conclusion. |
| `one_shot` | The session ends when the task is done rather than idling. |

The reference record ships **disabled** (`usr_mtd.enabled: false`), so installing it starts
no session and spends nothing until you enable it. With a passive key, an enabled agent is
safe — it can only investigate.

## Step 4 — Install the three triggers

The agent does nothing until something starts it. The reference ships three trigger rules
in `dr-general`, and they answer three different questions. Install them together with the
agent: a trigger without its agent fires and fails.

Each rule targets `edr` (the D&R target the `EMAIL_*` events arrive on), responds with
`start ai agent` pointing at the record from Step 3, and shares **one** org-local
suppression key capped at 60 starts per minute — a single ceiling on triage volume no
matter which rule fired. Save each rule to its own file and install it into `dr-general`.

### On a suspicious message

```yaml
detect:
  target: edr
  event: EMAIL_MESSAGE
  op: is
  path: event/verdict/verdict
  value: suspicious
respond:
  - action: start ai agent
    definition: hive://ai_agent/mailsec-triage
    debounce_key: "mailsec-triage-{{ .event.msg_uuid }}"
    data:
      oid: "{{ .routing.oid }}"
      msg_uuid: "{{ .event.msg_uuid }}"
      campaign_id: "{{ .event.campaign_id }}"
    suppression:
      is_global: true
      keys:
        - mailsec-triage-volume
      max_count: 60
      period: 1m
```

`suspicious` rather than `malicious` is the interesting choice. A malicious verdict is
already actionable and your automations handle it. The value of triage is the band where
the score did **not** settle the question — which is also the band that produces analyst
toil.

```bash
limacharlie hive set --hive-name dr-general --key mailsec-triage-suspicious \
  --input-file mailsec-triage-suspicious.yaml --oid "$OID" --enabled
```

### On a user report

```yaml
detect:
  target: edr
  event: EMAIL_USER_REPORT
  op: exists
  path: event/report_id
respond:
  - action: start ai agent
    definition: hive://ai_agent/mailsec-triage
    debounce_key: "mailsec-triage-report-{{ .event.report_id }}"
    data:
      oid: "{{ .routing.oid }}"
      report_id: "{{ .event.report_id }}"
      msg_uuid: "{{ .event.original_msg_uuid }}"
      reported_msg_uuid: "{{ .event.reported_msg_uuid }}"
      campaign_id: "{{ .event.campaign_id }}"
    suppression:
      is_global: true
      keys:
        - mailsec-triage-volume
      max_count: 60
      period: 1m
```

There is **no verdict filter** here. Someone took the trouble to report a message, which is
evidence the scorer did not have. Filtering reports by score would discard the signal
exactly when it disagrees with you — the only time it is interesting. See
[User Reports](user-reports.md).

!!! note "A report can arrive without an original"
    `original_msg_uuid` is empty when the reported message was never indexed — the mail
    predates the connection, or landed outside protected scope. The reference playbook
    falls back to `reported_msg_uuid` (the forwarded copy) and says plainly that the
    original was outside coverage rather than inventing one.

```bash
limacharlie hive set --hive-name dr-general --key mailsec-triage-user-report \
  --input-file mailsec-triage-user-report.yaml --oid "$OID" --enabled
```

### On an automation asking for a look

```yaml
detect:
  target: edr
  event: EMAIL_ACTION
  op: and
  rules:
    - op: is
      path: event/action
      value: submit_to_triage
    - op: is
      path: event/result
      value: ok
respond:
  - action: start ai agent
    definition: hive://ai_agent/mailsec-triage
    debounce_key: "mailsec-triage-{{ .event.msg_uuid }}"
    data:
      oid: "{{ .routing.oid }}"
      msg_uuid: "{{ .event.msg_uuid }}"
    suppression:
      is_global: true
      keys:
        - mailsec-triage-volume
      max_count: 60
      period: 1m
```

This rule lets your own [policy automations](policy.md) hand a message to the agent:
`submit_to_triage` is the action that says "this one warrants a look."

!!! warning "The `result == ok` filter is load-bearing, not decoration"
    An `alert_only` organization still emits `EMAIL_ACTION` for `submit_to_triage` as an
    **audit** of the action its policy withheld — with a non-`ok` result. Matching the
    action alone would start a paid AI session for exactly the organizations that chose not
    to act. The `result == ok` predicate keeps the trigger honest to the enforcement choke
    point. Keep it.

```bash
limacharlie hive set --hive-name dr-general --key mailsec-triage-submitted \
  --input-file mailsec-triage-submitted.yaml --oid "$OID" --enabled
```

## Cost and guardrails

Every cost control lives on the agent and on AI Sessions — none of it is metered or
mirrored by Email Security, so there is one budget in one place rather than two that can
disagree.

- `max_budget_usd` hard-stops a single run when it reaches the ceiling.
- `max_turns` and `ttl_seconds` bound how far and how long one run can go.
- `debounce_key` stops duplicate work on the same message or report.
- The **shared 60/1m suppression** bounds total triage volume across all three triggers —
  the single largest cost lever on this page. Widening the suspicious-message rule to every
  message, or raising the suppression cap, is the decision to make deliberately.
- Model and provider are yours; their rates are the provider's.

To see what you are spending, use the AI Sessions
[cost tracking](../9-ai-sessions/cost-tracking.md) surface.

## Verify it works

Prove the recipe before trusting it.

1. **Run the playbook by hand first.** It takes a minute and it is the difference between
   finding out now and finding out from a bill:

    ```bash
    limacharlie mailsec message list --verdict suspicious --limit 5 --oid "$OID" --output yaml
    limacharlie mailsec message get <msg_uuid> --oid "$OID" --output yaml
    limacharlie mailsec message similar <msg_uuid> --oid "$OID" --output yaml
    ```

    If those give you what you would want an analyst to see, the agent will have it too.

2. **Trigger a real run.** Report a test phishing message to the abuse mailbox, or wait for
   a message to land at the `suspicious` verdict, then watch a session start:

    ```bash
    limacharlie ai session list --status running --oid "$OID"
    limacharlie ai session get --id <SESSION_ID> --oid "$OID"
    ```

3. **Read the transcript, and see the write-back.** Confirm the agent read the message,
   pivoted sensibly, and reached a conclusion it can defend with evidence. When an active
   agent revises a verdict it lands as a `mode: ai` [verdict revision](detections.md): the
   message row updates and an `EMAIL_VERDICT` event is emitted at the next `revision/seq`, so
   the queue shows what the agent decided and why, exactly as it does for the scorer — whose
   own verdict shipped as `seq 0` on the same event type at ingest. An active agent's quarantine
   or report-resolution shows up in the message and report timelines and in the
   `EMAIL_ACTION` audit trail.

!!! warning "The agent needs the `mailsec` CLI in its runtime — the one real gap today"
    The agent reaches Email Security by driving the `limacharlie mailsec ...` command
    group, and that command group must be present in the CLI inside the session runtime.
    The `lc-essentials` plugin installs the `limacharlie` CLI
    ([runner environment](../9-ai-sessions/runner-environment.md)), but some runtimes still
    ship a CLI old enough to predate the `mailsec` commands — a runtime on `v5.6.2`, for
    example, lacks them.

    When that happens the agent still starts and still investigates through the events and
    data it is handed, but it cannot run the `mailsec` tools to pivot or act — the
    reference playbook detects the missing command group, reports the coverage gap, and
    defers to a human rather than guessing. Confirm your session runtime carries a
    `limacharlie` CLI new enough to include `limacharlie mailsec`. The server side —
    verdict write-back, actions, report resolution, and the `submit_to_triage` trigger —
    is live; this is purely about the CLI shipped in the agent's runtime.

## Passive first, then active

Run passive to begin — a key with `mailsec.get` and `ai_agent.operate` but **not**
`mailsec.act`. The agent investigates every trigger and writes a conclusion you can read,
but it cannot move mail, so a wrong call costs nothing but a session. Watch its transcripts
until its judgment matches what you would have done by hand.

When you trust it, widen the key to add `mailsec.act` (and `mailsec.set` if it should also
resolve reports). Nothing else changes — same agent, same triggers, same prompt. Active is
just a wider ceiling on the same key.

## Turning it off

Disable the three trigger rules. The agent record can stay; it costs nothing when nothing
starts it.

```bash
limacharlie hive set --hive-name dr-general --key mailsec-triage-suspicious \
  --input-file mailsec-triage-suspicious.yaml --oid "$OID" --disabled
limacharlie hive set --hive-name dr-general --key mailsec-triage-user-report \
  --input-file mailsec-triage-user-report.yaml --oid "$OID" --disabled
limacharlie hive set --hive-name dr-general --key mailsec-triage-submitted \
  --input-file mailsec-triage-submitted.yaml --oid "$OID" --disabled
```

## Customize, or bring your own

The reference is a starting point, not a black box. Because triage is ordinary AI Sessions
content, every part of it is yours to change:

- **Edit the prompt.** It is the part you should expect to tune — the pivots you want
  emphasized, the bar for calling something malicious, how conservatively it should act.
- **Swap the model or provider.** Reference a different provider credential on the record
  and pick its model; the tools, permissions, budgets and lifecycle are identical across
  [providers](../9-ai-sessions/providers.md).
- **Change when it runs.** The triggers are plain D&R rules. Narrow them, widen them, or
  add your own — for example a rule that only triages mail to your VIP list.
- **Write your own agent.** The events (`EMAIL_MESSAGE`, `EMAIL_USER_REPORT`,
  `EMAIL_ACTION`) and the `limacharlie mailsec ...` API are a stable contract. Any harness
  that can consume them and hold a LimaCharlie API key can do triage; the reference just
  saves you the first draft.
