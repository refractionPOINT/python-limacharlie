[Documentation](../README.md) > [SDK](README.md) > Streaming

# Streaming

Classes for real-time data streaming from LimaCharlie.

## Spout

`Spout` provides live streaming of events, detections, or audit logs filtered by tag:

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

## Firehose

`Firehose` provides high-volume streaming of all data types:

```python
from limacharlie.sdk.firehose import Firehose
```

## See Also

- [CLI: stream](../cli/data-query.md#stream) — CLI equivalents
- [Search & Insight](search-insight.md) — Query historical data
- [Sensors](sensors.md) — Per-sensor event retrieval
