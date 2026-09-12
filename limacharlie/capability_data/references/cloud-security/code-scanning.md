# Code Scanning

Cloud Security scans the source repositories behind your cloud estate and files
what it finds into the same risk-ranked worklist as everything else. Vulnerable
dependencies, credentials committed to git, misconfigured infrastructure-as-code,
container images, code weaknesses and end-of-life runtimes all arrive as ordinary
[findings](findings.md) — same shape, same triage verbs, same automation events.

The point is not to add a second security product next to the first one. It is
that a dependency advisory means something different when the graph can show the
image it is baked into and the workload running that image, and an
infrastructure-as-code check means something different when the bucket it
declares is a bucket you actually own.

!!! info "In the console it's the **Code** page"
    Repositories, their scan status and their findings live under **Cloud
    Security → Code**. The same findings also appear on **Risks**, where the
    **Repository** filter narrows to one repository.

## What it scans

| Lane | What it reads | Finding class |
|---|---|---|
| **Dependencies (SCA)** | lockfiles and manifests, resolved to a software bill of materials, matched against the vulnerability database | `vulnerability` |
| **Malicious packages** | the same dependency set, matched against a malicious-package feed | `malware` |
| **Secrets** | credentials in the working tree, and — as a separate switch — in the full commit history | `secret` |
| **Infrastructure as code** | Terraform, CloudFormation, Kubernetes manifests, Helm charts, Dockerfiles | `misconfig` |
| **Container images** | images the repositories reference, and optionally images your workloads run | `vulnerability` on the image |
| **Static analysis (SAST)** | source files, against a curated rule pack mapped to CWE | `code_weakness` |
| **Licenses** | dependency licenses that carry obligation or compatibility risk | `license_risk` |
| **End-of-life runtimes** | language and base-image runtimes past their published support date | `eol_runtime` |

Dependency findings carry the package, the installed version and the **fixed
version** where one exists, plus EPSS and KEV so the queue is ordered by
exploitability rather than by CVSS alone. Secrets found only in history carry a
different remediation — rotate, because deleting the file does not un-leak the
credential.

## How scanning works, and what leaves your repository

Scanning code means reading code. The invariant is therefore not "we never read
it", it is **we never keep it**:

- Each scan runs in an **ephemeral, sandboxed container** in your data
  region. It shallow-clones the repository into scratch storage, runs the
  engines, writes one normalized report, and is destroyed.
- The container runs with **no cloud identity attached**, a read-only root
  filesystem, restricted egress and a hard 30-minute wall clock. It reaches
  your source-control host, our object storage and our vulnerability-database
  mirror, and nothing else.
- The access token it is handed is **scoped to the single repository being
  scanned** and expires in an hour.
- **Only the report leaves.** Findings, the bill of materials and hashes — never
  file contents, never a diff, never a secret's value.
- A discovered secret is stored as a **salted hash**. There is no field on a
  finding capable of holding the credential, which is deliberate: the plaintext
  never reaches storage, a log, or an event.
- The connected GitHub App stays **read-only**. Publishing pull-request checks
  or opening fix pull requests takes a **separate, opt-in App** that you create
  and install yourself (see [Pull-request checks](#pull-request-checks-and-merge-gating)).
  The read connection never gains a write permission.

## Turning it on

Two things are required: the App needs to be able to read repository contents,
and you need a `code_scanning` policy that says which repositories to scan.

Before either, you need:

- the organization subscribed to `ext-cloud-security` — this is a **separate**
  gate from permissions, and without it every `code` route answers `403`
  whatever the API key can do;
- an API key with `cloudsec.get`, plus `cloudsec.set` to write a policy or push
  a document. See [API Keys](../7-administration/access/api-keys.md);
- the current [LimaCharlie CLI](cli.md); and
- Docker, for local scans only. Pushing an existing document does not need it.

Authenticate interactively with `limacharlie auth login`, or set `LC_OID` and
`LC_API_KEY` in CI.

The policy can also be edited in the console under **Cloud Security → Policies →
Code scanning**: turn on **Enable code scanning**, add the repository's
`<owner>/<repository>` under **Include**, and select at least one engine.

### 1. Grant `Contents: Read-only`

The connector's baseline permissions inventory repositories but cannot read them.
Add the **Contents → Read-only** *Repository* permission to your GitHub App and
approve the permission change on the organization's installation page — GitHub
requires an owner to accept a permission increase on an existing installation.

See [GitHub provider setup](provider-setup/github.md) for the full permission
table, including the two **optional** alert permissions that let LimaCharlie
ingest GitHub's own Dependabot, code-scanning and secret-scanning alerts and
deduplicate them against its own findings.

!!! warning "Without it, scans fail with a clear error, not silently"
    A repository selected for scanning while the App lacks `Contents` reports
    `github_app_missing_contents_permission` on the code scan status, with the
    remediation attached. Nothing is scanned and no findings are invented.

### 2. Create the policy

Code scanning is **opt-in**. With no `code_scanning` policy the lane never runs
— it does not default to scanning everything you connected.

```yaml
# code-policy.yaml
policy_type: code_scanning
enabled: true
repos:
  include: ["acme/api-*", "acme/payments"]
  exclude: ["acme/api-archive"]
scanners:
  sca: true
  secrets: true
  secrets_history: true
  iac: true
  sast: true
  images: true
  licenses: true
severity_floor: LOW          # LOW means no floor: record everything
schedule: daily
image_sources: ["dockerfile"]
autofix_registry_access: true
```

```bash
limacharlie hive set --hive-name cloudsec_policy --key code-scanning \
    --input-file code-policy.yaml --enabled
```

| Field | Meaning |
|---|---|
| `enabled` | **Required.** `false` parks the policy — kept and editable, but nothing is scanned. |
| `repos.include` | Globs matched case-insensitively against `owner/name` and the bare `name`. **Empty means every repository the provider can see** — write it explicitly unless that is genuinely what you want. |
| `repos.exclude` | Always beats `include`. |
| `scanners` | Each engine is an explicit boolean; **at least one must be true**. There is no implicit "all on", and no engine implies another. `sast` and `secrets_history` are off unless you turn them on. |
| `severity_floor` | `CRITICAL`…`HIGH`…`MEDIUM`. Findings below the floor are **not recorded at all** — see the note below. `LOW`, `INFO` and an empty value all mean no floor. |
| `schedule` | `daily` (the default), `weekly`, or `manual`. |
| `sast_ruleset` | Which static-analysis pack runs. Leave it empty for the curated default. |
| `image_sources` | A **list**. Where the image lane looks: `dockerfile` (the default) or `workloads`. `registries` is accepted but does nothing — see [Not yet available](#not-yet-available). |
| `autofix_registry_access` | Whether dependency AutoFix may make read-only package-registry metadata requests. Omitted means `true`; set it to `false` to keep AutoFix on the ordinary restricted scan lane. See [Dependency AutoFix](#dependency-autofix-pull-requests). |
| `pr_checks`, `pr_comments`, `gating.fail_on` | The pull-request lane — see [below](#pull-request-checks-and-merge-gating). |

!!! warning "`severity_floor` drops, it does not hide"
    A finding under the floor is never synthesized, so it is absent rather than
    filtered — it has no row, no history and no triage state. Lower the floor
    later and it comes back as a **new** finding, with `first_seen` set to the
    scan that recreated it, not to when the code was first vulnerable. Raising
    the floor closes what is already open with `closed_reason:
    below_severity_floor`.

    The ladder starts at `MEDIUM`: `LOW`, `INFO` and an empty value are all "no
    floor" and drop nothing. The floor composes across records as the **lowest**
    of the records that select a repository, so an added record can widen
    coverage but never narrow it.

    If you want everything recorded and only your *view* narrowed, leave the
    floor empty and filter the worklist by severity instead.

An org may hold **several** `code_scanning` records and they compose, so you can
scan a small set of sensitive repositories daily with every engine on, and the
rest weekly with a narrower set. Composition takes the union of the enabled
engines, the lowest `severity_floor` and the most frequent schedule, so a record
can generally add coverage. `autofix_registry_access` is deliberately stricter:
an explicit `false` in **any** matching record wins over `true` or an omitted
field. This prevents a broader policy from silently widening registry access
for a repository whose narrower policy disabled it.

!!! note "The glob dialect is the shared Cloud Security one"
    `*`, `?`, `[…]`, `{a,b}`, and a leading `!` for negation *within a list*.
    Write negations in `include`; a `!` in `exclude` reads as "exclude
    everything that is not this", which cancels your include list.

`secrets_history` is its own switch rather than a modifier on `secrets` because
it is the only thing that forces a full clone — on a large monorepo that is the
difference between a fast scan and one that hits the clone cap.

`image_sources: ["registries"]` is accepted and **not enumerated**: a policy
asking for it gets the referenced images only. Registry enumeration is not
implemented.

### Force a rescan

Bump the provider record's `sync_now` field to a new value, or ask for one
repository directly:

```bash
limacharlie cloudsec code rescan acme/payments
```

The next pass picks up the repositories the policy selects, respecting the
per-repository debounce.

## Reading the results

!!! note "CLI version"
    The `cloudsec code` commands were added **after CLI 5.6.2** and require the
    first `limacharlie` release newer than it. An older CLI has no `code`
    command group at all and answers `No such command`, so upgrading is not
    enough on its own until that release is out. Check with:

    ```bash
    limacharlie --version
    limacharlie cloudsec code scan --help
    ```

```bash
# Repositories, their scan state and open-finding rollups.
limacharlie cloudsec code repos
limacharlie cloudsec code repos --with-findings --all
limacharlie cloudsec code repos -q payments

# Has the lane run, and what happened last time?
limacharlie cloudsec code status

# The software bill of materials for one repository.
limacharlie cloudsec code sbom --repo acme/payments -o payments-sbom.json.gz
```

`code repos` returns a `repo` key (`<owner>/<name>`) that the other commands and
the `--repo` findings filter take. `code status` is the authoritative answer to
"did it run" — an empty `code` list means the lane has **never** run in this org,
which is not the same as the lane being off.

The findings themselves are ordinary findings:

```bash
limacharlie cloudsec finding list --repo acme/payments --class vulnerability
limacharlie cloudsec finding list --class secret --severity CRITICAL

# Which producer found it: the scan LimaCharlie ran, or a document you pushed.
limacharlie cloudsec finding list --repo acme/payments --source hosted
limacharlie cloudsec finding list --repo acme/payments --source ingest
```

Each finding also carries the producing scanner on its `code` evidence as
`detected_via` (`lc-code-scanner` for the hosted scan, `lc-code-scanner-byo` for
a pushed local scan, `sarif-ingest`/`cyclonedx-ingest` for a converted
document). Filter with `--source` rather than folding `detected_via` yourself:
`--source` is applied inside the query, so the counts describe the estate, while
folding a page at a time makes every count a count of one page. It takes
`hosted`, `ingest`, `other` (the source control's own detectors), `none` (no
code provenance at all) or `both`.

A repository row reports its own provenance the same way, as `hosted`, `ingest`
or `both`.

See the [CLI reference](cli.md) and the [API reference](api-reference.md) for the
full surface.

!!! note "Reading `scan_status`"
    Each repository carries a `scan_status` of `scanned`, `partial` or `unknown`
    with a machine-readable `scan_status_reason`. `unknown` with
    `repo_not_scanned` means nothing has scanned it yet — check that it is
    inside an enabled policy's include list, then let the next pass reach it.
    `partial` means a cap or an unavailable engine truncated the scan, so the
    finding list is a **lower bound** and must never be read as clean.

    `code status` remains the authoritative answer about the *run* itself;
    follow it when the two disagree.

    An older `repo_scan_props_not_projected` reason was a bug, since fixed. If
    you still see that spelling you are looking at a stale record.

### The bill of materials

Every scanned repository gets a CycloneDX SBOM, produced during the scan and
retrievable on request through a short-lived signed link. It is **not** stored as
inventory rows — a 2,000-package repository must not add 2,000 rows to your
estate — so the graph carries the vulnerability matches while the SBOM stays a
downloadable artifact.

A repository that has not been scanned yet reports `sbom_not_generated_yet`
rather than an empty document.

## Rescanning on every push

A daily schedule means a fix merged at 09:00 is still an open finding at 17:00.
A push webhook closes that gap: one repository, rescanned within minutes,
without waiting for or restarting the estate-wide pass.

```text
GitHub App webhook ──push──▶ LimaCharlie webhook adapter ──▶ D&R rule ──▶ rescan
```

1. **Create a webhook adapter** in your organization — a `cloud_sensor` record
   with `sensor_type: webhook`. The secret in the URL is what authenticates the
   hook, so make it long and random. See the
   [webhook adapter tutorial](../2-sensors-deployment/adapters/tutorials/webhook-adapter.md)
   for the record shape; the code lane's convention is the hostname
   `github-code-webhook`.

   ```bash
   OID=<your organization id>
   # An installation key for the org: `limacharlie --oid "$OID" installation-key list`,
   # or Sensors -> Installation Keys in the web app.
   INSTALLATION_KEY=<an installation key for that org>
   SECRET=$(python3 -c "import secrets;print(secrets.token_urlsafe(32))")
   cat > hook.json <<JSON
   {
     "sensor_type": "webhook",
     "webhook": {
       "secret": "$SECRET",
       "client_options": {
         "hostname": "github-code-webhook",
         "identity": {"oid": "$OID", "installation_key": "$INSTALLATION_KEY"},
         "platform": "json",
         "sensor_seed_key": "github-code-webhook"
       }
     }
   }
   JSON
   limacharlie hive set --hive-name cloud_sensor --key github-code-webhook \
       --input-file hook.json --enabled
   ```

   The hook URL is `https://<your org's hook domain>/<oid>/github-code-webhook/<secret>`;
   the domain comes from `GET /orgs/{oid}/urls`.

2. **Point the GitHub App's webhook at that URL**, `push` events only.

3. **Install the D&R rule.** It ships as a recipe rather than being installed for
   you, so you can read what it does and fork it. The Cloud Security **Code**
   page offers to write it under the name `cloudsec-code-push-rescan`; the
   equivalent YAML is:

   ```yaml
   detect:
     event: json
     op: and
     rules:
       - op: is
         path: routing/hostname
         value: github-code-webhook
       - op: exists
         path: event/head_commit/id
       - op: exists
         path: event/repository/full_name
       - op: starts with
         path: event/ref
         value: refs/heads/
       - op: is
         path: event/deleted
         value: false
   respond:
     - action: extension request
       extension name: ext-cloud-security
       extension action: code_scan_now
       extension request:
         repo: '{{ .event.repository.full_name }}'
         ref: '{{ .event.ref }}'
   ```

Pushes are coalesced: the first push arms a 10-minute window, everything inside
it collapses into one scan of the head of the burst. **Every gate the schedule
applies still applies** — the repository must be in your collected inventory,
not archived, and selected by an enabled policy — and only the default branch is
scanned, so a push to a feature branch is declined with a reason rather than
scanned silently.

A push-triggered scan does not update the estate-wide `code status` row. "Did my
push get scanned" is answered by that repository's row in
`limacharlie cloudsec code repos`.

## Pull-request checks and merge gating

A daily scan says what a repository *contains*. A pull-request check says what a
change *introduces*, on the pull request, before the merge.

This is the one part of the lane that writes to your organization, so it uses a
credential nothing else here has: a **separate, opt-in App that you create**.
The collection App is read-only forever and does not fall back into this role —
without the write App the lane refuses with `write_app_not_configured`.

### Create the "Code Actions" App

Post this manifest to
`https://github.com/organizations/<org>/settings/apps/new?state=lc-code-actions`
as a form field named `manifest`, or create the App by hand with exactly these
permissions and events:

```json
{
  "name": "LimaCharlie Code Actions",
  "url": "https://limacharlie.io",
  "public": false,
  "default_permissions": {
    "checks": "write",
    "pull_requests": "write",
    "contents": "write",
    "metadata": "read"
  },
  "default_events": ["pull_request"]
}
```

That permission set is the **union** of what pull-request checks and
[AutoFix](#dependency-autofix-pull-requests) need, so one App serves both. The
App's permissions are not what any single call holds: the check-run writer asks
for `checks + pull_requests + metadata` and deliberately **not** `contents`, so
publishing a status can never carry the ability to rewrite your source; the
AutoFix writer asks for `contents + pull_requests + metadata` and deliberately
not `checks`.

If you want **checks only**, use `"contents": "read"` (or drop it): everything
below works and AutoFix refuses with `write_app_lacks_contents`, naming the one
checkbox to add. If you want **AutoFix only**, `contents: write` +
`pull_requests: write` is enough and you simply leave `pr_checks` off.

Install it on the repositories you want checked — *Only select repositories* is
the right answer for a trial — and note the App ID and the installation ID.

### Wire it up

```bash
# 1. The private key, as its own secret — never the read connection's.
limacharlie secret set --key github-code-actions-key \
    --value "$(python3 -c 'import json;print(json.dumps({"private_key":open("code-actions.private-key.pem").read()}))')" \
    --enabled
```

```yaml
# 2. Three more fields on the provider record, alongside the read connection's,
#    which are left exactly as they are.
provider_type: github
github_org: "acme"
github_app_id: "1234567"
github_installation_id: "89012345"
credentials: hive://secret/github-app-key
github_actions_app_id: "7654321"
github_actions_installation_id: "54321098"
actions_credentials: hive://secret/github-code-actions-key
```

The record is refused if the write App is the same App, or points at the same
secret, as the read connection.

```yaml
# 3. Turn it on in the code_scanning policy.
pr_checks: true
pr_comments: true
gating:
  fail_on: HIGH
```

Finally, add `pull_request` to the webhook you created above and install the
second recipe rule, `cloudsec-code-pr-check`. It is the same shape as the push
rule: it matches `event/action` in `opened`, `synchronize` and `reopened` and
forwards `repo`, `pr`, `base_sha`, `head_sha` and `action` to the
`code_pr_check` extension action. Everything else on a pull request — labels,
assignments, reviews, closing — leaves the diff untouched and is refused, so a
busy repository's chatter does not become scan traffic.

### What the check says

Both commits are scanned and the two results are diffed by **identity**, never by
line number, so moving a finding within a file does not report it as introduced.

| Outcome | Conclusion |
|---|---|
| nothing introduced, both scans complete | `success` — the only green |
| findings introduced, none at or above the gate | `neutral` — it reports without blocking, and does not claim the pull request is clean |
| something at or above `gating.fail_on` | `failure` |
| either scan hit a limit | never `success` — a truncated scan has not looked everywhere |
| the scan could not run | `neutral`, titled "could not complete" — our outage does not block your merge |

`gating.fail_on` is `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` or `NONE`, and **absent
means NONE**: turning `pr_checks` on never silently starts failing merges. `INFO`
is deliberately not a value.

The check carries a summary with the full counts and up to 50 annotations
(GitHub's own per-request cap). The summary always states the full count, so a
pull request introducing two hundred findings is never described by the fifty
that fit, and only a finding that would *block* is annotated as a failure.

With `pr_comments: true` you also get **one** comment, edited in place on every
later push, never a second one.

## Dependency AutoFix pull requests

For a dependency finding with a published fixed version, the lane can open the
pull request that raises it. It needs the same write App as above (with
`contents: write`) and no extra policy switch: an enabled `code_scanning` record
selecting the repository is the scope, and the write App being present is the
opt-in.

The edit happens **inside the sandbox**, from the finding LimaCharlie's own scan
produced — you cannot ask for an arbitrary package to be raised to an arbitrary
string. Three resolvable findings are still refused, each with its reason: a
package flagged **malicious** (the remediation is removal and credential
rotation, not an upgrade), a vulnerability with **no published fixed version**,
and an ecosystem with no editor.

**Be aware of the lockfile behavior, because it decides whether the pull
request is complete:**

| Ecosystem | What is edited | Is that the whole fix? |
|---|---|---|
| **maven** | `pom.xml` `<version>`, or the property it references | **Yes** — there is no lockfile |
| **pip** | the pin in `requirements.txt` | **Yes** — there is no lockfile. A `--hash`-pinned requirement, or a lock file from another Python tool, is refused with the reason |
| **npm** | `package.json`, range operator preserved; with registry metadata access, the corresponding `package-lock.json` entry | **Yes by default.** AutoFix uses the registry's published version, resolved tarball URL and integrity metadata to rewrite the lockfile entry alongside the manifest. With `autofix_registry_access: false`, it edits the manifest only and marks the lockfile stale |
| **go** | the `require` line in `go.mod` | **Yes when there is no `go.sum`.** When one exists, it carries a hash of the module zip that cannot be computed without downloading it, so the pull request marks that lockfile stale |

The sandbox carries no package manager, deliberately: running one would execute
resolution code — and, for npm, lifecycle scripts — from the dependency graph
under suspicion. Default-enabled npm AutoFix instead makes one read-only
registry metadata request and rewrites the existing lockfile entry directly; it
does not install or execute the package. The registry-enabled AutoFix job uses a
separate, tightly scoped egress lane from ordinary scans.

Set `autofix_registry_access: false` when even that metadata request is not
acceptable. The npm pull request then raises `package.json` only and carries an
unmissable stale-lockfile warning with
`npm install --package-lock-only --ignore-scripts`. Go AutoFix remains
manifest-only by design; when the repository has a `go.sum`, its pull request
carries the corresponding `go mod tidy` warning. Merging either stale-lockfile
pull request believing the lock moved would fix nothing, which is why the
warning appears on the pull request rather than in a footnote.

Nothing is written to your findings when the branch is pushed. A branch is a
proposal: the finding closes when the merge lands and the next scan of the
default branch no longer sees the package.

There is one open AutoFix pull request per (repository, package) — the branch
name is deterministic, so the open pull request *is* the open fix.

Ask for one by finding id:

```bash
limacharlie cloudsec code autofix fnd_2290bab86c1b4d0374d1e2666f64aeca
```

The call **accepts and returns**; the clone, the edit and the pull request happen
minutes later in the sandbox, so `accepted` does not mean a pull request exists —
the pull request is the result. Every refusal above is a quiet no-op on this call
for the same reason: it has already answered by the time the work runs. If no
pull request appears, the reason is on the `cloudsec.code_autofix_refused`
operational event.

## Bring your own scanner

Not everything worth knowing about a repository comes from the hosted scan. You
may already run a scanner in CI, use an analyzer for a language the hosted lane
does not cover, or want results for a repository before you connect the
organization. So the lane takes results **you** produced:

```bash
limacharlie cloudsec code ingest --repo acme/payments --source sarif -f results.sarif
```

`--source` is `sarif` (SARIF 2.1.0, which nearly every scanner can emit),
`cyclonedx` (a bill of materials, with or without its `vulnerabilities`
section), or `report` — the LimaCharlie scanner's own document, which is what
`code scan` below produces.

### It is the same finding, not a copy of it

A pushed finding is **deduplicated against the hosted scan by identity**. A
dependency vulnerability is identified by its advisory, the package and the
manifest that declares it — never by a line number — so when both lanes see
`CVE-2021-23337` in `lodash` in `package-lock.json`, there is one finding, whose
age and triage state survive. Pushing the same document twice writes nothing at
all.

Three rules follow from that, and they are worth knowing before you wire up a
pipeline:

- **A pushed document can only close findings it previously reported.** Fix a
  dependency, push again, and that finding closes. It can never close something
  the hosted scanner found — your dependency scan says nothing about the secrets
  and misconfigurations the sandbox looked for. The reverse is also true: a
  hosted scan will not close what you pushed.
- **What the format cannot carry is reported, not guessed.** The response's
  `notes` names it. `iac_resource_ref_absent`, for example, means the document
  identified an infrastructure finding by file alone, because SARIF has no field
  for the resource address — so those findings do not dedupe against the hosted
  scan's, which identify the resource.
- **Credential findings in a third-party document are refused**
  (`secrets_not_ingestable`). A secret is identified here by a keyed digest of
  the matched value, which no foreign format carries; what such a document *does*
  routinely carry is the credential itself, in a snippet, and that is not
  something to accept. Use the hosted lane for secrets.

The repository does **not** have to come from a connected source-control
organization. A push for a repository nothing collects creates the repository
entry from the facts the document supplies — which is what makes this the path
for code you scan but do not connect. In that case also pass
`--default-branch`, because no provider connection can state it:

```bash
limacharlie --output yaml cloudsec code ingest \
  --repo acme/private-api \
  --source sarif \
  --file results.sarif \
  --default-branch main \
  --commit "$COMMIT_SHA"
```

It must still match an enabled `code_scanning` policy — the same switch and the
same globs the hosted lane uses — and it counts against the same repository
quota as a connected one.

A document can be up to **20 MiB**; files ending in `.gz` stay compressed in
transit. Narrow the scan or split independent results into separate documents if
you exceed it.

### Scanning locally

`code scan` runs the LimaCharlie scanner over a checkout on your own machine —
or in your CI — and, with `--ingest`, pushes the result:

```bash
# Look at the report without sending anything.
limacharlie cloudsec code scan ~/src/payments -o report.json.gz

# Scan and push.
limacharlie cloudsec code scan ~/src/payments --repo acme/payments --ingest
```

Nothing about the checkout leaves the machine except the report. The scanner runs
in a container by default (which carries the pinned engines and their databases);
`--binary` runs an already-installed agent instead, which is what a CI image that
ships one should do. `--scanners` defaults to `sca,iac,licenses`; `sast` and
`images` also run locally.

A scan must use `--ingest`, `-o`, or both, so a completed scan never discards its
only copy of the report. The `-o` output is a gzipped LimaCharlie `report/v1`
document, which is also what `code ingest --source report` takes.

**Secret scanning cannot run locally**, and asking for it is an error rather than
a quietly narrower scan: `--scanners sca,iac,secrets` fails. A secret's identity
here is a digest keyed by a deployment-side value this command does not have, so
locally-found credentials could not deduplicate against the hosted scan's — and
the ingest refuses them for the same reason. Use the hosted lane for secrets.

### A GitHub Actions recipe

This runs on every push to the default branch, scans the checkout, and pushes the
report. It uses no LimaCharlie CI minutes: the work happens in your runner.

```yaml
name: Cloud Security code scan

on:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          # The scanner reads the working tree. Full history is only needed if you
          # scan git history for secrets, which the local scan does not do.
          fetch-depth: 1

      - name: Install the LimaCharlie CLI
        run: pipx install limacharlie

      - name: Scan and push
        env:
          # A LimaCharlie API key with `cloudsec.set`, stored as a repository secret.
          LC_OID: ${{ secrets.LC_OID }}
          LC_API_KEY: ${{ secrets.LC_API_KEY }}
        run: |
          limacharlie auth login --oid "$LC_OID" --api-key "$LC_API_KEY"
          limacharlie cloudsec code scan . \
            --repo "$GITHUB_REPOSITORY" \
            --commit "$GITHUB_SHA" \
            --ingest
```

To push results from a scanner you already run, replace the last step with an
`ingest` of its output — most tools have a SARIF formatter:

```yaml
      - name: Push existing results
        run: |
          limacharlie cloudsec code ingest \
            --repo "$GITHUB_REPOSITORY" \
            --source sarif \
            --commit "$GITHUB_SHA" \
            -f results.sarif
```

`$GITHUB_REPOSITORY` is already `<owner>/<name>`, which is exactly the repository
key the lane uses.

## In your IDE

The code lane is exposed to AI assistants over the Model Context Protocol, so a
session in your editor can read repository findings and scan the working copy
before anything is pushed. See [Cloud Security in your IDE](mcp.md).

## The joins that make it worth doing

Code findings are not a separate island. The repository is a node in the
[security graph](graph.md), container images are nodes keyed by digest, and two
edges connect them to the running estate: **`built-from`** (image → the
repository that produced it) and **`runs-image`** (workload → the image it runs).

That gives you questions no repository scanner can answer on its own, shipped in
the [query pack](graph.md):

| Query | Question |
|---|---|
| `vulnerable_packages_on_exposed_workloads` | which advisories are in images that internet-facing workloads actually run |
| `images_with_kev_on_exposed_workloads` | the same, narrowed to known-exploited vulnerabilities |
| `secrets_in_repos_with_cloud_oidc` | which federated pipeline identities can assume a cloud identity — the blast radius of a leaked repository credential |
| `eol_runtimes_in_production_images` | which end-of-life runtimes reach a running workload |

!!! note "Read an empty result carefully"
    Three of the four need the **`runs-image`** link, and that link only covers
    the image sources your policy's `image_sources` enables — `dockerfile` (the
    default) links images a scanned repository declares, `workloads` links the
    digest-pinned images your cloud inventory reports a workload running. So an
    empty result can mean "that link was not collected here" rather than
    "nothing is affected". Each query's `description` says exactly which.

    `secrets_in_repos_with_cloud_oidc` anchors on every **federated** principal,
    not only CI ones, so a directory federation into your cloud appears
    alongside pipeline trusts — read the principal's subject to tell them apart.

## Compliance

Two frameworks are graded off the code lane, alongside the cloud benchmarks:

- **`owasp-top10`** — OWASP Top 10:2021, mapped by CWE. All ten categories are
  assessable once static analysis has run over at least one repository; with
  `sast` off, the five categories that only static analysis can evidence report
  **NOT_ASSESSED** with their mapping already written down.
- **`cis-supply-chain`** — the CIS Software Supply Chain Security Guide's
  *Source Code* and *Dependencies* sections in full (60 controls), 10 of which
  have a detector. Every other control says in its own words *why* it is not
  assessed.

```bash
limacharlie cloudsec compliance report --framework owasp-top10
limacharlie cloudsec compliance report --framework cis-supply-chain
```

**"NOT_ASSESSED — reason" is a statement, not a gap in the report.** It means
this build has no detector for that control, or the signal a detector needs was
never produced, and the alternative — reporting PASS because no finding exists —
would be a false clean bill. Every such control carries its own reason, so the
list doubles as a map of what the framework asks for and what is measured.

Both frameworks apply only when a source-code provider is connected; on an
estate without one they report **NOT_APPLICABLE** rather than a vacuous pass. And
every control that grades an *outcome* ("are there secrets in the source?")
additionally waits for the lane to have **completed a scan pass**: a connected
provider is not the same fact as a scanned repository. The six controls that
depend on static analysis additionally wait for a static-analysis pass to have
actually run — `sast` is off by default, and an empty `code_weakness` list from
an engine that never started is not evidence of anything.

Because most of `cis-supply-chain` is not auto-assessable, its report carries the
low-coverage qualifier — read the coverage figure next to the score, never the
score alone. See [Compliance](compliance.md) for how scoring and coverage work.

!!! warning "These controls grade the outcome, not the configuration"
    Several controls in both frameworks ask whether a *scanner is in place*.
    What the finding store can answer is whether there are *findings*. The two
    differ exactly where it matters: a repository your policy **excludes**
    produces no findings and therefore cannot fail those controls. Read the
    score next to the Code page's scan coverage. Each affected control says so
    in its description.

## Limits

Free-tier organizations are capped on how much of an estate the lane covers:

| Free-tier limit | Value |
|---|---|
| Repositories scanned | the first **10** by name, **per connected source-control organization** |
| Container images scanned | the **5** most referenced, **per organization** |

Held-back repositories and images are reported with a machine-readable reason
(`free_tier_code_repos_cap`, `free_tier_code_images_cap`) rather than silently
omitted, and the covered set is stable — it does not rotate, so you do not watch
the same findings open and close.

Everything else is a scale guard rather than a tier:

| Limit | Value |
|---|---|
| Scan wall clock | 30 minutes per repository |
| Concurrent scans per organization | 4 |
| Repositories scanned per day, per connection | 500 |
| Container images per pass | 50 |
| Per-file size read by static analysis | 1 MiB (larger files are counted, not opened) |
| Clone size | 2 GB |
| Report size | 20 MiB compressed |
| Pull-request writes per day, per connection | 500 |
| AutoFix pull requests per day, per connection | 20 |

When a cap truncates a scan, the code scan status carries what was hit. A partial
scan **never closes findings** it did not have the chance to re-observe.

## Not yet available

Named here so their absence is not mistaken for a clean result:

- **Custom static-analysis rule packs.** `sast_ruleset: custom:<ref>` is accepted
  by the policy validator and **refused by the scanner**. The refusal is scoped
  to static analysis alone: the repository reports `scan_status: partial` with
  `sast_ruleset_unresolved`, and its dependency, secret, infrastructure and
  licence findings are complete and still close normally. Clear the value to use
  the curated pack.
- **Container-registry enumeration** (`image_sources: ["registries"]`). The value
  is accepted by the policy validator, but nothing enumerates a registry — this
  is the expensive, unbounded half of the image lane and it is not built.
- **Source-control platforms other than GitHub.** The scanner and the storage
  model are source-control-agnostic by design, but GitHub is the only connector
  today.

## Troubleshooting

| Problem | What to check |
|---|---|
| A `cloudsec code` command is missing | Upgrade to a CLI release newer than 5.6.2. |
| The CLI cannot identify the repository | Pass `--repo <owner>/<repository>` explicitly. |
| Docker is not found | Install and start Docker, or upload a document produced by an existing scanner with `code ingest`. |
| The repository is not recorded | Confirm that the repository matches an enabled code-scanning policy and is within the organization's repository quota. |
| The document is rejected as too large | Keep it below 20 MiB by narrowing the scan or splitting independent results into separate documents. |
| Secret results do not appear | Use hosted secret scanning; local and third-party secret findings are intentionally not ingested. |
| Hosted scanning reports `github_app_missing_contents_permission` | The connected GitHub App cannot read repository contents, so nothing could be cloned. Add **Repository → Contents: Read-only** to the App, then approve the permission request on the organization's installation page: GitHub requires an owner to accept a permission increase on an existing installation, so editing the App alone is not enough. Nothing was cloned or code-scanned, and no existing finding changed — the provider's own sweep is unaffected. |
| A repository reports `scan_status: partial` with `sast_ruleset_unresolved` | The code-scanning policy names a static-analysis rule pack that is not available, so static analysis did not run on that repository. Clear the custom `sast_ruleset` value to use the built-in pack. Nothing else about the repository is affected: its dependency, infrastructure, license and secret findings are complete and still close normally. |
| A repository reports `scan_status: unknown` with `repo_not_scanned` | Nothing has scanned it yet. Confirm it is inside an enabled code-scanning policy's include list, then allow the next scheduled pass to reach it. `limacharlie cloudsec code status` is the authoritative answer about the scan run itself; follow it when the two disagree. |
| A repository or image reports `free_tier_code_repos_cap` or `free_tier_code_images_cap` | The organization is on the free tier, which covers the first 10 repositories per connected source-control organization and the 5 most-referenced container images per organization. The covered set is stable rather than rotating, so findings do not appear and disappear between passes. Narrow the policy to the repositories you care about, or move off the free tier. A `_report` suffix means the limit is not being applied: everything was scanned, and the message reports what the limit would have done. |
| A pull-request check or AutoFix does nothing, reporting `write_app_not_configured` or `write_app_lacks_contents` | Only the write was refused. Scanning and existing findings are unaffected. The write App is separate from the read connection and opt-in: the first message means no Code Actions App is configured, the second that it lacks `Contents: Read and write`. They are two different pages in GitHub's settings. |
| An AutoFix pull request reports `lockfile_stale` | The pull request is real and correct; the lockfile still has to be regenerated. npm: `npm install --package-lock-only --ignore-scripts`. Go: `go mod tidy`. This is expected for Go whenever a `go.sum` exists, and for npm only under `autofix_registry_access: false`, a `yarn.lock`/`pnpm-lock.yaml`, or an entry that could not be rewritten safely. |
| A finding you expected is absent entirely | Check the policy's `severity_floor`. A finding under the floor is never recorded, so it has no row to filter for. `LOW`, `INFO` and an empty value mean no floor. |

## See also

- [GitHub provider setup](provider-setup/github.md) — permissions, the App, and the credentials secret
- [Findings & Triage](findings.md) — the worklist every code finding lands in
- [Cloud Security in your IDE](mcp.md) — the MCP tools
- [Security Graph & Queries](graph.md) — the query pack and the graph vocabulary
- [Compliance](compliance.md) — scoring, coverage and evidence
- [Configuration Reference](configuration.md) — every Cloud Security policy record
