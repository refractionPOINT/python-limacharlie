[Documentation](../README.md) > [CLI](README.md) > Investigation Engine

# Investigation Engine

Install or upgrade with `python -m pip install --upgrade limacharlie`. See [installation](../getting-started.md#installation) for setup.

The `investigate` group builds, tests and tunes Investigation Engine templates and runs investigations. A template says what to gather for an alert (`gather`), which rules decide it (`rules`: `escalate` and `close`, each with an id and a sentence for the case) and, optionally, one AI review for what rules cannot decide (`ai_review`). Nothing is scored: a run ends with an **outcome** and the rule or the AI behind it (see [How a run ends](#how-a-run-ends)). A person or an AI agent (Claude Code, Codex, ...) can drive the whole loop from the CLI.

The Investigation Engine is **experimental and gated per deployment**. Where it is not enabled the API does not serve the routes and the CLI says so (a 404 with no engine error code). Where your organization has no engine, the API answers 503.

Every command supports `--ai-help`, and `limacharlie help investigation-engine` prints the workflow below. Output is JSON when piped (`--output` selects another format); see [output formats](README.md#output-formats).

## Permissions

All the listed permissions are required.

| Operation | Permissions |
|---|---|
| Reads: runs, templates, operators, packs, kit, policy, test results, the approvals inbox | `investigation.get` + `insight.evt.get` |
| Writes: start a run, wave, cancel, delete a run, test a template, decide an action | `investigation.set` + `insight.evt.get` |
| Approve / deny an action | the writes above + the permission of the action's class (for example `sensor.task`, `mailsec.act`, `sensor.tag`) |
| `stats`, and `runs list --outcome` / `--verdict` | the reads above + `investigation_policy.set` |
| `policy ai` / `policy ai-set` | `investigation_policy.get` / `.set` (they read and change the `ai_may_decide` field of the `default` record) |
| `policy status` / `policy pause` / `policy resume` | `investigation_policy.get` / `.set` / `.del` (they read, save and delete the `autonomy-manual-pause` record; explicit grants, no default role has them) |
| Template records (`investigation_plan` hive) | `investigation_plan.get`, `investigation_plan.set`, `investigation_plan.del` (explicit grants; no default role has them) |

Waves and template tests always execute with **your own token**, so the operators enforce your permissions. A run started with `runs start` executes as the identity the organization's `investigation_policy` names for its template: your token when the policy names none, otherwise the Hive secret the policy points to, in which case the operators enforce that secret's permissions and not yours. An active template can therefore reach data or take actions beyond your own permissions. Before you start one, check `limacharlie investigate policy get --template NAME`: its `identity` shows the default identity, the allowed ones and where they come from. A finished run's `identity` field (`kind` caller or secret) records which one it used. Runs started by a detection rule or a case never have a caller and always use the policy's secret identity.

Live sensor metadata operators (`sensor.read.*`) need `sensor.task.read` (or the
broader `sensor.task`) plus `output.set` on the execution identity. Explicitly grant
`sensor.task.read` for an observe-only identity; no default or preset includes it.
It authorizes only allowlisted metadata commands, and only when the Investigation
Engine is enabled for the deployment. File contents, mutations and unknown
commands are refused server-side; with the gate off it grants no tasking. Keep
observe-only policies at `suggest`. Action permissions above remain unchanged.

## AI agent workflow

Hand an agent this loop. It never activates anything on its own: a person does the last step.

```bash
# 1. Learn the language, in parts (the whole kit is ~33k tokens)
limacharlie investigate kit --section guide --section policy --section codes
limacharlie investigate kit --section schema --section library
limacharlie investigate packs --brief
limacharlie investigate operators --brief

# 2. Look at real data, try operators and packs with a wave
limacharlie investigate wave --file wave.yaml --validate-only
limacharlie investigate wave --file wave.yaml

# 3. Draft plan.yaml, then validate until there are no errors
limacharlie investigate templates validate --file plan.yaml

# 4. Test on past alerts; read validation, summary, each disagree, then undecided
#    (which rule decided, what the AI recommended, what stayed unknown)
limacharlie investigate templates test --file plan.yaml --detect-cat my-category --last 10

# 5. Refine and repeat 3-4, then save a DRAFT with what you tested
limacharlie investigate templates save my-plan --file plan.yaml \
  --comment "10 samples: 7 decided by rules (0 disagree), 2 AI recommendations agree, 1 unknown (index_lag)"

# 6. A PERSON reviews the draft and its test results, then promotes it
limacharlie investigate templates promote my-plan --confirm
```

Rules the CLI enforces:

- `templates save` writes a **draft**. A source that says `status: active` is refused, and only a person's explicit `--status active` writes an active template. AI agents must not pass `--status active` and must not run `templates promote`.
- A record is never overwritten without `--overwrite`, and a draft **never** replaces an active template (save under a new name; a person decides whether it replaces the active one).
- A draft runs only through `templates test` or a run a person starts, with response actions capped at `suggest`. A run started by a D&R rule or a case never uses a draft.
- Nothing is saved when validation reports an error.
- The CLI never rewrites a template's content beyond `status`: a rule's `when` can be a string, a list (all of) or `{any: [...]}`, and its `say` sentence is stored and printed as written. A template in the format the engine had before (`facts`, `proofs`, `evidence`, ...) is refused with `legacy_template_format`; the CLI converts nothing.
- Saving never lets the AI decide. That is the policy's `ai_may_decide` (below), which a person sets.

## Reference data

```bash
limacharlie investigate kit [--section schema|guide|operators|examples|policy|codes|packs|library]...
limacharlie investigate operators [--brief] [--name OP]... [--match TEXT]
limacharlie investigate packs [--brief] [--name PACK]
```

`kit` returns the template JSON Schema, the authoring guide, the org's typed operator catalogue (and which operators the org may use), examples, the effective policy and budgets, every validation code with its usual fix, and the fact packs. The `size` entry of the answer says what was returned. `--section library` returns the default template library; it needs an engine version that serves that section.

## How a run ends

A run ends with one `verdict.outcome`; `verdict.label` follows from it.

| Outcome | Meaning | `label` |
|---|---|---|
| `closed_by_rule`, `escalated_by_rule` | a rule decided. `verdict.decided_by` = `{kind: rule, rule, say}`: the rule id and its sentence | `false_positive`, `true_positive` |
| `closed_by_ai`, `escalated_by_ai` | an AI-assisted rule or the AI review decided, because the policy's `ai_may_decide` allows it for the template. `decided_by.kind` is `ai_rule` or `ai_review` | `false_positive`, `true_positive` |
| `ai_recommends_benign`, `ai_recommends_malicious` | the AI recommends and a person acts on it. `verdict.recommendation` = `{label, self_rated_confidence, rationale, citations, by}` | `inconclusive` |
| `couldnt_tell` | no rule decided and the AI did not recommend. `verdict.missing` lists `{step, reason, needed_by, ask}`: what could not be established, why, which rules or the review needed it, and the question for a person | `inconclusive` |
| `conflict` | a rule on each side held | `inconclusive` |

`self_rated_confidence` is the AI's own rating. It is shown, labeled as such, and never used to decide. A rule that reads an `ask_ai` answer is *AI-assisted* (`validate` lists them in `ai_rules`) and decides only where `ai_may_decide` allows; otherwise it recommends. `runs get` also shows `ai_may_decide` (the mode the run started with) and `ai_agent` (the AI agent record it uses). `runs steps` gives every step a `narrative`: `why` it ran, what it `found`, and what it was `used` for (`rule:<id>`, `ai_review`, `step:<id>`, `case`, or nothing).

The case document a run writes opens with the outcome sentence: the deciding rule's `say`, or the AI's recommendation and what was missing.

## Templates

Templates are plain Hive records (`investigation_plan`). Their YAML cannot contain a `name:` key: the record name is the template name (lowercase letters, digits, `-` and `_`, at most 64 characters).

```bash
limacharlie investigate templates list [--status draft|active]
limacharlie investigate templates get NAME [--yaml]
limacharlie investigate templates validate --file plan.yaml        # '-' reads stdin; exit 4 when invalid
limacharlie investigate templates test [NAME | --file plan.yaml] [samples] [options]
limacharlie investigate templates save NAME --file plan.yaml [--overwrite] [--comment TEXT] [--tag T]...
limacharlie investigate templates promote NAME --confirm
limacharlie investigate templates delete NAME --confirm
limacharlie investigate templates install-defaults [--name NAME]... [--overwrite]
```

A template, in short (this one is checked by the engine's own tests; `kit --section guide` has the full guide and `kit --section library` the default templates):

```yaml
status: draft
version: 1
description: "Escalate a message whose link lands on a password page a recipient reached; close one from a sender with history whose fired reasons are all explained."
applies_to: {detect_cat: ['mailsec-ai-triage']}
starts_from: message
gather:                      # what to read; steps can read each other with $step.field
  message: {op: mailsec.message_get, args: {msg_uuid: $msg_uuid}}
  sender_history:
    why: "Has this sender written to the org before?"
    op: mailsec.sender_profile
    args: {sender: '$message.sender', domain: '$message.sender_domain', before: '$message.received', exclude_group: '$message.group_id'}
  link_landing:
    op: mailsec.link_resolve
    args: {links: '$message.links', links_complete: '$message.links_complete', sender_domain: '$message.sender_domain', reply_to_domain: '$message.reply_to_domain', detonation: '$message.detonation'}
  recipients: {op: mailsec.group_recipients, args: {group_id: '$message.group_id'}}
  clicks:
    ask: "Did the recipients whose machines could not be checked open the link?"
    op: endpoint.click_check
    args: {copies: '$recipients.copies', domains: '$link_landing.malicious_domains', window: [{at: '$message.received'}, now]}
    only_if: 'link_landing.credential_harvest'   # skipped (and read as unknown) unless true
rules:                       # cheapest deciding rules first; the first that holds decides
  escalate:
    - id: clicked_credential_harvest
      when: ['link_landing.credential_harvest', 'clicks.any_clicked']
      say: "A link lands on a page that asks for a password, and a recipient's machine reached it after delivery."
  close:
    - id: known_sender
      when: [signals.all_explained, 'sender_history.prior_messages_30d > 0']
      say: "The sender wrote {sender_history.prior_messages_30d} message(s) in the last 30 days, and every reason Email Security flagged has a benign explanation."
explain_signals:
  ms_sender_first_contact:
    question: Is this really the first time this sender wrote to the org?
    malicious_when: 'sender_history.prior_messages_30d == 0'
    benign_when: 'sender_history.prior_messages_30d > 0'
act:
  - {class: contain.email, target: '$message.msg_id', attrs: {group_id: '$recipients.action_attrs.group_id'}, on_rules: [clicked_credential_harvest]}
case:
  mode: create
  severity: {escalated_by_rule: high, closed_by_rule: low, default: medium}
  kind: [phishing]
```

An `act` entry says which rules fire it with `on_rules: [<rule id> | ai_review]`. The key is `on_rules`, not `on`: YAML 1.1 parsers (Python's `yaml.safe_load`, many sync tools) read a bare `on:` as the boolean `true`, and the engine refuses an `on` key.

Add an `ai_review` (`question`, `sees`, `needs`) for what rules cannot decide, and `ask_ai` steps for a focused question a rule reads; both only recommend until the policy's `ai_may_decide` allows them to decide.

`validate` prints the report: `valid`, `errors` and `warnings` (each `{code, path, message, suggestion?}`), the worst-case step count, an `estimate` of the worst-case cost and `ai_rules` (the AI-assisted rules).

### Test on past alerts

`templates test` dry-runs a template on real past alerts. The plan's read-only operators run with your token; nothing is written (no run, case, label or action). `act` entries that would run are only listed in `would_propose`. A test counts against the org's concurrent run cap and may bill AI steps. Its numbers are for you: nothing blocks on them and nothing at run time reads them.

Samples (at most 25 after expansion):

| Flag | Sample |
|---|---|
| `--detection-id ID` | a stored detection |
| `--case-id ID` | a case; a closed case's classification is the expected label |
| `--detect-cat CATEGORY --last N` | the newest N alerts of a category (N is 1..25) |
| `--sample '{"inputs": {...}, "expected": "false_positive"}'` | free inputs with an optional expected label |
| `--samples-file FILE` | a YAML/JSON list of sample objects |

Use 5 to 10 samples and include known false **and** true positives. Each sample reports:

- `verdict`: the `outcome`, `decided_by` (`{kind, rule}`; a test result has no `say`), the AI's `recommendation` (no `rationale`) and `missing`;
- `expected` (the analyst's label, when there is one) and `agreement`: `{rule: agree|disagree|none, ai: agree|disagree|unclear|none}`;
- `unknowns`: the steps that could not be resolved and why (the usual cause is a wrong field path or argument).

The `summary` has `decided_by_rules` and `rule_share`, `rules` (per rule id: `decided`, `agree`, `disagree`), `ai` (`recommended`, `agree`, `disagree`, `unclear`), `by_outcome`, `unknown_reasons` and `cost_per_sample`. Read it in this order: `validation`, `summary`, each `disagree` (tighten or remove that rule), then `undecided` samples (`couldnt_tell`, `conflict`). A pattern the AI keeps recommending correctly is a candidate for a new rule. Compact output keeps problem steps in `problem_steps` and safe step diagnostics in `step_diagnostics`. Table and CSV rows show the outcome, who decided, both agreements, what the AI recommended, how much was missing and the AI cost; `unpriced` means USD is only the priced subtotal. `--include-steps` additionally retains the full step records and timing.

The command waits for the test (`--timeout`, default 600 s). A test still running prints its `test_id`; continue with `--test-id`. `--no-wait` returns right after the start. In table output the per-sample outcomes and the per-rule and AI summary are printed as text.

Exit codes: `0` done, `4` the template is `invalid` (the `validation` report says why), `1` the test failed.

### Save, promote, delete

`save` validates the exact text it stores, then writes the record as a draft and reads it back. A refusal (validation errors, existing record, active record) prints `{"saved": false, "reason": ...}` and exits `4`. `promote` validates again and writes conditionally on the version it read. `install-defaults` writes the engine's default template library, **never overwriting silently**: existing records are skipped with their installed and library versions (so an available update is visible) unless `--overwrite`. Library templates are installed as drafts; use `--status active` (a person's choice) to install them active.

## Runs

```bash
limacharlie investigate runs start (--template NAME | --file plan.yaml | --auto) \
    (--detection-id ID | --case-id ID | --entity-id ID | --question TEXT) \
    [--category C] [--severity S] [--priority N] [--tag T]... \
    [--input K=V]... [--inputs-json JSON] [--urgency low|medium|high|critical] [--mode triage|full|scope] \
    [--case-mode create|none|attach:ID] [--idempotency-key KEY] [--wait SECONDS] [--follow [--timeout SECONDS]] \
    [--trust-lookup NAME]... [--trust-value VALUE]...
limacharlie investigate runs get RUN_ID
limacharlie investigate runs list [--state S] [--outcome O] [--verdict V] [--template T] [--trigger T] [--entity E] \
    [--started-by user:UID] [--since TIME] [--until TIME] [--limit N] [--cursor C | --all]
limacharlie investigate runs events RUN_ID [--after SEQ] [--wait SECONDS] [--limit N] [--follow [--timeout S]]
limacharlie investigate runs steps RUN_ID [--values]
limacharlie investigate runs case RUN_ID
limacharlie investigate runs cancel RUN_ID [--revert-leases]
limacharlie investigate runs delete RUN_ID --confirm
```

`--auto` sends no plan, which is how the engine is asked to pick the **active** template whose `applies_to` matches the trigger (a draft is never picked; the engine refuses `plan.auto` itself for a person's run). `applies_to` keys are `detect_cat`, `severity`, `tag` and `source`; the first three are matched against `--category`, `--severity` and `--tag` (a start from the CLI always has `source: api`), so pass the alert's attributes. When no template matches, the start is refused with the reason. `--category`, `--severity`, `--priority` and `--tag` also select the run-scoped policy records. `--urgency` defaults to a value derived from `--priority` (8+ critical, 6+ high, 3+ medium, else low) or `--severity`, and medium when neither is given. A start is sent once and never retried automatically; `--idempotency-key` makes a repeated start return the same run (`joined: true`).

`runs delete` requires explicit `--confirm` and returns the engine's deletion response. It needs `investigation.set` + `insight.evt.get`. Deletion requests are sent once and are not automatically replayed after a gateway timeout. The API deployment must serve run deletion, which is newer than the other run routes; an older deployment answers 404 without an engine error code, and the CLI says so.

`runs list` filters: `--state` (queued, running, decided, completed, cancelled, failed, budget_exhausted), `--outcome` (one of the eight outcomes, or `undecided`), `--verdict` (the label: true_positive, false_positive, inconclusive, undecided), `--trigger` (the kind of trigger: detection, message, entity, case, question) and `--started-by` (an identity such as `user:UID` or `apikey:ID`, or a user's email or a key's name).

`--mode` is `full` by default (triage, scoping and containment); `triage` stops at the outcome and costs less, `scope` is for scoping an already-triaged alert. (`templates test` defaults to `triage`.)

`runs list` pages: structured formats print `{"runs": [...], "next_cursor": "..."}` and table/CSV/JSONL print rows with the cursor on stderr. Continue with `--cursor`, or use `--all`.

`runs events --follow` polls until the run is over and writes **one JSON event per line** (a text line in table mode), flushing as they arrive. It exits `0` when the run finished and `1` when `--timeout` (default 900 s) elapsed first; the resume point is printed on stderr (`--after N`). Events carry structure only, never customer values.

## Waves

A wave is a batch of questions: the engine runs every ready step in parallel with your token (no template, no outcome, no case), reuses what it already knows and can stop as soon as the answer is known.

```yaml
# wave.yaml
steps:
  - {id: host, use: host_context, args: {sid: "<SID>"}}
  - {id: prev, op: ioc.prevalence, args: {file_hash: "<SHA256>"}, select: [hosts_30d, seen]}
  - {id: kids, op: event.children, args: {sid: "<SID>", atom: "<ATOM>"}, limit: 5}
stop_when:
  - "prev.hosts_30d >= 50 and kids.count == 0"
deadline_ms: 20000
```

```bash
limacharlie investigate wave --file wave.yaml [--validate-only] [--full] \
    [--stop-when EXPR]... [--deadline-ms N] [--input K=V]...
```

A step has an `id` and exactly one of `op` (an operator) or `use` (a fact pack). The answer is compact: per step `status` (`ok`, `unknown` with a `reason`, `cancelled`, `partial`), `complete` (`false` means a lower bound, not proof of absence), `ms` and the selected `value`, plus `stopped_by` and `usage`. An `unknown` step established nothing: it is never an absence. `--full` returns raw values (many more tokens).

An invalid wave prints `{"valid": false, "errors": [...], "warnings": [...]}` with the engine's coded errors on **stdout** and exits `4`; `--validate-only` checks without running anything.

## Approvals and policy

```bash
limacharlie investigate actions list [--state awaiting_approval,proposed] [--class C] [--run-id ID] [--limit N] [--cursor C | --all]
limacharlie investigate actions approve RUN_ID ACTION_ID
limacharlie investigate actions deny RUN_ID ACTION_ID [--note TEXT]
limacharlie investigate policy get [--category C] [--priority N] [--severity S] [--target-tag T]... [--class C] [--template NAME]
limacharlie investigate policy ai
limacharlie investigate policy ai-set TEMPLATE|'*' off|escalate|close_and_escalate --confirm
limacharlie investigate policy status
limacharlie investigate policy pause
limacharlie investigate policy resume
```

`actions list` is the approvals inbox across all runs; what needs a person comes first.

`policy ai` shows what the AI may decide per template: the `ai_may_decide` field of the `default` policy record. `off` (the default when a template has no entry) means an AI-assisted rule or the AI review only recommends and a person acts on it; `escalate` lets it escalate; `close_and_escalate` lets it also close. `"*"` covers every template and a template's own entry wins. Only the `default` record grants; other records and run overrides can only lower it, and a run keeps the mode it started with. `policy ai-set` changes only that field of the record, conditional on the version it read, and needs `--confirm`: it is a person's decision about the org's automation, not an AI agent's. If Git Sync manages the `investigation_policy` hive, keep `ai_may_decide` in git too: the next sync overwrites a change made here. With no `default` record nothing is granted, so `ai-set TEMPLATE off` is a no-op and `ai-set '*' off` is refused. There are no confidence thresholds, mandatory checks or calibration in the policy any more; rules decide, and this switch says what the AI may.

`policy pause` stops automatic actions for the whole org by saving the enabled `investigation_policy` record `autonomy-manual-pause` (every action class held at `suggest`). Suggestions stay visible and a person can still approve; nothing already executed is undone. `policy resume` deletes the record, and the other policy records decide what new actions may do. `policy status` reads the record: `paused`, who last saved it, and an `inactive_reason` (`disabled`, `edited` or `expires`) when it exists but does not pause. `policy get` shows what the policy records allow right now. If Git Sync manages the `investigation_policy` hive, keep the pause in git too.

## Errors

In a structured output format (`--output json`, the default when piped) a failure is written to **stderr** as the engine's answer and the command exits non-zero:

```json
{
  "error": "the wave is invalid\n  [unknown_field] steps[0].select[0]: no such field (did you mean hosts_30d)",
  "status": 400,
  "error_code": "bad_request",
  "errors": [{"code": "unknown_field", "path": "steps[0].select[0]", "message": "no such field", "suggestion": "hosts_30d"}],
  "warnings": []
}
```

`error_code` is the engine's (`bad_request`, `forbidden`, `not_found`, `conflict`, `too_many_runs`, `not_implemented`, `unavailable`). A refused run start also carries `reason_code`, the specific cause (for example `no_template_applies`, `template_draft`, `unknown_template`); a refused policy field carries `path`, a JSON Pointer to it. In table mode the reason code ends the error message. It is absent when the answer did not come from the engine: a 404 without it means the feature is not enabled, and `suggestion` says what to check. Exit codes follow the CLI's: `2` authentication or permission, `3` not found, `4` validation or a refused result, `5` rate limit.

Every other failure is written the same way: a Hive or API error carries its `message`, HTTP `status` and the backend's code as `error_code` (the `lc_error_code` of a Hive answer, for example a refused promote), and a refused input file (unreadable, not YAML/JSON, wrong shape) carries `errors: [{code: invalid_input, path: --file, message}]` and exits `4`.

Templates, wave files and sample files are read the way the engine's YAML library reads them, not with YAML 1.1 rules, so `off`, `yes`, `no` and an unquoted date such as `2026-11-10` are text, not a boolean or a date. What an unquoted scalar means depends on where it is:

- In a template, under a step's `args` (and an `act` entry's `attrs`), a number is read as the engine reads it: `012` is 10, `1_000` is 1000, `0o17` and `0x1F` are 15 and 31, `1e3` is the float 1000, `.inf` and `.nan` are floats (refused, see below), and an unquoted date or timestamp is stored as its UTC RFC 3339 text (`2026-11-10` becomes `2026-11-10T00:00:00Z`). Quote a value (`"012"`, `"1e3"`) to keep it as text.
- Elsewhere in a template (`description`, `applies_to`, a rule's `when` and `say`, `only_if`, ...) a scalar is text exactly as written, except the numeric and boolean fields (`version`, `pack_version`, and `always` on a step). Mapping keys are always text.
- In a wave or samples file every unquoted scalar is read like an argument, except that a date stays the text you wrote.

`templates get --yaml` quotes every string that would otherwise read back as something else, and `templates save` / `promote` validate exactly the text they store. A value JSON cannot carry (`.nan`, `.inf`, `NaN`, `Infinity`) is refused as `invalid_input` before anything is sent.

## SDK

```python
from limacharlie.sdk.organization import Organization
from limacharlie.client import Client
from limacharlie.sdk.investigation import Investigation, InvestigationError

inv = Investigation(Organization(Client()))
report = inv.validate_plan(open("plan.yaml").read())
test = inv.wait_for_test(inv.test_plan([{"detect_cat": "my-category", "last": 10}], inline=open("plan.yaml").read()))
result = inv.save_template("my-plan", open("plan.yaml").read(), comment="10 samples")  # a draft
```

`InvestigationError` carries `status_code`, `error_code`, `issues` and `warnings`.

## Explicit trust

Templates may declare `trust: {lookups: [partner-domains], values: [partner.example.test]}`.
The identity starting the run needs `lookup.get` to read these same-org Lookup records.
For Autopilot this is the onboarding key, rather than an identity that only reads settings.
Repeat `--trust-lookup NAME` or `--trust-value VALUE` on `investigate runs start` to add
trust for that run only (up to 64 Lookup names and 100 nonblank inline values).
Runs started automatically by D&R rules or Autopilot use only the template's trust.
The manual `--auto` option selects a template and still allows these run-only additions.
A match accounts for the initial target as customer-declared trusted and skips active
analysis; it never means verified or benign. Domains include DNS-boundary subdomains
and URL hosts. Broad/shared entries and embedded URL destinations do not skip analysis.
Missing, disabled or unreadable Lookups grant nothing and appear as run problems.


`runs start --follow` waits up to 900 seconds by default; `--timeout 0` removes the time limit. Timeout, interruption and stream errors print an `--after N` resume point for `runs events RUN_ID --follow --after N`.

## Org-authored fact packs

Use `limacharlie investigate packs` to discover the caller's managed and org
packs. Store org packs with the existing Hive permissions
`investigation_plan.get`, `.set`, `.del`:

```sh
limacharlie investigate pack save fictional_pack --file pack.yaml
limacharlie investigate pack get fictional_pack
# Replace only the revision you read:
limacharlie investigate pack save fictional_pack --file pack.yaml --etag REVISION
limacharlie investigate pack delete fictional_pack --confirm
```

The Hive type is `investigation_pack`; its data is exactly `{"yaml":"<source>"}`.
The SDK methods are `org.investigation.get_pack`, `save_pack`, and `delete_pack`.
Sources are stored byte for byte. The server rejects invalid packs, unknown
fields, managed-name collisions and invalid dependencies. Packs cannot nest
packs. Deletion does not alter admitted snapshots.

Validation and the initial test response's `validation` include
`resolved_packs: [{scope, name, version, digest}]` for every version-only pack
pin, including descendant scopes such as `root/assessment`. SDK responses and
CLI JSON preserve this list exactly, alongside `ai_rules` and
`trust_provenance`, so each resolved digest can be copied into a `pack_digest`
lock on the `use` step:

```yaml
gather:
  context:
    use: fictional_context
    pack_version: 1
    pack_digest: 'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
```

Replace the example digest with the returned pack digest. `pack_digest` locks
pack source bytes on `use`. Inspect expanded plans and `trust_provenance` in JSON
output from the existing validate/test/run/wave commands. Trust is a declaration,
not verified analysis. Org packs require `org_fact_packs_v1`; check the
server's advertised capabilities before authoring against them.

## Performance statistics

```bash
limacharlie investigate stats [--template NAME] [--since RFC3339] [--until RFC3339]
```

Prints the engine's own numbers about its work: run volumes by state and outcome (`runs.by_outcome`), time to outcome, step and cache counts, search and AI cost, per-operator latency and errors, and what happened to the actions it proposed. The numbers are computed from the engine's records of runs, steps and actions, over at most the most recent runs that match the filters (`window.truncated` is `true` when more runs matched than were aggregated). The report describes what the engine did. It does not judge whether an outcome or an action was right, and nothing in it changes a decision: the `investigation_policy` record alone decides what the engine may do. Plain counts of the labels and corrections people submitted on runs are in `feedback: {labels, corrections}`.

`--since` and `--until` are RFC 3339 times on the run's creation time; `--template` limits the report to one template. It needs the same permissions as the other reads (`investigation.get` and `insight.evt.get`). The SDK call is `Investigation.get_stats(template=None, since=None, until=None)`, which returns the parsed response.

Inside `actions`, `by_class_state` counts actions per action class and engine action state. `by_template_class` is an array with one row per `(template, action_class)` that has at least one action in the window, ordered by template then action class:

```json
"actions": {
  "by_class_state": { "close.false_positive": { "executed": 7, "proposed": 2 } },
  "by_template_class": [
    {
      "template": "phishing-triage",
      "action_class": "close.false_positive",
      "total": 12,
      "suggested": 3,
      "approved": 4,
      "denied": 1,
      "expired": 1,
      "auto_executed": 5,
      "failed": 0,
      "undone": 1,
      "held": 2,
      "held_by_reason": { "policy_no_approvers": 1, "rate_cap": 1 },
      "by_state": { "executed": 8, "proposed": 2, "denied": 1, "expired": 1 }
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `total` | Actions of this template and class in the window. |
| `by_state` | The same actions by engine action state (same names as `by_class_state`). The values sum to `total`. |
| `suggested` | Recorded as a suggestion only: the policy mode is `suggest`, nothing was dispatched and no approval was asked. |
| `approved` | A person approved the action. |
| `denied` | A person denied the action. |
| `expired` | Nobody decided within the approval timeout. |
| `auto_executed` | Dispatched under mode `auto` with no person involved. |
| `failed` | Dispatch was attempted and failed. |
| `undone` | Reverted through the engine's own undo path. |
| `held` | Would have run automatically under the policy mode but was held. An action with several hold reasons counts once here. |
| `held_by_reason` | `held` split by the engine's stored hold reason (for example `rate_cap`). An action with several reasons counts once under each. Always an object, empty when nothing was held. |

The counters are not a partition of `total`: an approved action can later be undone, so it counts under both `approved` and `undone`. Use `by_state` when you need a partition. The exact rule behind each counter is in the engine documentation.

## See Also

- [Hive & Data Stores](hive-data.md) - the `investigation_plan` records are ordinary hive records
- [Detection & Response](detection-response.md) - D&R rules that start runs
