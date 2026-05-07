[Documentation](../README.md) > [SDK](README.md) > Sensors

# Sensors

The `Sensor` class provides operations on individual sensors: info, tasking, tagging, network isolation, events, and lifecycle management.

## Setup

```python
from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.sensor import Sensor

client = Client(oid="your-org-id", api_key="your-api-key")
org = Organization(client)
sensor = Sensor(org, "SENSOR-ID-HERE")
```

## Sensor Info

```python
info = sensor.get_info()
is_online = sensor.is_online()
sensor.wait_online(timeout=120)
```

## Listing Sensors

Sensor listing is done through the `Organization` class:

```python
# List all sensors
for sensor_info in org.list_sensors():
    print(sensor_info["hostname"], sensor_info["sid"])

# Filter by tag, hostname, or selector expression
for s in org.list_sensors(selector="`production` in tags", limit=50):
    print(s)
```

## Tasking

```python
sensor.task("os_processes")
sensor.task(["os_processes", "os_services"])
```

## Tags

```python
tags = sensor.get_tags()
sensor.add_tag("suspicious", ttl=600)
sensor.remove_tag("suspicious")
```

## Network Isolation

```python
sensor.isolate()
sensor.rejoin()
```

## Historical Events

```python
for event in sensor.get_events(start=1704067200, end=1704153600, event_type="NEW_PROCESS"):
    print(event)
```

## Lifecycle

```python
sensor.delete()
```

## See Also

- [CLI: sensor, tag, endpoint-policy, task](../cli/sensor-management.md) — CLI equivalents
- [Organization](organization.md) — Sensor listing and org-level operations
- [Streaming](streaming.md) — Live event streaming
