[Documentation](../README.md) > [CLI](README.md) > Cloud Security

# Cloud Security (CNAPP) & Code Security

Commands for the LimaCharlie Cloud Security surface: the merged, risk-ranked findings worklist (CSPM misconfigurations + attack paths + CIEM + code and container-image vulnerabilities), the cloud resource inventory and security graph, compliance assessment (live and audit-grade), the risk overview, CAASM (third-party asset attack surface), the AppSec code lane and container-image inventory, sensor↔cloud-asset resolution, finding triage, CSV exports, and the multi-org fleet overview.

Reads require the `cloudsec.get` permission and writes require `cloudsec.set`. Every command requires the org to be subscribed to the `ext-cloud-security` extension:

```bash
limacharlie extension subscribe --name ext-cloud-security
```

Provider credentials and the cloudsec policies are hive records — manage them with the hive commands (`limacharlie hive list cloudsec_provider`, `... cloudsec_policy`, `... cloudsec_query`, `... cloudsec_code_rule`).

Every command supports `--ai-help` for a detailed description with examples.

## Overview & posture

```bash
limacharlie cloudsec overview --trend-days 90     # composed risk overview
limacharlie cloudsec risk-trend --trend-days 90   # score history (sparkline)
limacharlie cloudsec changes --limit 100          # recent created/closed findings
limacharlie cloudsec scan-status --provider aws   # collection sweep status
limacharlie cloudsec chokepoint list              # shared attack-path hops
limacharlie cloudsec chokepoint dismiss "lcrn:..." --reason "planned decom"
limacharlie cloudsec chokepoint restore "lcrn:..."
limacharlie cloudsec free-tier                    # tier + provider usage vs the limits
```

`free-tier` only DESCRIBES the free-tier limits — the collector and the provider-record validator enforce them, so a limit applies whether or not you ask. `enabled_providers` is omitted rather than zeroed when the count could not be read, so an absent field means "unknown", never "none configured". There is no trial countdown: the authoritative clock lives in the datacenter, and a gated collection reports its reason through `scan-status`.

## Fleet (multi-org, MSSP)

One posture row per authorized org, plus cross-tenant rollups on the first page. With user-scoped credentials the CLI mints a temporary multi-org token, so the fleet is not limited to the configured `--oid`.

```bash
limacharlie cloudsec fleet overview
limacharlie cloudsec fleet overview --group <GROUP_ID> --trend-days 90
limacharlie cloudsec fleet overview --oid <OID1> --oid <OID2>
```

## Findings

Repeatable filters are OR within a key and AND across keys, and every one of them is truncated at 100 values by the API with no error and no signal in the response — a script fanning out over more than 100 repositories, owners or image urns has to batch them. Finding classes: `toxic_combination`, `public_exposure`, `ciem_risk`, `privilege_escalation`, `vulnerability`, `misconfig`, `coverage_gap`. Sort keys: `lc_risk` (default), `severity`, `first_seen`.

`--owner` filters by assigned owner and `--unassigned` selects the untriaged bucket; they combine, so "mine or nobody's" is one filter with both. On `finding facets` the `owner` facet is capped at the top 50 owners by count (`owner_truncated` reports whether any were dropped) — `--owner-pin` keeps named owners in it even when they would not rank in, and filters nothing. That is bounded by the same cap: pins share the 50 slots with any `--owner` values, so past ~50 combined a pin can still be dropped and `owner_truncated` will not say so.

`finding causes` groups findings by the mutable object whose single edit resolves all of them, so a worklist can be worked by fix instead of by row. It takes the same filters as `finding list`; `distinct` is the total number of matching causes, so you can see how much tail the ranked head hides. `--cause` narrows any of `finding list`, `finding facets` and `export findings` to one cause's findings.

### Vulnerability selectors

`--grain`, `--fix-state` and `--exploit-band` are the vulnerability noise controls, and `--image-urn` is the pivot from a container image to its findings. All four work on `finding list`, `finding facets`, `finding causes` and `export findings`.

**`--grain` is the one filter whose ABSENCE is not "no constraint."** The default worklist leads with the `package` grain — "upgrade `<pkg>` on host X, closing N CVEs" — and excludes the per-CVE rollups a package finding already states pair for pair, so the same pair is never counted twice under two rule ids. Without `--grain cve` the per-CVE findings are unreachable. The `grain` facet always reports the full per-grain population, so you can see what the default is holding back.

| Filter | Values |
|---|---|
| `--grain` | `package`, `cve`, `other` (container-image and source-repository lanes) |
| `--fix-state` | `fix_available`, `no_fix`, `unknown` |
| `--exploit-band` | `kev_overdue`, `kev_due`, `exploit_likely`, `exploit_probable`, `elevated`, `baseline`, `none` |

`unknown` is a first-class fix state and NOT a synonym for `no_fix` — a fixed version nobody collected is not a fix that does not exist; `no_fix` is asserted only on a positive signal. KEV dominates EPSS, and a KEV entry with no parseable due date bands `kev_due`, never `kev_overdue`. All three vocabularies are validated client-side, because dropping a `--grain` value would silently re-engage the default and answer a different question successfully.

```bash
limacharlie cloudsec finding list --grain cve --exploit-band kev_overdue
limacharlie cloudsec finding list --class vulnerability --fix-state fix_available
limacharlie cloudsec finding list --image-urn "lcrn:...:lc:container-image:sha256:..."
limacharlie cloudsec finding facets --grain cve --grain package   # the full population
```

```bash
limacharlie cloudsec finding list --severity CRITICAL --severity HIGH
limacharlie cloudsec finding list --class public_exposure --kev
limacharlie cloudsec finding list --owner alice@corp.com --unassigned
limacharlie cloudsec finding facets --status open
limacharlie cloudsec finding facets --owner-pin me@corp.com
limacharlie cloudsec finding causes --severity CRITICAL --limit 5
limacharlie cloudsec finding causes --cause "lcrn:...:firewalls/allow-all"
limacharlie cloudsec finding get fnd_0123abcd

# Triage
limacharlie cloudsec finding resolve fnd_abc --kind mitigated --reason "SG tightened"
limacharlie cloudsec finding resolve fnd_abc --kind open        # reopen
limacharlie cloudsec finding bulk-resolve --finding-id fnd_a --finding-id fnd_b --kind false_positive
limacharlie cloudsec finding set-owner fnd_abc --owner alice@corp.com
limacharlie cloudsec finding set-ticket fnd_abc --ticket JIRA-123
```

### Runtime check: did that code actually run?

`finding runtime-check` asks whether the vulnerable package behind a finding was
actually running on the finding's cloud resource, using the endpoint telemetry
LimaCharlie already retains. It is **informational**: it never changes the finding's
risk score, status, identity or disposition.

```bash
limacharlie cloudsec finding runtime-check fnd_0123abcd
limacharlie cloudsec finding runtime-check fnd_0123abcd --verdict
limacharlie cloudsec finding runtime-check fnd_0123abcd --packages
```

The answer is one of **five** rungs, and only one of them is negative:

| Rung | Means |
|---|---|
| `unknown` | no usable evidence: missing, stale, expired, unattributable or conflicting |
| `present` | an agent is on the resource, but the telemetry cannot carry a claim |
| `not_observed` | a **complete** telemetry window saw the package never run |
| `loaded` | the package is mapped into a running process |
| `executing` | the package **is** the running executable |

**`not_observed` is not a safety claim.** It says a complete window did not see the
code run — not that the package is gone, that the finding is fixed, or that the
vulnerability is not exploitable. Nothing this command returns proves anything about
exploitability.

**A telemetry lapse never produces a negative.** An interrupted or too-young window,
a shed write, a truncated watch list, a package with no version and an unattributable
package all come back as `present` or `unknown` **with a `reason`** explaining which
gate failed. A negative is reported only for a complete window over a complete sensor
set.

**Asking is what starts the measurement**, which is why the route is a POST. The check
publishes the finding's packages as relevant so the agents begin summarizing them, and
evidence accumulates over the following minutes. A **first call is expected to be
inconclusive**: `complete: false` with a `retry_after_seconds` means the window has not
matured yet, so ask again. That is not a finished answer.

**The runtime-evidence feature is default-off.** With it off the call still succeeds and
returns `accepted: false` with reason `feature_disabled` — an explicit "we did not run",
never a fabricated verdict. Read `accepted` before reading `status`. The same shape
covers `no_resource`, `no_packages`, `no_sensors` and `cache_unavailable`; an unknown
finding id returns `runtime: null`.

The response is `{"accepted": …, "runtime": {…}}`. `runtime` carries the server's
whole-resource verdict at the top (`status`, `reason`, `level`, `source`) alongside
`resource_urn`, `sensors`, `sensors_complete`, `complete`, `checked_at` and `packages`
— one flat row per package.

`--verdict` prints that whole-resource verdict; `--packages` prints just the rows.
`--verdict` is a **field read, not a local fold**: the backend computes the verdict, and
re-deriving it from the rows is the one mistake worth naming — the negative rung ranks
*below* `present` on purpose, so taking the strongest per-package answer reports a
whole-machine negative whenever nothing positive turned up, losing the veto that a
single incomplete package (or an incomplete sensor set) is supposed to exercise.

`dormant`, the old spelling of `not_observed`, is decoded on read and never emitted.

> This command needs a gateway route that is **not deployed yet**
> (`POST /cloudsec/{oid}/findings/{id}/runtime-check`). Until it ships the command
> fails the way any unknown route does, rather than answering from nothing.

## Attack paths & CIEM

`ciem facets` and `ciem identities` take the SAME cross-filter, so the rail's counts describe the population the list returns — with one exception: the no-tier bucket `--unclassified` selects is skipped when counting, so it is the only selection the rail cannot give a count for (the same is true of `--unclassified` on `data-security`). The boolean filters are tri-state: omitting one leaves the dimension unconstrained, which is not the same as pinning it false. `--mfa unknown` is everyone the MFA question does not apply to (no identity-provider observation, or non-human) — it is not `off`.

`--risk-band` and `--criticality` are closed vocabularies (`critical`, `high`, `medium`, `low`) validated client-side, because the backend fails closed: an unrecognized value would return zero rows with a successful exit. `--unclassified` selects identities with no tier assigned and combines with `--criticality`.

```bash
limacharlie cloudsec attack-path list --severity CRITICAL
limacharlie cloudsec ciem public-access    # public/external access to sensitive resources
limacharlie cloudsec ciem facets --kind service_account --admin
limacharlie cloudsec ciem identities --limit 50            # ranked, paginated population
limacharlie cloudsec ciem identities --external --with-sensitive
limacharlie cloudsec ciem identities --mfa off --admin
limacharlie cloudsec ciem identities --risk-band critical --unclassified
limacharlie cloudsec ciem identity "lcrn:gcp:...:serviceAccount/deploy"   # one identity
```

## Inventory, resources & data security

`data-security facets` and `data-security stores` share their selectors for the same reason (with the same `--unclassified` exception). `--sensitive` / `--public` are tri-state (`--no-sensitive` / `--no-public` pin them false). `--tier` takes the same closed tier vocabulary as `--criticality` above, with `--unclassified` for stores that have none.

```bash
limacharlie cloudsec inventory list --type gcp_bucket --region us-central1
limacharlie cloudsec inventory list --provider okta      # scope to one provider's sweep
limacharlie cloudsec inventory facets
limacharlie cloudsec data-security facets                # DSPM data-store rollup
limacharlie cloudsec data-security stores --sensitive --public
limacharlie cloudsec data-security stores --store-kind bucket --data-class pii
limacharlie cloudsec resource get "lcrn:gcp:...:bucket/prod-data"
```

## Security graph & queries

```bash
limacharlie cloudsec graph neighbors "lcrn:...instance/web-1" --limit 500
limacharlie cloudsec query list
limacharlie cloudsec query run --named public-buckets
limacharlie cloudsec query run --text "public bucket with sensitive data"
```

## Compliance

`compliance report` is the LIVE, point-in-time assessment: ask it and it answers about the estate as it is now, keeping nothing.

```bash
limacharlie cloudsec compliance frameworks
limacharlie cloudsec compliance report --framework cis-aws
limacharlie cloudsec compliance assignments              # scoped assignments
limacharlie cloudsec compliance report --assignment prod-scope
```

`score` covers ASSESSABLE controls only, and `low_coverage` is true when that is under half the gradeable ones — never show the score without the coverage beside it. Check `applicable` first: false means nothing was assessable at all, so a `0` there does not mean "failed everything" — and `low_coverage` is false in that case too, because it is only computed when `applicable` is true.

### Audit-grade compliance (immutable runs, attestations, drift)

For when somebody has to prove what was true on a date. `compliance run` PERSISTS an assessment as an immutable run; the rest read it.

```bash
limacharlie cloudsec compliance run --assignment prod-scope
limacharlie cloudsec compliance run --assignment prod-scope --run-id 2026-Q3   # idempotent
limacharlie cloudsec compliance runs --assignment prod-scope --framework cis-aws
limacharlie cloudsec compliance runs --run-id <RUN_ID>          # one run + its controls
limacharlie cloudsec compliance events --days 30                # the drift stream
limacharlie cloudsec compliance export --run-id <RUN_ID> --format pdf -o run.pdf
limacharlie cloudsec compliance attestations --assignment prod-scope
limacharlie cloudsec compliance attest --assignment prod-scope --input-file att.json
limacharlie cloudsec compliance schedules
limacharlie cloudsec compliance schedule-set --input-file schedule.json
```

`compliance run` is the expensive verb: it evaluates every control against the estate and, WITHOUT `--run-id`, writes a new run every time (the generated id embeds the current time, so two calls a second apart make two runs). Pass `--run-id` to make a retry idempotent — it replays the stored run, and is refused rather than quietly assessing something else if the scope moved.

`compliance runs` does NOT derive the framework from the assignment the way `compliance run` does: pass both or neither, because an assignment without its matching framework returns an empty list rather than an error.

`--days` and `--limit` on `compliance events` have ceilings (3650 and 1000), and an ask above a ceiling falls back to the DEFAULT rather than clamping to it — `--days 5000` gives 90 days, not 3650.

`compliance events` is a CHANGE-ONLY stream. A control that stayed PASS across ten runs produces one event, not ten, so an empty window means "nothing moved," never "nothing ran."

`compliance export` reads the STORED run, never the live estate, and the JSON snapshot carries no generation timestamp on purpose — exporting the same run id a year from now returns the same bytes. `-o` decodes and writes the document; without it the envelope prints with `content` base64-encoded. The PDF is an executive handoff, one line per control; use `json` or `csv` when something downstream has to parse it.

**Attestations are append-only immutable revisions** — manual evidence for a control no detector can grade. Required: `id`, `revision` (≥ 1), `control_key`, `outcome` (`pass`/`fail`/`not_applicable`), `effective_at` and `expires_at`. The server stamps the attribution and the scope over anything you send.

`approved_at` is optional to write and load-bearing to use: an attestation without it is stored and returned but **never counts toward a control**, so omitting it writes a record that silently does nothing. `rationale` is not validated either, but it is the only field that says why a human asserted this — write it. `evidence_refs` entries must be `https://`, `output://` or `ticket://` urls with no embedded credentials.

Only a revocation is pinned to exactly `previous + 1`, because the server copies that prior revision forward. An ordinary superseding revision is merely inserted, so its `(id, revision)` must be unused — and since only the highest revision of an id is ever consulted, one written below the current high-water mark is accepted and then inert. Nothing refuses it, so raise the number yourself.

REVOCATION IS A LATER REVISION, never a delete: re-send the same `id` with `revision` exactly one higher and a `revoked_at`. Everything else in that body is ignored — the server carries the previous revision forward and overlays only those two fields, so the original author's attribution survives and yours is recorded separately. An attestation counts only while approved, unrevoked, inside its window, and while its framework version, control key and scope still match; editing an assignment's scope silently orphans the attestations written under the old one.

A schedule needs `id`, `assignment`, `framework_id`, `owner`, `cadence` (`weekly`/`monthly`), `delivery` (`output`/`email`/`webhook`), `destination_ref`, `formats` and `next_run_at`, plus a `revision` an edit must RAISE (any higher value, not strictly `+1`) — it is an optimistic-concurrency token, not a version label. `destination_ref` must be an `output://` or `secret://` reference; credentials never travel inline.

## Azure scope hierarchy

```bash
limacharlie cloudsec azure scope-hierarchy
```

Tenant → management group → subscription → resource group → resource containment evidence. `traversable` is `false`, and that is a contract rather than a status that might change: containment can explain inherited authorization, but it must never become a free traversal step in a graph query, because "contained by" is not "can reach."

## CSV exports

The server walks the full filtered set (no pagination), capped at 100k rows; a trailing `#` comment row marks a truncated export.

```bash
limacharlie cloudsec export findings -o findings.csv --severity CRITICAL
limacharlie cloudsec export findings --owner alice@corp.com   # same filters as 'finding list'
limacharlie cloudsec export inventory -o inventory.csv --provider gcp
limacharlie cloudsec export compliance -o cis-gcp.csv
limacharlie cloudsec export query --named public-buckets -o rows.csv
```

## Sensor ↔ cloud asset resolution

```bash
limacharlie cloudsec resolve sensors <SID1> <SID2>       # sensor -> cloud asset
limacharlie cloudsec resolve assets "lcrn:...instance/web-1"  # asset -> sensors
```

## CAASM (third-party asset attack surface)

```bash
limacharlie cloudsec caasm assets -q laptop --limit 50
limacharlie cloudsec caasm coverage --status open --severity HIGH
limacharlie cloudsec caasm policy get
limacharlie cloudsec caasm policy set --input-file policy.yaml
limacharlie cloudsec caasm ingest --source okta --records-file users.json
```

Ingest sources today: `sentinelone`, `crowdstrike`, `defender`, `okta`, `entraid`, `ms_graph`, `wiz` (the registry grows and is validated server-side).

## Providers

```bash
limacharlie cloudsec provider test --input-file provider.yaml   # credential preflight (ephemeral)
limacharlie cloudsec provider manifest                          # coverage manifests, all providers
limacharlie cloudsec provider manifest --type gcp
```

Saved provider configs live in the `cloudsec_provider` hive:

```bash
limacharlie hive set --hive-name cloudsec_provider --key my-gcp --input-file provider.json --enabled
```

## Code Security: the hosted code lane

The lane scans a connected source-control organization's repositories and emits findings into the SAME worklist the cloud collectors feed, so the findings themselves are read with `cloudsec finding list --repo <owner>/<name>`. The commands here are the repository-shaped views and triggers that worklist cannot give you.

```bash
limacharlie cloudsec code repos --with-findings --all
limacharlie cloudsec code status                       # run status per connection
limacharlie cloudsec code capabilities --repo acme/api # what the connection may DO
limacharlie cloudsec code fixes --all                  # the dependency-upgrade queue
limacharlie cloudsec code sbom --repo acme/api -o sbom.json.gz
limacharlie cloudsec code rescan acme/api --ref refs/heads/main
limacharlie cloudsec code autofix <FINDING_ID>         # open the upgrade PR
limacharlie cloudsec code ingest --repo acme/api --source sarif --file report.sarif
```

`code ingest` (and `code scan --ingest`) retries a push the service answers with HTTP 429, which means the organization already has as many pushes in progress as it may, or the request quota is spent. It waits at least the response's `Retry-After`, adds random jitter so a CI fan-out that was refused together does not come back together, and gives up after 5 retries or 10 minutes of waiting, exiting with the rate-limit error. A refused push recorded nothing, so the retry is safe.

`code repos` reports `scan_status` as `scanned`, `partial` or `unknown`. `partial` means the scan tripped a limit, so the finding set is INCOMPLETE — not a clean bill. `unknown` means this view has no scan state and says so rather than guessing; `code status` is the authoritative view of the run.

`code capabilities` covers **GitHub connections only** — a GitLab or Bitbucket connection scans with its own read-only token and has no write plane to detect, so it never appears, not even as `unknown`. Use `provider manifest` for those. A capability of `available` means the control MAY be offered, not that anything fires on its own.

`code fixes` pages differently from the rest of cloudsec: backend default 5, max 20, not the shared 1000-row cap.

`code rescan` and `code autofix` ACCEPT and return; `accepted` means QUEUED, never that a scan ran or a pull request exists. Both are debounced, and each carries a set of quiet no-ops (policy scope, free-tier quota, daily caps, failure backoff, a paused connection) — read the outcome per repository with `code repos`, not from the response.

### Pull-request checks

```bash
limacharlie cloudsec code pr-check acme/api --pr 42 \
  --base-sha <FULL_SHA> --head-sha <FULL_SHA> --action synchronize
```

Scans the pull request's base and head and publishes a GitHub check run on the head commit reporting only what the change INTRODUCES; the repository's own findings stay on `code repos`. Its normal caller is the shipped D&R rule on the org's source-control webhook — this is the same door for a CI job.

`--head-sha` and `--base-sha` must be FULL commit ids; a branch or tag name is refused, because the check is published ON the commit and a ref would let it be attached to a commit nobody proposed. The pull request is read from the provider before anything is scanned and what it says wins — the check is published only when the PR is open, belongs to this repository, and its head commit is the `--head-sha` you sent.

`--action` is **required**. The gateway tolerates an absent action, but the collection host behind it tests membership of the closed set with no empty-string exemption, so a request carrying no action is refused every time — including the CI case above. A job with no webhook to quote should send `synchronize`, which is what a push to an open pull request is.

`--action edited` is in the accepted set for one of the things a provider reports with it: a pull request RETARGETED at a different base branch, which changes the diff under review without pushing a commit. A title or body change is reported the same way and changes nothing, so `--action edited` REQUIRES `--prev-base-sha` (the webhook's `changes.base.sha.from`). That value is evidence, never a scan input: the check is refused if the base did not actually move, so an editing spree costs no scan.

A check needs the connection's GitHub App to hold *Checks: Read and write* and *Pull requests: Read and write* — it is read-only by default, and `code capabilities` names the missing permission. A scan that cannot complete publishes a NEUTRAL check run, never a failure.

### Wiring the webhook

```bash
limacharlie cloudsec code webhook --connection my-github \
  --url "https://<hooks domain>/<OID>/github-code-webhook-my-github/<URL_SECRET>" \
  --secret "$WEBHOOK_SECRET"
```

Push rescans and pull-request checks are driven by the GitHub App's OWN webhook — one per App, covering every repository it is installed on. This is the "Fix webhook" door for a connection whose App has no webhook or one pointing elsewhere. The hooks domain is the `url.hooks` value of `limacharlie org url`, always under `.hook.limacharlie.io`; the url shape is enforced exactly, because a caller who could name any url could redirect an org's source-control event stream (and the secret needed to accept it) to a server they control. Neither the url nor the secret is ever returned or logged.

Two outcomes need a human and cannot be fixed through the API: event subscriptions (Push, Pull request) must be ticked in the App's settings — a SUCCESSFUL call can still report `state: unavailable` with `reason: missing_events` — and an App whose webhook is not Active cannot have one created by GitHub's API (`reason: webhook_not_active`). A `timeout` MAY STILL HAVE BEEN APPLIED, so re-read the status rather than retrying blindly; `host_unavailable` is transient and the write is idempotent.

## Container images

```bash
limacharlie cloudsec image repos --with-findings --sort risk
limacharlie cloudsec image repo-facets
limacharlie cloudsec image list --findings with --running --sort risk
limacharlie cloudsec image list --tag latest --registry gcr.io --all
limacharlie cloudsec image get sha256:<64 hex>
limacharlie cloudsec finding list --image-urn "<urn from image list>"
```

An image is keyed on its **digest alone**, so one row is the same artifact everywhere it is stored — tags, registry and push time belong to the repository↔image MEMBERSHIP, not to the image. The placement filters on `image list` (`--repo-urn`, `--provider`, `--account`, `--registry`, `--tag`) therefore select images with AT LEAST ONE matching placement; the row still lists its other placements.

`repositories`, `memberships`, `workloads` and `source_repositories` are BOUNDED SAMPLES of 100 with no pagination — the paired `*_count` is the truth, and only memberships carry a `_truncated` flag. To get past 100 placements, use `image list --repo-urn ...` instead.

`--scanning-state` is the one image selector that is **not** repeatable: the backend would take several values, but the API forwards only one, so a second would be dropped without a word.

Tri-state flags: omitting `--with-findings`/`--with-images`/`--running`/`--signed` leaves the dimension unconstrained; the negative form is a real selection. `--signed`/`--unsigned` is special — signing status is recorded only when a provider reports it, so an image whose status is UNKNOWN matches NEITHER, and the field is not echoed back in the row.

Read `coverage` before concluding anything from an empty list. `mode` is `observed_only` (no registry inventory collected at all — the rows exist only because something was seen running or scanned), `registry`, or `mixed` (registry inventory exists but some images were only ever observed at runtime). An empty list with `repository_inventory_available: false` means "not collected," never "zero repositories."

`top_severity` is ABSENT when there are no open findings — a missing key means "none," never `INFO`. Counts and the `risk`/`pushed` sort keys come from a rollup rebuilt once per collection pass, so they describe the last rebuild rather than this instant.

Pagination on both lists is keyset: `next_cursor` is the ONLY end-of-set signal (a short page is not necessarily the last), and a cursor is bound to the filter and sort it was issued under. `--all` walks it for you.

## Code scanning: local scans

`cloudsec code scan` runs the LimaCharlie code scanner over a local checkout, in a container by default or with an installed scanner binary (`--binary`), and writes a report you can keep (`-o`) or push to the org (`--ingest`).

```bash
limacharlie cloudsec code scan ~/src/api -o report.json.gz                   # sca,iac,licenses
limacharlie cloudsec code scan ~/src/api --repo acme/api --ingest            # push the report
limacharlie cloudsec code scan --scanners sca,sast -o report.json.gz         # sast: default rules
limacharlie cloudsec code scan --scanners sast --org-rules -o report.json.gz # sast: this org's rules
limacharlie cloudsec code scan --scanners sast --rules-file rules.json -o report.json.gz
```

The scanner runs only the static-analysis rules it is given. When `sast` is in `--scanners`, the CLI picks the rule set:

| Option | Rules the `sast` pass runs |
|---|---|
| _(none)_ | LimaCharlie's default rule set, shipped with the scanner |
| `--org-rules` | This org's enabled, unexpired `cloudsec_code_rule` records: the rules a hosted scan of the org runs. Needs read access to that hive. Refused if the org has no enabled record with rules |
| `--rules-file PATH` | A rule set document from disk |

Give at most one of `--org-rules` and `--rules-file`. Both are refused when `sast` is not in `--scanners`.

A rule set document holds one entry per rule file, where each `rules` value is an Opengrep/Semgrep rule file in JSON form:

```json
{"version": 1, "records": [
  {"key": "no-eval", "rules": {"rules": [
    {"id": "no-eval", "languages": ["python"], "severity": "ERROR",
     "message": "eval() on dynamic input", "pattern": "eval(...)"}
  ]}}
]}
```

Before the scan starts, the CLI refuses a document the scanner would not accept: unknown fields, a version other than 1, a record without a unique non-empty `key` or a `rules` object, more than 32 MiB, or no rules at all. The scanner checks each rule, then reports and skips any rule it cannot load.

**Scanner version.** The default image is pinned to scanner v0.16.0. A `--image` or `--binary` running `sast` must be v0.16.0 or newer, because older scanners reject the rule-set flags. That failure is a usage error (exit 2), and the CLI's error message names the version you need. A scan without `sast` passes no rule-set flag, so it still runs on older scanners.

### Sanitized IaC maps

Extract locally before uploading. Install `iac-map-extract` from the LimaCharlie
scanner distribution on `PATH`. The extractor never authenticates or sends raw
Terraform input to a service. Produce a local `terraform show -json` file, then:

```sh
limacharlie cloudsec code iac-map extract --input terraform.json \
  --source-kind state_identity --repository owner/repo \
  --commit FULL_COMMIT --workspace default > sanitized-map.json
limacharlie cloudsec code iac-map push --input sanitized-map.json
```

`FULL_COMMIT` is the full 40- or 64-character lowercase source revision. Use
`--source-kind plan_desired` for plan JSON, `--tool opentofu` for OpenTofu, and
`--provider gitlab` or `bitbucket` where appropriate. State output includes only
resource identity. Plan output additionally permits closed desired booleans;
secret values, source snippets, outputs and arbitrary attributes are omitted.
Unknown or unsupported inputs make coverage partial; partial/failed pushes cannot
delete prior mappings. Raw state and plans are refused by the push command/API.

Raw extraction input is limited to 64 MiB; sanitized uploads to 10 MiB, 50,000
resources, depth 8 and strings of 4 KiB. Push requires `cloudsec.set` for the selected
organization and feature availability. The API limits pushes to 30/minute per
identity and organization. A successful response describes reconciliation and
coverage, not deployment or remediation verification. Keep raw files local; only
`sanitized-map.json` belongs in the upload step. No collection credential is used
for response actions.

SDK equivalent: `CloudSec(org).push_iac_map(sanitized_json_bytes)`, which performs local bounded preflight before its HTTP request.
### IaC provenance selectors (CS-02)

When server-side provenance queries are enabled, finding list, facets, causes and
CSV export accept repeatable `--iac-attribution` values (`attributed`, `ambiguous`,
`none`, `unknown`). Findings and inventory list/facets/export accept
`--has-iac-origin` or `--no-has-iac-origin`. Omit both for no origin constraint.
The negative selector means no **recorded** origin evidence, not proof that a
resource has no IaC. Unknown, partial and stale evidence never establish safety.

```bash
limacharlie cloudsec finding list --iac-attribution unknown --no-has-iac-origin
limacharlie cloudsec inventory list --has-iac-origin
limacharlie cloudsec export findings --iac-attribution ambiguous
```

SDK equivalents use keyword arguments `iac_attribution=["unknown"]` and
`has_iac_origin=False`; explicit false is preserved on the wire. Malformed values
are rejected before HTTP. Selectors remain scoped to the bound organization.
Facets exclude their own selector. Resource detail may include bounded
`iac_origin` and `iac_origin_partial` evidence even for a clean resource. Source
permalinks are optional and commit-bound; missing revision metadata is unknown,
not a link to HEAD. These read-only clients do not fetch source URLs.

Rollout requires the compatible gateway and graph reader before use; a disabled
provenance server rejects the new selectors. Revert clients independently or omit
the selectors; no schema rollback or feature enablement is performed by this CLI.
Program: maximelb/claude-config#137, epic maximelb/claude-config#134.

New-selector requests require an exact `applied_iac_filters` receipt in JSON.
CSV responses carry a bounded first comment line with a base64url JSON receipt;
the SDK validates and removes it before returning CSV. Older or partly upgraded
servers that do not acknowledge the requested selectors raise an error instead
of presenting an unfiltered result. Selector-free calls remain unchanged.


## Build provenance

`limacharlie cloudsec code provenance push -f provenance.json` sends an LC
`lc-build-provenance/v1`, SLSA Provenance v1 or offline Sigstore bundle, bounded to
1 MiB. The server assigns the authenticated tenant and signer context. A signature
is verified only against configured tenant trust; failed verification is refused.
Do not include raw source, credentials, environment variables or build output.

`limacharlie cloudsec code provenance list --digest sha256:<64-hex>` reads
normalized attestations. Optional `--repo-urn`, `--commit` and `--cursor` select a
page. Use the response's `result.next_cursor` for the next page. Conflicting claims
remain visible and resolve to unknown even when a commit filter hides one claim.
Writes require `cloudsec.set`, reads `cloudsec.get`. The server feature must be
enabled after schema installation; command availability grants no deployment or
response authorization.

## Evidence chain

`limacharlie cloudsec finding chain <finding_id>` shows the evidence chain for one
finding in eight stages: declared, committed, built, running, exposed, observed,
responded, verified. Each stage is `proven`, `partial`, `unknown` or
`not_applicable`, with its evidence level, times and a reason. Every stage that is
not proven also names the next action, such as `push_build_provenance`,
`run_runtime_check` or `approve_remediation`.

- `proven` means the evidence for the stage is complete. It does not mean the
  news is good. Read `outcome`: a complete runtime window can prove
  `not_observed`, and a remediation can be `regressed`.
- An unknown stage is never a statement that something is safe, not exposed or
  fixed.
- A reason this CLI version does not recognise is printed exactly as the server
  sent it, with `reason_recognised: false` and the action `review_reason`.
- `--runtime` adds the current runtime evidence to the observed stage. It only
  reads existing evidence. `finding runtime-check` is what starts a measurement.
- `--summary` prints one row per stage and the number of stages with gaps.

## Coverage

`limacharlie cloudsec code coverage` shows Code Security coverage with explicit
denominators. It covers workloads with an immutable digest, digests with a source
commit, remediation outcomes and six more metrics.

- Every metric is listed. A metric that is not measured has no numbers, never
  0 of 0.
- With `--summary`, a percentage appears only for a complete, fresh, untruncated
  count with a positive denominator. Otherwise the counts are shown with the
  reason and the next action.

## Code impact

`limacharlie cloudsec code impact --repo-urn <urn> [--commit <sha>]`, or
`--finding-id <id>`, shows which live resources a repository's infrastructure code
touches. Anything the server could not fully establish is `partial` with a reason,
never "no impact".

## Remediation runs

`limacharlie cloudsec remediation list|get|create|approve|reject|cancel` manages
remediation runs.

- A run never acts before a human approves it. The server resolves every target
  from the finding, so a caller cannot name one.
- Creating and deciding need `cloudsec.respond`, which `cloudsec.set` does not
  imply.
- Deciding takes two steps. Without `--confirm`, `approve`, `reject` and `cancel`
  send nothing. They print what the decision would apply to (action, targets, old
  digests, deadline, generation) and a confirmation token.
- Repeating the command with `--confirm <token>` sends the decision. The token is
  derived from the run's generation and target digest, so it stops matching when
  the run or its targets change. The token is a review step, not a secret. The
  server is the gate: it requires `cloudsec.respond` and refuses a decision whose
  generation or target digest no longer matches the run.
