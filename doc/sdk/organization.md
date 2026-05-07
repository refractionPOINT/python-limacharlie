[Documentation](../README.md) > [SDK](README.md) > Organization

# Organization

The `Organization` class is the main entry point for all org-scoped operations. It wraps a `Client` instance and provides methods for org info, stats, configuration, users, rules, and more.

## Setup

```python
from limacharlie.client import Client
from limacharlie.sdk.organization import Organization

client = Client(oid="your-org-id", api_key="your-api-key")
org = Organization(client)
```

## Org Info & Stats

```python
info = org.get_info()              # Name, sensor count, quotas
urls = org.get_urls()              # Service URLs
stats = org.get_stats()            # Usage statistics
errors = org.get_errors()          # Platform errors
mitre = org.get_mitre_report()     # MITRE ATT&CK coverage
```

## Configuration

```python
org.set_config("vt", "my-api-key")
value = org.get_config("vt")
```

## Sensors

Sensor listing is available directly from `Organization`:

```python
for sensor_info in org.list_sensors():
    print(sensor_info["hostname"], sensor_info["sid"])

# Filter by selector expression
for s in org.list_sensors(selector="`production` in tags", limit=50):
    print(s)
```

For single-sensor operations, see [Sensors](sensors.md).

## Rules

Rules can be managed directly from `Organization`:

```python
rules = org.get_rules()
org.add_rule(
    "my-rule",
    detection={"op": "is", "event": "NEW_PROCESS"},
    response=[{"action": "report", "name": "my-detection"}],
)
org.delete_rule("my-rule")
```

For the dedicated helper class, see [Detection Rules](detection-rules.md).

## Detections

```python
for detection in org.get_detections(start=1704067200, end=1704153600):
    print(detection)
```

## Outputs

```python
outputs = org.get_outputs()
org.add_output("my-output", "syslog", "event", dest_host="1.2.3.4:514")
org.delete_output("my-output")
```

## See Also

- [CLI: org command](../cli/platform-admin.md#org) — CLI equivalent
- [Sensors](sensors.md) — Single sensor operations
- [Detection Rules](detection-rules.md) — DRRules helper class
