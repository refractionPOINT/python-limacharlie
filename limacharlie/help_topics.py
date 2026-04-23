"""Inline help topic content for LimaCharlie CLI v2.

Each help topic provides a concept guide available via `limacharlie help <topic>`.
Cheatsheets provide quick-reference examples via `limacharlie cheatsheet <topic>`.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Help topics registry
# ---------------------------------------------------------------------------
HELP_TOPICS = {}

HELP_TOPICS["d&r-rules"] = """\
Detection & Response (D&R) Rules
================================

D&R rules are the core detection mechanism in LimaCharlie. Each rule has two
parts:

  detect  - A declarative pattern that matches against incoming events.
  respond - One or more actions to take when the detect pattern matches.

Rules are evaluated in real time against telemetry as it arrives from sensors.

Key concepts:
  - Namespace: rules in the "managed" namespace are read-only (from extensions).
    Custom rules are in the "general" namespace.
  - Operator: the detect block uses operators like "is", "contains", "starts with",
    "matches", "and", "or", "exists", and "not" to build matching logic.
  - Target: the "event" field in detect specifies which event type to match
    (e.g., NEW_PROCESS, DNS_REQUEST, FILE_CREATE).
  - Respond actions include: "report" (generate a detection), "task" (send a
    sensor command), "add tag", "remove tag", "isolate network", and more.

Workflow:
  1. List existing rules:       limacharlie rule list
  2. Create a new rule:         limacharlie rule create --name myRule --detect '...' --respond '...'
  3. Test against historical:   limacharlie replay run --rule-name myRule --start ... --end ...
  4. View detections:           limacharlie detection list

False Positives:
  FP rules suppress specific detections. They match against detection output
  and prevent the detection from being emitted.

  limacharlie fp list
  limacharlie fp create --name myFP --data '...'

Related commands: rule, fp, replay, detection, ai generate-rule
"""

HELP_TOPICS["hive"] = """\
Hive - Key-Value Store
======================

Hive is LimaCharlie's distributed key-value store. It's used to store
configuration, secrets, lookups, playbooks, SOPs, adapters, and more.

Each hive has:
  - A hive name (e.g., "secret", "lookup", "cloud_sensor")
  - A partition key (usually the organization ID)
  - Records identified by a key name

Each record contains:
  - data:    The record's payload (arbitrary JSON)
  - usr_mtd: User metadata including:
    - enabled:  Whether the record is active
    - expiry:   Optional Unix timestamp for auto-expiry (0 = no expiry)
    - tags:     List of string tags for organization
    - comment:  Free-text description
  - sys_mtd: System metadata including:
    - etag:     Version identifier for optimistic concurrency control

Etag-based transactions:
  When updating a record, you can pass the current etag to ensure no one else
  has modified the record since you read it. If the etag doesn't match, the
  update fails and you can retry.

Shortcut commands:
  Instead of using `limacharlie hive` directly, use the convenience wrappers:
    limacharlie secret list/get/set/delete
    limacharlie lookup list/get/set/delete
    limacharlie playbook list/get/set/delete
    limacharlie adapter list/get/set/delete
    limacharlie cloud-sensor list/get/set/delete
    limacharlie sop list/get/set/delete
    limacharlie note list/get/set/delete

Related commands: hive, secret, lookup, playbook, adapter, cloud-sensor, sop, note
"""

HELP_TOPICS["lcql"] = """\
LCQL - LimaCharlie Query Language
==================================

LCQL is the query language for searching historical telemetry stored in
LimaCharlie. It supports structured queries with filtering, aggregation,
and time-range scoping.

Query format (pipe-separated components):
  [SENSOR_SELECTOR] | [EVENT_TYPES] | FILTER [| PROJECTION]

  The time range is provided via --start/--end (unix epoch seconds) in
  the CLI, or as the first component in the full LCQL format (e.g. -24h).

Examples:
  * | NEW_PROCESS | event/FILE_PATH contains "cmd.exe"
  plat == windows | DNS_REQUEST | event/DOMAIN_NAME == "evil.com"
  * | NEW_PROCESS | event/COMMAND_LINE contains "powershell"
  plat == windows | DNS_REQUEST | event/DOMAIN_NAME contains 'google' | event/DOMAIN_NAME as domain COUNT(event) as count GROUP BY(domain)

Pagination:
  Large result sets are paginated. The SDK handles this automatically.
  Use --limit to control page size.

CLI usage:
  limacharlie search run --query '* | NEW_PROCESS | event/COMMAND_LINE contains "powershell"' --start 1700000000 --end 1700086400
  limacharlie search validate --query '* | NEW_PROCESS | event/COMMAND_LINE contains "powershell"'
  limacharlie ai generate-query --description "find all PowerShell executions"

Related commands: search, event, detection, ai generate-query
"""

HELP_TOPICS["sensor"] = """\
Sensors
=======

Sensors are lightweight agents installed on endpoints that collect telemetry
and execute commands. LimaCharlie supports multiple platforms:

Platforms:
  windows (code 1)  - Windows endpoints
  linux (code 2)    - Linux endpoints
  macos (code 3)    - macOS endpoints
  chrome (code 4)   - Chrome OS / Chromebook

Sensor identifiers:
  SID  - Sensor ID, a unique 5-part UUID (e.g., 8cbe27f4-bfa1-4afb-b...)
  IID  - Installation ID, based on the installation key used
  The first segment of the SID encodes the OID.

Sensor lifecycle:
  1. Install with an installation key
  2. Sensor enrolls and appears in the organization
  3. Sensor collects telemetry and can receive tasks
  4. Sensor can be tagged, isolated, upgraded, or deleted

Key operations:
  limacharlie sensor list              - List all sensors (with optional --tag filter)
  limacharlie sensor get --sid <sid>   - Get sensor details
  limacharlie tag add --sid <sid> --tag <tag>   - Tag a sensor
  limacharlie endpoint-policy isolate --sid <sid>    - Network-isolate a sensor
  limacharlie task send --sid <sid> --task <cmd> --args '...'  - Send a task

Online status:
  limacharlie sensor online            - List currently online sensors
  limacharlie sensor wait-online --sid <sid>  - Wait for a sensor to come online

Related commands: sensor, tag, endpoint-policy, task, installation-key
"""

HELP_TOPICS["output"] = """\
Outputs
=======

Outputs route telemetry and detections from LimaCharlie to external
destinations. Each output has:
  - A name (unique identifier)
  - A module (the destination type: s3, gcs, scp, slack, webhook, syslog, etc.)
  - Configuration specific to the module (bucket name, URL, credentials, etc.)
  - A type filter: which data to forward (event, detect, audit, deployment, etc.)

Common output modules:
  s3          - Amazon S3 bucket
  gcs         - Google Cloud Storage bucket
  scp         - SCP/SFTP file transfer
  slack       - Slack webhook
  webhook     - Generic HTTP webhook
  syslog      - Syslog (UDP/TCP/TLS)
  smtp        - Email via SMTP
  humio       - CrowdStrike Falcon LogScale
  kafka       - Apache Kafka

Output types (what data to send):
  event       - Raw telemetry events
  detect      - Detection alerts
  audit       - Audit log entries
  deployment  - Deployment/enrollment events
  artifact    - Artifact/log events

CLI usage:
  limacharlie output list
  limacharlie output create --name myOutput --module webhook --type detect --config '{"dest_host":"https://..."}'
  limacharlie output delete --name myOutput

Related commands: output, stream
"""

HELP_TOPICS["extension"] = """\
Extensions
==========

Extensions are add-on services that can be subscribed to from the LimaCharlie
marketplace. They provide additional detection content, integrations, and
capabilities beyond the core platform.

Each extension:
  - Has a unique name
  - Can inject managed D&R rules (in the "managed" namespace)
  - Can provide configuration options
  - May have associated costs

Types of extensions:
  - Detection packs: curated sets of D&R rules for specific threats
  - Integration packs: connectors to third-party tools
  - Service extensions: additional platform features

CLI usage:
  limacharlie extension list               - List available extensions
  limacharlie extension subscribe --name <ext>  - Subscribe to an extension
  limacharlie extension unsubscribe --name <ext>

Related commands: extension, rule (managed namespace)
"""

HELP_TOPICS["sync"] = """\
Infrastructure as Code (Sync)
==============================

The sync system allows you to manage your LimaCharlie configuration as code.
You can export (pull) your current configuration to YAML files and import
(push) configuration from files back to LimaCharlie.

Supported configuration types:
  - rules:            D&R rules
  - fps:              False positive rules
  - outputs:          Output configurations
  - extensions:       Extension subscriptions
  - resources:        Hive resources
  - integrity:        Integrity monitoring rules
  - exfil:            Exfil prevention rules
  - artifact:         Artifact collection rules
  - org-value:        Organization config values
  - hives:            Hive records
  - installation_keys: Installation keys
  - yara:             YARA rules and sources

Workflow:
  1. Pull current config:   limacharlie sync pull --dir ./lc-config
  2. Edit files locally
  3. Push changes:          limacharlie sync push --dir ./lc-config --dry-run
  4. Apply for real:        limacharlie sync push --dir ./lc-config

The push uses the infrastructure-service by default, or the cloud-based
infrastructure extension if configured.

File structure:
  ./lc-config/
    rules/
      my-rule.yaml
    outputs/
      my-output.yaml
    hives/
      secret/
        my-secret.yaml
    ...

Related commands: sync, rule, output, hive
"""

HELP_TOPICS["auth"] = """\
Authentication
==============

LimaCharlie CLI supports multiple authentication methods:

1. API Key (org-scoped):
   limacharlie auth login --api-key <key> --oid <oid>
   Authenticates to a specific organization using an API key.

2. User API Key (user-scoped):
   limacharlie auth login --uid <uid> --api-key <key>
   Authenticates as a user with access to multiple organizations.

Environment variables:
  LC_OID           - Organization ID
  LC_API_KEY       - API key
  LC_UID           - User ID (for user-scoped keys)
  LC_CURRENT_ENV   - Active environment/profile name
  LC_CREDS_FILE    - Custom credentials file path
  LC_EPHEMERAL_CREDS - Set to "1" to prevent writing credentials to disk

Credentials file:
  Default location: ~/.limacharlie.d/config.yaml (YAML format)
  Legacy location: ~/.limacharlie (auto-detected with deprecation warning)
  Windows: %APPDATA%/limacharlie/config.yaml
  Use 'limacharlie config show-paths' to see active paths.
  Use 'limacharlie config migrate' to move from legacy to new layout.
  Supports named environments for managing multiple orgs.

Priority (highest to lowest):
  1. Command-line flags (--oid, --api-key)
  2. Environment variables (LC_OID, LC_API_KEY)
  3. Credentials file (~/.limacharlie.d/config.yaml)

JWT tokens:
  The SDK automatically generates and refreshes JWT tokens from API keys.
  JWTs are short-lived and provide the actual authentication to API calls.

Related commands: auth
"""

HELP_TOPICS["permissions"] = """\
Permissions
===========

LimaCharlie uses a permission system to control access to API operations.
Permissions are granted to API keys and determine what actions can be
performed.

Common permissions:
  dr.list           - List D&R rules
  dr.set            - Create/update D&R rules
  dr.del            - Delete D&R rules
  sensor.list       - List sensors
  sensor.get        - Get sensor details
  sensor.task       - Send tasks to sensors
  output.list       - List outputs
  output.set        - Create outputs
  output.del        - Delete outputs
  apikey.ctrl       - Manage API keys
  user.ctrl         - Manage users
  billing.ctrl      - Manage billing
  insight.evt.get   - Read events
  insight.det.get   - Read detections
  insight.obj.get   - IOC lookups

Testing permissions:
  limacharlie auth test
  limacharlie auth test --permissions sensor.list,sensor.task

Related commands: auth, api-key, user
"""

HELP_TOPICS["event"] = """\
Events
======

Events are the raw telemetry collected by LimaCharlie sensors. Each event
has a type (e.g., NEW_PROCESS, DNS_REQUEST, FILE_CREATE) and a structured
payload containing the event data.

Common event types:
  NEW_PROCESS    - New process execution
  TERMINATE      - Process termination
  DNS_REQUEST    - DNS query
  NEW_TCP4_CONNECTION / NEW_UDP4_CONNECTION - Network connections
  FILE_CREATE / FILE_DELETE / FILE_MODIFIED - File operations
  REG_KEY_CREATE / REG_VALUE_SET - Registry operations (Windows)
  USER_OBSERVED  - User activity
  MODULE_LOAD    - Module/library loading
  NETWORK_SUMMARY - Periodic network summary

Each event contains:
  - routing: metadata (SID, event type, timestamp, tags, etc.)
  - event: the actual event data (varies by type)

Querying events:
  limacharlie event list --sid <sid> --event-type NEW_PROCESS --limit 50
  limacharlie search run --query '* | NEW_PROCESS | event/FILE_PATH exists' --start 1700000000 --end 1700086400

Related commands: event, search, detection, stream
"""

HELP_TOPICS["detection"] = """\
Detections
==========

Detections are alerts generated by D&R rules when telemetry matches a detect
pattern. Each detection contains:
  - The detection name (from the rule that triggered it)
  - The matched event(s)
  - The respond actions that were executed
  - Timestamp and routing information

Detections are stored and can be queried historically. They can also be
streamed in real time via the spout system.

Viewing detections:
  limacharlie detection list --limit 20
  limacharlie detection get --id <detection_id>
  limacharlie stream detections          (real-time)

False positives:
  If a detection is a false positive, create an FP rule to suppress it:
  limacharlie fp create --name suppress-fp --data '...'

Related commands: detection, rule, fp, stream
"""

HELP_TOPICS["adapter"] = """\
Adapters (USP - Universal Sensor Protocol)
==========================================

Adapters allow LimaCharlie to ingest data from sources beyond its native
sensor agents. Using the Universal Sensor Protocol (USP), you can parse
and normalize logs from any source into LimaCharlie events.

How it works:
  1. Create an adapter configuration (stored in the external_adapter hive)
  2. The adapter defines parsing rules to transform raw log lines into
     structured LimaCharlie events
  3. Data is sent to LimaCharlie via the ingestion endpoint
  4. Events from adapters appear like native sensor events and can trigger
     D&R rules

Testing:
  limacharlie usp validate --adapter <name> --data '...'
  Validates that an adapter configuration correctly parses sample data.

Managing adapters:
  limacharlie adapter list
  limacharlie adapter get --name <name>
  limacharlie adapter set --name <name> --data '...'
  limacharlie adapter delete --name <name>

Related commands: adapter, usp, cloud-sensor
"""

HELP_TOPICS["download"] = """\
Downloads - Sensor Installers & Adapter Binaries
=================================================

LimaCharlie provides pre-built binaries for sensors (EDR agents) and
adapters (USP) across many platforms.  The CLI can download these
directly from downloads.limacharlie.io.

Sensors (EDR agents):
  Sensors are lightweight agents installed on endpoints that collect
  telemetry and execute commands.

  Platforms:
    windows   - 64, 32, arm64, msi64, msi32
    linux     - 64, deb64, debarm64, alpine64
    mac       - 64 (Intel), arm64 (Apple Silicon)
    chrome    - browser extension redirect

  Install a sensor:
    ./lc_sensor_64 -i YOUR_INSTALLATION_KEY

Adapters (USP binaries):
  Adapters ingest data from sources beyond native sensor agents using
  the Universal Sensor Protocol.

  Platforms:
    linux     - 64, arm, arm64
    windows   - 64
    mac       - 64, arm64
    aix       - ppc64
    freebsd   - 64
    openbsd   - 64
    netbsd    - 64
    solaris   - 64

  Docker image: refractionpoint/lc-adapter

CLI usage:
  limacharlie download list                           # Show all targets
  limacharlie download sensor --list                  # Show sensor targets
  limacharlie download sensor --platform linux --arch 64
  limacharlie download sensor --platform windows --arch msi64 -o sensor.msi
  limacharlie download adapter --platform linux --arch 64
  limacharlie download adapter --list                 # Show adapter targets

Related commands: download, installation-key, sensor, adapter
"""

HELP_TOPICS["platform-codes"] = """\
Platform Codes
==============

LimaCharlie uses numeric platform codes to identify operating systems:

  1 = Windows
  2 = Linux
  3 = macOS
  4 = Chrome OS

These codes appear in sensor information, D&R rule filters, and various
API responses.

In the SDK:
  from limacharlie.sdk.sensor import (
      PLATFORM_WINDOWS, PLATFORM_LINUX,
      PLATFORM_MACOS, PLATFORM_CHROME
  )

Architecture codes:
  1 = x86
  2 = x64
  3 = ARM
  4 = ARM64
  5 = ALPINE64

Related commands: sensor
"""

HELP_TOPICS["ioc-types"] = """\
IOC Types
=========

LimaCharlie supports the following Indicator of Compromise (IOC) types
for searching across your telemetry:

  file_hash      - File hash (MD5, SHA1, SHA256)
  file_name      - File name
  file_path      - Full file path
  ip             - IP address (IPv4 or IPv6)
  domain         - Domain name
  user           - User name
  service_name   - Service/daemon name
  package_name   - Software package name

Usage:
  limacharlie ioc search --type ip --value "10.0.0.1"
  limacharlie ioc batch-search --input-file iocs.json

The batch-search command accepts a JSON file with multiple IOC searches.

Related commands: ioc, search
"""

HELP_TOPICS["timestamps"] = """\
Timestamps
==========

LimaCharlie uses Unix epoch timestamps (seconds since 1970-01-01 UTC) in
most API interactions.

The CLI --start and --end flags accept Unix epoch seconds (integers):
  limacharlie search run --start 1704067200 --end 1704153600
  limacharlie event list --start 1704067200 --end 1704153600

LCQL queries support relative time ranges (e.g. -24h, -7d, -30m) as
the first component of the query string itself, but the CLI --start/--end
flags require integer timestamps.

All timestamps in API responses are Unix epoch seconds (integers).
"""

HELP_TOPICS["bexpr"] = """\
Boolean Expressions (bexpr)
===========================

Boolean expressions are used in various LimaCharlie contexts (D&R rules,
sensor selectors) to create complex matching conditions.

Operators:
  and     - All sub-conditions must match
  or      - At least one sub-condition must match
  not     - Negates the sub-condition
  exists  - The specified path exists in the event
  is      - Exact match
  contains - Substring match
  starts with / ends with - Prefix/suffix match
  matches  - Regular expression match
  is greater than / is lower than - Numeric comparison

Example D&R detect block:
  {
    "op": "and",
    "rules": [
      {"op": "is", "event": "NEW_PROCESS", "path": "event/FILE_PATH", "value": "cmd.exe"},
      {"op": "contains", "path": "event/COMMAND_LINE", "value": "/c"}
    ]
  }

Path notation:
  Uses "/" as separator: "event/COMMAND_LINE", "routing/hostname"
  Wildcards: "event/*/FILE_PATH" matches any intermediate key

Related commands: rule, fp, ai generate-rule
"""

HELP_TOPICS["billing"] = """\
Billing
=======

LimaCharlie billing is usage-based. You can monitor your usage and costs
through the CLI.

Key metrics:
  - Sensor count (active sensors)
  - Event volume (events ingested)
  - Artifact storage (bytes stored)
  - Output volume (bytes forwarded)

CLI usage:
  limacharlie billing status   - Current billing summary
  limacharlie billing details  - Detailed usage breakdown
  limacharlie billing plans    - Available plan options
  limacharlie billing invoice  - Invoice history

Billing endpoints are served under api.limacharlie.io at /v1/orgs/{oid}/billing/ and /v1/plans.

Related commands: billing, org
"""


# ---------------------------------------------------------------------------
# Cheatsheets registry
# ---------------------------------------------------------------------------
CHEATSHEETS = {}

CHEATSHEETS["common-operations"] = """\
Common Operations Cheatsheet
=============================

# Authentication
limacharlie auth login --api-key <key> --oid <oid>
limacharlie auth whoami
limacharlie auth use-org <oid>

# Sensor management
limacharlie sensor list
limacharlie sensor list --tag server
limacharlie sensor get --sid <sid>
limacharlie sensor online

# Tagging
limacharlie tag add --sid <sid> --tag my-tag
limacharlie tag remove --sid <sid> --tag my-tag
limacharlie tag find --tag my-tag

# D&R Rules
limacharlie rule list
limacharlie rule get --name my-rule
limacharlie rule create --name my-rule --detect '{"op":"is","event":"NEW_PROCESS","path":"event/FILE_PATH","value":"cmd.exe"}' --respond '[{"action":"report","name":"cmd-execution"}]'
limacharlie rule delete --name my-rule

# Search
limacharlie search run --query '* | NEW_PROCESS | event/COMMAND_LINE contains "powershell"' --start 1700000000 --end 1700086400

# Outputs
limacharlie output list
limacharlie output create --name my-output --module webhook --type detect --config '{"dest_host":"https://hooks.example.com/lc"}'

# Hive records
limacharlie secret list
limacharlie secret get --name my-secret
limacharlie lookup list
limacharlie hive list --hive-name secret

# Organization
limacharlie org info
limacharlie org errors

# Streaming
limacharlie stream events
limacharlie stream detections
"""

CHEATSHEETS["detection-engineering"] = """\
Detection Engineering Cheatsheet
=================================

# List all rules
limacharlie rule list

# Create a detection rule
limacharlie rule create --name proc-detect \\
  --detect '{"op":"is","event":"NEW_PROCESS","path":"event/FILE_PATH","value":"suspicious.exe"}' \\
  --respond '[{"action":"report","name":"suspicious-process"}]'

# Update existing rule
limacharlie rule update --name proc-detect \\
  --detect '{"op":"and","rules":[...]}' \\
  --respond '[...]'

# Test rule against historical data
limacharlie replay run --rule-name proc-detect --start -7d --end now

# View recent detections
limacharlie detection list --limit 20

# Create false positive
limacharlie fp create --name suppress-benign \\
  --data '{"op":"is","path":"detect/event/FILE_PATH","value":"benign.exe"}'

# AI-assisted rule generation
limacharlie ai generate-rule --description "Detect PowerShell downloading files"

# Export/import rules for version control
limacharlie sync pull --dir ./lc-config
limacharlie sync push --dir ./lc-config --dry-run
"""

CHEATSHEETS["incident-response"] = """\
Incident Response Cheatsheet
==============================

# Isolate a compromised host
limacharlie endpoint-policy isolate --sid <sid>

# Check isolation status
limacharlie endpoint-policy status --sid <sid>

# Tag for tracking
limacharlie tag add --sid <sid> --tag incident-2024-01

# Send investigative tasks
limacharlie task send --sid <sid> --task os_processes
limacharlie task send --sid <sid> --task os_services
limacharlie task send --sid <sid> --task dir_list --args '{"rootDir":"C:\\\\Users"}'
limacharlie task send --sid <sid> --task file_hash --args '{"filePath":"C:\\\\suspect.exe"}'

# Search for IOCs
limacharlie ioc search --type file_hash --value <sha256>
limacharlie ioc search --type ip --value <ip_address>
limacharlie ioc search --type domain --value <domain>

# Search historical telemetry
limacharlie search run --query '* | NEW_PROCESS | event/COMMAND_LINE contains "powershell"' --start 1700000000 --end 1700086400

# Stream live events from sensor
limacharlie stream events --tag incident-2024-01

# Request memory dump
limacharlie sensor dump --sid <sid>

# Rejoin network after investigation
limacharlie endpoint-policy rejoin --sid <sid>
limacharlie tag remove --sid <sid> --tag incident-2024-01
"""

CHEATSHEETS["downloads"] = """\
Downloads Cheatsheet
=====================

# List everything available
limacharlie download list

# --- Sensors (EDR agents) ---

# List available sensor targets
limacharlie download sensor --list

# Download Linux sensor (x64)
limacharlie download sensor --platform linux --arch 64

# Download Windows MSI installer (x64)
limacharlie download sensor --platform windows --arch msi64 -o ./sensor.msi

# Download macOS sensor (Apple Silicon)
limacharlie download sensor --platform mac --arch arm64

# Download Linux Debian package
limacharlie download sensor --platform linux --arch deb64

# --- Adapters (USP binaries) ---

# List available adapter targets
limacharlie download adapter --list

# Download Linux adapter (x64)
limacharlie download adapter --platform linux --arch 64

# Download macOS adapter (Apple Silicon)
limacharlie download adapter --platform mac --arch arm64 -o ./lc_adapter

# Pipe binary to stdout (useful for remote deploy)
limacharlie download sensor --platform linux --arch 64 -o -
"""

CHEATSHEETS["fleet-management"] = """\
Fleet Management Cheatsheet
=============================

# Download sensor installers
limacharlie download sensor --platform linux --arch 64
limacharlie download sensor --platform windows --arch msi64

# List all sensors
limacharlie sensor list
limacharlie sensor list --tag production
limacharlie sensor list --output json | jq '.[] | select(.platform == "windows")'

# Installation keys
limacharlie installation-key list
limacharlie installation-key create --description "Production deploy key" --tags server,production

# Bulk tagging
limacharlie tag find --tag needs-upgrade
limacharlie tag add --sid <sid> --tag production

# Sensor versioning
limacharlie sensor upgrade --sid <sid>

# Export sensor list
limacharlie sensor export --output csv

# Infrastructure as Code
limacharlie sync pull --dir ./lc-config
limacharlie sync push --dir ./lc-config --dry-run
limacharlie sync push --dir ./lc-config

# Monitor organization health
limacharlie org info
limacharlie org errors
limacharlie org stats
limacharlie billing status
"""

CHEATSHEETS["searching"] = """\
Searching Cheatsheet
=====================

# Basic LCQL search
limacharlie search run --query '* | NEW_PROCESS | event/FILE_PATH exists' --start 1700000000 --end 1700086400

# Search with field filters
limacharlie search run --query '* | NEW_PROCESS | event/FILE_PATH contains "cmd.exe"' --start 1700000000 --end 1700086400

# DNS queries
limacharlie search run --query '* | DNS_REQUEST | event/DOMAIN_NAME == "evil.com"' --start 1700000000 --end 1700086400

# Network connections
limacharlie search run --query '* | NEW_TCP4_CONNECTION | event/IP_ADDRESS == "10.0.0.1"' --start 1700000000 --end 1700086400

# Validate query syntax
limacharlie search validate --query '* | NEW_PROCESS | event/COMMAND_LINE contains "powershell"'

# IOC searches
limacharlie ioc search --type file_hash --value abc123...
limacharlie ioc search --type ip --value 1.2.3.4
limacharlie ioc search --type domain --value evil.example.com

# Batch IOC search
limacharlie ioc batch-search --input-file iocs.json

# AI-generated queries
limacharlie ai generate-query --description "find all SSH connections from external IPs"

# Events by sensor
limacharlie event list --sid <sid> --event-type NEW_PROCESS --limit 100

# Output as JSON for piping
limacharlie search run --query '* | NEW_PROCESS | event/FILE_PATH exists' --start 1700000000 --end 1700086400 --output json | jq '.events[]'
"""


# ---------------------------------------------------------------------------
# Lookup functions
# ---------------------------------------------------------------------------

def get_help_topic(name: str) -> str | None:
    """Get help topic content by name.

    Tries an exact match first, then falls back to simple singular/plural
    variants so that both ``limacharlie help output`` and
    ``limacharlie help outputs`` resolve to the same topic.

    Args:
        name: Topic name (e.g., 'd&r-rules', 'hive', 'lcql').

    Returns:
        str or None.
    """
    topic = HELP_TOPICS.get(name)
    if topic is not None:
        return topic
    # Try adding/removing a trailing "s" for singular/plural tolerance.
    if name.endswith("s"):
        topic = HELP_TOPICS.get(name[:-1])
    else:
        topic = HELP_TOPICS.get(name + "s")
    return topic


def list_help_topics() -> list[str]:
    """List all available help topic names.

    Returns:
        list of topic name strings.
    """
    return sorted(HELP_TOPICS.keys())


def get_cheatsheet(name: str) -> str | None:
    """Get cheatsheet content by name.

    Tries an exact match first, then falls back to simple singular/plural
    variants for tolerance.

    Args:
        name: Cheatsheet name.

    Returns:
        str or None.
    """
    sheet = CHEATSHEETS.get(name)
    if sheet is not None:
        return sheet
    if name.endswith("s"):
        sheet = CHEATSHEETS.get(name[:-1])
    else:
        sheet = CHEATSHEETS.get(name + "s")
    return sheet


def list_cheatsheets() -> list[str]:
    """List all available cheatsheet names.

    Returns:
        list of cheatsheet name strings.
    """
    return sorted(CHEATSHEETS.keys())
