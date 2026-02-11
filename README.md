# LimaCharlie Python SDK & CLI

![LimaCharlie.io](https://storage.googleapis.com/limacharlie-io/logo_fast_glitch.gif)

Python SDK and command-line interface for the [LimaCharlie](https://limacharlie.io) endpoint detection and response platform.

* General Documentation: https://doc.limacharlie.io/
* REST API: https://api.limacharlie.io

## Installation

```bash
pip install limacharlie
```

Docker image is also available:

```bash
docker run refractionpoint/limacharlie:latest --help

# Mount local credentials into the container
docker run -v ${HOME}/.limacharlie:/root/.limacharlie:ro refractionpoint/limacharlie:latest org info
```

## Authentication

### Login (recommended)

Store credentials locally using an [API key](https://docs.limacharlie.io/docs/platform-management-api-keys):

```bash
# Login to default environment
limacharlie auth login --oid YOUR_ORG_ID --key YOUR_API_KEY

# Login to a named environment
limacharlie auth login --oid YOUR_ORG_ID --key YOUR_API_KEY --environment staging

# Login with a user-scoped API key
limacharlie auth login --oid YOUR_ORG_ID --key YOUR_API_KEY --uid YOUR_USER_ID

# List configured environments
limacharlie auth envs

# Switch environment for the current shell
. <(limacharlie auth use prod-org)

# Check current identity
limacharlie auth whoami
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
# Default credentials
api_key: xxx
oid: xxx
uid: xxx  # optional, for user-scoped keys

# Named environments
env:
  staging:
    api_key: xxx
    oid: xxx
  production:
    api_key: xxx
    oid: xxx
```

Override the credentials file path with `LC_CREDS_FILE`. Set `LC_EPHEMERAL_CREDS` to prevent any file I/O (for CI/CD).

### Resolution Order

Credentials are resolved in this order (highest priority first):
1. Explicit parameters passed to `Client()`
2. `LC_OID`, `LC_API_KEY`, `LC_UID` environment variables
3. Named environment from `LC_CURRENT_ENV` (or `default`)
4. Default credentials in `~/.limacharlie`

## CLI Usage

The CLI follows a consistent `limacharlie <noun> <verb>` pattern:

```bash
# Organization
limacharlie org info
limacharlie org stats

# Sensors
limacharlie sensor list
limacharlie sensor get --sid SENSOR_ID
limacharlie tag add --sid SENSOR_ID --tag suspicious --ttl 600
limacharlie task send --sid SENSOR_ID --command os_processes

# Detection & Response Rules
limacharlie rule list
limacharlie rule get --name my-rule
limacharlie rule create --name my-rule --detect '{"op":"is","event":"NEW_PROCESS"}' --respond '[{"action":"report","name":"my-detection"}]'
limacharlie rule delete --name my-rule

# False Positive Rules
limacharlie fp list
limacharlie fp create --name my-fp --detect '{"op":"is","cat":"my-detection"}'

# Outputs
limacharlie output list
limacharlie output create --name my-output --module scp --type event --dest 'user@host:/path'

# Hive Records
limacharlie hive list --category secret
limacharlie hive get --category secret --key my-key
limacharlie hive set --category secret --key my-key --data '{"value":"secret123"}'

# Hive Shortcuts (secret, lookup, playbook, adapter, cloud-sensor, sop, note)
limacharlie secret list
limacharlie lookup set --name ioc-list --data '{"evil.com": {"note": "C2"}}'
limacharlie playbook list

# Search (LCQL)
limacharlie search ioc --type domain --value evil.com
limacharlie search event --query 'event_type=NEW_PROCESS AND file_path LIKE *evil*' --start 2024-01-01

# Artifacts
limacharlie artifact list --type 2 --sid SENSOR_ID
limacharlie artifact upload --file /path/to/artifact --type 2 --sid SENSOR_ID

# Installation & API Keys
limacharlie installation-key list
limacharlie api-key list

# Sync (Infrastructure as Code)
limacharlie sync fetch --config lc_conf.yaml
limacharlie sync push --config lc_conf.yaml --dry-run
limacharlie sync push --config lc_conf.yaml --force

# Streaming
limacharlie stream events --tag vip
limacharlie stream detections

# Replay
limacharlie replay create --start 2024-01-01 --end 2024-01-02

# Extensions
limacharlie extension list
limacharlie extension request --name my-ext --action my-action --data '{}'

# AI Generation
limacharlie ai generate-rule --prompt 'detect powershell downloading files'

# ARLs
limacharlie arl get --arl 'lcr://api/...'

# Jobs
limacharlie job list
```

### Output Formats

All commands support `--output` to control the format:

```bash
limacharlie sensor list --output json     # JSON (default when piped)
limacharlie sensor list --output yaml     # YAML
limacharlie sensor list --output csv      # CSV
limacharlie sensor list --output table    # Rich table (default for TTY)
limacharlie sensor list --output jsonl    # Newline-delimited JSON

# Filter output with JMESPath
limacharlie sensor list --output json --filter '[].hostname'
```

### Discovery & Help

```bash
# List all commands grouped by use-case
limacharlie discover
limacharlie discover --profile detection_engineering

# Concept guides
limacharlie help d&r-rules
limacharlie help hive
limacharlie help lcql

# Quick-reference examples
limacharlie cheatsheet common-operations
limacharlie cheatsheet detection-engineering
limacharlie cheatsheet incident-response

# Detailed explanation of any command
limacharlie rule create --explain

# JSON schema for a command's parameters
limacharlie schema rule create
```

## SDK Usage

```python
from limacharlie import Client, Organization

# Create a client (uses default credentials)
client = Client()

# Or with explicit credentials
client = Client(oid="your-org-id", api_key="your-api-key")

# Organization operations
org = Organization(client)
info = org.get_info()
sensors = org.list_sensors()

# Detection & Response Rules
from limacharlie.sdk.dr_rules import DRRules
rules = DRRules(client)
all_rules = rules.list()
rules.create("my-rule", detect={"op": "is", "event": "NEW_PROCESS"}, respond=[{"action": "report", "name": "my-det"}])

# Hive
from limacharlie.sdk.hive import Hive
hive = Hive(client)
records = hive.list("secret")
hive.set("secret", "my-key", data={"value": "secret"})

# Outputs
from limacharlie.sdk.outputs import Outputs
outputs = Outputs(client)
all_outputs = outputs.list()

# Search
from limacharlie.sdk.search import Search
search = Search(client)
results = search.ioc_search(ioc_type="domain", ioc_value="evil.com")

# Sensors
from limacharlie.sdk.sensor import Sensor
sensor = Sensor(client)
info = sensor.get("SENSOR_ID")
sensor.tag("SENSOR_ID", "suspicious", ttl=600)
sensor.task("SENSOR_ID", "os_processes")

# Sync (Infrastructure as Code)
from limacharlie.sdk.configs import Configs
configs = Configs(client)
config_data = configs.fetch()
configs.push(config_data, dry_run=True)

# Artifacts
from limacharlie.sdk.artifacts import Artifacts
artifacts = Artifacts(client)
artifacts.upload("/path/to/file", artifact_type=2, sensor_id="SID")

# Streaming
from limacharlie.sdk.spout import Spout
spout = Spout(client, data_type="event", tag="vip")
for event in spout.events():
    print(event)
```

## Migration from v1

| v1 Pattern | v2 Pattern |
|---|---|
| `limacharlie.Manager(oid=..., secret_api_key=...)` | `Client(oid=..., api_key=...)` |
| `man.sensors()` | `Organization(client).list_sensors()` |
| `man.rules()` | `DRRules(client).list()` |
| `man.add_rule(name, detect, respond)` | `DRRules(client).create(name, detect, respond)` |
| `man.del_rule(name)` | `DRRules(client).delete(name)` |
| `man.outputs()` | `Outputs(client).list()` |
| `limacharlie.Sensor(man, sid)` | `Sensor(client).get(sid)` |
| `sensor.tag(tag, ttl)` | `Sensor(client).tag(sid, tag, ttl)` |
| `sensor.task(command)` | `Sensor(client).task(sid, command)` |
| `limacharlie.Firehose(...)` | `Spout(client, data_type=...)` (Firehose removed) |
| `limacharlie.Configs(man).fetch()` | `Configs(client).fetch()` |
| `limacharlie login` | `limacharlie auth login` |
| `limacharlie use` | `limacharlie auth envs` / `limacharlie auth use` |
| `limacharlie whoami` | `limacharlie auth whoami` |
| `limacharlie dr --list` | `limacharlie rule list` |
| `limacharlie configs fetch` | `limacharlie sync fetch` |
| `limacharlie configs push` | `limacharlie sync push` |

Key changes:
- `Manager` replaced by `Client` (auth/HTTP) + domain-specific SDK classes
- CLI uses `noun verb` pattern instead of flat commands with flags
- `gevent` dependency removed; streaming uses `requests` directly
- All commands support `--output json|yaml|csv|table|jsonl` and `--filter`
- Built-in help system: `--explain`, `limacharlie help <topic>`, `limacharlie discover`
