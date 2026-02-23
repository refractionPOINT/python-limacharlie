# LimaCharlie Python SDK & CLI v2.0.0 - Design & Implementation Plan

## Executive Summary

This document describes the design for a complete rewrite of the LimaCharlie Python SDK and CLI (v2.0.0). The primary design goal is **AI/LLM-first discoverability**: every command, parameter, and concept should be self-documenting enough that an AI agent (like Claude Code) can operate the CLI effectively without prior LimaCharlie knowledge.

The new CLI covers 100%+ of the current CLI features, plus new capabilities from the API gateway (AI generation, groups, investigations, SOPs, org notes, etc.).

---

## Table of Contents

1. [Design Principles](#1-design-principles)
2. [CLI Architecture](#2-cli-architecture)
3. [Authentication & Configuration](#3-authentication--configuration)
4. [SDK Core Classes](#4-sdk-core-classes)
5. [Command Groups & Commands](#5-command-groups--commands)
6. [Output & Formatting](#6-output--formatting)
7. [AI/LLM Discoverability Features](#7-aillm-discoverability-features)
8. [Testing Strategy](#8-testing-strategy)
9. [Migration & Packaging](#9-migration--packaging)
10. [Detailed Command Reference](#10-detailed-command-reference)
11. [Implementation Checklist](#11-implementation-checklist)

---

## 1. Design Principles

### 1.1 AI/LLM-First Discoverability
- [ ] Every command has a `--explain` flag that prints a detailed paragraph explaining what the command does, when to use it, and common patterns
- [ ] Every parameter has a rich `help=` string with type info, examples, and constraints
- [ ] `limacharlie help <topic>` provides concept guides (e.g., `limacharlie help d&r-rules`, `limacharlie help hive`, `limacharlie help lcql`)
- [ ] `limacharlie discover` lists all commands grouped by use-case profile (matching MCP server profiles: sensor_management, detection_engineering, platform_admin, etc.)
- [ ] `limacharlie cheatsheet <topic>` prints quick-reference examples
- [ ] Every error message includes a suggestion for what to do next
- [ ] JSON Schema output available for every command's parameters via `limacharlie schema <command>`

### 1.2 Consistent Command Structure
- [ ] All commands follow `limacharlie <noun> <verb>` pattern (e.g., `limacharlie sensor list`, `limacharlie rule create`)
- [ ] CRUD operations use consistent verbs: `list`, `get`, `create`, `update`, `delete`
- [ ] Bulk operations use consistent verbs: `export`, `import`, `sync`
- [ ] Destructive operations require `--confirm` or print a confirmation prompt
- [ ] All identifiers use consistent flag names: `--oid`, `--sid`, `--name`, `--key`

### 1.3 Machine-Readable Output
- [ ] Default output is human-readable tables (for interactive use)
- [ ] `--output json` for JSON (default when stdout is piped/not a TTY)
- [ ] `--output yaml` for YAML
- [ ] `--output csv` for CSV
- [ ] `--output jsonl` for newline-delimited JSON (for streaming)
- [ ] `--quiet` / `-q` suppresses all output except errors
- [ ] Exit codes are meaningful: 0=success, 1=general error, 2=auth error, 3=not found, 4=validation error

### 1.4 Composability
- [ ] All commands accept `--oid` to specify org (overrides env/config)
- [ ] All create/update commands support `--input-file` to read parameters from JSON/YAML file (rule create, hive set, output create, extension config set, etc.)
- [ ] All list commands support `--filter` for client-side jmespath filtering
- [ ] All list commands support `--limit` and `--offset` for pagination
- [ ] Stdin support for piping data between commands

---

## 2. CLI Architecture

### 2.1 Entry Point & Framework
- [ ] Use `click` library for CLI framework (replacing raw argparse)
- [ ] Single entry point: `limacharlie` command with click groups
- [ ] Plugin architecture: each command group is a separate module auto-discovered from `limacharlie/commands/`
- [ ] Global options: `--oid`, `--env`, `--output`, `--debug`, `--quiet`, `--profile`
- [ ] Version command: `limacharlie version` (replaces `limacharlie version`)

### 2.2 Module Structure

v2 replaces the existing code directly in the `limacharlie/` package (no backwards compatibility with v1 needed). Old v1 modules are removed.

```
limacharlie/
├── __init__.py
├── __main__.py                  # Entry point: limacharlie CLI
├── cli.py                       # Main CLI entry point & click groups
├── config.py                    # Auth & configuration management
├── client.py                    # HTTP client with retry, auth, rate limiting
├── output.py                    # Output formatting (json/yaml/csv/table)
├── errors.py                    # Custom exception hierarchy
├── help_topics.py               # Inline help topic content
├── discovery.py                 # Command discovery & explain system
├── sdk/
│   ├── __init__.py
│   ├── organization.py          # Organization management
│   ├── sensor.py                # Sensor operations
│   ├── dr_rules.py              # Detection & Response rules
│   ├── fp_rules.py              # False positive rules
│   ├── hive.py                  # Hive key-value store
│   ├── outputs.py               # Output integrations
│   ├── artifacts.py             # Artifact/log management
│   ├── payloads.py              # Payload management
│   ├── search.py                # Search & LCQL queries
│   ├── insight.py               # IOC search & event queries
│   ├── extensions.py            # Extension management
│   ├── installation_keys.py     # Installation key management
│   ├── ingestion_keys.py        # Ingestion key management
│   ├── users.py                 # User & permission management
│   ├── groups.py                # Organization group management
│   ├── api_keys.py              # API key management
│   ├── billing.py               # Billing & usage
│   ├── spout.py                 # Real-time streaming (WebSocket)
│   ├── firehose.py              # Real-time streaming (TCP/TLS)
│   ├── replay.py                # D&R rule replay/testing
│   ├── integrity.py             # Integrity monitoring rules
│   ├── exfil.py                 # Exfil prevention rules
│   ├── logging_rules.py         # Logging/log collection rules
│   ├── configs.py               # Configuration sync (IaC)
│   ├── ai.py                    # AI-powered generation
│   ├── investigations.py        # Investigation management
│   ├── usp.py                   # USP adapter validation
│   ├── jobs.py                  # Service job tracking
│   ├── yara.py                  # YARA scanning & rule management
│   └── arl.py                   # Authenticated Resource Locator resolution
├── commands/
│   ├── __init__.py
│   ├── auth.py                  # login, logout, whoami, use-org
│   ├── sensor.py                # sensor list, get, delete, upgrade, export, dump, sweep
│   ├── rule.py                  # rule list, get, create, delete, test, ...
│   ├── fp.py                    # fp list, get, create, delete
│   ├── hive.py                  # hive list, get, set, delete, validate, ...
│   ├── output_cmd.py            # output list, create, delete
│   ├── artifact.py              # artifact upload, list, download
│   ├── payload.py               # payload list, upload, download, delete
│   ├── search.py                # search run, validate, interactive, saved-queries
│   ├── ioc.py                   # ioc search, batch-search, enrich
│   ├── event.py                 # event list, get, timeline
│   ├── detection.py             # detection list, get
│   ├── extension.py             # extension list, subscribe, unsubscribe, convert-rules, ...
│   ├── installation_key.py      # installation-key list, create, delete
│   ├── ingestion_key.py         # ingestion-key list, create, delete, configure
│   ├── user.py                  # user list, invite, remove, permission
│   ├── group.py                 # group list, create, delete, member, ...
│   ├── api_key.py               # api-key list, create, delete
│   ├── org.py                   # org info, create, delete, rename, config, errors, ...
│   ├── billing.py               # billing status, details, invoice, plans
│   ├── stream.py                # stream events, detections, audit (spout)
│   ├── replay_cmd.py            # replay run, test-rule
│   ├── integrity.py             # integrity list, create, delete
│   ├── exfil.py                 # exfil list, create, delete
│   ├── logging_cmd.py           # logging list, create, delete
│   ├── sync.py                  # sync push, pull, diff
│   ├── ai.py                    # ai generate-rule, generate-query, ...
│   ├── investigation.py         # investigation list, get, create, delete
│   ├── usp.py                   # usp validate
│   ├── schema.py                # schema list, get
│   ├── tag.py                   # tag list, add, remove, mass-tag
│   ├── task.py                  # task send, reliable-send, list-reliable
│   ├── endpoint_policy.py       # endpoint-policy (isolate, rejoin, seal, unseal)
│   ├── yara.py                  # yara scan, rules, sources
│   ├── cloud_sensor.py          # cloud-sensor list, get, set, delete
│   ├── job.py                   # job list, get, delete, wait
│   ├── arl.py                   # arl get
│   ├── spotcheck.py             # spotcheck run
│   ├── secret.py                # secret list, get, set, delete (NEW)
│   ├── lookup.py                # lookup list, get, set, query, delete (NEW)
│   ├── playbook.py              # playbook list, get, set, delete (NEW)
│   ├── adapter.py               # adapter list, get, set, delete (NEW)
│   ├── sop.py                   # sop list, get, set, delete (NEW)
│   ├── note.py                  # note list, get, set, delete (NEW)
│   ├── audit.py                 # audit list
│   └── help_cmd.py              # help, discover, cheatsheet, schema
tests/
├── unit/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_cli_commands.py
│   ├── test_config.py
│   ├── test_client.py
│   ├── test_output.py
│   ├── test_errors.py
│   ├── test_sdk_organization.py
│   ├── test_sdk_sensor.py
│   ├── test_sdk_dr_rules.py
│   ├── test_sdk_hive.py
│   ├── test_sdk_search.py
│   ├── test_sdk_configs.py
│   └── ...
└── integration/
    ├── __init__.py
    ├── conftest.py              # Integration fixtures with cleanup
    ├── test_auth.py
    ├── test_sensor.py
    ├── test_rules.py
    ├── test_hive.py
    ├── test_outputs.py
    ├── test_artifacts.py
    ├── test_search.py
    ├── test_extensions.py
    ├── test_users.py
    ├── test_api_keys.py
    ├── test_installation_keys.py
    ├── test_ingestion_keys.py
    ├── test_sync.py
    ├── test_replay.py
    ├── test_stream.py
    ├── test_ai.py
    ├── test_billing.py
    ├── test_groups.py
    ├── test_org_management.py
    ├── test_usp.py
    ├── test_integrity.py
    ├── test_exfil.py
    ├── test_logging.py
    ├── test_yara.py
    ├── test_jobs.py
    └── test_cli_e2e.py          # End-to-end CLI tests
```

- [ ] Create this directory structure (remove all v1 modules)
- [ ] Each command module auto-registers its click group

### 2.3 Clean Break from v1
This is a full v2.0.0 rewrite with no backwards compatibility requirement:
- [ ] v2 code replaces v1 code directly in the `limacharlie/` package (no `v2/` subpackage)
- [ ] All v1 modules (Manager.py, Sensor.py, etc.) are removed
- [ ] Entry point `limacharlie` runs the new Click-based CLI
- [ ] SDK classes available as `limacharlie.sdk.*` (e.g., `from limacharlie.sdk.organization import Organization`)
- [ ] No fallback to v1 CLI, no `limacharlie-v1` entry point

---

## 3. Authentication & Configuration

### 3.1 Credential Storage
- [ ] Same file location: `~/.limacharlie` (YAML format)
- [ ] Support named environments/profiles: `limacharlie auth use-env production`
- [ ] Environment variables: `LC_OID`, `LC_API_KEY`, `LC_UID`, `LC_CURRENT_ENV`, `LC_CREDS_FILE`, `LC_EPHEMERAL_CREDS`
- [ ] Ephemeral mode (no disk writes) via `LC_EPHEMERAL_CREDS=1`
- [ ] File permissions enforced at 600

### 3.2 Auth Commands
- [ ] `limacharlie auth login` - Interactive login (OAuth or API key)
- [ ] `limacharlie auth login --api-key <key> --oid <oid>` - Non-interactive API key login
- [ ] `limacharlie auth login --uid <uid> --api-key <key>` - User-scoped API key login
- [ ] `limacharlie auth logout` - Clear stored credentials
- [ ] `limacharlie auth whoami` - Show current identity, permissions, accessible orgs
- [ ] `limacharlie auth test [--permissions perm1,perm2]` - Test current auth and optional specific permissions
- [ ] `limacharlie auth use-env <name>` - Switch named environment
- [ ] `limacharlie auth list-envs` - List configured environments
- [ ] `limacharlie auth use-org <oid-or-name>` - Set default organization (resolves names to OIDs)
- [ ] `limacharlie auth list-orgs [--filter <text>]` - List accessible organizations

### 3.3 Client Features
- [ ] Automatic JWT generation and refresh
- [ ] Retry logic: 3 retries with exponential backoff for 429/504
- [ ] Rate limit awareness: log warnings on rate limit headers
- [ ] Request debugging via `--debug` (prints curl-equivalent commands)
- [ ] User-Agent header: `limacharlie-cli/2.0.0 python/3.x`
- [ ] Idempotent key support for safe retries on write operations

---

## 4. SDK Core Classes

### 4.1 Client
- [ ] `limacharlie.Client(oid, api_key, uid, environment, jwt, ...)`
- [ ] Automatic credential resolution: explicit params > env vars > config file
- [ ] Thread-safe JWT management with automatic refresh
- [ ] Request/response logging for debugging
- [ ] Rate limit tracking and backoff
- [ ] Context manager support (`with Client(...) as client:`)

### 4.2 Organization
- [ ] `Organization(client)` - Main entry point for all org-scoped operations
- [ ] Properties: `oid`, `name`, `info`, `urls`
- [ ] Methods for all org-level operations (sensors, rules, hives, etc.)
- [ ] Lazy-loaded cached properties for org info and URLs

### 4.3 Sensor
- [ ] `Sensor(organization, sid)` - Represents a single sensor
- [ ] Properties: `sid`, `hostname`, `platform`, `architecture`, `external_ip`, `internal_ip`, `is_online`, `is_isolated`, `tags`, `version`, `enrollment_time`, `last_seen`
- [ ] Platform helpers: `is_windows`, `is_linux`, `is_macos`, `is_chrome`
- [ ] Task methods: `task()`, `request()`, `simple_request()`
- [ ] Tag methods: `add_tag()`, `remove_tag()`, `get_tags()`
- [ ] Network methods: `isolate()`, `rejoin()`, `is_isolated`
- [ ] Lifecycle methods: `delete()`, `seal()`, `unseal()`
- [ ] Event methods: `get_events()`, `get_timeline()`, `get_overview()`

### 4.4 Hive
- [ ] `Hive(organization, hive_name, partition_key=None)` - Key-value store
- [ ] `HiveRecord` - Record with data, metadata, etag support
- [ ] Methods: `list()`, `get()`, `set()`, `delete()`, `validate()`, `rename()`
- [ ] Transaction support: `update_tx(callback)` with automatic etag retry
- [ ] Batch operations: `batch().get().set().delete().execute()`

### 4.5 Search
- [ ] `Search(organization)` - LCQL query execution
- [ ] Methods: `validate()`, `estimate()`, `execute()`, `execute_streaming()`
- [ ] Iterator-based pagination for large result sets
- [ ] Progress callback support
- [ ] Saved query management: `list_saved()`, `get_saved()`, `create_saved()`, `delete_saved()`

### 4.6 Spout (Real-time Streaming)
- [ ] `Spout(organization, data_type, filters=...)` - WebSocket streaming
- [ ] Configurable filters: investigation_id, tags, categories, sensor_ids
- [ ] Auto-reconnect with exponential backoff
- [ ] Queue-based buffering with configurable max
- [ ] Context manager: `with Spout(...) as spout: for event in spout: ...`
- [ ] Future results tracking for sensor tasking

### 4.7 Configs (Infrastructure-as-Code)
- [ ] `Configs(organization)` - Configuration sync
- [ ] `fetch(components)` - Download current config
- [ ] `push(config, components, force=False, dry_run=False)` - Upload config
- [ ] `diff(config, components)` - Show differences
- [ ] Component selection: rules, fps, outputs, integrity, exfil, logging, artifacts, extensions, org_configs, hives, installation_keys, yara

### 4.8 AI Generation (NEW)
- [ ] `AI(organization)` - AI-powered generation
- [ ] `generate_dr_rule(description)` - Generate D&R rule from natural language
- [ ] `generate_detection(description)` - Generate detection component
- [ ] `generate_response(description)` - Generate response component
- [ ] `generate_lcql(description)` - Generate LCQL query from natural language
- [ ] `generate_sensor_selector(description)` - Generate bexpr selector
- [ ] `generate_playbook(description)` - Generate Python playbook
- [ ] `summarize_detection(detection_data)` - Summarize a detection

---

## 5. Command Groups & Commands

### Organization Commands - `limacharlie org`
- [ ] `org info` - Get organization details (sensor count, version, quotas, name)
- [ ] `org list` - List accessible organizations (with --filter support)
- [ ] `org create <name> --location <loc> [--template <t>]` - Create new org
- [ ] `org delete --confirm <token>` - Delete organization (two-step)
- [ ] `org rename <new-name>` - Rename organization
- [ ] `org config get [<key>]` - Get org configuration value(s)
- [ ] `org config set <key> <value>` - Set org configuration value
- [ ] `org urls` - Get service URLs for organization
- [ ] `org quota set <n>` - Set sensor quota
- [ ] `org stats` - Get usage statistics
- [ ] `org errors [--dismiss <component>]` - List/dismiss org errors
- [ ] `org mitre-report` - Get MITRE ATT&CK coverage report
- [ ] `org schema [--event-type <type>] [--platform <plat>]` - Get event schemas/ontology
- [ ] `org runtime-metadata [--entity-type <t>] [--entity-name <n>]` - Get runtime metadata
- [ ] `org check-name <name>` - Check if organization name is available

### Sensor Commands - `limacharlie sensor`
- [ ] `sensor list [--selector <bexpr>] [--limit <n>] [--online-only] [--with-ip <ip>] [--with-hostname <prefix>]` - List sensors with rich filtering
- [ ] `sensor get <sid>` - Get sensor details
- [ ] `sensor delete <sid> --confirm` - Delete sensor
- [ ] `sensor online <sid>` - Check if sensor is online
- [ ] `sensor wait-online <sid> --timeout <secs>` - Wait for sensor to come online
- [ ] `sensor upgrade [--selector <bexpr>]` - Upgrade sensors to latest version across fleet
- [ ] `sensor set-version --version <version>` - Set sensor version/branch for organization
- [ ] `sensor export [--selector <bexpr>]` - Export full sensor manifest as JSON/CSV
- [ ] `sensor dump <sid> --confirm` - Trigger full memory dump on sensor (DESTRUCTIVE/HEAVY)
- [ ] `sensor sweep <sid> --config <json-or-file>` - Run host sweep/scan on sensor

### Tag Commands - `limacharlie tag`
- [ ] `tag list [--sensor <sid>]` - List all tags or tags for a sensor
- [ ] `tag add <sid> <tag> [--ttl <duration>]` - Add tag to sensor
- [ ] `tag remove <sid> <tag>` - Remove tag from sensor
- [ ] `tag find <tag>` - Find all sensors with a tag
- [ ] `tag mass-add --selector <bexpr> --tag <tag> [--ttl <duration>]` - Bulk tag sensors
- [ ] `tag mass-remove --selector <bexpr> --tag <tag>` - Bulk untag sensors

### Endpoint Policy Commands - `limacharlie endpoint-policy`
- [ ] `endpoint-policy isolate <sid> --confirm` - Isolate sensor from network (DESTRUCTIVE)
- [ ] `endpoint-policy rejoin <sid> --confirm` - Rejoin sensor to network (DESTRUCTIVE)
- [ ] `endpoint-policy status <sid>` - Check isolation status
- [ ] `endpoint-policy seal <sid>` - Seal sensor
- [ ] `endpoint-policy unseal <sid>` - Unseal sensor

### Sensor Tasking Commands - `limacharlie task`
- [ ] `task send <sid> <task-command> [--investigation-id <id>]` - Send task to sensor (fire-and-forget)
- [ ] `task request <sid> <task-command> [--timeout <secs>]` - Send task and wait for response
- [ ] `task reliable-send <sid> <task-command>` - Guaranteed delivery task
- [ ] `task reliable-list <sid>` - List pending reliable tasks
- [ ] `task reliable-delete <sid> <task-id>` - Cancel reliable task

### D&R Rule Commands - `limacharlie rule`
- [ ] `rule list [--namespace <ns>]` - List D&R rules (namespace: general, managed, service)
- [ ] `rule get <name> [--namespace <ns>]` - Get rule details
- [ ] `rule create <name> --detect <json-or-file> --respond <json-or-file> [--namespace <ns>] [--enabled] [--ttl <secs>] [--replace]` - Create/replace rule
- [ ] `rule create --input-file <yaml-or-json>` - Create rule from file
- [ ] `rule update <name> --detect <json-or-file> --respond <json-or-file> [--namespace <ns>]` - Update existing rule
- [ ] `rule delete <name> [--namespace <ns>]` - Delete rule
- [ ] `rule test <name> --events <json-or-file> [--trace]` - Test rule against sample events
- [ ] `rule replay <name> --start <time> --end <time> [--sid <sid>] [--selector <bexpr>] [--trace] [--dry-run]` - Replay rule against historical data
- [ ] `rule validate --detect <json-or-file> --respond <json-or-file>` - Validate rule components without deploying
- [ ] `rule export [--namespace <ns>]` - Export all rules as YAML
- [ ] `rule import --input-file <yaml> [--namespace <ns>] [--dry-run]` - Import rules from YAML

### False Positive Commands - `limacharlie fp`
- [ ] `fp list` - List false positive rules
- [ ] `fp get <name>` - Get FP rule details
- [ ] `fp create <name> --rule <json-or-file> [--replace]` - Create FP rule
- [ ] `fp delete <name>` - Delete FP rule

### Hive Commands - `limacharlie hive`
- [ ] `hive list-types` - List available hive types (dr-general, dr-managed, fp, cloud_sensor, yara, secret, lookup, query, playbook, ai_agent, external_adapter, ...)
- [ ] `hive list <hive-name> [--partition-key <pk>]` - List records in a hive
- [ ] `hive get <hive-name> <key> [--partition-key <pk>]` - Get record
- [ ] `hive set <hive-name> <key> --data <json-or-file> [--enabled] [--tags <t1,t2>] [--comment <text>] [--expiry <ts>] [--etag <etag>] [--partition-key <pk>]` - Create/update record
- [ ] `hive delete <hive-name> <key> [--partition-key <pk>]` - Delete record
- [ ] `hive validate <hive-name> <key> --data <json-or-file> [--partition-key <pk>]` - Validate record
- [ ] `hive rename <hive-name> <key> <new-key> [--partition-key <pk>]` - Rename record
- [ ] `hive export <hive-name> [--partition-key <pk>]` - Export all records as YAML
- [ ] `hive import <hive-name> --input-file <yaml> [--partition-key <pk>] [--dry-run]` - Import records

### Output Commands - `limacharlie output`
- [ ] `output list` - List configured outputs
- [ ] `output get <name>` - Get output details
- [ ] `output create <name> --module <type> --type <data-type> [--params <json>]` - Create output
- [ ] `output create --input-file <yaml-or-json>` - Create from file
- [ ] `output delete <name>` - Delete output

### Artifact Commands - `limacharlie artifact`
- [ ] `artifact upload <file-path> [--source <src>] [--hint <hint>] [--retention-days <n>] [--original-path <path>]` - Upload artifact/log
- [ ] `artifact list [--sensor <sid>]` - List artifacts
- [ ] `artifact get <artifact-id>` - Get artifact details
- [ ] `artifact download <artifact-id> [--output-path <path>]` - Download artifact
- [ ] `artifact rules list` - List artifact collection rules
- [ ] `artifact rules create <name> --patterns <p1,p2> [--tags <t1,t2>] [--platforms <plats>]` - Create rule
- [ ] `artifact rules delete <name>` - Delete rule

### Payload Commands - `limacharlie payload`
- [ ] `payload list` - List payloads
- [ ] `payload upload <name> --file <path>` - Upload payload
- [ ] `payload download <name> [--output-path <path>]` - Download payload
- [ ] `payload delete <name>` - Delete payload

### Search Commands - `limacharlie search`
- [ ] `search run <lcql-query> --start <time> --end <time> [--stream <event|detect|audit>] [--limit <n>]` - Execute LCQL query
- [ ] `search run --input-file <query-file> --start <time> --end <time>` - Execute from file
- [ ] `search validate <lcql-query>` - Validate LCQL syntax
- [ ] `search estimate <lcql-query> --start <time> --end <time>` - Estimate billing cost
- [ ] `search saved list` - List saved queries
- [ ] `search saved get <name>` - Get saved query
- [ ] `search saved create <name> --query <lcql> --start <time> --end <time>` - Create saved query
- [ ] `search saved run <name>` - Execute saved query
- [ ] `search saved delete <name>` - Delete saved query
- [ ] `search interactive [--limit-events <n>] [--limit-evals <n>] [--format <table|json>]` - Interactive REPL shell for LCQL queries with history, help, and inline results

### IOC Search Commands - `limacharlie ioc`
- [ ] `ioc search <type> <value> [--case-sensitive] [--wildcards] [--limit <n>]` - Search for IOC (type: domain, ip, file_hash, file_path, file_name, user, service_name, package_name, hostname)
- [ ] `ioc batch-search --input-file <file>` - Batch IOC search from file
- [ ] `ioc hosts <hostname-prefix>` - Find sensors by hostname
- [ ] `ioc enrich <type> <value>` - Get enrichment info for an indicator (object information lookup)
- [ ] `ioc batch-enrich --input-file <file>` - Batch enrichment lookup from file

### Event Commands - `limacharlie event`
- [ ] `event list --sensor <sid> --start <time> --end <time> [--event-type <type>] [--limit <n>] [--forward]` - Get historical events for sensor
- [ ] `event get --atom <atom>` - Get event by atom
- [ ] `event children --atom <atom>` - Get child events of an atom
- [ ] `event overview --sensor <sid> --start <time> --end <time>` - Get event overview
- [ ] `event timeline --sensor <sid> --start <time> --end <time> [--bucket <day|hour>] [--types <t1,t2>]` - Get event timeline
- [ ] `event types [--platform <plat>]` - List available event types with schemas
- [ ] `event schema <event-type>` - Get schema for specific event type
- [ ] `event retention --start <time> --end <time> [--sensor <sid>] [--detailed]` - Get event retention stats

### Detection Commands - `limacharlie detection`
- [ ] `detection list --start <time> --end <time> [--category <cat>] [--limit <n>]` - List detections in time range
- [ ] `detection get <detection-id>` - Get detection by ID
- [ ] `detection list --sensor <sid> --start <time> --end <time>` - Get detections for specific sensor

### Extension Commands - `limacharlie extension`
- [ ] `extension list` - List subscribed extensions
- [ ] `extension list-available` - List all available extensions
- [ ] `extension subscribe <name>` - Subscribe to extension
- [ ] `extension unsubscribe <name>` - Unsubscribe from extension
- [ ] `extension rekey <name>` - Rotate extension API key
- [ ] `extension schema <name>` - Get extension configuration schema
- [ ] `extension request <name> --action <action> [--data <json>]` - Call extension
- [ ] `extension config list` - List extension configurations (from extension_config hive)
- [ ] `extension config get <name>` - Get extension config
- [ ] `extension config set <name> --data <json-or-file>` - Set extension config
- [ ] `extension config delete <name>` - Delete extension config
- [ ] `extension convert-rules <name> [--dry-run]` - Convert/migrate D&R rules for use with an extension

### Installation Key Commands - `limacharlie installation-key`
- [ ] `installation-key list` - List installation keys
- [ ] `installation-key get <iid>` - Get key details
- [ ] `installation-key create --description <desc> [--tags <t1,t2>] [--use-public-ca]` - Create key
- [ ] `installation-key delete <iid>` - Delete key

### Ingestion Key Commands - `limacharlie ingestion-key`
- [ ] `ingestion-key list` - List ingestion keys
- [ ] `ingestion-key create <name>` - Create key
- [ ] `ingestion-key delete <name>` - Delete key
- [ ] `ingestion-key configure <name> [--parse-hint <hint>] [--format-re <regex>]` - Configure USP on key

### User Commands - `limacharlie user`
- [ ] `user list` - List organization users
- [ ] `user invite <email> [--emails-file <file>]` - Invite user(s) to organization
- [ ] `user remove <email>` - Remove user from organization
- [ ] `user permissions list` - List user permissions
- [ ] `user permissions add <email> <permission>` - Grant permission
- [ ] `user permissions remove <email> <permission>` - Revoke permission
- [ ] `user permissions set-role <email> <role>` - Set user role (owner, admin, operator, viewer, basic)

### Group Commands - `limacharlie group` (NEW)
- [ ] `group list [--detailed]` - List organization groups
- [ ] `group get <gid>` - Get group details
- [ ] `group create <name>` - Create group
- [ ] `group delete <gid>` - Delete group
- [ ] `group member add <gid> <email>` - Add member to group
- [ ] `group member remove <gid> <email>` - Remove member
- [ ] `group owner add <gid> <email>` - Add owner
- [ ] `group owner remove <gid> <email>` - Remove owner
- [ ] `group permissions set <gid> --permissions <p1,p2,...>` - Set group permissions
- [ ] `group org add <gid> <oid>` - Add org to group
- [ ] `group org remove <gid> <oid>` - Remove org from group
- [ ] `group logs <gid>` - Get group audit logs

### API Key Commands - `limacharlie api-key`
- [ ] `api-key list` - List API keys
- [ ] `api-key create <name> --permissions <p1,p2,...> [--ip-range <cidr>]` - Create API key
- [ ] `api-key delete <key-hash>` - Delete API key

### Billing Commands - `limacharlie billing`
- [ ] `billing status` - Get billing status (is past due?)
- [ ] `billing details` - Get full billing details
- [ ] `billing invoice <year> <month> [--format pdf|csv]` - Get invoice URL
- [ ] `billing plans` - List available plans
- [ ] `billing skus` - Get SKU definitions

### Stream Commands - `limacharlie stream`
- [ ] `stream events [--investigation-id <id>] [--tag <tag>] [--category <cat>] [--sensor <sid>]` - Stream events in real-time (Spout)
- [ ] `stream detections [--investigation-id <id>] [--tag <tag>] [--category <cat>]` - Stream detections
- [ ] `stream audit` - Stream audit logs
- [ ] `stream --firehose --listen <ip:port> [--tls-cert <path> --tls-key <path>]` - Start firehose listener

### Replay Commands - `limacharlie replay`
- [ ] `replay run <rule-name-or-file> --start <time> --end <time> [--sid <sid>] [--selector <bexpr>] [--stream <type>] [--trace] [--dry-run] [--limit-events <n>] [--limit-evals <n>]` - Replay D&R rule against historical data

### Integrity Commands - `limacharlie integrity`
- [ ] `integrity list` - List integrity monitoring rules
- [ ] `integrity get <name>` - Get rule details
- [ ] `integrity create <name> --patterns <p1,p2> [--tags <t1,t2>] [--platforms <plats>]` - Create rule
- [ ] `integrity delete <name>` - Delete rule

### Exfil Commands - `limacharlie exfil`
- [ ] `exfil list` - List exfil prevention rules
- [ ] `exfil create-watch <name> --event <type> --value <val> --operator <op> --path <path> [--tags <t1,t2>] [--platforms <plats>]` - Create watch rule
- [ ] `exfil create-event <name> --events <e1,e2> [--tags <t1,t2>] [--platforms <plats>]` - Create event-based rule
- [ ] `exfil delete <name>` - Delete exfil rule

### Logging Commands - `limacharlie logging`
- [ ] `logging list` - List log collection rules
- [ ] `logging get <name>` - Get log collection rule details
- [ ] `logging create <name> --patterns <p1,p2> [--tags <t1,t2>] [--platforms <plats>] [--retention-days <n>] [--delete-after]` - Create log collection rule
- [ ] `logging delete <name>` - Delete log collection rule

### YARA Commands - `limacharlie yara`
- [ ] `yara scan <sid> --rule <yara-rule-or-file> [--timeout <secs>]` - Ad-hoc YARA scan on a sensor
- [ ] `yara rules list` - List active YARA scanning rules
- [ ] `yara rules add <name> --sources <s1,s2> [--tags <t1,t2>] [--platforms <plats>]` - Add YARA scanning rule
- [ ] `yara rules delete <name>` - Delete YARA scanning rule
- [ ] `yara sources list` - List YARA signature sources
- [ ] `yara sources get <name>` - Get a YARA source definition
- [ ] `yara sources add <name> --source <url-or-file>` - Add YARA signature source
- [ ] `yara sources delete <name>` - Delete YARA signature source

### Sync (IaC) Commands - `limacharlie sync`
- [ ] `sync pull [--rules] [--fps] [--outputs] [--integrity] [--exfil] [--logging] [--artifacts] [--extensions] [--org-configs] [--hives <h1,h2>] [--installation-keys] [--yara] [--all] --output-file <path>` - Download current config
- [ ] `sync push --input-file <path> [--rules] [--fps] [--outputs] [--integrity] [--exfil] [--logging] [--artifacts] [--extensions] [--org-configs] [--hives <h1,h2>] [--installation-keys] [--yara] [--all] [--force] [--dry-run]` - Upload config
- [ ] `sync diff --input-file <path> [--rules] [--fps] [--all]` - Show diff between local and remote

### AI Generation Commands - `limacharlie ai` (NEW)
- [ ] `ai generate-rule <description>` - Generate complete D&R rule from natural language
- [ ] `ai generate-detection <description>` - Generate detection component only
- [ ] `ai generate-response <description>` - Generate response component only
- [ ] `ai generate-query <description> [--start <time> --end <time>]` - Generate LCQL query from natural language
- [ ] `ai generate-selector <description>` - Generate sensor selector expression
- [ ] `ai generate-playbook <description>` - Generate Python playbook
- [ ] `ai summarize-detection --detection-id <id>` - Summarize a detection

### Investigation Commands - `limacharlie investigation` (NEW)
- [ ] `investigation list` - List investigations
- [ ] `investigation get <id>` - Get investigation details
- [ ] `investigation create --data <json-or-file>` - Create investigation
- [ ] `investigation update <id> --data <json-or-file>` - Update investigation
- [ ] `investigation delete <id>` - Delete investigation
- [ ] `investigation expand <id> --sensor <sid> [--events <json>]` - Expand investigation timeline

### USP Commands - `limacharlie usp`
- [ ] `usp validate --platform <plat> [--mapping <json-or-file>] [--mappings-file <file>] [--input <data-or-file>] [--hostname <h>] [--indexing-file <file>]` - Validate USP adapter configuration

### Secret Commands - `limacharlie secret` (NEW - shortcuts for hive/secret)
- [ ] `secret list` - List secrets
- [ ] `secret get <name>` - Get secret value
- [ ] `secret set <name> --value <val>` - Set secret
- [ ] `secret delete <name>` - Delete secret

### Lookup Commands - `limacharlie lookup` (NEW - shortcuts for hive/lookup)
- [ ] `lookup list` - List lookups
- [ ] `lookup get <name>` - Get lookup data
- [ ] `lookup set <name> --data <json-or-file>` - Create/update lookup
- [ ] `lookup query <name> --value <val>` - Query a lookup table by value
- [ ] `lookup delete <name>` - Delete lookup

### Playbook Commands - `limacharlie playbook` (NEW - shortcuts for hive/playbook)
- [ ] `playbook list` - List playbooks
- [ ] `playbook get <name>` - Get playbook
- [ ] `playbook set <name> --data <json-or-file>` - Create/update playbook
- [ ] `playbook delete <name>` - Delete playbook

### Adapter Commands - `limacharlie adapter` (NEW - shortcuts for external adapters)
- [ ] `adapter list` - List external adapters
- [ ] `adapter get <name>` - Get adapter config
- [ ] `adapter set <name> --data <json-or-file>` - Create/update adapter
- [ ] `adapter delete <name>` - Delete adapter

### Cloud Sensor Commands - `limacharlie cloud-sensor` (NEW - shortcuts for hive/cloud_sensor)
- [ ] `cloud-sensor list` - List cloud sensor configurations (S3, GCS, etc.)
- [ ] `cloud-sensor get <name>` - Get cloud sensor config
- [ ] `cloud-sensor set <name> --data <json-or-file>` - Create/update cloud sensor
- [ ] `cloud-sensor delete <name>` - Delete cloud sensor

### SOP Commands - `limacharlie sop` (NEW)
- [ ] `sop list` - List SOPs
- [ ] `sop get <name>` - Get SOP
- [ ] `sop set <name> --data <json-or-file>` - Create/update SOP
- [ ] `sop delete <name>` - Delete SOP

### Note Commands - `limacharlie note` (NEW)
- [ ] `note list` - List org notes
- [ ] `note get <name>` - Get note
- [ ] `note set <name> --data <json-or-file>` - Create/update note
- [ ] `note delete <name>` - Delete note

### ARL Commands - `limacharlie arl`
- [ ] `arl get <arl-url>` - Resolve and fetch data from an Authenticated Resource Locator (ARL)

### Job Commands - `limacharlie job`
- [ ] `job list` - List service/replicant jobs
- [ ] `job get <job-id>` - Get job details and status
- [ ] `job wait <job-id> [--timeout <secs>]` - Wait for job to finish, printing status updates
- [ ] `job delete <job-id>` - Cancel/delete a job

### Audit Commands - `limacharlie audit`
- [ ] `audit list --start <time> --end <time> [--limit <n>] [--event-type <type>] [--sensor <sid>]` - Get audit logs

### SpotCheck Commands - `limacharlie spotcheck`
- [ ] `spotcheck run --config <json-or-file>` - Run concurrent IOC spot checks

### Help & Discovery Commands - `limacharlie help` / `limacharlie discover`
- [ ] `limacharlie discover` - List all commands grouped by profile/use-case
- [ ] `limacharlie discover --profile <profile>` - List commands for a specific profile (sensor_management, detection_engineering, historical_data, live_investigation, threat_response, fleet_management, platform_admin, ai_powered)
- [ ] `limacharlie help <topic>` - Concept guides (topics: d&r-rules, hive, lcql, sensors, outputs, extensions, sync, auth, permissions, events, detections, adapters, platform-codes, ioc-types, timestamps)
- [ ] `limacharlie cheatsheet <topic>` - Quick reference with copy-paste examples
- [ ] `limacharlie schema <command>` - JSON Schema for command parameters
- [ ] Any command with `--explain` - Detailed description of what the command does

---

## 6. Output & Formatting

### 6.1 Output Modes
- [ ] `--output table` (default for TTY) - Rich tables with borders and colors
- [ ] `--output json` (default for pipes) - Pretty-printed JSON
- [ ] `--output yaml` - YAML format
- [ ] `--output csv` - CSV with headers
- [ ] `--output jsonl` - One JSON object per line (for streaming)
- [ ] Auto-detection: use `json` when stdout is not a TTY

### 6.2 Filtering & Transformation
- [ ] `--filter <jmespath>` - JMESPath expression for filtering/transforming output
- [ ] `--fields <f1,f2,f3>` - Select specific fields to display
- [ ] `--sort-by <field>` - Sort results by field
- [ ] `--reverse` - Reverse sort order

### 6.3 Progress & Status
- [ ] Progress bars for long-running operations (upload, search, replay)
- [ ] Status spinners for operations in progress
- [ ] Suppress progress with `--quiet`

---

## 7. AI/LLM Discoverability Features

### 7.1 Concept Help System
- [ ] Embedded help for every LimaCharlie concept
- [ ] Each help topic includes: what it is, when to use it, how it relates to other concepts, examples
- [ ] Topics auto-linked (e.g., "See also: `limacharlie help hive`")

### 7.2 Rich Help Text Content

The following help topics should be embedded in the CLI and available via `limacharlie help <topic>` (check ../documentation to better understand):

- [ ] **d&r-rules**: What D&R rules are, namespaces (general/managed/service), rule structure (detect + respond), operators (is, contains, matches, and, or, etc.), common patterns, testing with replay, lifecycle
- [ ] **hive**: What hives are, available hive types and what each stores, record structure (data + usr_mtd), etag for transactions, ARL for remote data, partition keys, common operations
- [ ] **lcql**: LCQL query syntax (5 components: timeframe, sensors, events, filter, projection), operators (comparison, string, pattern, network, scope), field selectors, common query examples, billing implications
- [ ] **sensors**: Sensor lifecycle, platforms (windows, linux, macos, chrome), architecture types, sensor selectors (bexpr syntax), installation keys, online/offline, isolation, tagging, tasking
- [ ] **outputs**: Output types (S3, GCS, Syslog, Webhook, Slack, SMTP, Kafka, Elastic, DataDog, etc.), data types (event, detect, audit, deployment, artifact, tailored, billing), configuration options
- [ ] **extensions**: What extensions are, subscribing/unsubscribing, extension configs, schemas, requesting actions
- [ ] **sync**: Infrastructure-as-Code with LimaCharlie, push/pull/diff workflow, component selection, force mode, dry-run, file format
- [ ] **auth**: Authentication methods (API key, OAuth, JWT), credential storage, environments/profiles, permission model, roles (owner, admin, operator, viewer, basic)
- [ ] **permissions**: Full list of permissions (org.get, sensor.task, dr.set, etc.) with descriptions of what each grants
- [ ] **events**: Event types available in LimaCharlie, event structure (routing + event), atoms and event trees, retention, event schemas
- [ ] **detections**: How D&R rules generate detections, detection categories, detection lifecycle, false positives
- [ ] **adapters**: External adapters, cloud sensors, USP (Universal Sensor Protocol), adapter types and configuration
- [ ] **platform-codes**: Platform identifiers (windows=268435456, linux=536870912, macos=805306368, etc.) and when they're used
- [ ] **ioc-types**: IOC types supported (domain, ip, file_hash, file_path, file_name, user, service_name, package_name, hostname) with examples
- [ ] **timestamps**: Timestamp conventions (API=seconds, events=milliseconds), conversion rules, time range formats
- [ ] **bexpr**: Sensor selector expression syntax (bexpr), available fields (sid, oid, plat, arch, hostname, int_ip, ext_ip, alive, tags), operators (==, !=, in, matches, contains), examples
- [ ] **billing**: Billing model, SKU types, usage metrics, quota management

### 7.3 Command Explain System
- [ ] Every command supports `--explain` flag
- [ ] Explain output includes: purpose, when to use, related commands, examples, common pitfalls
- [ ] Example: `limacharlie rule create --explain` prints a multi-paragraph guide about creating D&R rules

### 7.4 Profile-Based Discovery
- [ ] `limacharlie discover --profile sensor_management` - Sensor lifecycle commands
- [ ] `limacharlie discover --profile detection_engineering` - Rule creation, testing, deployment commands
- [ ] `limacharlie discover --profile historical_data` - Search, LCQL, event queries
- [ ] `limacharlie discover --profile live_investigation` - Sensor tasking, process/network inspection
- [ ] `limacharlie discover --profile threat_response` - Isolation, tagging, sensor management during incidents
- [ ] `limacharlie discover --profile fleet_management` - Installation keys, deployment, upgrades
- [ ] `limacharlie discover --profile platform_admin` - Users, groups, API keys, billing, outputs
- [ ] `limacharlie discover --profile ai_powered` - AI generation commands

### 7.5 Error Messages with Guidance
- [ ] Every error message includes a "Suggestion:" line
- [ ] Example: `Error: OID not set. Suggestion: Run 'limacharlie auth use-org <oid>' or set LC_OID environment variable`
- [ ] Example: `Error: Permission denied (missing 'dr.set'). Suggestion: Ask your org admin to grant 'dr.set' permission, or create a new API key with 'limacharlie api-key create'`
- [ ] Example: `Error: Rate limited. Suggestion: Wait 10 seconds and retry, or use --retry flag for automatic retry`

---

## 8. Testing Strategy

### 8.1 Test Framework
- [ ] pytest as test runner
- [ ] pytest-asyncio for async tests
- [ ] pytest-cov for coverage reporting
- [ ] responses library for HTTP mocking in unit tests
- [ ] click.testing.CliRunner for CLI command testing

### 8.2 Unit Tests
All unit tests should be runnable without credentials or network access.

- [ ] **test_cli_commands.py** - Test every CLI command's argument parsing, help text, and error handling using CliRunner
- [ ] **test_config.py** - Test credential resolution order, environment handling, ephemeral mode, file I/O
- [ ] **test_client.py** - Test HTTP client retry logic, JWT refresh, rate limit handling, request formatting (mocked)
- [ ] **test_output.py** - Test all output formatters (json, yaml, csv, table, jsonl), field selection, filtering, sorting
- [ ] **test_errors.py** - Test error hierarchy, error messages with suggestions, exit codes
- [ ] **test_sdk_organization.py** - Test Organization class methods with mocked HTTP responses
- [ ] **test_sdk_sensor.py** - Test Sensor class methods with mocked HTTP
- [ ] **test_sdk_dr_rules.py** - Test D&R rule CRUD with mocked HTTP, namespace handling, validation
- [ ] **test_sdk_hive.py** - Test Hive operations with mocked HTTP, etag transactions, batch operations
- [ ] **test_sdk_search.py** - Test Search/LCQL with mocked HTTP, pagination, saved queries
- [ ] **test_sdk_configs.py** - Test Configs sync with mocked HTTP, diff generation
- [ ] **test_discovery.py** - Test help system, explain mode, profile-based discovery
- [ ] **test_help_topics.py** - Ensure all help topics are valid, complete, and don't reference missing commands

### 8.3 Integration Tests
All integration tests use a real LimaCharlie org (credentials via `--oid` and `--key` pytest options). Every test must **clean up** after itself, including on failure, to ensure the test org stays in a known state.

**Test pattern**: Setup -> Action -> Assert -> **Cleanup in finally block**

- [ ] **test_auth.py**
  - Test `auth whoami` returns valid identity
  - Test `auth test --permissions org.get,sensor.list` succeeds
  - Test `auth list-orgs` returns at least one org

- [ ] **test_sensor.py**
  - Test `sensor list` returns sensors (if any online)
  - Test `sensor list --selector 'plat == \`windows\`'` filters correctly
  - Test `sensor get <sid>` returns valid sensor info
  - Test `tag add/remove` cycle on a sensor
  - Test `tag list` returns tags for org
  - Test network isolation and rejoin cycle (on compatible sensor)

- [ ] **test_rules.py**
  - Test create D&R rule -> verify exists -> delete -> verify gone
  - Test create rule in managed namespace -> verify -> delete
  - Test create rule with --replace flag
  - Test create rule with --ttl flag
  - Test create rule from --input-file (YAML)
  - Test rule validate succeeds for valid rule and fails for invalid
  - Test rule replay against historical data (if data exists)
  - Test rule export/import round-trip

- [ ] **test_hive.py**
  - Test CRUD lifecycle: set -> get -> validate -> rename -> delete
  - Test set with metadata (enabled, tags, comment, expiry)
  - Test etag-based transaction (set -> modify with etag -> verify)
  - Test different hive types: dr-general, cloud_sensor, lookup
  - Test hive list returns correct records
  - Test export/import round-trip

- [ ] **test_outputs.py**
  - Test create syslog output -> verify in list -> delete -> verify gone
  - Test output with various modules (syslog, webhook, etc.)

- [ ] **test_artifacts.py**
  - Test upload small file -> verify upload succeeded
  - Test artifact list (verify uploaded artifact appears)
  - (Cleanup: artifacts auto-expire, but verify cleanup logic)

- [ ] **test_search.py**
  - Test search validate with valid LCQL
  - Test search validate with invalid LCQL (expect error)
  - Test search estimate returns billing info
  - Test search run returns results (if data exists)
  - Test saved query lifecycle: create -> list -> get -> run -> delete

- [ ] **test_extensions.py**
  - Test extension list returns subscribed extensions
  - (Note: subscribe/unsubscribe may have billing implications - test carefully)

- [ ] **test_users.py**
  - Test user list returns at least one user
  - Test user permissions list returns permissions
  - (Note: invite/remove are destructive - test with care)

- [ ] **test_api_keys.py**
  - Test api-key list returns at least one key
  - Test create key -> verify in list -> delete -> verify gone
  - Test create key with specific permissions
  - Test create key with IP range restriction

- [ ] **test_installation_keys.py**
  - Test installation-key list
  - Test create -> get -> delete lifecycle
  - Test create with tags and description

- [ ] **test_ingestion_keys.py**
  - Test ingestion-key list
  - Test create -> list -> delete lifecycle

- [ ] **test_sync.py**
  - Test sync pull downloads config
  - Test sync push with dry-run shows expected changes
  - Test sync push/pull round-trip for rules
  - Test sync push with force for hive
  - Test sync diff shows correct differences

- [ ] **test_replay.py**
  - Test replay with inline rule
  - Test replay with trace output
  - Test replay dry-run

- [ ] **test_stream.py**
  - Test spout connection for events (connect, receive 1 event or timeout, disconnect)
  - Test spout with filter (tag or category)

- [ ] **test_ai.py**
  - Test ai generate-query with simple description
  - Test ai generate-detection with simple description
  - (Note: AI endpoints have rate limits - test sparingly)

- [ ] **test_billing.py**
  - Test billing status returns valid response
  - Test billing plans returns available plans

- [ ] **test_groups.py**
  - Test group list
  - Test group create -> get -> delete lifecycle
  - (Note: group membership tests need careful cleanup)

- [ ] **test_org_management.py**
  - Test org info returns valid data
  - Test org config get
  - Test org urls returns URLs
  - Test org stats returns usage data
  - Test org errors returns error list (may be empty)
  - Test org mitre-report returns report data

- [ ] **test_usp.py**
  - Test usp validate with valid mapping
  - Test usp validate with invalid mapping (expect error details)

- [ ] **test_integrity.py**
  - Test integrity rule lifecycle: create -> list -> get -> delete

- [ ] **test_exfil.py**
  - Test exfil rule lifecycle: create watch -> list -> delete
  - Test exfil rule lifecycle: create event -> list -> delete

- [ ] **test_logging.py**
  - Test logging rule lifecycle: create -> list -> get -> delete
  - Test create with patterns, retention, and platforms

- [ ] **test_yara.py**
  - Test yara sources list
  - Test yara source add -> list -> delete lifecycle
  - Test yara rules list
  - Test yara rule add -> list -> delete lifecycle
  - Test yara scan on an online sensor (if available)

- [ ] **test_jobs.py**
  - Test job list returns valid response
  - Test job get for a known job (created by replay or other service)

- [ ] **test_cli_e2e.py**
  - End-to-end test using subprocess to invoke actual CLI
  - Test `limacharlie --version`
  - Test `limacharlie discover` output contains expected profiles
  - Test `limacharlie help d&r-rules` returns non-empty help
  - Test `limacharlie org info --output json` returns valid JSON
  - Test `limacharlie sensor list --output json` returns valid JSON array
  - Test piping: `limacharlie sensor list --output json | limacharlie --input-json ...` (if applicable)

### 8.4 Test Fixtures & Cleanup
- [ ] `conftest.py` with shared fixtures:
  - `lc_client` fixture that creates authenticated Client
  - `lc_org` fixture that creates Organization
  - `unique_name()` helper that generates unique test names with prefix `test-cli-v2-`
  - `cleanup` fixture that tracks created resources and deletes them in teardown
  - Automatic cleanup on fixture teardown (even on assertion failure)
- [ ] All test names prefixed to avoid collision with other tests
- [ ] Tests are idempotent (can be re-run without manual cleanup)
- [ ] Each test creates its own resources and cleans up after

### 8.5 Test CI Configuration
- [ ] Update `cloudbuild.yaml` to run v2 tests
- [ ] Unit tests: `pytest tests/unit/ -v`
- [ ] Integration tests: `pytest tests/integration/ -v --oid=$OID --key=$KEY`
- [ ] Can run locally with `LC_OID` and `LC_API_KEY` env vars

---

## 9. Migration & Packaging

### 9.1 Package Structure
- [ ] Package name remains `limacharlie`
- [ ] Version bumped to `2.0.0`
- [ ] v2 code replaces v1 code directly in `limacharlie/` package
- [ ] Entry point `limacharlie` runs Click-based CLI
- [ ] No legacy v1 entry point (clean break)

### 9.2 Dependencies
- [ ] `click` - CLI framework
- [ ] `requests` - HTTP client
- [ ] `websocket-client` - WebSocket for Spout
- [ ] `pyyaml` - YAML support
- [ ] `tabulate` - Table output
- [ ] `jmespath` - Output filtering
- [ ] `rich` - Rich terminal output (progress bars, spinners, tables)
- [ ] `typing-extensions` - Type annotation support

### 9.3 Python Version Support
- [ ] Python 3.9+
- [ ] Type annotations throughout (for IDE support and documentation)

---

## 10. Detailed Command Reference

### 10.1 Time Format Specification

All `--start` and `--end` parameters accept:
- **Relative**: `-1h`, `-24h`, `-720h` (30 days), `-1h30m`
- **Absolute**: `2025-01-15T00:00:00Z`, `2025-01-15`
- **Unix timestamp**: `1705276800` (seconds), `1705276800000` (milliseconds, auto-detected)
- **Note**: Days (`d`) should also be supported as shorthand: `-7d` = `-168h`

### 10.2 Common Flag Conventions

| Flag | Type | Description |
|------|------|-------------|
| `--oid` | UUID | Organization ID (overrides default) |
| `--sid` | UUID | Sensor ID |
| `--name` | string | Resource name |
| `--output` | enum | Output format: json, yaml, csv, table, jsonl |
| `--input-file` | path | Read input from JSON or YAML file |
| `--filter` | jmespath | JMESPath expression for filtering output |
| `--fields` | csv | Comma-separated list of fields to display |
| `--limit` | int | Maximum number of results |
| `--offset` | int | Pagination offset |
| `--confirm` | flag | Required for destructive operations |
| `--dry-run` | flag | Simulate without making changes |
| `--debug` | flag | Show request/response debug info |
| `--quiet` / `-q` | flag | Suppress non-error output |
| `--explain` | flag | Print detailed command explanation |
| `--retry` | flag | Auto-retry on rate limits |

### 10.3 Sensor Selector Syntax (bexpr)

Used in `--selector` parameter for commands like `sensor list`, `tag mass-add`, `rule replay`:

```
plat == `windows`                    # Windows sensors
`production` in tags                 # Sensors with 'production' tag
hostname matches `^web-`             # Hostname starts with 'web-'
int_ip == `10.0.0.1`               # Internal IP match
ext_ip matches `^192\\.168\\.`     # External IP pattern
arch == `x64`                       # 64-bit architecture
plat == `windows` and `prod` in tags # Combined filters
```

Available fields: `sid`, `oid`, `plat`, `arch`, `hostname`, `int_ip`, `ext_ip`, `alive`, `tags`, `os`, `version`, `did`

### 10.4 Permission Reference

Full list of permissions available for API keys and user roles:

| Permission | Description |
|-----------|-------------|
| `org.get` | View organization info |
| `org.set` | Modify organization settings |
| `sensor.get` | View sensor info |
| `sensor.list` | List sensors |
| `sensor.task` | Send tasks to sensors |
| `sensor.tag` | Manage sensor tags |
| `dr.list` | List D&R rules |
| `dr.set` | Create/modify D&R rules |
| `dr.del` | Delete D&R rules |
| `dr.list.managed` | List managed D&R rules |
| `dr.set.managed` | Create/modify managed D&R rules |
| `dr.del.managed` | Delete managed D&R rules |
| `output.list` | List outputs |
| `output.set` | Create/modify outputs |
| `output.del` | Delete outputs |
| `ikey.list` | List installation keys |
| `ikey.set` | Create installation keys |
| `ikey.del` | Delete installation keys |
| `ingestkey.ctrl` | Manage ingestion keys |
| `audit.get` | View audit logs |
| `fp.ctrl` | Manage false positive rules |
| `org.conf.get` | View org configuration |
| `org.conf.set` | Modify org configuration |
| `user.ctrl` | Manage users |
| `apikey.ctrl` | Manage API keys |
| `billing.ctrl` | View billing info |
| `replicant.get` | List replicants |
| `replicant.task` | Run replicant tasks |
| `insight.evt.get` | Query events (Insight) |

---

## 11. Implementation Checklist

### Phase 1: Core Infrastructure
- [x] Remove v1 modules and create new `limacharlie/` directory structure (sdk/, commands/)
- [x] Implement `errors.py` - Error hierarchy with suggestion messages
- [x] Implement `config.py` - Credential resolution, environment management
- [x] Implement `client.py` - HTTP client with retry, auth, rate limiting
- [x] Implement `output.py` - All output formatters (json, yaml, csv, table, jsonl)
- [x] Implement `cli.py` - Main click entry point with global options
- [x] Implement `discovery.py` - Help topics, explain system, profile-based discovery
- [x] Write unit tests for all core infrastructure

### Phase 2: SDK Classes
- [x] Implement `sdk/organization.py` - Organization class
- [x] Implement `sdk/sensor.py` - Sensor class
- [x] Implement `sdk/dr_rules.py` - D&R rule operations
- [x] Implement `sdk/fp_rules.py` - False positive operations
- [x] Implement `sdk/hive.py` - Hive client with records, batch, transactions
- [x] Implement `sdk/outputs.py` - Output management
- [x] Implement `sdk/artifacts.py` - Artifact upload/download with multipart
- [x] Implement `sdk/payloads.py` - Payload management
- [x] Implement `sdk/search.py` - LCQL search with pagination
- [x] Implement `sdk/insight.py` - IOC search, event queries
- [x] Implement `sdk/extensions.py` - Extension management
- [x] Implement `sdk/installation_keys.py`
- [x] Implement `sdk/ingestion_keys.py`
- [x] Implement `sdk/users.py` - User & permission management
- [x] Implement `sdk/groups.py` - Group management (NEW)
- [x] Implement `sdk/api_keys.py` - API key management
- [x] Implement `sdk/billing.py` - Billing operations
- [x] Implement `sdk/spout.py` - WebSocket real-time streaming
- [x] Implement `sdk/firehose.py` - TCP/TLS streaming
- [x] Implement `sdk/replay.py` - D&R replay
- [x] Implement `sdk/integrity.py` - Integrity monitoring rules
- [x] Implement `sdk/exfil.py` - Exfil prevention rules
- [x] Implement `sdk/logging_rules.py` - Logging rules
- [x] Implement `sdk/configs.py` - Configuration sync
- [x] Implement `sdk/ai.py` - AI generation (NEW)
- [x] Implement `sdk/investigations.py` - Investigation management (NEW)
- [x] Implement `sdk/usp.py` - USP validation (note: sensor tasking/comms is handled via sdk/sensor.py task methods, no separate comms module needed)
- [x] Implement `sdk/jobs.py` - Service job tracking
- [x] Implement `sdk/yara.py` - YARA scanning & rule management
- [x] Implement `sdk/arl.py` - Authenticated Resource Locator resolution
- [x] Write unit tests for all SDK classes

### Phase 3: CLI Commands
- [x] Implement `commands/auth.py` - login, logout, whoami, use-org, test
- [x] Implement `commands/org.py` - org info, list, create, delete, config, errors, stats, mitre
- [x] Implement `commands/sensor.py` - sensor list, get, delete, online, wait-online, upgrade, set-version, export, dump, sweep
- [x] Implement `commands/tag.py` - tag list, add, remove, find, mass-add, mass-remove
- [x] Implement `commands/endpoint_policy.py` - isolate, rejoin, status, seal, unseal
- [x] Implement `commands/task.py` - send, request, reliable-send, reliable-list
- [x] Implement `commands/rule.py` - list, get, create, update, delete, test, replay, validate, export, import
- [x] Implement `commands/fp.py` - list, get, create, delete
- [x] Implement `commands/hive.py` - list-types, list, get, set, delete, validate, rename, export, import
- [x] Implement `commands/output_cmd.py` - list, get, create, delete
- [x] Implement `commands/artifact.py` - upload, list, get, download, rules
- [x] Implement `commands/payload.py` - list, upload, download, delete
- [x] Implement `commands/search.py` - run, validate, estimate, interactive, saved queries
- [x] Implement `commands/ioc.py` - search, batch-search, hosts, enrich, batch-enrich
- [x] Implement `commands/event.py` - list, get, children, overview, timeline, types, schema, retention
- [x] Implement `commands/detection.py` - list, get
- [x] Implement `commands/extension.py` - list, subscribe, unsubscribe, rekey, schema, request, config, convert-rules
- [x] Implement `commands/installation_key.py` - list, get, create, delete
- [x] Implement `commands/ingestion_key.py` - list, create, delete, configure
- [x] Implement `commands/user.py` - list, invite, remove, permissions
- [x] Implement `commands/group.py` - list, get, create, delete, member, owner, permissions, org, logs (NEW)
- [x] Implement `commands/api_key.py` - list, create, delete
- [x] Implement `commands/billing.py` - status, details, invoice, plans, skus
- [x] Implement `commands/stream.py` - events, detections, audit, firehose
- [x] Implement `commands/replay_cmd.py` - run
- [x] Implement `commands/integrity.py` - list, get, create, delete
- [x] Implement `commands/exfil.py` - list, create-watch, create-event, delete
- [x] Implement `commands/logging_cmd.py` - list, get, create, delete
- [x] Implement `commands/yara.py` - scan, rules list/add/delete, sources list/get/add/delete
- [x] Implement `commands/sync.py` - pull, push, diff
- [x] Implement `commands/ai.py` - generate-rule, generate-detection, generate-response, generate-query, generate-selector, generate-playbook, summarize-detection (NEW)
- [x] Implement `commands/investigation.py` - list, get, create, update, delete, expand (NEW)
- [x] Implement `commands/usp.py` - validate
- [x] Implement `commands/secret.py` - list, get, set, delete (NEW)
- [x] Implement `commands/lookup.py` - list, get, set, query, delete (NEW)
- [x] Implement `commands/playbook.py` - list, get, set, delete (NEW)
- [x] Implement `commands/adapter.py` - list, get, set, delete (NEW)
- [x] Implement `commands/cloud_sensor.py` - list, get, set, delete (NEW)
- [x] Implement `commands/sop.py` - list, get, set, delete (NEW)
- [x] Implement `commands/note.py` - list, get, set, delete (NEW)
- [x] Implement `commands/arl.py` - get
- [x] Implement `commands/job.py` - list, get, wait, delete
- [x] Implement `commands/audit.py` - list
- [x] Implement `commands/spotcheck.py` - run
- [x] Implement `commands/schema.py` - list, get
- [x] Implement `commands/help_cmd.py` - help, discover, cheatsheet

### Phase 4: Help & Discovery Content
- [x] Write help topic: d&r-rules
- [x] Write help topic: hive
- [x] Write help topic: lcql
- [x] Write help topic: sensors
- [x] Write help topic: outputs
- [x] Write help topic: extensions
- [x] Write help topic: sync
- [x] Write help topic: auth
- [x] Write help topic: permissions
- [x] Write help topic: events
- [x] Write help topic: detections
- [x] Write help topic: adapters
- [x] Write help topic: platform-codes
- [x] Write help topic: ioc-types
- [x] Write help topic: timestamps
- [x] Write help topic: bexpr
- [x] Write help topic: billing
- [x] Write cheatsheet: common-operations
- [x] Write cheatsheet: detection-engineering
- [x] Write cheatsheet: incident-response
- [x] Write cheatsheet: fleet-management
- [x] Write cheatsheet: searching
- [x] Write explain text for every command

### Phase 5: Integration Tests
- [x] Implement test fixtures in `tests/integration/conftest.py`
- [x] Implement `test_v2_auth.py`
- [x] Implement `test_v2_sensors.py`
- [x] Implement `test_v2_rules.py`
- [x] Implement `test_v2_hive.py`
- [x] Implement `test_v2_outputs.py`
- [x] Implement `test_v2_keys.py` (api_keys, installation_keys, ingestion_keys)
- [x] Implement `test_v2_org.py` (info, urls, errors, stats)
- [x] Implement `test_v2_billing.py`
- [x] Implement `test_artifacts.py`
- [x] Implement `test_search.py`
- [x] Implement `test_extensions.py`
- [x] Implement `test_users.py`
- [x] Implement `test_sync.py`
- [x] Implement `test_replay.py`
- [x] Implement `test_stream.py`
- [x] Implement `test_ai.py`
- [x] Implement `test_groups.py`
- [x] Implement `test_org_management.py`
- [x] Implement `test_usp.py`
- [x] Implement `test_integrity.py`
- [x] Implement `test_exfil.py`
- [x] Implement `test_logging.py`
- [x] Implement `test_yara.py`
- [x] Implement `test_jobs.py`
- [x] Implement `test_cli_e2e.py`

### Phase 6: Packaging & CI
- [x] Update `setup.py` / `pyproject.toml` for v2
- [x] Update entry points to use v2 CLI
- [x] Update `cloudbuild.yaml` and `cloudbuild_pr.yaml`
- [x] Update `Dockerfile`
- [x] Update `requirements.txt` with new dependencies
- [x] Create `requirements-tests.txt` for test dependencies
- [x] Verify wheel and sdist builds

### Phase 7: Documentation
- [x] Update `README.md` with v2 usage
- [x] Migration guide from v1 to v2

---

## Appendix A: Feature Gap Analysis (API vs Current CLI)

Features in the API gateway that are **NOT** in the current CLI and are **added in v2**:

| Feature | API Endpoint | v2 Command |
|---------|-------------|------------|
| AI D&R Rule Generation | `POST /ai/dr` | `limacharlie ai generate-rule` |
| AI Detection Generation | `POST /ai/detection` | `limacharlie ai generate-detection` |
| AI Response Generation | `POST /ai/response` | `limacharlie ai generate-response` |
| AI LCQL Generation | `POST /ai/lcql` | `limacharlie ai generate-query` |
| AI Sensor Selector | `POST /ai/sensor_selector` | `limacharlie ai generate-selector` |
| AI Python Playbook | `POST /ai/playbook/python` | `limacharlie ai generate-playbook` |
| AI Detection Summary | `POST /ai/det_summary` | `limacharlie ai summarize-detection` |
| Organization Groups | `GET/POST/DELETE /groups/*` | `limacharlie group *` |
| Investigations | Various | `limacharlie investigation *` |
| Secrets (shortcut) | Hive `secret` | `limacharlie secret *` |
| Lookups (shortcut) | Hive `lookup` | `limacharlie lookup *` |
| Playbooks (shortcut) | Hive `playbook` | `limacharlie playbook *` |
| External Adapters (shortcut) | Hive `external_adapter` | `limacharlie adapter *` |
| SOPs (shortcut) | Hive `sop` | `limacharlie sop *` |
| Org Notes (shortcut) | Hive `note` | `limacharlie note *` |
| Cloud Sensors (shortcut) | Hive `cloud_sensor` | `limacharlie cloud-sensor *` |
| Extension Config Management | Various | `limacharlie extension config *` |
| Extension Rule Conversion | `POST /extension/convert_rules` | `limacharlie extension convert-rules` |
| User Role Setting | Via permissions | `limacharlie user permissions set-role` |
| Lookup Query | `GET /lookup/{name}/query` | `limacharlie lookup query` |
| IOC Enrichment | `GET /object_information` | `limacharlie ioc enrich` |
| Sensor Version Mgmt | `POST /sensor_version` | `limacharlie sensor set-version` |
| Sensor Export | `GET /sensor_list_export` | `limacharlie sensor export` |
| Memory Dump | Via sensor tasking | `limacharlie sensor dump` |
| Host Sweep | Via replicant | `limacharlie sensor sweep` |
| Job Tracking | Various | `limacharlie job *` |
| ARL Resolution | `GET /arl` | `limacharlie arl get` |
| Interactive LCQL | N/A (CLI-only) | `limacharlie search interactive` |
| Log Collection Rules | Via replicant | `limacharlie logging *` |
| YARA Scanning | Via replicant | `limacharlie yara *` |
| Template Testing | `POST /test_template` | (available via hive validate) |
| Transform Testing | `POST /test_transform` | (available via hive validate) |

## Appendix B: Hive Type Reference

| Hive Name | Purpose | Common Use |
|-----------|---------|------------|
| `dr-general` | Custom D&R rules | Rule management |
| `dr-managed` | LimaCharlie-managed D&R rules | Managed rule overrides |
| `dr-service` | Service-level D&R rules | Service rules |
| `fp` | False positive rules | FP management |
| `cloud_sensor` | Cloud sensor configurations | Cloud log ingestion |
| `extension_config` | Extension configurations | Extension settings |
| `yara` | YARA scanning rules | Malware detection |
| `secret` | Encrypted secrets | API keys, tokens |
| `lookup` | Lookup tables | Allowlists, blocklists |
| `query` | Saved LCQL queries | Reusable queries |
| `playbook` | Automation playbooks | Response automation |
| `ai_agent` | AI agent configurations | AI agent settings |
| `external_adapter` | External adapter configs | Third-party integrations |
| `sop` | Standard Operating Procedures | Runbooks |
| `note` | Organization notes | Documentation |

## Appendix C: Output Module Reference

| Module | Data Types | Description |
|--------|-----------|-------------|
| `syslog` | event, detect, audit | Forward to syslog server |
| `s3` | event, detect, audit, artifact | AWS S3 bucket |
| `gcs` | event, detect, audit, artifact | Google Cloud Storage |
| `pubsub` | event, detect | Google Pub/Sub |
| `bigquery` | event, detect | Google BigQuery |
| `scp` | event, detect, audit | SCP file transfer |
| `sftp` | event, detect, audit | SFTP file transfer |
| `slack` | detect | Slack notifications |
| `webhook` | event, detect, audit | HTTP webhook |
| `webhook_bulk` | event, detect, audit | Bulk HTTP webhook |
| `smtp` | detect | Email notifications |
| `humio` | event, detect | Humio/LogScale |
| `kafka` | event, detect, audit | Apache Kafka |
| `azure_storage_blob` | event, detect, audit | Azure Blob Storage |
| `azure_event_hub` | event, detect | Azure Event Hub |
| `elastic` | event, detect | Elasticsearch |
| `tines` | detect | Tines SOAR |
| `torq` | detect | Torq SOAR |
| `datadog` | event, detect | DataDog |
| `opensearch` | event, detect | OpenSearch |
| `websocket` | event, detect | WebSocket stream |

## Appendix D: Rate Limiting Reference

| Category | Limit | Window |
|----------|-------|--------|
| General API calls | 100 | 10 minutes |
| Built-in/SDK calls | 1,000 | 10 minutes |
| Bulk operations | 10,000 | 10 minutes |
| AI generation | 10 | 1 minute |

When rate limited, the CLI should:
1. Log a warning with retry-after time
2. If `--retry` flag is set, automatically retry with exponential backoff
3. Return exit code 5 for rate limit errors (distinct from other errors)
