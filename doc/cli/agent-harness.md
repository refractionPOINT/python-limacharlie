# CLI agent mode

The CLI owns capability procedures, packaged references and workflow validation.
Use `limacharlie help capability` for the catalog (including exact command roots),
`help capability ID` for a procedure, and `--reference PATH` for its documentation.
`help capability --prompt` supplies the compact system instructions for an agent runner.

Set `LC_AGENT_MODE=1` in an agent runner. Organization-scoped operations recheck
`ai_agent.operate`; discovery (`org list`, `auth list-orgs`, `auth whoami`) works
without an organization. The API enforces individual resource permissions.
Procedures are read on demand: commands do not inject guidance, force a retry,
print generic receipt IDs, or buffer/replace stdout. Binary and streaming output
retain their normal CLI behavior. Semantic workflows such as `dr deploy` own
validation and durable recovery. Agent mode is not an isolation boundary against
arbitrary code with the same credentials.

Use `dr deploy` to validate, test, apply and read back an ordinary D&R rule.
Required: `--key`, `--input-file`, `--positive`, `--negative`. The two fixture files
are nonempty JSON arrays. Use `--namespace`, `--enabled/--disabled`, `--tag`
(repeatable, replaces tags), `--clear-tags`, `--comment`, and `--etag` for explicit
scope and metadata. New rules require enabled state; updates require current etag
and preserve omitted metadata. `--dry-run` validates without writing.

Interrupted deployments leave durable receipts under `.lc-agent` (override with
`LC_AGENT_STATE_DIR`). `help receipt ID` reads evidence. `dr reconcile --key NAME`
reads remote state without retrying a write. `--accept-current` acknowledges
divergent state and releases the local recovery fence; subsequent changes need a
fresh candidate and current etag. Other commands use their documented read-back or job status commands to verify the outcome.

Capability procedures and their referenced documents are packaged with the CLI.
New capabilities must update the catalog, procedure, CLI command registration,
discovery profiles and command documentation in this repository. No AI Sessions
MCP command registration or separate LC skills release is required.
