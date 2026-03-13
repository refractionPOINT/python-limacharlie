# Changelog

## 5.0.x - TBD

### Search

- **Structured search errors**: Search failures now raise `SearchError` with
  `query_id`, `region`, `oid`, and `query` attributes for easier troubleshooting.
  Error messages include these fields in bracket-formatted context:
  `"Search failed [query_id=q-123, region=9157798c50af372c, oid=..., query=...]"`.
  Long queries are truncated to 120 characters in the message but the full query
  is always available via the `query` attribute.

- **Region extraction**: The search region identifier (hex hash from the search
  URL) is automatically extracted and included in error messages.

## 5.0.0 - February 18th, 2026

Complete rewrite of the CLI and SDK. This is a major release with breaking
changes.

### CLI Rewrite

- **Click framework**: The CLI has been rewritten from scratch using Click,
  replacing the legacy argparse-based implementation. All commands now follow a
  consistent `limacharlie <noun> <verb>` pattern across 50+ command groups.

- **Modular command architecture**: Each command group lives in its own module
  under `limacharlie/commands/`. Commands are auto-discovered and registered
  at startup.

- **Global option hoisting**: Options like `--output`, `--filter`, `--wide`,
  and `--oid` can appear anywhere on the command line, not just before the
  subcommand.

- **Smart output formatting**: New unified output system supporting JSON, YAML,
  CSV, table, and JSONL formats. TTY output defaults to tables with smart
  column truncation; piped output defaults to JSON. Use `--wide` to disable
  truncation, `--filter` for JMESPath expressions, and `--fields` for column
  selection.

- **Columnar tables for nested data**: Dict-of-dicts API responses are now
  rendered as columnar tables instead of key/JSON pairs.

- **Unwrapped API responses**: The SDK strips useless wrapper keys from API
  responses (e.g. `{"sensors": {...}}` returns the inner dict directly).

### Authentication

- **OAuth login**: `limacharlie auth login --oauth` opens a browser for Google
  or Microsoft authentication with MFA/2FA support. Use `--no-browser` for
  headless environments. Tokens are automatically refreshed on expiry.

- **Account signup**: `limacharlie auth signup` provides a full self-service
  onboarding flow (OAuth, account creation, organization setup).

- **Named environments**: The credential file (`~/.limacharlie`) now supports
  multiple named environments for multi-org workflows. Switch with
  `limacharlie auth use-env <name>`.

- **Early OID validation**: Missing organization ID is detected before any API
  call with an actionable error instead of a confusing "unknown api key"
  message.

- **Credential resolution order**: Explicit parameters, then environment
  variables (`LC_OID`, `LC_API_KEY`, `LC_UID`, `LC_CURRENT_ENV`), then named
  environment from config, then default credentials. New `LC_CREDS_FILE` and
  `LC_EPHEMERAL_CREDS` variables for CI/CD use.

### New SDK

- **New `Client` class** (`limacharlie/client.py`): Redesigned HTTP client with
  built-in JWT generation/refresh, exponential backoff retry, rate limit
  handling, and request debugging (`--debug`).

- **30+ SDK modules** under `limacharlie/sdk/`: Clean, composable interfaces
  covering the full LimaCharlie API surface, including: `organization`,
  `sensor`, `dr_rules`, `fp_rules`, `hive`, `search`, `insight`, `spout`,
  `firehose`, `artifacts`, `payloads`, `outputs`, `extensions`, `users`,
  `groups`, `api_keys`, `billing`, `ai`, `investigations`, `jobs`, `yara`,
  `configs`, `downloads`, `replay`, `integrity`, `exfil`, `logging_rules`,
  `installation_keys`, `arl`, `usp`.

- **Custom exception hierarchy**: All errors inherit from `LimaCharlieError`
  with meaningful exit codes (0=success, 1=general, 2=auth, 3=not found,
  4=validation, 5=rate limit) and actionable suggestion messages.

### AI-First Discoverability

- **`--ai-help` flag**: Available on every command and command group. Generates
  compact markdown with purpose, patterns, examples, and data structures,
  designed for LLM consumption. Replaces the old `--explain` flag.

- **`limacharlie discover`**: Lists all commands grouped by use-case profiles
  (sensor management, detection engineering, historical data, live
  investigation, threat response, fleet management, platform admin).

- **`limacharlie help <topic>`**: Inline help topics for LCQL, D&R rules, hive
  concepts, and more.

### New Commands

- `auth` - Login, logout, signup, whoami, environment management.
- `org` - Organization info, stats, URLs, config, errors, MITRE coverage,
  schema inspection, creation/deletion.
- `sensor` - List (with `--online` and `--selector` filters), get, delete,
  upgrade, export, dump, sweep, wait-online.
- `rule` / `fp` - D&R and false-positive rule CRUD, validation, testing,
  replay, import/export.
- `hive` / `secret` / `lookup` / `playbook` / `sop` - Generic and shortcut
  hive operations with validation.
- `task` - Sensor tasking including reliable task queues.
- `stream` - Real-time event, detection, and audit streaming (WebSocket and
  legacy TCP/TLS firehose).
- `search` - LCQL queries with estimation, validation, streaming, interactive
  REPL, and saved query management.
- `event` / `detection` / `audit` - Event inspection, detection browsing, audit
  log listing.
- `ioc` - IOC search, batch search, enrichment, host queries.
- `tag` - Individual and bulk tag operations.
- `endpoint-policy` - Network isolation, boot integrity sealing, status.
- `investigation` - Investigation management with automatic expansion.
- `ai` - LLM-powered rule, detection, response, and query generation.
- `extension` - Extension subscription, configuration, schema inspection.
- `download` - Sensor installer and adapter binary downloads.
- `output` / `artifact` / `payload` - Output integrations, artifact management,
  payload management.
- `user` / `group` / `api-key` - User, group, and API key management.
- `installation-key` / `ingestion-key` - Deployment key management.
- `external-adapter` / `cloud-adapter` / `cloud-sensor` - Adapter and cloud
  sensor configuration.
- `billing` - Billing status and invoicing.
- `yara` - YARA rule scanning.
- `replay` - Rule replay operations.
- `integrity` / `exfil` / `logging` - Integrity monitoring, exfiltration
  prevention, log collection rules.
- `sync` - Infrastructure-as-Code pull/push/diff.
- `job` / `spotcheck` / `arl` / `usp` / `note` / `schema` - Additional
  management commands.

### Sync Changes

- The sync system now uses the `ext-infrastructure` extension exclusively.
- Legacy `--rules` and `--fps` flags are replaced with hive-based flags
  (`--hive-dr-general`, `--hive-fp`, etc.).
- Version 3 configuration format with hive-based resource organization.

### Testing

- 60+ unit test files and 30+ integration test files covering all command
  groups, SDK modules, config management, output formatting, and OAuth flows.
- Comprehensive HTTP contract tests validating SDK methods against the Go
  backend API.

### Packaging

- Migrated from `setup.py` to `pyproject.toml`.
- Added type annotations and a `py.typed` marker.
- Minimum Python version: 3.9.
- New dependencies: `click>=8.0`, `jmespath`.
- Entry point changed to `limacharlie.cli:main`.

### Breaking Changes

- The legacy `Manager`, `Sensor`, and `Spout` classes have been replaced by the
  new SDK modules.
- CLI entry point moved from `limacharlie.__main__:main` to
  `limacharlie.cli:main`.
- `limacharlie login` is now `limacharlie auth login`.
- `--explain` renamed to `--ai-help`.
- `adapter` command split into `external-adapter` and `cloud-adapter`.
- `net-policy` renamed to `endpoint-policy`.
- `sensor online` removed; use `sensor list --online` instead.
- Sync flags `--rules`/`--fps` removed; use `--hive-dr-general`/`--hive-fp`.
- API responses are unwrapped by default (wrapper keys stripped).
- Configuration file format extended with named environments and OAuth token
  storage.

## 4.11.2 - January 13th, 2026

- Add support for `external_adapter` hive in the SDK and CLI.

  The `external_adapter` hive stores configurations for external adapters that
  ingest non-endpoint telemetry data (Windows Event Logs, syslog, cloud service
  logs, etc.) into LimaCharlie.

  **New CLI flag:**

  - `--hive-external-adapter` - Sync external adapter configurations

  **Example CLI usage:**

  ```bash
  # Fetch external adapter configs
  limacharlie configs fetch --hive-external-adapter

  # Push external adapter configs
  limacharlie configs push --hive-external-adapter

  # Sync all hives including external_adapter
  limacharlie configs push --all
  ```

  **Example YAML configuration:**

  ```yaml
  hives:
    external_adapter:
      wel_dhcp:
        data:
          sensor_type: wel
          wel:
            client_options:
              platform: windows
              sensor_seed_key: wel-dhcp
              hostname: dhcp-server-01
              identity:
                oid: <org-id>
                installation_key: <installation-key>
            write_timeout_sec: 30
            evt_sources: "DhcpAdminEvents:'*'"
  ```

## 4.11.1 - January 12th, 2026

- Add support for `model` and `ai_agent` hives in the SDK and CLI.

  **New CLI flags:**

  - `--hive-model` - Sync model configurations
  - `--hive-ai-agent` - Sync AI agent configurations

  **Example CLI usage:**

  ```bash
  # Fetch model and AI agent configs
  limacharlie configs fetch --hive-model --hive-ai-agent

  # Push model and AI agent configs
  limacharlie configs push --hive-model --hive-ai-agent
  ```

## 4.11.0 - December 18th, 2025

- Add SDK methods and CLI commands for the new Search API.

  The Search API allows executing powerful queries against your organization's
  telemetry data (events, detections, audit logs) with automatic pagination
  support.

  **New SDK methods on Manager class:**

  - `validateSearch()` - Validate a query and get estimated pricing before
    execution.
  - `initiateSearch()` - Start a search query and get a query ID.
  - `pollSearchResults()` - Poll for results with pagination token support.
  - `executeSearch()` - High-level method that returns a generator yielding
    results with automatic pagination handling.
  - `cancelSearch()` - Cancel a running search query.

  **Example SDK usage:**

  ```python
  from limacharlie import Manager
  import time

  man = Manager()

  # Define time range
  end_time = int(time.time())
  start_time = end_time - 3600  # 1 hour ago

  # Execute search - returns a generator that automatically handles pagination
  for result in man.executeSearch(
      query="event_type = NETWORK_CONNECTIONS",
      start_time=start_time,
      end_time=end_time,
      stream='event'
  ):
      print(result)
  ```

  **New CLI commands:**

  - `limacharlie search-api validate` - Validate a query and see estimated cost.
  - `limacharlie search-api execute` - Execute a search with automatic pagination.

  The CLI supports flexible time formats including relative times (`now-1h`,
  `now-7d`), ISO dates, and Unix timestamps. Output can be written to JSONL
  or CSV files.

  **Example CLI usage:**

  ```bash
  # Validate a query
  limacharlie search-api validate \
    --query "event_type = NEW_PROCESS" \
    --start "now-1h" \
    --end "now"

  # Execute search and export to CSV
  limacharlie search-api execute \
    --query "event_type = DETECTION" \
    --start "now-24h" \
    --end "now" \
    --output-file detections.csv
  ```

  For more details, see the [Search API documentation](docs/SEARCH_API.md).

- Add support for Hive record validation API endpoint.

  The new `validate()` method on both `Hive` and `HiveRecord` classes allows
  dry-run validation of Hive records without storing them. This helps prevent
  invalid configurations from being committed.

  Example usage:
  ```python
  # Validate a record before setting it
  result = hive.validate(record)
  if 'error' not in result:
      # Safe to proceed with setting the record
      hive.set(record)
  ```

  Also adds `validate` action to the CLI:
  ```bash
  limacharlie hive validate <hive_name> -k <key> -d <data_file>
  ```

- Add new general `--debug-request` CLI flag.

  When this flag is used, CLI will output additional debugging information,
  including cURL commands which can be used to reproduce underlying requests
  made by the CLI.

  Keep in mind that this output can contain secrets (JWT authentication token)
  so be careful how you use it and where and how you share the output of the
  command when this flag is used.

  Example usage:

  ```bash
  limacharlie --debug-request query  --query "-1m | plat == linux | * | event/DOMAIN_NAME contains 'akamai'" --pretty
  ```

- Various improvements in the `limacharlie query` command, including support
  for colors in the interactive and non-interactive mode when using `--pretty`
  flag.

  Colors can use be disabled using `NO_COLOR=1` environment variable.

- The library now depenends on two additional dependencies - `pygments`,
  `rich`.

- Add support for new `--labs` and `--force-replay-url` argument to the
  `limacharlie query` command.

  This flag enables some functionality which is experimental. As such, users
  should not depend on it since there are no gurantees in terms of API stability,
  performance, user experience, etc. It can get changed or removed at any point
  without any prior notice.

  Example usage:

  ```bash
  limacharlie ---query "-1m | plat == linux | * | event/DOMAIN_NAME contains 'akamai'" --labs --force-replay-url=https://0651b4f82df0a29c.replay.limacharlie.io
  ```


## 4.9.13 - February 24th, 2025

- Fix Docker image build.

- Docker image has been updated to be based on top of `python:3.12-slim`.

- Docker images are now versioned. In addition to the `latest` tag, new version
  specific tags will be available going forward, starting with this release.

  For example:

  * `refractionpoint/limacharlie:latest` -> Always points to the latest release.
  * `refractionpoint/limacharlie:4.9.13` -> Release version 4.9.13.

## 4.9.12 - February 21st, 2025

- Add `whoami` alias for `who` command.

- Fix a possible race condition when writting credentials to `~/.limacharlie` file on disk.

- Add a new global `--debug` option. When this option is set and CLI command throws
  an exception, traceback will be printed to standard error.

- Add new `limacharlie users invite` command for inviting user(s) to LimaCharlie.

  **Example usage**

  Invite a single user:

  ```bash
  $ limacharlie users invite --email=test1@example.com
  ```

  Invite multiple users:

  ```bash
  $ limacharlie users invite --email=test1@example.com,test@example.com
  ```

  Invite multiple users (new line delimited entries in a file):

  ```
  $ cat users_to_invite.txt
  tomaz+test1@example.com
  tomaz+test2@example.com
  tomaz+test3@example.com
  tomaz+test4@example.com

  $ limacharlie users invite --file=users_to_invite.txt
  ```

  The corresponing API operations operates in the context of the user which means you need to specify a user scoped API key + UID when using `limacharlie login`.

  For more information, see https://docs.limacharlie.io/apidocs/introduction#getting-a-jwt.
