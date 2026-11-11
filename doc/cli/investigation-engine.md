[Documentation](../README.md) > [CLI](README.md) > Investigation Engine

# Investigation Engine

Install or upgrade with `python -m pip install --upgrade limacharlie`. See [installation](../getting-started.md#installation) for setup.

The `investigate` group builds, tests and tunes Investigation Engine templates and runs investigations. The engine gathers facts for an alert with typed operators, weighs them and reaches a verdict (`true_positive`, `false_positive` or `inconclusive`) with a proof. A person or an AI agent (Claude Code, Codex, ...) can drive the whole loop from the CLI.

The Investigation Engine is **experimental and gated per deployment**. Where it is not enabled the API does not serve the routes and the CLI says so (a 404 with no engine error code). Where your organization has no engine, the API answers 503.

Every command supports `--ai-help`, and `limacharlie help investigation-engine` prints the workflow below. Output is JSON when piped (`--output` selects another format); see [output formats](README.md#output-formats).

## Permissions

All the listed permissions are required.

| Operation | Permissions |
|---|---|
| Reads: runs, templates, operators, packs, kit, policy, test results, the approvals inbox | `investigation.get` + `insight.evt.get` |
| Writes: start a run, wave, cancel, delete a run, test a template, decide an action | `investigation.set` + `insight.evt.get` |
| Approve / deny an action | the writes above + the permission of the action's class (for example `sensor.task`, `mailsec.act`, `sensor.tag`) |
| `policy pause` / `policy resume` | `org.conf.set` |
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
limacharlie investigate templates test --file plan.yaml --detect-cat my-category --last 10

# 5. Refine and repeat 3-4, then save a DRAFT with what you tested
limacharlie investigate templates save my-plan --file plan.yaml \
  --comment "10 samples: 9 agree, 1 undecided (index_lag), 0 errors"

# 6. A PERSON reviews the draft and its test results, then promotes it
limacharlie investigate templates promote my-plan --confirm
```

Rules the CLI enforces:

- `templates save` writes a **draft**. A source that says `status: active` is refused, and only a person's explicit `--status active` writes an active template. AI agents must not pass `--status active` and must not run `templates promote`.
- A record is never overwritten without `--overwrite`, and a draft **never** replaces an active template (save under a new name; a person decides whether it replaces the active one).
- A draft runs only through `templates test` or a run a person starts, with response actions capped at `suggest`. A run started by a D&R rule or a case never uses a draft.
- Nothing is saved when validation reports an error.
- The CLI never rewrites a template's content beyond `status`: a `report.summary` sentence can be a plain string or `{text, when}` (written only when the condition holds), and both are stored and printed as written.

## Reference data

```bash
limacharlie investigate kit [--section schema|guide|operators|examples|policy|codes|packs|library]...
limacharlie investigate operators [--brief] [--name OP]... [--match TEXT]
limacharlie investigate packs [--brief] [--name PACK]
```

`kit` returns the template JSON Schema, the authoring guide, the org's typed operator catalogue (and which operators the org may use), examples, the effective policy and budgets, every validation code with its usual fix, and the fact packs. The `size` entry of the answer says what was returned. `--section library` returns the default template library; it needs an engine version that serves that section.

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

`validate` prints the report: `valid`, `errors` and `warnings` (each `{code, path, message, suggestion?}`), the worst-case step count and an `estimate` of the worst-case cost.

### Test on past alerts

`templates test` dry-runs a template on real past alerts. The plan's read-only operators run with your token; nothing is written (no run, case, label or action). Response steps that would run are only listed in `would_propose`. A test counts against the org's concurrent run cap and may bill LLM steps.

Samples (at most 25 after expansion):

| Flag | Sample |
|---|---|
| `--detection-id ID` | a stored detection |
| `--case-id ID` | a case; a closed case's classification is the expected label |
| `--detect-cat CATEGORY --last N` | the newest N alerts of a category (N is 1..25) |
| `--sample '{"inputs": {...}, "expected": "false_positive"}'` | free inputs with an optional expected label |
| `--samples-file FILE` | a YAML/JSON list of sample objects |

Use 5 to 10 samples and include known false **and** true positives. Each sample reports a verdict, the `expected` label when there is one, and an `agreement` of `agree`, `disagree`, `undecided` or `none`; `summary.agreement_rate` is the share that agreed. `unknowns` lists the facts that could not be resolved and why (the usual cause is a wrong field path or argument). Steps that succeeded are dropped from the output (`problem_steps` keeps the others); `--include-steps` keeps all.

The command waits for the test (`--timeout`, default 600 s). A test still running prints its `test_id`; continue with `--test-id`. `--no-wait` returns right after the start. In table output the per-sample verdicts and the agreement summary are printed as text.

Exit codes: `0` done, `4` the template is `invalid` (the `validation` report says why), `1` the test failed.

### Save, promote, delete

`save` validates the exact text it stores, then writes the record as a draft and reads it back. A refusal (validation errors, existing record, active record) prints `{"saved": false, "reason": ...}` and exits `4`. `promote` validates again and writes conditionally on the version it read. `install-defaults` writes the engine's default template library, **never overwriting silently**: existing records are skipped with their installed and library versions (so an available update is visible) unless `--overwrite`. Library templates are installed as drafts; use `--status active` (a person's choice) to install them active.

## Runs

```bash
limacharlie investigate runs start (--template NAME | --file plan.yaml | --auto) \
    (--detection-id ID | --case-id ID | --entity-id ID | --question TEXT) \
    [--category C] [--severity S] [--priority N] [--tag T]... \
    [--input K=V]... [--inputs-json JSON] [--urgency low|medium|high|critical] [--mode triage|full|scope] \
    [--case-mode create|none|attach:ID] [--idempotency-key KEY] [--wait SECONDS] [--follow]
limacharlie investigate runs get RUN_ID
limacharlie investigate runs list [--state S] [--verdict V] [--template T] [--trigger T] [--entity E] \
    [--started-by user:UID] [--since TIME] [--until TIME] [--limit N] [--cursor C | --all]
limacharlie investigate runs events RUN_ID [--after SEQ] [--wait SECONDS] [--limit N] [--follow [--timeout S]]
limacharlie investigate runs steps RUN_ID [--values]
limacharlie investigate runs case RUN_ID
limacharlie investigate runs cancel RUN_ID [--revert-leases]
limacharlie investigate runs delete RUN_ID --confirm
```

`--auto` sends no plan, which is how the engine is asked to pick the **active** template whose `applies_to` matches the trigger (a draft is never picked; the engine refuses `plan.auto` itself for a person's run). `applies_to` keys are `detect_cat`, `severity`, `tag` and `source`; the first three are matched against `--category`, `--severity` and `--tag` (a start from the CLI always has `source: api`), so pass the alert's attributes. When no template matches, the start is refused with the reason. `--category`, `--severity`, `--priority` and `--tag` also select the run-scoped policy records. `--urgency` defaults to a value derived from `--priority` (8+ critical, 6+ high, 3+ medium, else low) or `--severity`, and medium when neither is given. A start is sent once and never retried automatically; `--idempotency-key` makes a repeated start return the same run (`joined: true`).

`runs delete` requires explicit `--confirm` and returns the engine's deletion response. It needs `investigation.set` + `insight.evt.get`. Deletion requests are sent once and are not automatically replayed after a gateway timeout. The API deployment must serve run deletion, which is newer than the other run routes; an older deployment answers 404 without an engine error code, and the CLI says so.

`runs list` filters: `--state` (queued, running, decided, completed, cancelled, failed, budget_exhausted), `--verdict` (true_positive, false_positive, inconclusive, undecided), `--trigger` (the kind of trigger: detection, message, entity, case, question) and `--started-by` (an identity such as `user:UID` or `apikey:ID`, or a user's email or a key's name).

`--mode` is `full` by default (triage, scoping and containment); `triage` stops at the verdict and costs less, `scope` is for scoping an already-triaged alert. (`templates test` defaults to `triage`.)

`runs list` pages: structured formats print `{"runs": [...], "next_cursor": "..."}` and table/CSV/JSONL print rows with the cursor on stderr. Continue with `--cursor`, or use `--all`.

`runs events --follow` polls until the run is over and writes **one JSON event per line** (a text line in table mode), flushing as they arrive. It exits `0` when the run finished and `1` when `--timeout` (default 900 s) elapsed first; the resume point is printed on stderr (`--after N`). Events carry structure only, never customer values.

## Waves

A wave is a batch of questions: the engine runs every ready step in parallel with your token (no template, no verdict, nothing stored), reuses what it already knows and can stop as soon as the answer is known.

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
limacharlie investigate policy status
limacharlie investigate policy pause
limacharlie investigate policy resume
```

`actions list` is the approvals inbox across all runs; what needs a person comes first. `policy pause` stops automatic actions for the whole org (the kill switch) and needs `org.conf.set`.

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

`error_code` is the engine's (`bad_request`, `forbidden`, `not_found`, `conflict`, `too_many_runs`, `not_implemented`, `unavailable`). It is absent when the answer did not come from the engine: a 404 without it means the feature is not enabled, and `suggestion` says what to check. Exit codes follow the CLI's: `2` authentication or permission, `3` not found, `4` validation or a refused result, `5` rate limit.

Every other failure is written the same way: a Hive or API error carries its `message`, HTTP `status` and the backend's code as `error_code` (the `lc_error_code` of a Hive answer, for example a refused promote), and a refused input file (unreadable, not YAML/JSON, wrong shape) carries `errors: [{code: invalid_input, path: --file, message}]` and exits `4`.

Templates, wave files and sample files are read the way the engine's YAML library reads them, not with YAML 1.1 rules, so `off`, `yes`, `no` and an unquoted date such as `2026-11-10` are text, not a boolean or a date. What an unquoted scalar means depends on where it is:

- In a template, under a fact's `args`, a number is read as the engine reads it: `012` is 10, `1_000` is 1000, `0o17` and `0x1F` are 15 and 31, `1e3` is the float 1000, `.inf` and `.nan` are floats (refused, see below), and an unquoted date or timestamp is stored as its UTC RFC 3339 text (`2026-11-10` becomes `2026-11-10T00:00:00Z`). Quote a value (`"012"`, `"1e3"`) to keep it as text.
- Elsewhere in a template (`description`, `applies_to`, `inputs`, ...) a scalar is text exactly as written, except the numeric and boolean fields (`version`, `prior`, the weights, `predict`, `case` on a fact). Mapping keys are always text.
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

## See Also

- [Hive & Data Stores](hive-data.md) - the `investigation_plan` records are ordinary hive records
- [Detection & Response](detection-response.md) - D&R rules that start runs
