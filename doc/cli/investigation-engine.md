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
| Reads: runs, templates, operators, packs, kit, settings (`settings get`), test results, the approvals inbox | `investigation.get` + `insight.evt.get` |
| Reads: the run queue (`queue`) | `investigation.get` + `insight.evt.get` |
| Writes: start a run, wave, cancel, delete a run, flush the queue (`queue flush`), test a template, decide an action | `investigation.set` + `insight.evt.get` |
| Approve / deny an action | the writes above + the permission of the action's class (for example `sensor.task`, `mailsec.act`, `sensor.tag`) |
| `stats`, and `runs list --outcome` / `--verdict` | the reads above + `investigation_policy.set` |
| `settings pause` / `settings resume` | `investigation_policy.get` + `investigation_policy.set` (they read the `default` settings record and write its `paused` field; explicit grants, no default role has them). `settings get` is an engine read and needs only the reads above |
| Template records (`investigation_plan` hive) | `investigation_plan.get`, `investigation_plan.set`, `investigation_plan.del` (explicit grants; no default role has them) |

Waves and template tests always execute with **your own token**, so the operators enforce your permissions. A run started with `runs start` executes as the identity the organization's settings record (`investigation_policy/default`) names for its template: your token when the settings name none, otherwise the Hive secret they point to, in which case the operators enforce that secret's permissions and not yours. That identity's own platform permissions are the real limit on what a run can read and do. An active template can therefore reach data or take actions beyond your own permissions. Before you start one, check `limacharlie investigate settings get`: its `identity` shows the default identity, the allowed ones and where they come from. A finished run's `identity` field (`kind` caller or secret) records which one it used. Runs started by a detection rule or a case never have a caller and always use the settings' secret identity.

Live sensor metadata operators (`sensor.read.*`) need `sensor.task.read` (or the
broader `sensor.task`) plus `output.set` on the execution identity. Explicitly grant
`sensor.task.read` for an observe-only identity; no default or preset includes it.
It authorizes only allowlisted metadata commands, and only when the Investigation
Engine is enabled for the deployment. File contents, mutations and unknown
commands are refused server-side; with the gate off it grants no tasking. For an
observe-only identity, write no `act` entry that acts alone (`approval: none`).
Action permissions above remain unchanged.

## AI agent workflow

Hand an agent this loop. It never activates anything on its own: a person does the last step.

```bash
# 1. Learn the language, in parts (the whole kit is ~33k tokens)
limacharlie investigate kit --section guide --section settings --section codes
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
- A draft only suggests: through `templates test` or a run a person starts, every `act` entry is recorded as `suggested` and never executed or approvable. A run started by a D&R rule or a case never uses a draft.
- Every `act` entry is checked before it is saved: `approval` is required (a missing key is the error `missing_approval`), a reversible action needs `lease` and `on_lease_end`, and `class` is refused (`act_class_renamed`: it is `do`). Nobody gets an automatic action by omission.
- Nothing is saved when validation reports an error.
- The CLI never rewrites a template's content beyond `status`: a rule's `when` can be a string, a list (all of) or `{any: [...]}`, and its `say` sentence is stored and printed as written. A template in the format the engine had before (`facts`, `proofs`, `evidence`, ...) is refused with `legacy_template_format`; the CLI converts nothing.
- Saving never lets the AI decide on its own say-so: that is the template's `ai_may_decide` key (see [What a template does](#what-a-template-does-the-act-entry)), which the person who promotes the template reviews.

## Reference data

```bash
limacharlie investigate kit [--section schema|guide|operators|examples|settings|codes|packs|library]...
limacharlie investigate operators [--brief] [--name OP]... [--match TEXT]
limacharlie investigate packs [--brief] [--name PACK]
```

`kit` returns the template JSON Schema, the authoring guide, the org's typed operator catalogue (and which operators the org may use), examples, the org settings (budgets, pause, circuit breaker, whether an AI agent is configured), every validation code with its usual fix, and the fact packs. The `size` entry of the answer says what was returned. `--section library` returns the default template library; it needs an engine version that serves that section.

## How a run ends

A run ends with one `verdict.outcome`; `verdict.label` follows from it.

| Outcome | Meaning | `label` |
|---|---|---|
| `closed_by_rule`, `escalated_by_rule` | a rule decided. `verdict.decided_by` = `{kind: rule, rule, say}`: the rule id and its sentence | `false_positive`, `true_positive` |
| `closed_by_ai`, `escalated_by_ai` | an AI-assisted rule or the AI review decided, because the template's `ai_may_decide` allows it. `decided_by.kind` is `ai_rule` or `ai_review` | `false_positive`, `true_positive` |
| `ai_recommends_benign`, `ai_recommends_malicious` | the AI recommends and a person acts on it. `verdict.recommendation` = `{label, self_rated_confidence, rationale, citations, by}` | `inconclusive` |
| `couldnt_tell` | no rule decided and the AI did not recommend. `verdict.missing` lists `{step, reason, needed_by, ask}`: what could not be established, why, which rules or the review needed it, and the question for a person | `inconclusive` |
| `conflict` | a rule on each side held | `inconclusive` |

`self_rated_confidence` is the AI's own rating. It is shown, labeled as such, and never used to decide. A rule that reads an `ask_ai` answer is *AI-assisted* (`validate` lists them in `ai_rules`) and decides only where the template's `ai_may_decide` allows; otherwise it recommends. `runs get` also shows `ai_may_decide` (the mode the run started with, pinned from the template) and `ai_agent` (the AI agent record it uses). `runs steps` gives every step a `narrative`: `why` it ran, what it `found`, and what it was `used` for (`rule:<id>`, `ai_review`, `step:<id>`, `case`, or nothing).

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
ai_may_decide: off           # off | escalate | close_and_escalate: may the AI decide, or only recommend
act:
  - do: contain.email
    target: '$message.msg_id'
    attrs: {group_id: '$recipients.action_attrs.group_id'}
    on_rules: [clicked_credential_harvest]
    approval: required       # a person approves first
    lease: 12h               # reversible actions only
    on_lease_end: release    # undo it when the lease ends
  - do: close.false_positive
    on_rules: [known_sender]
    approval: none           # acts on its own
case:
  mode: create
  severity: {escalated_by_rule: high, closed_by_rule: low, default: medium}
  kind: [phishing]
```

An `act` entry says which rules fire it with `on_rules: [<rule id> | ai_review]`. The key is `on_rules`, not `on`: YAML 1.1 parsers (Python's `yaml.safe_load`, many sync tools) read a bare `on:` as the boolean `true`, and the engine refuses an `on` key.

### What a template does: the `act` entry

The template is the authority: no org-level policy sits above it, there are no per-class modes, and nothing intersects with an approver list. What a template does, who approves it and for how long is written in the template, so a reviewer reading it sees all of it. The identity the run executes as limits it through its own platform permissions. An AI agent writes templates and people read them: a template is a draft until a person makes it active, and making it active is the permission to act.

```yaml
act:
  - do: contain.network            # the action (was `class`)
    target: $sensor                # a step path or a literal; not on a close
    on_rules: [downloaded_then_run]
    approval: {when: '"server" in host.tags'}   # REQUIRED: none | required | {when: <expression>}
    approval_timeout: 1h           # optional, default 1h, 1m..7d
    lease: 2h                      # reversible actions only
    on_lease_end:                  # REQUIRED with lease
      check: template:host-still-suspicious
      args: {sid: $sensor}
      extend: 2h
      max: 24h
      at_max: hold                 # REQUIRED with `check`: hold | release
```

- **`do`**: `contain.network`, `contain.seal`, `contain.email`, `tag`, `tag.add`, `tag.remove`, `eradicate.file`, `close.false_positive`, plus custom actions the kit lists (`kit` `capabilities.action_classes` is the authoritative list). Any other class is refused at validation (`action_not_supported`). `class` is refused (`act_class_renamed`).
- **`approval`** is required on every entry and has no default. `none`: the action acts on its own. `required`: it always waits for a person. `{when: <expression>}`: it waits when the condition holds or is unknown, and acts on its own when it is false. The expression reads what a rule may read (gather steps, `starts_from` inputs, `org.*`, `signals.*`) and may read an AI answer ("approve when the AI is unsure" is legitimate). "Protect these hosts" is such a condition, or a shared `kind: check` template the condition reads: there is no org-side deny list. An action that waits is in `awaiting_approval` with a reason (`approval_required`, `approval_condition`, `paused`, `circuit_breaker`, `ai_recommendation`, `settings_unavailable`); a person approves or denies it with `actions approve|deny`, and it expires after `approval_timeout`.
- **`lease`** (1m..7d) is for reversible actions only (`contain.*`). Tags keep `attrs.ttl`; irreversible actions and the close take no lease (`lease_not_allowed`). **`on_lease_end`** says what happens when the lease runs out: `release` (undo it), `hold` (keep it until a person looks; the action becomes `held`, and a person can confirm or undo it) or `{check, args, extend, max, at_max}`: re-run the named check template, undo the action when it now says benign, otherwise extend the lease by `extend`, never past `max` from when the action took effect. At `max`, `at_max: hold` keeps it (`held`) and `at_max: release` undoes it. That is the automatic rollback of a false positive. Limits: `extend` defaults to the lease (1m..7d); `max` is required, 1h..30d and at least the lease; `at_max` is required with `check` (`bad_on_lease_end`, `bad_lease_max`, `bad_lease`). The check runs as its own run with the origin run's identity; it counts as benign only if it closed, and an AI close counts only where the origin template's `ai_may_decide` allows it. A run that executes with the caller's own token (one a person started) cannot hold or re-check past that token: for it `hold` and `check` behave as `release`, and the action records `lease_end_note: caller_token`. Runs started by a D&R rule always have a secret identity, so this affects person-started runs only.
- **The close** is an `act` entry too: `do: close.false_positive`, `on_rules` naming close rules or `ai_review`, and `approval`. It takes no `target`, `attrs`, `lease` or `on_lease_end`, and a template has at most one. Without a close entry a close verdict writes the case conclusion and closes nothing. A person's own decision on the case always wins over an automatic close.
- **`ai_may_decide`** is a top-level key of the template: `off` (default), `escalate` or `close_and_escalate`. A run pins it with the template. An action fired by an AI decision follows its own `approval`; an AI recommendation (the AI may not decide) fires the entries that name it and always waits for a person.
- **A draft template** and an inline plan only suggest: every entry is recorded as `suggested` and never executed.
- Removed from the entry: `authorize`, `before` (`unknown_field`).

`validate` summarizes each entry in `actions` (`do`, `approval`, `lease`, `on_lease_end`, `acts_alone_possible`), and `templates test` lists in `would_propose` the actions each sample would propose, with `approval` and whether it `would_wait`. A test never reads the pause or the circuit breaker.

A step says what the case shows of it with `record:` (one entry or a list; a `use:` step takes none). Kinds: `entity` (`entity_type`, `indicator`, `title`, `note` with `{step.path}` values, `malicious_when`, `benign_when`), `telemetry` and `artifact` (`source`, `type`, `ref`: ids only, never customer data). The verdict is `malicious` when `malicious_when` holds, else `benign` when `benign_when` holds, else `unknown`: an unknown never asserts a verdict. With `each` (a list in the step's result), one entity is written per element: `item_key` names the indicator, `outcome_key` the outcome word, `outcome_map` maps outcomes to verdicts, `absence` lists the outcomes that are claims of absence (they hold only on a complete step) and `outcome_notes` overrides the sentence per outcome. The engine adds, with no template, the telemetry of steps a rule or the review reads, an `entity.get` step's entity and the `mailsec/messages/<uuid>` artifact of each message step; what a step records itself replaces the default of the same kind. The paths are checked like references (`unknown_field`, `not_an_array`), and `bad_record_kind` / `entity_needs_indicator` are its own codes.

```yaml
gather:
  link_landing:
    op: mailsec.link_resolve
    args: {links: '$message.links'}
    record:
      kind: entity
      entity_type: domain
      indicator: link_landing.final_domain
      title: Where the link lands
      note: "The link lands on {link_landing.final_domain}."
      malicious_when: 'link_landing.open_redirect'
      benign_when: 'link_landing.via_tracker'
  clicks:
    op: endpoint.click_check
    args: {copies: '$recipients.copies'}
    record:
      kind: entity
      entity_type: account
      each: clicks.per_recipient
      item_key: recipient
      outcome_key: outcome
      outcome_map: {clicked: malicious, not_clicked: benign, unknown: unknown}
      absence: [not_clicked]
      outcome_notes: {clicked: "The recipient's machine looked up the landing domain after delivery."}
  message:
    op: mailsec.message_get
    args: {msg_uuid: $msg_uuid}
    record: {kind: artifact, source: mailsec, type: email, ref: 'mailsec/messages/{message.msg_uuid}'}
```

Add an `ai_review` (`question`, `sees`, `needs`) for what rules cannot decide, and `ask_ai` steps for a focused question a rule reads; both only recommend until the template's `ai_may_decide` allows them to decide.

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

`--auto` sends no plan, which is how the engine is asked to pick the **active** template whose `applies_to` matches the trigger (a draft is never picked; the engine refuses `plan.auto` itself for a person's run). `applies_to` keys are `detect_cat`, `severity`, `tag` and `source`; the first three are matched against `--category`, `--severity` and `--tag` (a start from the CLI always has `source: api`), so pass the alert's attributes. When no template matches, the start is refused with the reason. `--urgency` defaults to a value derived from `--priority` (8+ critical, 6+ high, 3+ medium, else low) or `--severity`, and medium when neither is given. A start is sent once and never retried automatically; `--idempotency-key` makes a repeated start return the same run (`joined: true`).

`runs delete` requires explicit `--confirm` and returns the engine's deletion response. It needs `investigation.set` + `insight.evt.get`. Deletion requests are sent once and are not automatically replayed after a gateway timeout. The API deployment must serve run deletion, which is newer than the other run routes; an older deployment answers 404 without an engine error code, and the CLI says so.

`runs list` filters: `--state` (queued, running, decided, completed, cancelled, failed, budget_exhausted, flushed, capped), `--outcome` (one of the eight outcomes, or `undecided`), `--verdict` (the label: true_positive, false_positive, inconclusive, undecided), `--trigger` (the kind of trigger: detection, message, entity, case, question) and `--started-by` (an identity such as `user:UID` or `apikey:ID`, or a user's email or a key's name).

`--mode` is `full` by default (triage, scoping and containment); `triage` stops at the outcome and costs less, `scope` is for scoping an already-triaged alert. (`templates test` defaults to `triage`.)

`runs list` pages: structured formats print `{"runs": [...], "next_cursor": "..."}` and table/CSV/JSONL print rows with the cursor on stderr. Continue with `--cursor`, or use `--all`.

`runs events --follow` polls until the run is over and writes **one JSON event per line** (a text line in table mode), flushing as they arrive. It exits `0` when the run finished and `1` when `--timeout` (default 900 s) elapsed first; the resume point is printed on stderr (`--after N`). Events carry structure only, never customer values.

## The run queue

```bash
limacharlie investigate queue
limacharlie investigate queue flush (--rule NAME | --template NAME | --all) [--note TEXT] [--yes]
```

An org runs at most `limits.max_parallel_runs` investigations at once (a field of the settings record, 1 to 2000, default 100). A start above that is never refused: it waits in the queue as a run in state `queued` and starts when a slot frees. A start that a template coalesces (`coalesce: sensor`, the default) joins the run already queued or running for that sensor instead of queueing another. An optional `limits.runs_per_hour` caps the starts of an hour: a start above the cap is recorded as a terminal run in state `capped` (never dropped silently), and the next hour starts again. Only runs that start count: a joined, flushed, capped or failed-to-start run does not.

`queue` shows the totals (`queued`, `claimed`, `running`, `max_parallel_runs`), `oldest_enqueued_at` and `oldest_wait_ms`, the queued count by urgency band (`by_band`), by rule (`by_rule`) and by template (`by_template`), the hour's counters (`hour`: `started`, `runs_per_hour`, `flushed`, `capped`, `resets_at`) and the recent flushes with their progress (`flushes`). The totals are exact for the moment the answer was read (`as_of`, at most a few seconds old) and the breakdowns come whole from the engine; the count `queue flush` shows before it asks is that number, and the flush cancels what is queued when it runs. It needs the reads of the other `investigate` commands.

`queue flush` cancels starts that are queued and not yet running. Name exactly one scope: a detection rule, a template, or `--all`. Each flushed start becomes a terminal run in state `flushed` that records who flushed it, when and your `--note`; its alert shows as not investigated. **Running investigations are not touched, and a flush cannot be undone.** A start that arrives after the flush began queues normally, so fixing a rule does not lose its new alerts. The command first reads the queue and tells you how many starts the flush cancels, then asks you to confirm; `--yes` skips the question (scripts and agents). The answer is `{"flush_id", "flushed", "done"}`: a large flush finishes in the engine while `done` is false, and `queue` shows its progress under `flushes`. A flush needs `investigation.set` + `insight.evt.get`, is sent once and is never retried, and is recorded in the org's audit log.

Where the engine of the organization's region does not serve the queue yet, both commands fail with "The run queue is not available on this deployment yet." (HTTP 501, `error_code` `not_implemented`).

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

## Approvals and settings

```bash
limacharlie investigate actions list [--state awaiting_approval,held,proposed] [--class C] [--run-id ID] [--limit N] [--cursor C | --all]
limacharlie investigate actions approve RUN_ID ACTION_ID
limacharlie investigate actions deny RUN_ID ACTION_ID [--note TEXT]
limacharlie investigate settings get
limacharlie investigate settings pause
limacharlie investigate settings resume
```

`actions list` is the approvals inbox across all runs; what needs a person comes first. An action waits for a person when its template says so (`approval: required`, or a `when` that holds or is unknown), when the AI only recommended it, or when the org is paused or the circuit breaker is over its cap. Anyone with the permission of the action's class can approve or deny it: there are no approver lists.

The org keeps three controls that belong to no single template, in the `default` record of the `investigation_policy` hive (the "settings"):

- **Pause** (`paused`): one emergency stop. While it is true nothing acts alone: an action that would have acted alone waits for a person. Runs still investigate, and approvals, denials, undos, lease ends and lease checks still work. Actions that waited stay waiting after the pause is lifted, until a person decides or `approval_timeout` passes.
- **Circuit breaker** (`circuit_breaker.per_hour`, default 20 in a sliding hour, 1..10000; `.per_run`, default 5, 1..1000): an org-wide cap on automatic containments, so one bad template cannot isolate a fleet. Over the cap an action waits for a person. It counts containment-family actions with no person involved, not closes, tags, approved actions, undos or lease extensions.
- **Plain settings**: the key the engine runs as (`identity`), where notifications go (`notify`, including `action.held`), which AI agent answers (`llm.agent`), run budgets, case mode and speculation.
- **Limits** (`limits.max_parallel_runs`, 1..2000, default 100; optional `limits.runs_per_hour`, at least 1, absent means no cap): how many investigations run at once and, optionally, how many start in an hour. They replace the old `budgets.max_concurrent_runs`. What waits, what is capped and how to flush it: see [The run queue](#the-run-queue).

`settings get` shows what the engine enforces: `paused`, `set_by` and `set_at` (who last saved the record and when: a pause is a field of the record, so this says who paused it unless someone saved the record again since), `circuit_breaker` with `used_last_hour` and `tripped`, the identity and whether it is ready, `notify`, `llm`, `budgets`, `limits`, `case` and `speculation`. `source: builtin` means the engine runs on its built-in settings: there is no record, or the only record stored does not parse (then `paused` is true, there is no identity and `warnings` says `settings_rejected`). With a rejected record the engine keeps its last good copy, so a `paused: true` you just wrote does not take effect until the record parses: always read `warnings`.

`settings pause` and `settings resume` set `paused` on the record and change nothing else in it: the write is conditional on the version read, so a concurrent edit is never overwritten, and pausing twice changes nothing. A record that does not exist yet is created holding only `paused: true`. A disabled record is refused for a pause, because the engine ignores it. The command fails when the saved record does not read back as paused (another writer or an expiry changed it in between). It writes the record and does not ask the engine: `settings get` is the check that the engine enforces it. A record that carries an expiry keeps it (the Hive deletes the whole record at the expiry, the pause with it); `settings pause` reports `expires` then. To change anything else in the settings, edit the `investigation_policy/default` record (`limacharlie hive`, or by IaC / Git Sync). If Git Sync manages the `investigation_policy` hive, keep the pause in git too: the next sync overwrites a change made here. These two commands need `investigation_policy.get` and `investigation_policy.set`.

The settings never override a template: whether an action acts alone, who approves it and the lease are written in the template, and `ai_may_decide` is a template key.

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

`error_code` is the engine's (`bad_request`, `forbidden`, `not_found`, `conflict`, `too_many_runs`, `not_implemented`, `unavailable`). A refused run start also carries `reason_code`, the specific cause (for example `no_template_applies`, `template_draft`, `unknown_template`); a refused settings field carries `path`, a JSON Pointer to it. In table mode the reason code ends the error message. It is absent when the answer did not come from the engine: a 404 without it means the feature is not enabled, and `suggestion` says what to check. Exit codes follow the CLI's: `2` authentication or permission, `3` not found, `4` validation or a refused result, `5` rate limit.

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
The identity the run executes with needs `lookup.get` to read these same-org Lookup records.
For a run started by a D&R rule that is the key the settings name for the template.
Repeat `--trust-lookup NAME` or `--trust-value VALUE` on `investigate runs start` to add
trust for that run only (up to 64 Lookup names and 100 nonblank inline values).
Runs started automatically by D&R rules use only the template's trust.
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

Prints the engine's own numbers about its work: run volumes by state and outcome (`runs.by_outcome`), time to outcome, step and cache counts, search and AI cost, per-operator latency and errors, and what happened to the actions it proposed. The numbers are computed from the engine's records of runs, steps and actions, over at most the most recent runs that match the filters (`window.truncated` is `true` when more runs matched than were aggregated). The report describes what the engine did. It does not judge whether an outcome or an action was right, and nothing in it changes a decision. Plain counts of the labels and corrections people submitted on runs are in `feedback: {labels, corrections}`.

`--since` and `--until` are RFC 3339 times on the run's creation time; `--template` limits the report to one template. It needs `investigation.get` and `insight.evt.get` plus `investigation_policy.set` (see Permissions). The SDK call is `Investigation.get_stats(template=None, since=None, until=None)`, which returns the parsed response.

Inside `actions`, `by_class_state` counts actions per action class and engine action state. `by_template_class` is an array with one row per `(template, action_class)` that has at least one action in the window, ordered by template then action class:

```json
"actions": {
  "by_class_state": { "contain.network": { "active": 7, "awaiting_approval": 2 } },
  "by_template_class": [
    {
      "template": "tmp-exec",
      "action_class": "contain.network",
      "total": 12,
      "acted_alone": 7,
      "waited": 4,
      "suggested": 1,
      "waited_by_reason": { "approval_required": 1, "approval_condition": 2, "paused": 0, "circuit_breaker": 1, "ai_recommendation": 0, "settings_unavailable": 0 },
      "approved": 3,
      "denied": 0,
      "expired": 1,
      "approval_timeouts": 1,
      "released_at_lease_end": 2,
      "released_by_check": 3,
      "held": 1,
      "withheld": 0,
      "failed": 0,
      "undone": 1,
      "by_state": { "active": 8, "reverted": 3, "held": 1 }
    }
  ]
}
```

| Field | Meaning |
|---|---|
| `total` | Actions of this template and class in the window. |
| `by_state` | The same actions by engine action state (same names as `by_class_state`). The values sum to `total`. |
| `acted_alone` | Executed with no person involved (`approval` was `none`, or its condition was false). |
| `waited` | Waited for a person (`approval`, a pause, the circuit breaker or an AI recommendation). |
| `waited_by_reason` | `waited` split by why the action waited (`approval_required`, `approval_condition`, `paused`, `circuit_breaker`, `ai_recommendation`, `settings_unavailable`). Always an object. |
| `suggested` | Recorded as a suggestion only: the template is a draft, nothing was dispatched and no approval was asked. |
| `approved` | A person approved the action. |
| `denied` | A person denied the action. |
| `expired` | Reached the `expired` state: nobody decided within the action's `approval_timeout`, or the run ended with the approval outstanding. |
| `approval_timeouts` | The part of `expired` that is the `approval_timeout` passing. |
| `released_at_lease_end` | Undone when its lease ended (`on_lease_end: release`). |
| `released_by_check` | Undone because the lease-end check said benign. |
| `held` | Kept in effect after the lease ended (`hold`, or a check that reached its `max`), or a close the product did not confirm, until a person looks. |
| `withheld` | Not executed because the engine withheld it (for example a person had already decided the case). |
| `by_outcome` | The same actions by the outcome of their run. |
| `failed` | Dispatch was attempted and failed. |
| `undone` | Reverted by a person through the engine's undo path. |

The counters are not a partition of `total`: an approved action can later be undone, so it counts under both `approved` and `undone`. Use `by_state` when you need a partition. The exact rule behind each counter is in the engine documentation.

## See Also

- [Hive & Data Stores](hive-data.md) - the `investigation_plan` records are ordinary hive records
- [Detection & Response](detection-response.md) - D&R rules that start runs
