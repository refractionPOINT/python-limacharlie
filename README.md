# LimaCharlie Python SDK & CLI

![LimaCharlie.io](https://storage.googleapis.com/limacharlie-io/logo_fast_glitch.gif)

Python SDK and command-line interface for the [LimaCharlie](https://limacharlie.io) endpoint detection and response platform.

* Documentation: https://doc.limacharlie.io/
* REST API: https://api.limacharlie.io
* Issues & Contributions: https://github.com/refractionPOINT/python-limacharlie

## Installation

```bash
pip install limacharlie
```

Docker:

```bash
docker run refractionpoint/limacharlie:latest --help

# Mount local credentials into the container
docker run -v ${HOME}/.limacharlie:/root/.limacharlie:ro refractionpoint/limacharlie:latest org info
```

## Quick Start

```bash
# New to LimaCharlie? Create an account directly from the CLI:
limacharlie auth signup

# Already have an account? Store credentials (API key):
limacharlie auth login --oid YOUR_ORG_ID --api-key YOUR_API_KEY

# -- or authenticate via browser (OAuth) --
limacharlie auth login --oauth --oid YOUR_ORG_ID

# Verify
limacharlie auth whoami

# Explore
limacharlie org info
limacharlie sensor list
limacharlie discover
```

## Authentication

Two authentication methods are supported: **API keys** (for automation and CI/CD) and **OAuth** (for interactive use with your Google or Microsoft account). If you don't have an account yet, see [New Account Signup](#new-account-signup) below.

### New Account Signup

Create a brand new LimaCharlie account and organization directly from the CLI:

```bash
# Sign up with Google (default) -- opens browser for OAuth
limacharlie auth signup

# Sign up with Microsoft
limacharlie auth signup --provider microsoft

# Provide the organization name upfront (non-interactive)
limacharlie auth signup --org-name "My Company"

# Headless environments
limacharlie auth signup --no-browser
```

This performs the full onboarding flow: OAuth authentication, account creation, and organization setup. After signup, the CLI is immediately ready to use.

### API Key Login

Store credentials locally using an [API key](https://docs.limacharlie.io/docs/platform-management-api-keys):

```bash
limacharlie auth login --oid YOUR_ORG_ID --api-key YOUR_API_KEY

# With a user-scoped API key
limacharlie auth login --oid YOUR_ORG_ID --api-key YOUR_API_KEY --uid YOUR_USER_ID

# Store under a named environment
limacharlie auth login --oid YOUR_ORG_ID --api-key YOUR_API_KEY --env staging
```

### OAuth Login (Browser-Based)

Authenticate interactively using your Google or Microsoft identity. This opens a browser window for authentication and supports MFA/2FA.

```bash
# Login with Google (default)
limacharlie auth login --oauth --oid YOUR_ORG_ID

# Login with Microsoft
limacharlie auth login --oauth --oid YOUR_ORG_ID --provider microsoft

# Login without specifying org (set it later with use-org)
limacharlie auth login --oauth

# Headless environments (prints URL instead of opening browser)
limacharlie auth login --oauth --no-browser

# Save to a named environment
limacharlie auth login --oauth --oid YOUR_ORG_ID --env production
```

OAuth tokens are automatically refreshed when they expire.

### Managing Environments

```bash
# List configured environments
limacharlie auth list-envs

# Switch environment
limacharlie auth use-env production

# Set default org (useful after OAuth login without --oid)
limacharlie auth use-org --oid YOUR_ORG_ID

# Check current identity
limacharlie auth whoami

# Test credentials
limacharlie auth test

# List accessible organizations
limacharlie auth list-orgs
```

### Environment Variables

```bash
export LC_OID=your-org-id
export LC_API_KEY=your-api-key
# Optional: user-scoped key
export LC_UID=your-user-id
# Optional: select a named environment
export LC_CURRENT_ENV=staging
```

### Credentials File

Credentials are stored in `~/.limacharlie` (YAML, mode 0600):

```yaml
# Default credentials (API key)
api_key: xxx
oid: xxx
uid: xxx  # optional, for user-scoped keys

# Default credentials (OAuth)
oid: xxx
oauth:
  id_token: xxx
  refresh_token: xxx
  expires_at: 1704067200
  provider: google

# Named environments
env:
  staging:
    api_key: xxx
    oid: xxx
  production:
    oid: xxx
    oauth:
      id_token: xxx
      refresh_token: xxx
      expires_at: 1704067200
      provider: google
```

Override the credentials file path with `LC_CREDS_FILE`. Set `LC_EPHEMERAL_CREDS` to prevent any file I/O (for CI/CD).

### Resolution Order

Credentials are resolved in this order (highest priority first):
1. Explicit parameters passed to `Client()`
2. `LC_OID`, `LC_API_KEY`, `LC_UID` environment variables
3. Named environment from `LC_CURRENT_ENV` (or `default`)
4. Default credentials in `~/.limacharlie`

## CLI Reference

The CLI follows a consistent `limacharlie <noun> <verb>` pattern. Every command supports `--output` to control the format, `--explain` for a detailed description, and `--help` for usage.

### Global Options

```
--oid TEXT          Organization ID (overrides env/config)
--output FORMAT     Output format: json, yaml, csv, table, jsonl
--debug             Print request details
--quiet / -q        Suppress non-error output
--env TEXT          Named environment from config file
```

### Organization

```bash
limacharlie org info                     # Name, sensor count, version, quotas
limacharlie org stats                    # Usage statistics
limacharlie org urls                     # Service URLs (for firewall rules)
limacharlie org errors                   # Platform errors
limacharlie org dismiss-error --component <name>
limacharlie org config-get --name vt     # Read a config value
limacharlie org config-set --name vt --value <key>
limacharlie org mitre                    # MITRE ATT&CK coverage report
limacharlie org schema                   # Event schemas
limacharlie org schema --event-type NEW_PROCESS
limacharlie org list                     # List accessible organizations
limacharlie org create --name my-org --location us
limacharlie org rename --name new-name
limacharlie org delete                   # Step 1: get confirmation token
limacharlie org delete --confirm-token <token>  # Step 2: confirm
```

### Sensors

```bash
limacharlie sensor list
limacharlie sensor list --tag production --limit 50
limacharlie sensor list --hostname web-server
limacharlie sensor get --sid SENSOR_ID
limacharlie sensor online --sid SENSOR_ID
limacharlie sensor wait-online --sid SENSOR_ID --timeout 120
limacharlie sensor delete --sid SENSOR_ID --confirm
limacharlie sensor export                # Full fleet manifest
limacharlie sensor upgrade               # Trigger version update
limacharlie sensor set-version --version 4.29.0
limacharlie sensor dump --sid SENSOR_ID --confirm  # Memory dump
limacharlie sensor sweep --sid SENSOR_ID --config '{"os_processes": true}'
```

### Tags

```bash
limacharlie tag list --sid SENSOR_ID
limacharlie tag add --sid SENSOR_ID --tag suspicious --ttl 600
limacharlie tag remove --sid SENSOR_ID --tag suspicious
limacharlie tag find --tag production    # Find all sensors with a tag
limacharlie tag mass-add --selector '`linux` in tags' --tag patch-pending
limacharlie tag mass-remove --selector '`linux` in tags' --tag patch-pending
```

### Network Policy

```bash
limacharlie net-policy status --sid SENSOR_ID
limacharlie net-policy isolate --sid SENSOR_ID
limacharlie net-policy rejoin --sid SENSOR_ID
limacharlie net-policy seal --sid SENSOR_ID
limacharlie net-policy unseal --sid SENSOR_ID
```

### Tasking

```bash
limacharlie task send --sid SENSOR_ID --command os_processes
limacharlie task request --sid SENSOR_ID --command os_processes  # Wait for response
limacharlie task reliable-send --sid SENSOR_ID --command os_processes
limacharlie task reliable-list --sid SENSOR_ID
```

### Detection & Response Rules

```bash
limacharlie rule list
limacharlie rule list --namespace managed
limacharlie rule get --name my-rule
limacharlie rule create --name my-rule \
  --detect '{"op":"is","event":"NEW_PROCESS"}' \
  --respond '[{"action":"report","name":"my-detection"}]'
limacharlie rule update --name my-rule --detect '...' --respond '[...]'
limacharlie rule delete --name my-rule
limacharlie rule test --detect '...' --respond '[...]' --events '[{...}]'
limacharlie rule validate --detect '...' --respond '[...]'
```

### False Positive Rules

```bash
limacharlie fp list
limacharlie fp get --name my-fp
limacharlie fp create --name my-fp --rule '{"op":"is","cat":"my-detection"}'
limacharlie fp delete --name my-fp
```

### Search (LCQL)

```bash
limacharlie search run --query 'event NEW_PROCESS' --start 2024-01-01 --end 2024-01-02
limacharlie search validate --query 'event NEW_PROCESS'
limacharlie search estimate --query 'event NEW_PROCESS' --start 2024-01-01 --end 2024-01-02
limacharlie search interactive                      # Interactive REPL
limacharlie search saved-list                        # Saved queries
limacharlie search saved-create --name my-query --query 'event NEW_PROCESS'
limacharlie search saved-run --name my-query --start 2024-01-01 --end 2024-01-02
```

### IOC Search

```bash
limacharlie ioc search --type domain --value evil.com
limacharlie ioc search --type ip --value 1.2.3.4
limacharlie ioc search --type file_hash --value abc123...
limacharlie ioc batch-search --input-file iocs.json  # {"domain": ["evil.com"], "ip": ["1.2.3.4"]}
limacharlie ioc hosts --hostname workstation-01       # Find sensors by hostname
limacharlie ioc enrich --type domain --value evil.com # Object enrichment
limacharlie ioc batch-enrich --input-file indicators.json
```

### Events & Detections

```bash
limacharlie event list --sid SENSOR_ID --start 1704067200 --end 1704153600
limacharlie event list --sid SENSOR_ID --start 1704067200 --end 1704153600 --event-type NEW_PROCESS
limacharlie event get --sid SENSOR_ID --atom ATOM_ID
limacharlie event children --sid SENSOR_ID --atom ATOM_ID
limacharlie event overview --sid SENSOR_ID --start 1704067200 --end 1704153600
limacharlie detection list --start 1704067200 --end 1704153600
limacharlie detection get --id DETECT_ID
```

### Streaming

```bash
limacharlie stream events --tag vip           # Live event stream
limacharlie stream detections                  # Live detection stream
limacharlie stream audit                       # Live audit log
limacharlie stream firehose                    # All data types
```

### Hive Records

Hives are key-value stores for LimaCharlie configuration data. Several hive types have dedicated shortcut commands (`secret`, `lookup`, `playbook`, `note`, `sop`, `cloud-sensor`):

```bash
# Generic hive access
limacharlie hive list --category dr-general
limacharlie hive get --category dr-general --key my-rule
limacharlie hive set --category secret --key my-key --input-file data.json
limacharlie hive delete --category secret --key my-key --confirm

# Shortcut commands (same operations, simpler syntax)
limacharlie secret list
limacharlie secret get --key my-secret
limacharlie secret set --key my-secret --input-file secret.json
limacharlie secret delete --key my-secret --confirm

limacharlie lookup list
limacharlie lookup set --key ioc-list --input-file iocs.json

limacharlie playbook list
limacharlie note list
limacharlie sop list
limacharlie cloud-sensor list
```

### Outputs

```bash
limacharlie output list
limacharlie output create --name my-output --module syslog --type event --dest 'host:514'
limacharlie output delete --name my-output
```

### Installation & API Keys

```bash
limacharlie installation-key list
limacharlie installation-key create --description "Production fleet"
limacharlie installation-key delete --iid KEY_ID

limacharlie api-key list
limacharlie api-key create --name ci-key --permissions '["dr.list","sensor.list"]'
limacharlie api-key delete --key-hash HASH

limacharlie ingestion-key list
limacharlie ingestion-key create --name my-ingest-key
```

### Users & Groups

```bash
limacharlie user list
limacharlie user invite --email user@example.com
limacharlie user remove --email user@example.com
limacharlie user permissions list
limacharlie user permissions add --email user@example.com --permission dr.set
limacharlie user permissions set-role --email user@example.com --role Administrator

limacharlie group list
limacharlie group create --name my-group
limacharlie group member-add --group-id GID --email user@example.com
```

### Extensions

```bash
limacharlie extension list                    # Subscribed extensions
limacharlie extension list-available          # All available extensions
limacharlie extension subscribe --name lookup/my-resource
limacharlie extension unsubscribe --name lookup/my-resource
limacharlie extension request --name my-ext --action do-thing --data '{}'
limacharlie extension schema --name my-ext
limacharlie extension config-list --name my-ext
```

### Investigations

```bash
limacharlie investigation list
limacharlie investigation get --id INV_ID
limacharlie investigation create --name "Suspicious activity" --data '{}'
limacharlie investigation expand --id INV_ID
```

### Artifacts & Payloads

```bash
limacharlie artifact list
limacharlie artifact upload --file /path/to/file --source my-source
limacharlie artifact download --id ARTIFACT_ID

limacharlie payload list
limacharlie payload upload --file /path/to/binary --name my-payload
limacharlie payload download --name my-payload
limacharlie payload delete --name my-payload
```

### Replay

```bash
limacharlie replay run --rule-name my-rule --start 1704067200 --end 1704153600
limacharlie replay run --detect '{"op":"is"}' --respond '[{"action":"report"}]' --start 1704067200 --end 1704153600
```

### YARA

```bash
limacharlie yara rules-list
limacharlie yara rule-add --name my-rule --rule-file rule.yar
limacharlie yara scan --sid SENSOR_ID --source my-rule
limacharlie yara sources-list
```

### AI-Assisted Generation

```bash
limacharlie ai generate-rule --prompt 'detect powershell downloading files'
limacharlie ai generate-query --prompt 'find all DNS lookups to evil.com'
limacharlie ai generate-selector --prompt 'all Windows servers'
limacharlie ai generate-playbook --prompt 'respond to ransomware detection'
limacharlie ai summarize-detection --id DETECT_ID
```

### Sync (Infrastructure as Code)

```bash
limacharlie sync pull --config lc_conf.yaml    # Export org config
limacharlie sync push --config lc_conf.yaml --dry-run  # Preview changes
limacharlie sync push --config lc_conf.yaml --force     # Apply changes
limacharlie sync diff --config lc_conf.yaml    # Show differences
```

### Other Commands

```bash
limacharlie billing status                     # Billing overview
limacharlie billing details                    # Detailed breakdown

limacharlie audit list --start 1704067200 --end 1704153600

limacharlie integrity list                     # File integrity rules
limacharlie logging list                       # Logging rules
limacharlie exfil list                         # Exfiltration watches

limacharlie arl get --arl 'lcr://api/...'      # Resolve an ARL
limacharlie usp validate                       # Test USP adapter parsing
limacharlie spotcheck run                      # Quick health check
```

### Output Formats

All commands support `--output` to control the format:

```bash
limacharlie sensor list --output json     # JSON (default when piped)
limacharlie sensor list --output yaml     # YAML
limacharlie sensor list --output csv      # CSV
limacharlie sensor list --output table    # Rich table (default for TTY)
limacharlie sensor list --output jsonl    # Newline-delimited JSON

# Filter with JMESPath
limacharlie sensor list --output json --filter '[].hostname'
```

### Discovery & Help

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
limacharlie rule create --explain

# JSON schema for a command's parameters
limacharlie schema rule create
```

## Python SDK

The v2 SDK is organized into domain-specific classes under `limacharlie.sdk`. All classes take an `Organization` instance which handles authentication and API routing.

### Basic Setup

```python
from limacharlie.client import Client
from limacharlie.sdk.organization import Organization

# Uses default credentials (~/.limacharlie or env vars)
# Works with both API key and OAuth credentials
client = Client()
org = Organization(client)

# Or with explicit API key
client = Client(oid="your-org-id", api_key="your-api-key")
org = Organization(client)

# With a pre-generated JWT
client = Client(oid="your-org-id", jwt="your-jwt-token")
org = Organization(client)
```

### Organization

```python
info = org.get_info()              # Name, sensor count, quotas
urls = org.get_urls()              # Service URLs
stats = org.get_stats()            # Usage statistics
errors = org.get_errors()          # Platform errors
mitre = org.get_mitre_report()     # MITRE ATT&CK coverage

org.set_config("vt", "my-api-key")
value = org.get_config("vt")
```

### Sensors

```python
from limacharlie.sdk.sensor import Sensor

# List sensors
for sensor_info in org.list_sensors():
    print(sensor_info["hostname"], sensor_info["sid"])

# Filter by tag, hostname, or IP
for s in org.list_sensors(selector="`production` in tags", limit=50):
    print(s)

# Single sensor operations
sensor = Sensor(org, "SENSOR-ID-HERE")
info = sensor.get_info()
is_online = sensor.is_online()
sensor.wait_online(timeout=120)

# Tasking
sensor.task("os_processes")
sensor.task(["os_processes", "os_services"])

# Tags
tags = sensor.get_tags()
sensor.add_tag("suspicious", ttl=600)
sensor.remove_tag("suspicious")

# Network isolation
sensor.isolate()
sensor.rejoin()
sensor.delete()
```

### Detection & Response Rules

```python
# Via Organization directly
rules = org.get_rules()
org.add_rule(
    "my-rule",
    detection={"op": "is", "event": "NEW_PROCESS"},
    response=[{"action": "report", "name": "my-detection"}],
)
org.delete_rule("my-rule")

# Or via DRRules helper
from limacharlie.sdk.dr_rules import DRRules

dr = DRRules(org)
all_rules = dr.list()
dr.create("my-rule", detection={...}, response=[...])
dr.delete("my-rule")
```

### Hive (Key-Value Store)

```python
from limacharlie.sdk.hive import Hive, HiveRecord

hive = Hive(org, "secret")
records = hive.list()                      # {name: HiveRecord}
record = hive.get("my-key")               # HiveRecord
print(record.data, record.etag)

# Create or update
new_record = HiveRecord("my-key", data={"value": "secret123"})
hive.set(new_record)

# Transactional update with automatic etag retry
def update_fn(record):
    record.data["counter"] = record.data.get("counter", 0) + 1

hive.update_tx("my-key", update_fn)

hive.delete("my-key")
```

### Search (LCQL)

```python
from limacharlie.sdk.search import Search

search = Search(org)
results = search.execute("event NEW_PROCESS", start=1704067200, end=1704153600)
```

### IOC Search & Enrichment

```python
from limacharlie.sdk.insight import Insight

insight = Insight(org)
results = insight.search_ioc("domain", "evil.com")
batch = insight.batch_search({"domain": ["evil.com"], "ip": ["1.2.3.4"]})
enrichment = insight.get_object_information("domain", "evil.com")
```

### Historical Events

```python
sensor = Sensor(org, "SENSOR-ID")
for event in sensor.get_events(start=1704067200, end=1704153600, event_type="NEW_PROCESS"):
    print(event)

# Detections
for detection in org.get_detections(start=1704067200, end=1704153600):
    print(detection)
```

### Streaming

```python
from limacharlie.sdk.spout import Spout

spout = Spout(org, "event", tag="vip")
try:
    while True:
        data = spout.get(timeout=5)
        if data is not None:
            process(data)
finally:
    spout.shutdown()
```

### Outputs

```python
outputs = org.get_outputs()
org.add_output("my-output", "syslog", "event", dest_host="1.2.3.4:514")
org.delete_output("my-output")
```

### Extensions

```python
from limacharlie.sdk.extensions import Extensions

ext = Extensions(org)
subscribed = ext.list_subscribed()
ext.subscribe("my-extension")
result = ext.request("my-extension", "do-action", {"key": "value"})
```

### Replay (Rule Testing)

```python
from limacharlie.sdk.replay import Replay

replay = Replay(org)

# Test against historical data
result = replay.run(
    detect={"op": "is", "event": "NEW_PROCESS"},
    respond=[{"action": "report", "name": "test"}],
    start=1704067200,
    end=1704153600,
)

# Test against specific events
result = replay.scan_events(
    events=[{"event": {"FILE_PATH": "evil.exe"}, "routing": {}}],
    rule_content={"detect": {"op": "is"}, "respond": [{"action": "report"}]},
)

# Validate rule syntax
replay.validate_rule({"detect": {"op": "is"}, "respond": [{"action": "report"}]})
```

### Artifacts

```python
from limacharlie.sdk.artifacts import Artifacts

artifacts = Artifacts(org, access_token="your-ingestion-key")
artifacts.upload("/path/to/file", source="my-source", retention_days=30)
artifact_list = artifacts.list()
```

### Configuration Sync

```python
from limacharlie.sdk.configs import Configurations

configs = Configurations(org)
data = configs.fetch()           # Export org config
configs.push(data, dry_run=True) # Preview changes
configs.push(data)               # Apply changes
```

### All SDK Classes

| Class | Import | Description |
|---|---|---|
| `Client` | `limacharlie.client` | HTTP client with JWT auth, retry, rate limiting |
| `Organization` | `limacharlie.sdk.organization` | Org-level operations (sensors, rules, users, etc.) |
| `Sensor` | `limacharlie.sdk.sensor` | Single sensor: tasking, tagging, events, isolation |
| `DRRules` | `limacharlie.sdk.dr_rules` | Detection & Response rules |
| `FPRules` | `limacharlie.sdk.fp_rules` | False positive rules |
| `Hive` / `HiveRecord` | `limacharlie.sdk.hive` | Key-value store with etag transactions |
| `Search` | `limacharlie.sdk.search` | LCQL query execution |
| `Insight` | `limacharlie.sdk.insight` | IOC search and enrichment |
| `Spout` | `limacharlie.sdk.spout` | Live event/detection streaming |
| `Firehose` | `limacharlie.sdk.firehose` | High-volume data streaming |
| `Replay` | `limacharlie.sdk.replay` | Rule testing against historical/sample data |
| `Extensions` | `limacharlie.sdk.extensions` | Extension management and requests |
| `Artifacts` | `limacharlie.sdk.artifacts` | Artifact upload, download, listing |
| `Payloads` | `limacharlie.sdk.payloads` | Executable/script deployment |
| `Outputs` | `limacharlie.sdk.outputs` | Data routing outputs |
| `Configurations` | `limacharlie.sdk.configs` | Infrastructure-as-code sync |
| `Users` | `limacharlie.sdk.users` | User management |
| `Investigations` | `limacharlie.sdk.investigations` | Investigation tracking |
| `AI` | `limacharlie.sdk.ai` | AI-assisted rule/query generation |
| `Billing` | `limacharlie.sdk.billing` | Billing and usage details |

## Legacy v1 SDK

The v1 SDK classes (`Manager`, `Sensor`, `Firehose`, `Sync`, etc.) remain available under `limacharlie.*` for backward compatibility. They are not actively developed but will continue to work.

```python
# v1 imports still work
import limacharlie
man = limacharlie.Manager(oid="...", secret_api_key="...")
sensors = man.sensors()
```

### Migration from v1

| v1 Pattern | v2 Pattern |
|---|---|
| `limacharlie.Manager(oid=..., secret_api_key=...)` | `Client(oid=..., api_key=...)` + `Organization(client)` |
| `man.sensors()` | `org.list_sensors()` |
| `man.rules()` | `org.get_rules()` or `DRRules(org).list()` |
| `man.add_rule(name, detect, respond)` | `org.add_rule(name, detect, respond)` |
| `man.del_rule(name)` | `org.delete_rule(name)` |
| `man.outputs()` | `org.get_outputs()` |
| `limacharlie.Sensor(man, sid)` | `Sensor(org, sid)` |
| `sensor.tag(tag, ttl)` | `sensor.add_tag(tag, ttl=ttl)` |
| `sensor.task(command)` | `sensor.task(command)` |
| `limacharlie.Firehose(...)` | `Spout(org, data_type=...)` |
| `limacharlie.Configs(man).fetch()` | `Configurations(org).fetch()` |
| `limacharlie login` | `limacharlie auth login` |
| `limacharlie use` | `limacharlie auth use-env` |
| `limacharlie whoami` | `limacharlie auth whoami` |
| `limacharlie dr --list` | `limacharlie rule list` |
| `limacharlie configs fetch` | `limacharlie sync pull` |
| `limacharlie configs push` | `limacharlie sync push` |

Key changes in v2:
- `Manager` replaced by `Client` (auth/HTTP) + domain-specific SDK classes
- CLI uses `noun verb` pattern instead of flat commands with flags
- `gevent` dependency removed; streaming uses `requests` directly
- All commands support `--output json|yaml|csv|table|jsonl` and `--filter`
- Built-in help: `--explain`, `limacharlie help <topic>`, `limacharlie discover`
