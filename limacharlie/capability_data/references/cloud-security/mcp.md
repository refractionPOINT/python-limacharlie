# Cloud Security in your IDE (MCP)

The [LimaCharlie MCP server](https://github.com/refractionPOINT/lc-mcp-server) exposes Cloud
Security to any [Model Context Protocol](https://modelcontextprotocol.io/) client — Claude Code,
Cursor, and others — so an AI assistant can read your cloud posture, triage findings, and, for the
AppSec code lane, scan the working copy on your own machine before anything is pushed.

This page covers the setup and the four code-lane tools. The rest of the Cloud Security tool surface
mirrors the [command line interface](cli.md) one-for-one.

## Setup — Claude Code

```bash
git clone https://github.com/refractionPOINT/lc-mcp-server
cd lc-mcp-server
go build -o lc-mcp-server ./cmd/server

claude mcp add limacharlie-cloudsec \
  --env LC_OID=<your-organization-id> \
  --env LC_API_KEY=<your-api-key> \
  --env MCP_MODE=stdio \
  --env MCP_PROFILE=cloud_security \
  -- /absolute/path/to/lc-mcp-server
```

`/mcp` in a session lists the server and its tools.

## Setup — Cursor

Add the server to `~/.cursor/mcp.json`, or to `.cursor/mcp.json` inside a project to scope the
credential to one repository:

```json
{
  "mcpServers": {
    "limacharlie-cloudsec": {
      "command": "/absolute/path/to/lc-mcp-server",
      "args": [],
      "env": {
        "LC_OID": "<your-organization-id>",
        "LC_API_KEY": "<your-api-key>",
        "MCP_MODE": "stdio",
        "MCP_PROFILE": "cloud_security",
        "LOG_LEVEL": "warn"
      }
    }
  }
}
```

`LOG_LEVEL=warn` matters more than it looks: the server logs to stderr, and in stdio mode a chatty
stderr is noise in the client's transport log.

## Profiles

`MCP_PROFILE` decides which tools the client is offered. For Cloud Security work:

| Profile | What it exposes |
|---|---|
| `cloud_security` | Every Cloud Security tool, including the triage writes |
| `cloud_security_readonly` | The reads only — for a session that must not be able to change anything |
| `all` | The whole platform |

A narrow profile is not just tidiness. An assistant chooses from what it is shown, so a session that
only needs to read posture is both cheaper and safer with `cloud_security_readonly`.

## Permissions

Reads need `cloudsec.get`; the triage writes and the code ingest need `cloudsec.set`. The whole
surface also requires the organization to be subscribed to the `ext-cloud-security` extension — a
403 saying cloud security is not enabled means exactly that, and the tools say so in their errors.

## The code-lane tools

| Tool | What it does |
|---|---|
| `cloudsec_code_repos` | The repositories the code lane sees, with scan state and the open-finding rollup |
| `cloudsec_code_findings` | Findings for one or more repositories, or the cross-filtered facet counts |
| `cloudsec_code_scan_local` | Scans a working copy on your machine with the same scanner the hosted lane runs |
| `cloudsec_code_autofix` | Opens the dependency fix pull request for an SCA finding |

### Before they can return anything

Code scanning is opt-in per organization, and two things must be true:

1. A source-control provider is connected (a `cloudsec_provider` record).
2. A `code_scanning` record exists in the `cloudsec_policy` hive, naming the repositories in scope
   and the engines that run.

Both are hive records — see [Code Scanning](code-scanning.md#turning-it-on) for the policy's
fields. **An empty answer from a code tool
usually means one of those two is missing, not that your code is clean**, and the tools say so
rather than implying an all-clear.

### Reading findings

`cloudsec_code_findings` will not list without at least one `repo`. That is deliberate: the findings
backend has no "any repository" selector, so dropping the constraint would return your whole
findings worklist — cloud findings included — under a tool named for the code lane. Filtering by
class does not scope it either, because `vulnerability`, `misconfig` and `malware` are shared with
the cloud lane.

The unscoped mode is `facets: true`, which is honest because the `repo` facet counts only findings
that have a repository. So the natural order is:

```text
cloudsec_code_findings { "facets": true }        → which repositories carry what
cloudsec_code_repos    { "has_findings": true }  → the same per repository, with scan state
cloudsec_code_findings { "repo": ["owner/name"], "severity": ["CRITICAL", "HIGH"] }
```

`source` narrows the same read by producer — `hosted` for the scan LimaCharlie ran, `ingest` for a
document your pipeline pushed, `other` for the source control's own detectors, `none` for a finding
with no code provenance, or `both`. It is applied inside the query, so the facet counts describe the
estate rather than the page you happen to be holding.

`repo` is matched **exactly** against a key whose owner and name segments are both ASCII
lower-cased, while a finding's `code.repo_name` is the source-control platform's display casing.
The filter folds what you pass, so a key read straight off a finding now scopes the read rather
than silently matching nothing. A key that is genuinely wrong still returns an empty page, and an
empty page under a single `repo` filter carries a note saying which case you are in: the key is
right and nothing matched, the key is wrong and here is the real one, or no such repository is in
the inventory.

### Scanning your working copy

```text
cloudsec_code_scan_local { "path": "/home/me/src/api" }
```

This runs on **your** machine, not in LimaCharlie: it needs Docker and the
[`limacharlie` CLI](cli.md) on PATH, and it takes minutes rather than seconds. Nothing about the
checkout leaves the machine, and without `ingest` nothing leaves it at all — the result says so
explicitly, so a scan that found plenty is not misread as a clean estate.

Because it runs a container locally, it is available only when the server is running in stdio mode.
A hosted MCP deployment refuses it.

`scanners` defaults to `sca,iac,licenses`; `sast` and `images` also run locally. **Secret scanning
does not**, and asking for it is an error rather than a silent omission: a credential's identity in
this pipeline is a digest keyed by a value only the hosted lane holds, so locally-found secrets
would neither deduplicate against a hosted scan's nor be accepted by the ingest. Use the hosted lane
for secrets.

With `ingest: true` and a `repo`, the report is pushed to your organization, where it deduplicates
against the hosted scan by identity — the report format is loss-free, so it lands on exactly the
rows a hosted scan of the same repository would write, and re-pushing an identical report writes
nothing. A pushed report can only close findings *it* previously reported, never one the hosted
scanner found.

Pass `output_path` alongside `ingest`. The report otherwise exists only for the duration of the
scan, so a push that fails — not subscribed, no enabled `code_scanning` policy selecting the
repository, a quota, a transient error — costs the whole scan again.

### `cloudsec_code_autofix`

Opens the pull request that raises a vulnerable dependency to its fixed version,
for one finding:

```text
cloudsec_code_autofix { "finding_id": "fnd_..." }
```

`finding_id` is required and is the only input that decides anything: the
backend resolves it against the dependency rows its own scan produced and raises
that package to that advisory's fixed version, so there is no way to name a
package or a version. `repo` and `provider` are optional search hints.

It needs the separate, opt-in **Code Actions** App on the connection — the
read-only collection App never gains write access.

The tool answers as soon as the request is **accepted**; the clone, the edit and
the pull request happen minutes later in a sandbox, so **the pull request is the
result**. Read it in the repository rather than in the tool's reply.

!!! warning "A refusal does not come back on this call"
    Because the call has already answered, every reason a fix does not happen is
    a quiet no-op here: no Code Actions App (`write_app_not_configured`) or one
    lacking `Contents: Read and write` (`write_app_lacks_contents`), a package
    flagged malicious, no published fixed version, an unsupported ecosystem, a
    repository outside the policy scope or over the free-tier quota, a pull
    request already open for that package, or the daily limit.

    None of these appear in the reply. They surface as the
    `cloudsec.code_autofix_refused` operational event — that is where to look
    when no pull request appears.

See [Code Scanning](code-scanning.md#dependency-autofix-pull-requests) for the
setup, the npm registry-metadata policy, and the Go lockfile caveat that decide
whether the pull request is complete on its own.

## See also

- [Code Scanning](code-scanning.md) — the lane these tools read
- [Command Line Interface](cli.md) — the same surface, without an assistant
