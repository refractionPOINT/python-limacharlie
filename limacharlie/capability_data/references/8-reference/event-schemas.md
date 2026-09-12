# Event Schemas

Since LimaCharlie standardizes on JSON, including arbitrary sources of data, it means that Schema in LimaCharlie is generally dynamic.

To enable users to create schemas in external systems that expect more strictly typed data, LimaCharlie makes a Schema API available.

This Schema API exposes the "learned" schema from specific event types. As data comes into LimaCharlie, the Schema API will accumulate the list of fields and types observed for those specific events. In turn, the API allows you to retrieve this learned schema.

## API

### Listing Schemas

The list of all available schemas can get retrieved by doing a `GET` to `api.limacharlie.io/v1/orgs/YOUR-OID/schema`.

The returned data looks like:

```json
{
  "event_types": [
    "evt:New-ExchangeAssistanceConfig",
    "det:00285-WIN-RDP_Connection_From_Non-RFC-1918_Address",
    "det:VirusTotal hit on DNS request",
    "evt:WEL",
    "evt:SHUTTING_DOWN",
    "evt:NETSTAT_REP",
    "evt:AdvancedHunting-DeviceEvents",
    "evt:NEW_DOCUMENT",
    "sched:12h_per_cloud_adapter",
    "sched:1h_per_sensor",
    "sched:3h_per_sensor",
    ...
}
```

Each element in the list of schema is composed of a prefix and a value.

Prefixes can be:

- `evt` for an Event.
- `dep` for a Deployment Event.
- `det` for a Detection.
- `art` for an Artifact Event.
- `sched` for Scheduling Events.

The value is generally the Event Type except for Detections where it is the `cat` (detection name).

### Retrieveing Schema Definition

Retrieving a specific schema definition can be done by doing a `GET` on `api.limacharlie.io/v1/orgs/YOUR-OID/schema/EVENT-TYPE`, where the `EVENT-TYPE` is one of the exact keys returned by the listing API above.

The returned data looks like:

```json
{
  "schema": {
    "elements": [
      "i:routing/event_time",
      "s:routing/sid",
      "i:routing/moduleid",
      "i:event/PROCESS_ID",
      "s:routing/this",
      "i:event/DNS_TYPE",
      "s:routing/iid",
      "s:routing/did",
      "i:event/DNS_FLAGS",
      "i:routing/tags",
      "s:event/IP_ADDRESS",
      "s:routing/event_type",
      "i:event/MESSAGE_ID",
      "s:event/CNAME",
      "s:event/DOMAIN_NAME",
      "s:routing/ext_ip",
      "s:routing/parent",
      "s:routing/hostname",
      "s:routing/int_ip",
      "i:routing/plat",
      "s:routing/oid",
      "i:routing/arch",
      "s:routing/event_id"
    ],
    "event_type": "evt:DNS_REQUEST"
  }
}
```

The `schema.elements` data returned is composed of a prefix and a value.

The prefix is one of:

- `i` indicating the element is an Integer.
- `s` indicating the element is a String.
- `b` indicating the element is a Boolean.

The value is a path within the JSON. For example, the schema above would represent the following event:

```json
{
  "event": {
    "CNAME": "cs9.wac.phicdn.net",
    "DNS_TYPE": 5,
    "DOMAIN_NAME": "ocsp.digicert.com",
    "MESSAGE_ID": 19099,
    "PROCESS_ID": 1224
  },
  "routing": {
    "arch": 2,
    "did": "b97e9d00-aaaa-aaaa-aaaa-27c3468d5901",
    "event_id": "8cec565d-14bd-4639-a1af-4fc8d5420b0c",
    "event_time": 1656959942437,
    "event_type": "DNS_REQUEST",
    "ext_ip": "35.1.1.1",
    "hostname": "demo-win-2016.c.lc-demo-infra.internal",
    "iid": "7d23bee6-aaaa-aaaa-aaaa-c8e8cca132a1",
    "int_ip": "10.1.1.1",
    "moduleid": 2,
    "oid": "8cbe27f4-aaaa-aaaa-aaaa-138cd51389cd",
    "parent": "42217cb0326ca254999554a862c3298e",
    "plat": 268435456,
    "sid": "bb4b30af-aaaa-aaaa-aaaa-f014ada33345",
    "tags": [
      "edr"
    ],
    "this": "a443f9c48bef700740ef27e062c333c6"
  }
}
```

## Event Structure Reference

All events in LimaCharlie follow a canonical structure with two top-level objects: `routing` and `event`. Understanding this structure is essential for writing D&R rules, LCQL queries, and configuring outputs.

### Top-Level Structure

```json
{
  "routing": { /* metadata about the event */ },
  "event": { /* event-specific data */ }
}
```

### The `routing` Object

The `routing` object contains **metadata** about the event - information about where it came from, when it occurred, and how it relates to other events. This metadata is consistent across all event types, making it useful for correlation, filtering, and investigation.

#### Core Routing Fields

| Field | Type | Description | Use Cases |
|-------|------|-------------|-----------|
| `oid` | string (UUID) | Organization ID | Multi-tenant filtering, audit trails |
| `sid` | string (UUID) | Sensor ID - uniquely identifies the endpoint | Host-based correlation, sensor management |
| `event_type` | string | Type of event (e.g., `NEW_PROCESS`, `DNS_REQUEST`) | Event filtering in D&R rules, LCQL queries |
| `event_time` | integer | Unix timestamp in milliseconds | Timeline analysis, temporal correlation |
| `event_id` | string (UUID) | Unique identifier for this specific event | Deduplication, event tracking |
| `hostname` | string | Hostname of the sensor | Host-based investigations |
| `iid` | string (UUID) | Installation Key ID used to install the sensor | Deployment tracking, sensor grouping |
| `did` | string (UUID) | Device ID - hardware identifier | Device tracking across reinstalls |

#### Network Information

| Field | Type | Description | Use Cases |
|-------|------|-------------|-----------|
| `ext_ip` | string | External IP address of the sensor | Geolocation, network-based correlation |
| `int_ip` | string | Internal IP address of the sensor | Network segmentation analysis |

#### Platform Information

| Field | Type | Description | Use Cases |
|-------|------|-------------|-----------|
| `plat` | integer | Platform identifier (Windows, Linux, macOS, etc.) | Platform-specific rules |
| `arch` | integer | Architecture (x86, x64, ARM, etc.) | Architecture-specific analysis |
| `moduleid` | integer | Sensor module that generated the event | Module-specific filtering |

#### Process Correlation Fields

| Field | Type | Description | Use Cases |
|-------|------|-------------|-----------|
| `this` | string (hash) | Hash representing the current process or object | Process tracking across events |
| `parent` | string (hash) | Hash of the parent process | Process tree reconstruction |
| `target` | string (hash) | Hash of the target object (in actions on other objects) | Object tracking, lateral movement detection |

#### Other Routing Fields

| Field | Type | Description | Use Cases |
|-------|------|-------------|-----------|
| `tags` | array[string] | Sensor tags applied at event time | Tag-based filtering, dynamic grouping |

### The `event` Object

The `event` object contains **event-specific data** that varies by event type. For example:

- **NEW_PROCESS** events contain: `FILE_PATH`, `COMMAND_LINE`, `PROCESS_ID`, `PARENT` (full parent process info)
- **DNS_REQUEST** events contain: `DOMAIN_NAME`, `IP_ADDRESS`, `DNS_TYPE`, `DNS_FLAGS`
- **NETWORK_CONNECTIONS** events contain: `NETWORK_ACTIVITY` array with connection details
- **WEL** (Windows Event Log) events contain: `EVENT` object with nested Windows event structure

### Event Structure in Practice

#### Accessing Fields in D&R Rules

In Detection & Response rules, you access fields using the `event/` and `routing/` path prefixes:

```yaml
detect:
  event: NEW_PROCESS
  op: and
  rules:
    - op: is
      path: routing/plat
      value: 0x10000000  # Windows
    - op: contains
      path: event/COMMAND_LINE
      value: powershell
      case sensitive: false
```

#### Event Correlation Using Routing

The `routing/this`, `routing/parent`, and `routing/target` hashes enable powerful event correlation:

```yaml
# Track all events from a specific process
detect:
  op: is
  path: routing/this
  value: "a443f9c48bef700740ef27e062c333c6"
```

### Relationship to Other Structures

> For a dedicated explanation of the `routing` metadata envelope shared by events and detections, see [The `routing` Section](routing.md).

**Events → Detections**: When a D&R rule matches an event, a Detection is created. The Detection inherits the `routing` object from the triggering event and adds detection-specific metadata.

**Events → Outputs**: Events can be routed to external systems via the "event" output stream. The full event structure (both `routing` and `event`) is sent.

**Events → Audit**: Audit logs track platform actions and have a different structure. See the Output Stream Structures documentation for details.

### Platform-Specific Considerations

#### Windows Events

- Often include nested structures like `event/EVENT/System/EventID` for Windows Event Logs
- Process events include detailed parent information in `event/PARENT`

#### Linux Events

- File paths use forward slashes
- Process events may include user/group information

#### Cloud Adapter Events

- May have custom `event` structures based on the source system
- `routing/event_type` reflects the adapter and event type (e.g., `WEL`, `AdvancedHunting-DeviceEvents`)

### Best Practices

1. **Use routing fields for correlation**: `sid`, `hostname`, `this`, `parent` are consistent across all events
2. **Filter by event_type early**: Most D&R rules should specify `event:` at the top level for performance
3. **Leverage platform and architecture**: Use `routing/plat` and `routing/arch` for OS-specific logic
4. **Understand timestamp format**: `routing/event_time` is Unix milliseconds (not seconds)
5. **Hash consistency**: `routing/this` and `routing/parent` use the same hashing algorithm, enabling cross-event tracking
