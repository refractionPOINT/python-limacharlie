[Documentation](../README.md) > [CLI](README.md) > Cloud Security

# Cloud Security (CNAPP) & Code Security

Install or upgrade with `python -m pip install --upgrade limacharlie`. See [installation](../getting-started.md#installation) for setup.

Commands for the LimaCharlie Cloud Security surface: the merged, risk-ranked findings worklist (CSPM misconfigurations + attack paths + CIEM + code and container-image vulnerabilities), the cloud resource inventory and security graph, compliance assessment (live and audit-grade), the risk overview, CAASM (third-party asset attack surface), the AppSec code lane and container-image inventory, sensor↔cloud-asset resolution, finding triage, CSV exports, and the multi-org fleet overview.

Reads usually require `cloudsec.get`. Local `code scan` without ingestion and
`code iac-map extract` work offline; they do not require a subscription or API key. Most writes require `cloudsec.set`; AutoFix and remediation decisions require `cloudsec.respond`, and reading an IaC map receipt requires `cloudsec.set`. API commands require the org to be subscribed to the Cloud Security extension:

```bash
limacharlie extension subscribe --name ext-cloud-security
```

Provider credentials and the cloudsec policies are hive records — manage them with the hive commands (`limacharlie hive list cloudsec_provider`, `... cloudsec_policy`, `... cloudsec_query`, `... cloudsec_code_rule`).

Every command supports `--ai-help` for a detailed description with examples.

For `code pr-check`, GitHub requires `--base-sha`; GitLab.com and Bitbucket
Cloud may omit it because the provider resolves the base. Supply `--head-sha`
and `--action` for every provider. `--action edited` is GitHub-only.

## Policy record enablement

Every `cloudsec_policy` type honours the Hive record's `usr_mtd.enabled` flag.
A disabled record does not apply, regardless of its policy type or body. For
`code_scanning`, the nested `code_scanning.enabled` must also be `true` to scan.

Once the updated Hive default is live, new `cloudsec_policy` records created
without `usr_mtd` default to enabled. Other hives have their own defaults.
Data-only updates preserve an existing record's metadata. Explicit metadata
remains authoritative: `usr_mtd.enabled: false`, or a metadata block without
an `enabled` key, creates a disabled record.

Use `--disabled` to stage a new policy, or disable an existing record:

```bash
limacharlie hive set --hive-name cloudsec_policy --key my-policy --input-file policy.yaml --disabled
limacharlie hive disable --hive-name cloudsec_policy --key my-policy
limacharlie hive enable --hive-name cloudsec_policy --key my-policy
```

Pass `--enabled` when creating a policy to request enablement explicitly,
including while the new default is being rolled out.

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

One posture row per authorized org, plus cross-tenant rollups on the first page. With user-scoped credentials the CLI mints a temporary thin user token; the gateway resolves its current org memberships, so the fleet is not limited to the configured `--oid` and the token remains small for users with many organizations.

```bash
limacharlie cloudsec fleet overview
limacharlie cloudsec fleet overview --group <GROUP_ID> --trend-days 90
limacharlie cloudsec fleet overview --oid <OID1> --oid <OID2>
```

## Findings

Repeatable filters are OR within a key and AND across keys, and every one of them is truncated at 100 values by the API with no error and no signal in the response — a script fanning out over more than 100 repositories, owners or image urns has to batch them. Use `cloudsec finding classes` to read the API's current finding-class vocabulary:
`toxic_combination`, `public_exposure`, `ciem_risk`, `privilege_escalation`,
`vulnerability`, `misconfig`, `malware`, `secret`, `scan_finding`, `coverage_gap`,
`workload_coverage_gap`, `vuln_coverage_gap`, `authz_coverage_gap`, `device_posture`,
`code_weakness`, `license_risk`, `eol_runtime`, `iac_drift`, `operational`.
Sort keys: `lc_risk` (default), `severity`, `first_seen`, `due_at`.
`--sla` accepts `on_track`, `due_soon`, `breached`, `exempt`, `none` and is repeatable (OR).
For example: `limacharlie cloudsec finding list --sla breached --sort due_at`.
Bulk resolution accepts at most 500 `--finding-id` values per call; the CLI and
SDK reject larger requests before sending them.

`--owner` filters by assigned owner and `--unassigned` selects the untriaged bucket; they combine, so "mine or nobody's" is one filter with both. On `finding facets` the `owner` facet is capped at the top 50 owners by count (`owner_truncated` reports whether any were dropped) — `--owner-pin` keeps named owners in it even when they would not rank in, and filters nothing. That is bounded by the same cap: pins share the 50 slots with any `--owner` values, so past ~50 combined a pin can still be dropped and `owner_truncated` will not say so.

`finding causes` groups findings by the mutable object whose single edit resolves all of them, so a worklist can be worked by fix instead of by row. It takes the same filters as `finding list`; `distinct` is the total number of matching causes, so you can see how much tail the ranked head hides. `--cause` narrows any of `finding list`, `finding facets` and `export findings` to one cause's findings. Repository SCA findings carry `vulnerable_package` causes for shared package upgrades; other vulnerability findings may carry no cause.

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

The gateway route is `POST /cloudsec/{oid}/findings/{id}/runtime-check`.
Its availability also depends on the runtime-evidence feature in the selected datacenter.

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

By default the server walks the full filtered set, capped at 100k rows; a trailing
`#` comment row marks a truncated export. For findings and inventory, use
`--max-rows` to export in bounded requests. The size is rounded up to full
1000-row pages. If more rows remain, the CSV ends with `# next_cursor=<token>`;
pass that token to the next request with the same size, filters and sort. A chunk
without a continuation comment is the end. Each chunk includes its own header.

```bash
limacharlie cloudsec export findings --max-rows 2000 -o findings-1.csv
limacharlie cloudsec export findings --max-rows 2000 --cursor "<token>" -o findings-2.csv
```

`--cursor` requires `--max-rows` so a resumed request cannot silently restart the
export. CSV comments can also report truncation or a mid-stream error; inspect
them before treating an export as complete.

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
limacharlie cloudsec caasm assets --kind device --source ms_graph --posture-encryption ""
limacharlie cloudsec caasm assets --sort last_seen
limacharlie cloudsec caasm coverage --status open --severity HIGH
limacharlie cloudsec caasm policy get
limacharlie cloudsec caasm policy set --input-file policy.yaml
limacharlie cloudsec caasm ingest --source okta --records-file users.json
```

Asset selectors `--kind`, `--source`, `--posture-encryption`,
`--posture-screen-lock`, `--posture-compromised` and `--posture-managed` are
repeatable: values within a selector are OR'd, selectors are AND'd. Use the posture
values your sources report; an empty value selects assets where no source reported
that fact. Unreported posture never means compliant. `--sort urn` is the stable
walk order; `--sort last_seen` shows the newest observations first. Follow
`next_cursor` until absent, including after short pages.

Ingest sources today: `sentinelone`, `crowdstrike`, `defender`, `okta`, `entraid`, `ms_graph`, `wiz` (the registry grows and is validated server-side).

## Providers

```bash
limacharlie cloudsec provider test --input-file provider.yaml   # credential preflight (ephemeral)
limacharlie cloudsec provider manifest                          # coverage manifests, all providers
limacharlie cloudsec provider manifest --type gcp
limacharlie cloudsec provider m365-certificate my-entra --client-id "<application-id>" --out connection.cer
```

For Entra/Microsoft 365 certificate authentication, `m365-certificate` requires
both `cloudsec.set` and `secret.set`. It stores the private key in the organization's
secret store and returns only the public certificate and a `credentials` Hive
reference. Upload `connection.cer` under **Certificates & secrets → Certificates**
in your Entra app registration, then use the returned reference as `credentials`
in the provider record. Grant the app the provider permissions before running
`provider test`. Repeating generation returns the same certificate.
`--replace` replaces the stored key pair immediately. An existing connection may
stop authenticating until you upload the replacement public certificate to the
Entra app registration.

Saved provider configs live in the `cloudsec_provider` hive:

```bash
limacharlie hive set --hive-name cloudsec_provider --key my-gcp --input-file provider.json --enabled
```

Collection, scanning and event-emission exclusions live in `cloudsec_policy`
records with `policy_type: "exclusions"`; use the hive commands to manage them.
`cloudsec policy vocabulary` reports the allowed matcher dimensions for each
surface. Collection and scanning can match `provider`, `region` and
`resource_type` (the resource kind in its URN). Emission can match `provider`
but cannot match `region` or `resource_type`, because emitted events do not
carry those fields. For collection only, `resource_types` (plural) narrows
collector model types such as `DataStore`; it differs from the
`resource_type` matcher. A collection exclusion removes matching inventory
on the next sweep, so review its scope before saving it.

## Configuring Code Security

Subscribe to the Cloud Security extension (`ext-cloud-security`), then create
`cloudsec_provider` and `cloudsec_policy` hive records. Provider records use
`cloudsec_provider.get` / `cloudsec_provider.set` (and corresponding `.get.mtd`,
`.set.mtd`, `.del` permissions for metadata and deletion). `cloudsec_policy`,
`cloudsec_query` and `cloudsec_code_rule` use `cloudsec.get` / `cloudsec.set`.
Credential values stay in the `secret` hive: provider records
store `hive://secret/<name>` references.

A GitHub connection's record data is:

```json
{"provider_type": "github", "github_org": "acme", "github_app_id": "123",
 "github_installation_id": "456", "credentials": "hive://secret/github-key"}
```

The IDs are numeric strings. The credentials secret holds a JSON credential with a `private_key` field
containing the GitHub App's PEM private key. Test the collection connection before saving it:

```bash
limacharlie cloudsec provider test --input-file github-provider.json
limacharlie hive set --hive-name cloudsec_provider --key github \
  --input-file github-provider.json --enabled
```

PR checks and fix PRs need write permissions. GitHub can use the connection App's
granted permissions, or a separate App configured with the complete triple
`github_actions_app_id`, `github_actions_installation_id`, `actions_credentials`.
A separate App must have a different App ID and a different secret reference.
GitLab.com uses `gitlab_write_credentials`; Bitbucket Cloud uses
`bitbucket_write_credentials`. These write-token references must differ from
`credentials`, so scan jobs cannot receive the workflow credential.
`provider test` probes collection credentials only; it does **not** test those
write credentials. Inspect `code capabilities` and webhook readiness separately.

A minimal `cloudsec_policy` record data enabling dependency scans is:

```json
{"policy_type": "code_scanning", "code_scanning": {
  "enabled": true, "repos": {"include": ["acme/api"]},
  "scanners": {"sca": true, "sast": false}}}
```

```bash
limacharlie hive set --hive-name cloudsec_policy --key code-scan \
  --input-file code-policy.json --enabled
```

The record's `usr_mtd.enabled` and the required `code_scanning.enabled` must both
be true to activate it. At least one scanner must resolve on. Fields in the
`code_scanning` body are:

| Field | Meaning |
|---|---|
| `repos.include`, `repos.exclude` | Repository globs; empty include selects all visible repositories; exclusions win within a record. |
| `scanners` | Independent `sca`, `sast`, `iac`, `licenses`, `images`, `secrets`, `secrets_history` switches. `sast` defaults on when omitted; the others default off. |
| `severity_floor` | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`; default `LOW`. |
| `schedule` | `daily` (default), `weekly`, `manual`. |
| `pr_checks`, `pr_comments` | Opt in to PR checks and a consolidated PR comment; both default off. |
| `gating.fail_on` | Lowest introduced severity that fails a check: `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `NONE`; default `NONE`. |
| `pr_live_context` | `off` (default), `risk_summary`, `resource_details`; controls the live context shown on PRs. |
| `image_sources` | `dockerfile` (default), `workloads`, `registries`; used with `scanners.images`. |
| `autofix_registry_access` | Allow package-registry reads for lockfile regeneration; defaults true, explicit false wins across matching policies. |
| `ai_fix` | Optional AI-fix consent and model/check configuration; requires deployment support and approval for each run. |
| `sast_ruleset` | Deprecated and ignored; hosted SAST uses enabled `cloudsec_code_rule` records. Omit it in new records. |

Each other policy type uses `policy_type` plus the same-named body:

| Type | Purpose and permissions |
|---|---|
| `sla` | Ordered remediation deadlines (`rules`, with `match` and `due_days`); read `cloudsec.get`, write `cloudsec.set`. |
| `suppression` | Auditable automatic acceptance or false-positive dispositions; read `cloudsec.get`, write `cloudsec.set`. |
| `vex` | Vulnerability exploitability assertions with attributable product/CVE scope; read `cloudsec.get`, write `cloudsec.set`. |
| `provenance_trust` | Exact repository/builder trust entries and key/root references; read `cloudsec.get`, write `cloudsec.set`. |
| `response` | Versioned response-playbook installations and consent; read `cloudsec.get`, write `cloudsec.set` **and** `cloudsec.respond`. |

A `cloudsec_code_rule` record is an Opengrep/Semgrep rule file in JSON form:

```json
{"rules": [{"id": "no-eval", "languages": ["python"], "severity": "ERROR",
            "message": "Avoid eval on dynamic input", "pattern": "eval(...)"}]}
```

Limits are 256 KiB per record, 1–100 rules per record, and 256 characters per rule
ID (letters, digits, `.`, `_`, `-`). Each rule requires a non-empty message,
languages, severity and exactly one matcher. Search rules choose `pattern`,
`patterns`, `pattern-either`, `pattern-regex` or `match`; taint rules use
`mode: "taint"` with `pattern-sources`/`pattern-sinks`, or a `taint` object with
`sources`/`sinks`. Severities are `CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `ERROR`,
`WARNING`, `INFO`. The hosted enabled set is bounded to 5,000 rules and 20 MiB.
Disable a record with `usr_mtd.enabled: false` to stop running it.

The extension exposes two setup request actions:

```bash
limacharlie extension request --name ext-cloud-security --action restore_default_code_rules
limacharlie extension request --name ext-cloud-security --action reset_code_webhook_rules
```

`restore_default_code_rules` installs missing default SAST records; existing
records are kept unless request data sets `overwrite: true`.
`reset_code_webhook_rules` installs missing webhook recipe rules and restores the
extension's own recipe records to the shipped version. The recipe contains seven
`dr-general` rules: GitHub push rescan, PR check and PR retarget; GitLab push rescan
and merge-request check; Bitbucket push rescan and PR check.

### Previewing policy scope

```bash
limacharlie cloudsec policy vocabulary
limacharlie cloudsec policy suggest --dimension name -q prod
limacharlie cloudsec simulate resources --rules-json '[{"name_glob":["prod-*"]}]'
limacharlie cloudsec simulate findings --match-json '{"finding_class":["code_weakness"]}'
limacharlie cloudsec topology
```

`policy suggest` completes resource names or accounts from current inventory.
`simulate resources` previews resource matcher rules (use `--surface` for the
policy surface); `simulate findings` previews a suppression matcher. Neither
stores a policy. `topology` reads pre-aggregated estate counts and relationships.

## Code Security: the hosted code lane

The lane scans a connected source-control organization's repositories and emits findings into the SAME worklist the cloud collectors feed, so the findings themselves are read with `cloudsec finding list --repo <owner>/<name>`. The commands here are the repository-shaped views and triggers that worklist cannot give you.

```bash
limacharlie cloudsec code repos --with-findings --all
limacharlie cloudsec code status                       # run status per connection
limacharlie cloudsec code capabilities --repo acme/api # repo-specific answers; all connections remain listed
limacharlie cloudsec code fixes --all                  # the dependency-upgrade queue
limacharlie cloudsec code sbom --repo acme/api -o sbom.json.gz
limacharlie cloudsec code rescan acme/api --ref refs/heads/main
limacharlie cloudsec code autofix <FINDING_ID>         # open the upgrade PR
limacharlie cloudsec code ingest --repo acme/api --source sarif --file report.sarif
```

For a repository created through ingest, a CI push that names a branch should
send its default branch too:

```bash
limacharlie cloudsec code ingest --repo acme/api --source sarif --file report.sarif \
  --ref refs/heads/main --default-branch main
```

Only a push for the known default branch can reconcile the repository's findings.
An explicit branch without a stored default branch is refused for a connected
repository or a new repository created through ingest. A legacy ingest-created
repository with prior findings or a scan stamp but no stored default records
activity only, with `default_branch_unknown` in the response. A repository
first seen through a pull request can establish its default on a later matching
branch push. A connected repository's default
branch is recorded from its source-control provider;
older rows may need a collector refresh. Until then, omit `--ref` to assert
that the document describes the default branch. `--default-branch` on the
same explicit push cannot establish that fact. A pull-request, feature-branch
or tag push can still report activity, but it does not alter the
repository's findings when the default is known; use `code pr-check` for a
pull request. An omitted ref or literal `HEAD` retains the legacy assertion that the document
describes the default branch. A branch claiming a default that conflicts with
the stored branch records activity only. After a rename, a repository created
through ingest can restate it with one ref-less push and the new
`--default-branch`; a connected repository uses the provider's next refresh.

`code ingest` (and `code scan --ingest`) retries a push the service answers with HTTP 429, which means the organization already has as many pushes in progress as it may, or the request quota is spent. It waits at least the response's `Retry-After`, adds random jitter so a CI fan-out that was refused together does not come back together, and gives up after 5 retries or 10 minutes of waiting, exiting with the rate-limit error. A refused push recorded nothing, so the retry is safe.

`code sbom --repo <owner/name>` calls `GET /code/sbom?repo=...`; the repository
key is a query value, not a path segment. Without `-o`, it returns a short-lived
download link when available. No SBOM is a successful response with `sbom: null`
and a reason; with `-o`, no SBOM exits nonzero and writes no file.

`code repos` reports `scan_status` as `scanned`, `partial` or `unknown`. `partial` means the scan tripped a limit, so the finding set is INCOMPLETE — not a clean bill. `unknown` means this view has no scan state and says so rather than guessing; `code status` is the authoritative view of the run.

`code status` reports each connection's last pass in `last_stats`, including an `outcome` of `complete`, `partial` or `failed`. `partial` means the pass ran and wrote results but could not cover some images for a stated reason; it is not a failure and not a clean bill. Images the pass could not pull are grouped in `last_stats.image_access[]` (`reason` is `image_registry_credential` or `image_registry_permission`, with `registry`, `registry_name`, `hosts`, an exact `images` count, `message`, `remedy` and `setup_path`), and each affected target carries `access_reason` and `remedy`. Only the registry's own refusal counts as an access problem; another fetch failure stays a failure with its own error.

Private Docker Hub, Quay and GHCR images are pulled only with a registry credential you provide: a `cloudsec_policy` hive record with `policy_type: "registry_credential"` naming exactly one repository. The token itself lives in a `secret` hive record and is referenced, never inlined:

```bash
# token.json: {"secret": "<read-only access token>"}
limacharlie hive set --hive-name secret --key hub-readonly --input-file token.json
cat > registry-policy.json <<'JSON'
{"policy_type": "registry_credential",
 "registry_credential": {"registry": "dockerhub", "repository": "acme/private-image",
                         "username": "readbot", "secret_ref": "hive://secret/hub-readonly"}}
JSON
limacharlie hive set --hive-name cloudsec_policy --key hub-private-image \
  --input-file registry-policy.json --enabled
```

`registry` is `dockerhub`, `quay` or `ghcr`; `repository` is one lowercase `namespace/image` (a GHCR path may be deeper), `username` a registry account or robot name, and `secret_ref` must be `hive://secret/<name>` of an existing secret you can read. Use a read-only token. ECR and ACR images use the cloud connection's own read access instead (`setup_path` `integrations/<provider>`), scoped to one repository per pull.

`code capabilities` reports GitHub connections. GitLab.com and Bitbucket Cloud
connections also appear when their workflow support is enabled in your deployment;
an absent connection does not mean repository scanning is off. Use
`provider manifest` for collection coverage. A capability of `available` means the
control can be offered, not that anything fires on its own. `--repo` narrows
an owning connection's answer to that repository; connections whose organizations
do not own it still appear unchanged. GitHub entries also carry a `webhook` object
with `state`, `reason`, `missing_events` and `detail`. Check webhook readiness
separately from workflow permissions.

`code repos --limit` has a server cap of 500 (default 100).
`code fixes` has a default page size of 5 and a maximum of 20. Its `cause_key`
drills down with `cloudsec finding list --cause <cause_key>`. `--all` follows
available cursors, keeps the API's `distinct` total, and sets `truncated: true`
when the result does not cover that total. The API stops issuing cursors once
the next offset exceeds 10,000, so a walk can finish without covering the queue.
AutoFix supports npm, pip, go and maven dependency findings.

`code rescan` accepts a debounced request; `accepted` does not prove a scan ran. Follow its outcome with `code repos`. `code autofix` requires `cloudsec.respond` and creates a governed `open_fix_pr` remediation run with the caller as requester and approver. Its response has `run_id`, `state`, `replayed`, and `run`, with no `debounce_seconds`. Use `cloudsec remediation get <run_id>` to follow the callback and PR. A second click before the PR opens returns the same run with `replayed: true`. A created run does not prove a PR exists or a fix is verified.

AutoFix refuses a request before creating a run with 403 `missing_permission`, 404 `finding_not_found`, 503 `disabled` or `unavailable` (retryable), 422 `action_unavailable`, or 429 `capacity` (active-run limit, or the per-identity request quota). `--repo` and `--provider` are validated hints that are not forwarded: the repository comes from the finding, and the response reports it. A run that cannot open a pull request ends `failed` with a closed `failure_reason`, such as `write_app_not_configured`, `write_app_lacks_contents`, `finding_not_autofixable`, `repository_not_connected`, `autofix_pr_already_open` (an open PR already exists for the package) or `autofix_budget_exhausted` (the connection's daily AutoFix limit); read it with `cloudsec remediation get`.

A major-version raise is proposed and flagged, never silent. Before you click, the finding's `code` block carries `autofix_version` and, for a major raise, `autofix_major_upgrade`, `autofix_from_line` and `autofix_to_line`; the PR title reads `(major upgrade)`, and the run's `change.upgrade` (`major_upgrade`, `from_line`, `to_line`) records the same verdict once the executor opens the PR. Some raises are refused outright, for example a stale finding or a Go module major above v1. After a PR merges, a run with no recorded deployment in scope ends `expired` with `pr_merged_unverifiable`; a PR closed without merge ends with `pr_closed`. Neither outcome is `verified`. A merged PR waiting for deployment evidence remains in `monitoring` but no longer uses a mutation slot. AutoFix has a smaller slot budget than containment actions.

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

The extension also provides `reset_code_webhook_rules`. The general extension
request command is its CLI and SDK path:

```bash
limacharlie extension request --name ext-cloud-security \
  --action reset_code_webhook_rules --data '{"missing_only":true}'
```

`missing_only` creates absent recipe rules without replacing edited ones.
Omitting it restores extension-owned rules to their shipped content and enabled
state; review that change before invoking it. This is an extension request,
not a `/cloudsec` API route. It requires `ext.request`. The SDK equivalent is
`Extensions(org).request("ext-cloud-security", "reset_code_webhook_rules", data={"missing_only": True}, unwrap=True)`.

## Container images

```bash
limacharlie cloudsec image repos --with-findings --sort risk
limacharlie cloudsec image repo-facets --lineage-facet
limacharlie cloudsec image list --findings with --running --sort risk
limacharlie cloudsec image list --tag latest --registry gcr.io --all
limacharlie cloudsec image list --lineage-status unknown --lineage-status ambiguous --all
limacharlie cloudsec image get sha256:<64 hex>
limacharlie cloudsec finding list --image-urn "<urn from image list>"
```

An image is keyed on its **digest alone**, so one row is the same artifact everywhere it is stored — tags, registry and push time belong to the repository↔image MEMBERSHIP, not to the image. The placement filters on `image list` (`--repo-urn`, `--provider`, `--account`, `--registry`, `--tag`) therefore select images with AT LEAST ONE matching placement; the row still lists its other placements.

`repositories`, `memberships`, `workloads` and `source_repositories` are BOUNDED SAMPLES of 100 with no pagination — the paired `*_count` is the truth, and only memberships carry a `_truncated` flag. To get past 100 placements, use `image list --repo-urn ...` instead.

`image list --lineage-status` accepts repeatable `verified`, `asserted`,
`inferred`, `ambiguous` and `unknown` selectors. They select the effective
source-lineage state, separately from image-signature status (`--signed`). A stale
decision counts as `unknown`. The SDK checks `applied_lineage_status`; an older
server that cannot acknowledge the filter raises an error instead of returning an
unfiltered page. `image repo-facets --lineage-facet` adds exact digest-global
`lineage_statuses` counts; repository selectors do not narrow those counts.

`image get` also returns a digest-bound `lineage` decision. Read its `tier`
(`inferred`, `tool_emitted`, or `our_signed_push`), `status`, and `reason`
together: `inferred` and `asserted` do not mean a verified build. The
`digests_with_source` line in `code coverage` gives an explicit denominator
and confidence-tier breakdown for running-digest source coverage. An OCI index
may be the digest named by a provenance statement; do not replace it with a
platform manifest digest or infer a build from an image label.

Per-workload digest evidence is on each `inventory list --type KubeWorkload`
or `--type ComputeInstance` row under `props.deployment` when collected. Each
declared image has provider-observed `digests` or a specific `reason` such as
`tag_only`, `revision_unavailable`, `provider_unreachable`, `not_running`, `malformed_digest`, `stale` or `other`.
`running`, `read_complete`, and `observed_at` qualify the observation. A
partial workload can have both resolved and unresolved images; the aggregate
coverage count cannot substitute for the individual rows. Older rows with no
`deployment` observation are unknown, not resolved.

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

The output schema is `lc-code-report/v1`. Ingestion accepts at most 20 MiB
on the wire and 64 MiB after decompression. `--repo` and `--commit` are inferred
from the checkout when possible. When `--provider` is omitted, origin hosts
`github.com`, `gitlab.com` and `bitbucket.org` select their respective providers.
For an unknown/self-managed host or a checkout without origin, ingestion requires
an explicit `--provider`; it never silently labels that repository GitHub.
`--default-branch` is inferred from the local `refs/remotes/origin/HEAD` symbolic
ref when available, never from the currently checked-out branch. Supply it when
pushing an explicit branch `--ref` for a new ingest-created repository if origin
HEAD is unavailable. The API trusts an existing stored default branch ahead of
this claim; a connected repository with no stored default branch needs a ref-less
push until collection learns its branch.

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

**Scanner version and access.** The default image is pinned to scanner v0.24.0.
Pulling the default image requires registry access. If it is unavailable to your
account, use an accessible scanner image with `--image` or an installed
`scanner-agent` with `--binary`; do not assume an organization API key grants
container-registry access. A `--image` or `--binary` running `sast` must be v0.16.0 or newer, because older scanners reject the rule-set flags. That failure is a usage error (exit 2), and the CLI's error message names the version you need. A scan without `sast` passes no rule-set flag, so it still runs on older scanners.

### Sanitized IaC maps

Extract locally before uploading. Install `iac-map-extract` from the LimaCharlie
scanner distribution on `PATH`. The extractor never authenticates or sends raw
Terraform input to a service. Produce a local `terraform show -json` file, then:

```sh
limacharlie cloudsec code iac-map extract --input terraform.json \
  --source-kind state_identity --repository owner/repo \
  --commit FULL_COMMIT --workspace default > sanitized-map.json
limacharlie cloudsec code iac-map push --input sanitized-map.json
limacharlie cloudsec code iac-map status --repository owner/repo \
  --provider github --workspace default --source-kind state_identity \
  --hash <64-character receipt hash>
```

`FULL_COMMIT` is the full 40- or 64-character lowercase source revision. Use
`--source-kind plan_desired` for plan JSON, `--tool opentofu` for OpenTofu, and
`--provider gitlab` or `bitbucket` where appropriate. State output includes only
resource identity. Plan output additionally permits closed desired booleans;
secret values, source snippets, outputs and arbitrary attributes are omitted.
Unknown or unsupported inputs make coverage partial; partial/failed pushes cannot
delete prior mappings. Raw state and plans are refused by the push command/API.

Raw extraction input is limited to 64 MiB; sanitized uploads to 20 MiB, 100,000
resources, depth 8 and strings of 4 KiB. Push requires `cloudsec.set` for the selected
organization and feature availability. The API limits pushes to 30/minute per
identity and organization. Push returns a receipt with a content hash and
`processing` or `published` status. The CLI polls until publication and
resubmits the same document if an interrupted worker becomes retryable. The SDK
returns the receipt immediately; call `CloudSec.get_iac_map_status` with the
document's repository, provider, workspace and source kind plus the receipt
hash. Only `published` means the map is visible. A successful receipt is not
deployment or remediation verification. Keep raw files local; only
`sanitized-map.json` belongs in the upload step. No collection credential is used
for response actions.

`status` reads one scoped receipt and exits zero when the read succeeds, even
for `processing`, `retryable` or `superseded`; inspect the returned `status`.
An invalid hash or mismatched response exits nonzero. A timed-out `push` exits
nonzero, and the same sanitized document can be submitted again safely.

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
For a multi-platform image, use the OCI index digest in the artifact's
`kind: "oci"` and `digest` fields when the index is the artifact being claimed.
The client sends the document unchanged and does not fetch or expand the index.
Do not include raw source, credentials, environment variables or build output.

`limacharlie cloudsec code provenance list --digest sha256:<64-hex>` reads
normalized attestations. Optional `--repo-urn`, `--commit` and `--cursor` select a
page. Use the response's `result.next_cursor` for the next page. Conflicting claims
remain visible and resolve to unknown even when a commit filter hides one claim.
Writes require `cloudsec.set`, reads `cloudsec.get`. The server feature must be
enabled after schema installation; command availability grants no deployment or
response authorization.

IaC-map pushes allow 30 requests/minute per identity; provenance pushes allow
60. Both SDK uploads retry 429 responses with the same bounded, jittered,
Retry-After-aware backoff as code ingestion (at most five retries, 600 seconds
of total waiting; Retry-After is capped at 120 seconds). Upload retries preserve
the exact document bytes. Exhaustion is an error, never a success receipt.

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
  reason and the next action. The summary also keeps the server's `breakdown`,
  observation and stale times, so confidence tiers and unknown reasons stay visible.

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

Choose `remediation create --action` for the finding and evidence it carries:

| Action | Eligible finding/target |
|---|---|
| `open_fix_pr` | Image package-vulnerability findings only. Repository dependency findings use `cloudsec code autofix` instead (npm, pip, go, maven). |
| `ai_fix_pr` | Scanner-produced SAST (`code_weakness`) or IaC (`misconfig`) repository findings with a usable source location; needs policy consent and human approval. |
| `temporary_detection` | Findings with server-resolvable scope and an installed temporary-detection response playbook. |
| `notify_ticket` | Findings with server-resolvable scope and an installed notification/ticket response playbook. |
| `isolate_endpoint` | A finding resolving to an eligible endpoint under the installed isolation policy; always needs fresh human approval. |
| `validate_detection` | A finding with an active temporary detection to read back; read-only validation. |
| `validate_runtime` | An open finding with a resource in this organization; reads runtime evidence and reports unknown when unavailable. |
| `disable_credential` | Reserved vocabulary; no service executor, so creation is refused. |
| `simulated` | Test executor with no external effect, only where explicitly enabled. |

Actions are deployment-gated: the relevant executor must be enabled and the
finding must carry the required evidence. A recognized name alone does not make
an action available. The CLI leaves `--action` as text to remain compatible with
future API additions; the API validates the closed set.

Run `state` is one of `requested`, `planning`, `awaiting_approval`, `executing`,
`monitoring`, `rejected`, `cancelled`, `expired`, `failed`, `verified`,
`persists` or `regressed`. Only `verified` says the fix was confirmed (and it can later become
`regressed`). `persists` means the old artifact is still running. The other
ending states are not a claim that the finding is fixed:

- `expired` with `failure: pr_merged_unverifiable`: the PR merged but the run had
  no recorded deployment in scope to verify against.
- `expired` with `failure: pr_closed`: the PR was closed without merging.
- `expired` with `failure: deadline`: the monitoring window ended without
  conclusive evidence.
- `failed` carries a `failure` (for example `action_unavailable`,
  `executor_error`, `dispatch_exhausted`) and, for `open_fix_pr`, a
  `failure_reason` naming why no PR opened.
- `expired` with `failure: window_ended`: a playbook run's window ended normally.
- A merged PR waiting for deployment evidence stays in `monitoring`.

`cancel` applies to `requested`, `planning`, `awaiting_approval` and `executing`
runs; `approve` and `reject` only to `awaiting_approval`. A run created by the
AutoFix button (`origin: autofix_button`) is requested and approved by the same person in one step.

## Entity Pivot

Resolve an identifier into a User or Host, inspect its card, and investigate its
cross-product activity. All commands require `cloudsec.get` and Cloud Security
enabled. Entity IDs returned by resolve/search are opaque.

```bash
limacharlie cloudsec entity pivot --identifier fixture@example.com
limacharlie cloudsec entity pivot --identifier 192.0.2.1 --type ip --at 1791000000
limacharlie cloudsec entity resolve --identifier host.example --type hostname
limacharlie cloudsec entity resolve --identifier 'CORP\fixture' --identifier fixture@example.com
limacharlie cloudsec entity resolve --identifier 192.0.2.1 --type ip --at 1791000000
limacharlie cloudsec entity resolve --identifier web-01 --foreign-hostname WEB-01
limacharlie cloudsec entity pivot --identifier web-01 --observation-selector '{"type":"vendor_device_id","platform":"sophos","value":"<device id>"}'
limacharlie cloudsec entity search --q host --kind host --limit 50
limacharlie cloudsec entity get --entity-id eh_aaaaaaaaaaaaaaaaaaaaaaaaaa --sightings-days 30
limacharlie cloudsec entity sightings --entity-id eh_aaaaaaaaaaaaaaaaaaaaaaaaaa --kind user --limit 100
limacharlie cloudsec entity activity --entity-id eh_aaaaaaaaaaaaaaaaaaaaaaaaaa --source sensor --source cloud
```

`pivot` is the default way to ask "what is this identifier?". It resolves ONE
identifier, then reads the card of each match whose confidence is
`authoritative` or `corroborated`, only for results that are not ambiguous
(de-duplicated, at most 10 cards). Ambiguous results and `possible` matches are
never followed. The output has `cards` (as `get` returns them), `candidates`
(the raw resolve results), every other top-level key of the resolve response
(`index_ready`, `sources`, `sightings`, `feature_disabled`, ...), and, when
needed, `truncated: true` (more than 10 qualified, or a card read failed) with
`card_errors` listing `{entity_id, status: "unavailable"}`. No cards are read
when `index_ready` is not true or `feature_disabled` is true.

`resolve` accepts up to 100 repeated `--identifier` values and returns
candidates only; `--type` applies to all values, or omit it for shape detection.
`--type` is free text of at most 64 bytes: the API owns the list of identifier
types (currently including `email`, `hostname`, `fqdn`, `ip`, `mac`,
`ad_account`, `ad_account_short`, `username`, `windows_sid`, `sensor_id`,
`device_id`, `serial`, `cloud_instance_id`, `aws_arn`, `graph_urn`,
`entra_object_id`, `okta_user_id`, `gws_user_id`, `github_login`,
`github_user_id`) and an unknown type returns its HTTP 400. It preserves every ambiguous and
possible candidate. Possible matches are unconfirmed; choosing one automatically
would hide uncertainty. `--at` is Unix seconds and supports historical IP reads.

Any organization with the Cloud Security subscription gets Entities built from
its LimaCharlie sensors alone; connecting a cloud or identity provider adds
directory identities, devices and cloud context but is not required. A Chrome
extension sensor (hostname `<email>@<32 hex>`) attaches to the signed-in
person's User as a telemetry source (`identity_type` `email`), not to a Host,
and Email Security mailbox sensors likewise show on the User of their mailbox
address. A User no directory record matched (for example a browser profile) has
`attrs.external: true`; that only says no directory record matched, not that
the person is malicious.

### Observed leads from other security products

Events delivered by adapters from Sophos, CrowdStrike, Office 365, Entra ID,
Okta and Duo are read for devices and sign-ins and joined to existing Hosts and
Users when you ask. These are explained, approximate **leads**, such as "same
hostname and internal IP observed that day"; they are never proof of the same
machine and never merge entities. They need `insight.evt.get` on top of
`cloudsec.get`, and cover at most the last 30 days with 20 rows per panel.

- `get` adds `card.also_seen_as[]` to Host cards (devices other products report
  that may be this Host, each `corroborated` or `possible` with a reason) and
  `card.cloud_sign_ins[]` to Host and User cards (the candidate Hosts of a
  sign-in are always `possible`, because of shared NAT/VPN egress).
- `resolve` and `pivot` look a device up by selector. `--foreign-hostname NAME`
  is a hostname another product reports. `--observation-selector JSON` takes a
  JSON object, for example
  `'{"type":"vendor_device_id","platform":"sophos","value":"<device id>"}'`
  (optional `origin_sid`); new selector types need no CLI change. Both flags
  repeat, with at most 4 selectors in total. Platforms are currently `sophos`,
  `crowdstrike`, `office365`, `entraid`, `okta` and `duo`; the API validates
  selector types and platforms and returns HTTP 400 for unknown ones. `--at`
  pins the UTC day; without it the newest days are returned. `--identifier`
  stays required, as the API needs 1 to 100 identifiers.
- Answers come back only in the top-level `observed_matches[]`
  (`{selector, devices[], truncated?}`), never in `matches`, and `pivot` never
  follows them into cards. An input typed `--type hostname` that the
  inventory does not know is also looked up as a foreign hostname
  automatically; untyped inputs are not.
- The response carries `observations: {status, reason?, queries, rows,
  truncated?}`. `status` is `ok`, `incomplete` (a bound cut the evidence),
  `unavailable` (could not be read now) or `forbidden` (no `insight.evt.get`).
  Only `ok` with nothing found means none; the other three never do.

`get` preserves merge redirects: when the id was merged into another entity,
`redirect_to` names the survivor and the card returned is the survivor's (if the
survivor is retired, `card` is `null` and `redirect_to` is still set). The kind
can change across a redirect: an old `eh_` Host id of a Chrome browser profile
now redirects to an `eu_` User. A `null`
card with `index_ready:true` is an unknown id; with `index_ready:false` the id
may simply not be indexed yet. `search` uses identifier prefixes of at least two characters and
at most 512 UTF-8 bytes, and returns at most 100 results per page. `sightings` returns best-effort evidence,
with optional `--since`/`--until` Unix seconds and a page size up to 500. Pass
`--cursor` with the returned `next_cursor` to continue either paginated read.
Missing sightings do not prove inactivity.

Sighting data needs `insight.evt.get`. Without it, `sightings` returns HTTP 403,
while resolve/get return `sightings:"forbidden"` and omit recent activity and
sighting-derived matches, and the observed lookups answer `forbidden`. User activity uses confirmed owned hosts; other
recently observed hosts need event-read permission too.

`activity` defaults to all four sources and the last 30 days; select sources by
repeating `--source`. The maximum window is 30 days. Email needs `mailsec.get`
and Email Security enabled, detections need `insight.det.get`, and sensor state
needs `sensor.get`. Each source reports `ok`, `forbidden`, `not_subscribed`,
`unavailable`, or `timeout`, with bounded `items`, `truncated`, and a full-view
`link`. An unavailable or truncated source is unknown, never evidence of no
activity. The window filters email/detections and the host sightings used to
select sensors; sensor state and open cloud findings are current.

`index_ready:false` means the index has not completed its first pass, while
`feature_disabled:true` means the reader is not enabled. Preserve these states
when scripting with `--output json`; they are not empty successful searches.

Every command has `--ai-help` with its response fields, how to read them and
examples. A typical investigation:

```bash
limacharlie cloudsec entity pivot --identifier fixture@example.com --output json
# cards[0].card.entity.id is e.g. eu_aaaaaaaaaaaaaaaaaaaaaaaaaa
limacharlie cloudsec entity activity --entity-id eu_aaaaaaaaaaaaaaaaaaaaaaaaaa
limacharlie cloudsec entity sightings --entity-id eu_aaaaaaaaaaaaaaaaaaaaaaaaaa --kind logon
```

The same reads are available in the Python SDK:

```python
from limacharlie.sdk.cloudsec import CloudSec

entities = CloudSec(org)
pivot = entities.pivot_entity("fixture@example.com", type="email")
resolution = entities.resolve_entities([{"value": "host.example", "type": "hostname"}])
observed = entities.resolve_entities(
    [{"value": "host.example"}],
    observation_selectors=[{"type": "foreign_hostname", "value": "HOST.EXAMPLE"}])
# observed["observed_matches"] and observed["observations"]['status'] hold the leads
page = entities.search_entities("host", kind="host", limit=50)
card = entities.get_entity("eh_aaaaaaaaaaaaaaaaaaaaaaaaaa", sightings_days=30)
sightings = entities.list_entity_sightings("eh_aaaaaaaaaaaaaaaaaaaaaaaaaa", limit=100)
activity = entities.get_entity_activity("eh_aaaaaaaaaaaaaaaaaaaaaaaaaa", sources=["sensor", "cloud"])
```
