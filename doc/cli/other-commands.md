[Documentation](../README.md) > [CLI](README.md) > Other Commands

# Other Commands

Miscellaneous commands: raw API access, ARL resolution, USP validation, health checks, jobs, schema introspection, shell completion, and help/discovery.

## api

Generic escape-hatch for making authenticated HTTP requests to any LimaCharlie API endpoint (similar to `gh api`). Useful for accessing endpoints not yet wrapped by dedicated CLI commands, scripting, and debugging.

The positional `ENDPOINT` argument is a relative API path. Use `{oid}` as a placeholder and it will be replaced with the resolved organization ID.

```bash
# GET request (default when no body provided)
limacharlie api orgs/{oid}
limacharlie api orgs/{oid}/sensors

# POST with form-encoded fields (default body format)
limacharlie api orgs/{oid}/sensors -X POST -f hostname=test
limacharlie api sensors/{oid} -f limit=2          # -f on GET becomes query params

# POST with JSON body (use --json to switch from form-encoded)
limacharlie api orgs/{oid} -X POST --json -F enabled=true

# Typed fields with -F: bools, ints, and @file references
limacharlie api orgs/{oid}/rules -X POST --json \
  -F enabled=true -F ttl=3600 -f name=my-rule \
  -F detect=@detect.json -F respond=@respond.json

# Raw body from file or stdin
limacharlie api orgs/{oid}/rules -X POST --input rules.json
echo '{"key":"value"}' | limacharlie api orgs/{oid}/endpoint --input -

# Target alternate API hosts
limacharlie api orgs/{oid}/status --target billing
limacharlie api --target jwt auth/token

# Show HTTP status code, add custom headers
limacharlie api orgs/{oid} -i
limacharlie api orgs/{oid} -H 'X-Custom: value'

# Skip authentication for public endpoints
limacharlie api orgs/{oid}/public-info --no-auth

# Suppress output
limacharlie api orgs/{oid}/sensors -X DELETE --silent

# Combine with global output/filter options
limacharlie api orgs/{oid}/sensors --output json --filter '[].hostname'
```

**Options:**

| Flag | Description |
|---|---|
| `-X` / `--method` | HTTP method (default: GET, or POST if body provided) |
| `-f` / `--raw-field` | String field as `key=value` (repeatable) |
| `-F` / `--field` | Typed field as `key=value` with coercion: true/false to bool, numeric strings to int/float, `@path` reads file, `@-` reads stdin (repeatable) |
| `--json` | Send fields as JSON body instead of form-encoded |
| `--input` | Request body from file (use `-` for stdin) |
| `--content-type` | Content-Type for `--input` body (default: auto-detect) |
| `--target` | API host alias or URL (aliases: `api`, `billing`, `jwt`, `stream`, `downloads`) |
| `-i` / `--include` | Show HTTP status code in output |
| `--silent` | Suppress response body |
| `--no-auth` | Skip authentication |
| `-H` / `--header` | Additional header as `Key: Value` (repeatable) |

**Exit codes:** 0 for 2xx, 4 for 4xx, 5 for 5xx.

## arl

```bash
limacharlie arl get --arl 'lcr://api/...'      # Resolve an ARL
```

## usp

```bash
limacharlie usp validate                       # Test USP adapter parsing
```

## spotcheck

```bash
limacharlie spotcheck run                      # Quick health check
```

## job

```bash
limacharlie job list
limacharlie job get --id JOB_ID
```

## schema

```bash
limacharlie schema dr create                   # JSON schema for a command
```

## completion

```bash
limacharlie completion bash                    # Shell completion for bash
limacharlie completion zsh                     # Shell completion for zsh
limacharlie completion fish                    # Shell completion for fish
```

## help & discover

```bash
# List all commands grouped by use-case
limacharlie discover
limacharlie discover --profile detection_engineering
limacharlie discover --profile incident_response

# Concept guides
limacharlie help d&r-rules
limacharlie help hive
limacharlie help lcql

# Quick-reference cheat sheets
limacharlie cheatsheet common-operations
limacharlie cheatsheet detection-engineering
limacharlie cheatsheet incident-response

# Detailed explanation of any command
limacharlie dr create --ai-help
```

## Case note editing and redaction

Use `case get --case-number 42` to find the original note event ID in the
case timeline. Both actions require `investigation.set` and use the selected
organization (`--oid`), including its staging Cases URL when applicable.

```bash
limacharlie --oid <OID> case edit-note --case-number 42 --event-id <EID> --content "Corrected text"
limacharlie --oid <OID> case edit-note --case-number 42 --event-id <EID> --input-file note.txt
cat note.txt | limacharlie --oid <OID> case edit-note --case-number 42 --event-id <EID>
limacharlie --oid <OID> case redact-note --case-number 42 --event-id <EID> --confirm
```

Editing accepts one text source: `--content`, `--input-file` (UTF-8 text,
`-` for stdin), or stdin. Leading/trailing whitespace is stripped, matching
`add-note`, before checking that text is nonempty and at most **8192 UTF-8 bytes**.
Earlier text, editor and time stay in case history. A note permits **100 actual
edits**; identical text is a no-op. After the limit, add a new note.
Malformed event IDs return HTTP 400. Transient transaction failures return
HTTP 503; retry the operation. `case update-note` visibility changes on a
redacted note return HTTP 409.
Both commands return `{event}`; redaction also returns
`images_pending_deletion`. JSON/YAML output preserves these fields.

Redaction is irreversible: it replaces the note with `[redacted]`, removes
all earlier text from active Cases storage and blocks image downloads.
Redacted notes cannot be edited or have their visibility changed. A nonzero
`images_pending_deletion` means image blobs still await cleanup; it does not
mean every image has been deleted. Repeating redaction retries cleanup.

Redaction deletes active records, not recovery copies: text may remain in
point-in-time recovery for up to **7 days** and backups for up to **30 days**.
Already delivered hooks-domain audit events follow the organization's retention
and cannot be recalled. Downloaded images, existing client copies, queued old
payloads and logs cannot be recalled either. Text submitted through extension
actions can enter Cloud Logging; redaction does not rewrite old logs or change
their retention. See `case edit-note --ai-help` and `case redact-note --ai-help`.

## See Also

- [CLI Overview](README.md) — Global options and output formats
- [Getting Started](../getting-started.md) — Installation and first steps
