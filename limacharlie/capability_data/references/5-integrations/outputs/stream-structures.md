# Output Stream Structures

LimaCharlie routes data through four distinct output streams, each with a different structure and purpose. Understanding these structures is essential for:

- Configuring output destinations correctly
- Building parsers in external systems (SIEM, data lake, etc.)
- Filtering and transforming data before sending it
- Integrating with webhooks, APIs, and automation platforms

## Overview of Output Streams

| Stream Type | Purpose | Typical Volume | Common Destinations |
|-------------|---------|----------------|---------------------|
| `event` | Real-time telemetry from sensors/adapters | High | SIEM, data lake, long-term storage |
| `detect` | Alerts from D&R rules | Low-Medium | SIEM, SOAR, incident response platforms |
| `audit` | Platform management actions | Low | Compliance logging, audit trails |
| `deployment` | Sensor lifecycle events | Very Low | Asset management, deployment tracking |

## 1. Event Stream Structure

**Purpose**: Capture real-time telemetry from endpoints and cloud adapters

**Stream Name**: `event`

### Structure

All events follow a canonical two-level structure:

```json
{
  "routing": {
    "oid": "8cbe27f4-aaaa-aaaa-aaaa-138cd51389cd",
    "sid": "bb4b30af-aaaa-aaaa-aaaa-f014ada33345",
    "event_type": "NEW_PROCESS",
    "event_time": 1656959942437,
    "event_id": "8cec565d-14bd-4639-a1af-4fc8d5420b0c",
    "hostname": "workstation-01",
    "iid": "7d23bee6-aaaa-aaaa-aaaa-c8e8cca132a1",
    "did": "b97e9d00-aaaa-aaaa-aaaa-27c3468d5901",
    "ext_ip": "203.0.113.45",
    "int_ip": "10.0.1.25",
    "plat": 268435456,
    "arch": 2,
    "moduleid": 2,
    "this": "a443f9c48bef700740ef27e062c333c6",
    "parent": "42217cb0326ca254999554a862c3298e",
    "tags": ["production", "critical-assets"]
  },
  "event": {
    "FILE_PATH": "C:\\Windows\\System32\\cmd.exe",
    "COMMAND_LINE": "cmd.exe /c whoami",
    "PROCESS_ID": 4812,
    "USER_NAME": "Administrator",
    "PARENT": {
      "FILE_PATH": "C:\\Windows\\explorer.exe",
      "PROCESS_ID": 2156
    }
  }
}
```

### Routing Object Fields

| Field | Type | Description |
|-------|------|-------------|
| `oid` | string (UUID) | Organization ID |
| `sid` | string (UUID) | Sensor ID - uniquely identifies the endpoint |
| `event_type` | string | Type of event (NEW_PROCESS, DNS_REQUEST, etc.) |
| `event_time` | integer | Unix timestamp in milliseconds |
| `event_id` | string (UUID) | Unique event identifier |
| `hostname` | string | Hostname of the sensor |
| `iid` | string (UUID) | Installation Key ID |
| `did` | string (UUID) | Device ID (hardware identifier) |
| `ext_ip` | string | External IP address |
| `int_ip` | string | Internal IP address |
| `plat` | integer | Platform (Windows=268435456, Linux=...) |
| `arch` | integer | Architecture (x86, x64, ARM) |
| `moduleid` | integer | Sensor module that generated the event |
| `this` | string (hash) | Hash of current process/object |
| `parent` | string (hash) | Hash of parent process |
| `target` | string (hash) | Hash of target object (optional) |
| `tags` | array[string] | Sensor tags at event time |

### Event Object Fields

The `event` object varies by `event_type`. Common event types include:

- **NEW_PROCESS**: `FILE_PATH`, `COMMAND_LINE`, `PROCESS_ID`, `USER_NAME`, `PARENT`
- **DNS_REQUEST**: `DOMAIN_NAME`, `IP_ADDRESS`, `DNS_TYPE`, `DNS_FLAGS`
- **NETWORK_CONNECTIONS**: `NETWORK_ACTIVITY` (array of connections)
- **FILE_MODIFIED**: `FILE_PATH`, `ACTION`, `HASH`
- **WEL** (Windows Event Logs): `EVENT` (nested Windows event structure)

[See complete Event Structure Reference](../../8-reference/event-schemas.md#event-structure-reference)

### Use Cases

- **SIEM Integration**: Parse `routing/event_type` to route to different indexes
- **Compliance**: Store all events for audit and forensic analysis
- **Threat Hunting**: Query historical events for IOCs
- **Analytics**: Build behavioral baselines from event patterns

---

## 2. Detection Stream Structure

**Purpose**: Alerts generated when D&R rules match events

**Stream Name**: `detect`

### Structure

Detections include the original event's routing, the triggering event data, and detection-specific metadata:

```json
{
  "cat": "Suspicious PowerShell Execution",
  "source": "dr-general",
  "routing": {
    "oid": "8cbe27f4-aaaa-aaaa-aaaa-138cd51389cd",
    "sid": "bb4b30af-aaaa-aaaa-aaaa-f014ada33345",
    "event_type": "NEW_PROCESS",
    "event_time": 1656959942437,
    "hostname": "workstation-01",
    "this": "a443f9c48bef700740ef27e062c333c6",
    "parent": "42217cb0326ca254999554a862c333c6"
  },
  "detect": {
    "FILE_PATH": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
    "COMMAND_LINE": "powershell.exe -enc SGVsbG8gV29ybGQ=",
    "PROCESS_ID": 5124
  },
  "detect_id": "f1e2d3c4-aaaa-aaaa-aaaa-123456789abc",
  "namespace": "production",
  "priority": 7,
  "mtd": {
    "custom_field": "value"
  },
  "detect_mtd": {
    "rule_name": "detect-encoded-powershell"
  },
  "detect_data": {
    "suspicious_process": "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe",
    "encoded_command": "SGVsbG8gV29ybGQ=",
    "process_hash": "a443f9c48bef700740ef27e062c333c6"
  },
  "link": "https://docs.company.com/playbooks/powershell-investigation",
  "author": "security-team",
  "source_rule": "detect-encoded-powershell",
  "rule_tags": ["windows", "powershell", "encoded"],
  "gen_time": 1656959942500
}
```

### Detection Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cat` | string | Yes | Detection name/category |
| `source` | string | Yes | Rule source (`dr-general`, `dr-managed`, `fp`) |
| `routing` | object | Yes | Inherited from triggering event |
| `detect` | object | Yes | Copy of event data that triggered detection |
| `detect_id` | string (UUID) | Yes | Unique detection identifier |
| `namespace` | string | No | Organizational namespace |
| `priority` | integer | No | Detection priority (0-10) |
| `mtd` | object | No | General metadata |
| `detect_mtd` | object | No | Detection-specific metadata |
| `detect_data` | object | No | **Structured IOCs extracted from event** |
| `link` | string | No | URL to playbook/documentation |
| `author` | string | No | Rule author |
| `source_rule` | string | No | Rule name that generated this |
| `rule_tags` | array[string] | No | Tags from the rule |
| `gen_time` | integer | No | Unix timestamp (ms) of generation |

### Key Field: detect_data

The `detect_data` field contains **structured IOCs** extracted by the D&R rule. This is extremely valuable for:

- Automated enrichment (lookup IPs, domains, hashes)
- SOAR playbook inputs
- Threat intelligence platform integration
- Case management systems

Example `detect_data` for different detection types:

**Malware Detection**:

```json
"detect_data": {
  "file_path": "C:\\Users\\admin\\Downloads\\malware.exe",
  "file_hash": "5d41402abc4b2a76b9719d911017c592",
  "process_id": 4812,
  "parent_process": "explorer.exe"
}
```

**Network IOC**:

```json
"detect_data": {
  "destination_ip": "198.51.100.42",
  "destination_port": 8443,
  "domain": "malicious.example.com",
  "bytes_sent": 1048576
}
```

### Use Cases

- **Incident Response**: Feed high-priority detections to SOAR platforms
- **Alerting**: Send to Slack, email, or case management systems
- **Triage**: Filter by `priority` and `cat` for analyst review
- **Enrichment**: Extract IOCs from `detect_data` for threat intel lookups

---

## 3. Audit Stream Structure

**Purpose**: Platform management and operational events

**Stream Name**: `audit`

### Structure

Audit logs track actions within the LimaCharlie platform:

```json
{
  "oid": "8cbe27f4-aaaa-aaaa-aaaa-138cd51389cd",
  "ts": "2024-06-05T14:23:18Z",
  "etype": "config_change",
  "msg": "D&R rule created",
  "origin": "api",
  "time": 1656959942,
  "ident": "user@company.com",
  "entity": {
    "type": "dr_rule",
    "name": "detect-encoded-powershell",
    "hive": "dr-general"
  },
  "mtd": {
    "action": "create",
    "source_ip": "203.0.113.10",
    "user_agent": "limacharlie-cli/2.0.0"
  }
}
```

### Audit Fields

| Field | Type | Description |
|-------|------|-------------|
| `oid` | string (UUID) | Organization ID |
| `ts` | string | ISO 8601 timestamp string |
| `etype` | string | Event type (config_change, api_call, user_action, error) |
| `msg` | string | Human-readable audit message |
| `origin` | string | Origin of action (api, ui, cli, system) |
| `time` | integer | Unix timestamp in seconds |
| `ident` | string | Identity performing the action (email, API key name) |
| `entity` | object | Object the action was performed on |
| `mtd` | object | Action characteristics (action type, source IP, etc.) |
| `component` | string | Component name (for error messages) |
| `error` | string | Error message (if applicable) |

### Entity Object Examples

**D&R Rule**:

```json
"entity": {
  "type": "dr_rule",
  "name": "detect-lateral-movement",
  "hive": "dr-general"
}
```

**Sensor**:

```json
"entity": {
  "type": "sensor",
  "sid": "bb4b30af-aaaa-aaaa-aaaa-f014ada33345",
  "hostname": "workstation-01"
}
```

**Output**:

```json
"entity": {
  "type": "output",
  "name": "splunk-events",
  "stream": "event"
}
```

### Use Cases

- **Compliance**: Track all configuration changes for SOC 2, ISO 27001
- **Security Monitoring**: Detect unauthorized platform changes
- **Troubleshooting**: Audit trail for configuration issues
- **User Activity**: Monitor API usage and user actions

---

## 4. Deployment Stream Structure

**Purpose**: Sensor deployment and lifecycle events

**Stream Name**: `deployment`

### Structure

Deployment events track sensor installations, removals, and updates:

```json
{
  "routing": {
    "oid": "8cbe27f4-aaaa-aaaa-aaaa-138cd51389cd",
    "sid": "bb4b30af-aaaa-aaaa-aaaa-f014ada33345",
    "event_type": "sensor_installed",
    "event_time": 1656959942437,
    "hostname": "workstation-01",
    "iid": "7d23bee6-aaaa-aaaa-aaaa-c8e8cca132a1",
    "did": "b97e9d00-aaaa-aaaa-aaaa-27c3468d5901",
    "plat": 268435456,
    "arch": 2
  },
  "event": {
    "action": "install",
    "sensor_version": "4.25.0",
    "installation_method": "msi",
    "tags": ["production", "finance-dept"],
    "installer_user": "Administrator"
  }
}
```

### Deployment Event Types

| Event Type | Description | Example Event Data |
|------------|-------------|-------------------|
| `sensor_installed` | New sensor deployment | `action`, `sensor_version`, `tags` |
| `sensor_uninstalled` | Sensor removal | `action`, `reason`, `uninstall_time` |
| `sensor_upgraded` | Sensor version update | `old_version`, `new_version`, `upgrade_method` |
| `sensor_checkin` | Periodic sensor heartbeat | `last_seen`, `connectivity_status` |

### Use Cases

- **Asset Tracking**: Monitor endpoint agent deployment status
- **Compliance**: Ensure all required endpoints have sensors
- **Lifecycle Management**: Track sensor versions and upgrades
- **Alerting**: Detect unexpected sensor removals

---

## Output Configuration Examples

### Sending Event Stream to Splunk

```yaml
name: splunk-events
module: webhook_bulk
type: event  # Event stream
dest_host: https://splunk.company.com:8088/services/collector/raw
auth_header_name: Authorization
auth_header_value: Splunk YOUR-HEC-TOKEN
```

### Sending Detections to Slack

```yaml
name: slack-critical-alerts
module: slack
type: detect  # Detection stream
slack_api_token: xoxb-your-slack-token
slack_channel: security-alerts
cat: high-priority  # Category filter for high-priority detections
```

### Audit Logs to S3

```yaml
name: compliance-audit-logs
module: s3
type: audit  # Audit stream
bucket: company-security-audit-logs
dir: limacharlie/audit/
key_id: YOUR-ACCESS-KEY
secret_key: YOUR-SECRET-KEY
```

---

## Filtering and Transforming Streams

**IMPORTANT**: Filter parameters use **newline-separated string format**, not YAML arrays. Each item must be on its own line within a multiline string.

### Event Type Filtering

Filter specific event types using whitelist/blacklist:

```yaml
# Only send NEW_PROCESS and TERMINATE_PROCESS events
event_white_list: |
  NEW_PROCESS
  TERMINATE_PROCESS

# Or exclude certain events
event_black_list: |
  DNS_REQUEST
  CONNECTED
```

**Format Notes**:

- Use the pipe (`|`) operator for multiline strings in YAML
- Each event type on its own line
- No hyphens or list syntax
- Empty lines and whitespace are automatically trimmed

### Category Filtering

Filter detections by category:

```yaml
# Only send specific detection categories
cat_white_list: |
  high-priority
  critical

# Or exclude certain categories
cat_black_list: |
  informational
```

### Tag-Based Filtering

Filter events from sensors with specific tags:

```yaml
# Only send events from tagged sensors (single tag)
tag: production

# Exclude events from multiple tags
tag_black_list: |
  dev
  test
  staging
```

**Note**: The `tag` parameter accepts a single tag string. To filter multiple tags, use `tag_black_list` to exclude unwanted tags.

### Rule Tag Filtering

Filter detections by D&R rule tags (detection stream only):

```yaml
# Only send detections from specific rule tags
rule_tag_white_list: |
  compliance
  ransomware
  lateral-movement

# Or exclude certain rule tags
rule_tag_black_list: |
  low-confidence
  experimental
```

**Use Case**: Rule tags help organize detections by threat type, compliance requirement, or confidence level.

---

## Best Practices

### 1. Choose the Right Stream

- **event**: Long-term storage, SIEM, threat hunting, compliance
- **detect**: Real-time alerting, SOAR, incident response
- **audit**: Compliance logging, change tracking, security monitoring
- **deployment**: Asset management, sensor lifecycle tracking

### 2. Optimize Event Stream Volume

Event streams can be high-volume. Consider:

- Filtering by `event_type` to send only relevant events
- Using separate outputs for different event types
- Sampling high-frequency events if full fidelity isn't needed

### 3. Parse Detection IOCs

Always extract and process `detect_data` - it contains pre-parsed IOCs ready for enrichment and response.

### 4. Retain Audit Logs Separately

Audit logs are critical for compliance and should be stored in tamper-proof, long-term storage separate from operational data.

### 5. Monitor Deployment Stream

Use deployment events to track sensor health and detect:

- Unexpected uninstalls (potential evasion)
- Sensors stuck on old versions (patch management)
- Gaps in coverage (missing sensors)

---

## Related Documentation

- [The `routing` Section](../../8-reference/routing.md) - Deep dive into the metadata envelope shared by events and detections
- [Event Structure Reference](../../8-reference/event-schemas.md#event-structure-reference)
- [Detection Structure](../../3-detection-response/tutorials/writing-testing-rules.md)
- [LimaCharlie Data Structures](../../1-getting-started/core-concepts.md#limacharlie-data-structures)
- [Output Destinations](destinations/amazon-s3.md) - Configuration guides for specific destinations
- [Testing Outputs](testing.md) - How to validate output configurations
