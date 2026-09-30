[Documentation](../README.md) > CLI Overview

# CLI Overview

The CLI follows a consistent `limacharlie <noun> <verb>` pattern. Every command supports `--output` to control the format, `--ai-help` for a detailed description, and `--help` for usage.

## Global Options

Global options can appear anywhere on the command line:

```
--oid TEXT          Organization ID (overrides env/config)
--output FORMAT     Output format: json, yaml, toon, csv, table, jsonl
--filter EXPR       JMESPath expression to filter/transform output
--wide / -W         Disable table value truncation (show full values)
--debug             Print request details
--debug-curl        Print curl commands with sensitive-header placeholders
--quiet / -q        Suppress non-error output
--env TEXT          Named environment from config file
```

`--debug-curl` replaces Authorization, X-API-Key, Cookie and Set-Cookie values
with required environment variables (`LC_TOKEN`, `LC_API_KEY`, `LC_COOKIE` and
`LC_SET_COOKIE`). To replay a command, set each referenced variable to the complete
header value; for example, `LC_TOKEN` includes the `Bearer ` prefix. Missing values
stop the command before curl runs. Header names are matched without regard to case.

URLs, request bodies and other headers are not redacted. Inspect debug output
before sharing it, including when combining `--debug-curl` with `--debug`.

## Extension requests

Some extension actions require the caller's authenticated permissions. Use
`--impersonate` to forward your identity through the SDK's caller authorization
path. This grants the extension no additional permissions; requests omit that
identity unless you select the flag.

```bash
limacharlie extension request --name my-ext --action run --impersonate --data '{"key":"value"}'
```

## Output Formats

All commands support `--output` to control the format:

```bash
limacharlie sensor list --output json     # JSON (default when piped)
limacharlie sensor list --output yaml     # YAML
limacharlie sensor list --output toon     # TOON (token-efficient, LLM-friendly)
limacharlie sensor list --output csv      # CSV
limacharlie sensor list --output table    # Rich table (default for TTY)
limacharlie sensor list --output jsonl    # Newline-delimited JSON
```

`--output toon` needs the optional `toon` extra; the other formats work with a default install. Asking for TOON without it fails immediately, before the command runs.

```bash
pip install 'limacharlie[toon]'
```

On uv older than 0.12, name the package directly instead. `toon_format` only publishes a pre-release, and those uv versions resolve pre-releases for directly named requirements only, so asking them for the extra makes them fall back to an older `limacharlie`:

```bash
uv tool install limacharlie --with 'toon-format>=0.9.0b1'
```

uv 0.12.0 changed its default to resolve transitive pre-releases the way pip does, so on 0.12 and later `uv tool install 'limacharlie[toon]'` works and the `--with` form is unnecessary.

## Filtering with JMESPath

Use `--filter` with a [JMESPath](https://jmespath.org/) expression to extract or transform output. This works with every command and any output format.

**Extracting fields:**

```bash
# Extract a single field from a dict
limacharlie auth whoami --filter 'user_perms'

# Get just the keys of a nested object
limacharlie auth whoami --filter 'keys(user_perms)'

# Get the values as an array
limacharlie auth whoami --filter 'values(user_perms)'

# Drill into nested data: permissions for the first org
limacharlie auth whoami --filter 'values(user_perms)[0]'
```

**Working with lists:**

```bash
# Extract one field from each item in a list
limacharlie sensor list --filter '[].hostname'

# Pick specific fields (reshaping output)
limacharlie sensor list --filter '[].{sid: sid, hostname: hostname, platform: platform}'

# First 5 results
limacharlie sensor list --filter '[0:5]'

# Filter items by condition
limacharlie sensor list --filter "[?platform=='windows']"
```

**Combining with other flags:**

```bash
# Filter + output format
limacharlie sensor list --filter '[].hostname' --output json

# Filter + wide mode (full values, no truncation)
limacharlie auth whoami --filter 'user_perms' --wide
```

## Wide Mode

Table output automatically truncates large values (dicts become `{N keys}`, long lists become `[N items]`) to fit the terminal. Use `--wide` / `-W` to disable truncation and show full values:

```bash
limacharlie auth whoami                # user_perms shown as "{8 keys}"
limacharlie auth whoami --wide         # user_perms shown in full
limacharlie sensor list -W             # All columns untruncated
```

## Discovery & Help

```bash
# List all commands grouped by use-case
limacharlie help discover
limacharlie help discover --profile cloud_security
limacharlie help discover --profile email_security

# Concept guides
limacharlie help d&r-rules
limacharlie help hive
limacharlie help lcql
limacharlie help cloud-security
limacharlie help code-security
limacharlie help email-security

# Quick-reference cheat sheets
limacharlie help cheatsheet --name cloud-security
limacharlie help cheatsheet --name code-security
limacharlie help cheatsheet --name email-security

# Detailed explanation of any command
limacharlie dr create --ai-help

# JSON schema for a command's parameters
limacharlie schema dr create
```

## Command Reference

| Guide | Commands |
|---|---|
| [Sensor Management](sensor-management.md) | sensor, tag, endpoint-policy, task, download, installation-key |
| [Detection & Response](detection-response.md) | dr, fp, replay, detection, ai |
| [Data & Query](data-query.md) | search, ioc, event, stream |
| [Platform Administration](platform-admin.md) | org, user, group, api-key, ingestion-key, billing, audit |
| [Hive & Data Stores](hive-data.md) | hive, secret, lookup, playbook, note, sop, adapter, cloud-sensor, extension |
| [Infrastructure](infrastructure.md) | sync, output, artifact, payload, yara, integrity, logging, exfil |
| [Cloud Security & Code Security](cloud-security.md) | cloudsec (findings, inventory, graph, compliance, CAASM, code lane, container images, fleet, exports) |
| [Email Security](email-security.md) | mailsec (onboarding, coverage, triage, EML, remediation, campaigns, reports, sample submission, rules, tenant purge) |
| [Other Commands](other-commands.md) | api, arl, usp, spotcheck, job, schema, completion, help/discover, case |

## See Also

- [Authentication](../authentication.md) - Credential setup, config directory migration
- [SDK Overview](../sdk/README.md) - Using the Python SDK directly
