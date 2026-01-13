# Changelog

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
