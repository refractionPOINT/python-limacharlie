[Documentation](../README.md) > [SDK](README.md) > Search & Insight

# Search & Insight

Classes for LCQL query execution and IOC search/enrichment.

## Search (LCQL)

```python
from limacharlie.sdk.search import Search

search = Search(org)
results = search.execute("event NEW_PROCESS", start=1704067200, end=1704153600)
```

## Insight (IOC Search & Enrichment)

```python
from limacharlie.sdk.insight import Insight

insight = Insight(org)

# Single IOC search
results = insight.search_ioc("domain", "evil.com")

# Batch search
batch = insight.batch_search({"domain": ["evil.com"], "ip": ["1.2.3.4"]})

# Object enrichment
enrichment = insight.get_object_information("domain", "evil.com")
```

## See Also

- [CLI: search, ioc](../cli/data-query.md) — CLI equivalents
- [Sensors](sensors.md) — Historical events per sensor
- [Streaming](streaming.md) — Live data streaming
