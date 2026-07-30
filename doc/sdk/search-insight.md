[Documentation](../README.md) > [SDK](README.md) > Search & Insight

# Search & Insight

Classes for LCQL query execution and IOC search/enrichment.

## Search (LCQL)

```python
from limacharlie.sdk.search import Search

search = Search(org)
results = search.execute("event NEW_PROCESS", start=1704067200, end=1704153600)
```

### Open queries

`list_open_queries()` reports the searches the organization currently has open, and which of them are consuming its concurrency limit. Those are different numbers: a paginated search sitting between pages is open and resumable but holds no slot, so `slotsHeld` (not `count`) is what the limit applies to.

```python
listing = search.list_open_queries()
print(f"{listing['slotsHeld']} of {listing['limit']} slots in use, {listing['count']} searches open")

# Only what is consuming the limit, which is what to look at after a
# "maximum concurrent queries reached" rejection.
for q in search.iter_open_queries(state="executing"):
    print(q["queryId"], q["submittedBy"], q.get("progressPercent"), q["eventsScanned"])
```

Each entry carries the query text and time range as submitted, who submitted it and from which client, how long the current page has been running, how far along it is, how much it has scanned, and when its slot and its resumability expire. `progressPercent` is absent when the scope estimate was unavailable, which means progress cannot be computed rather than that nothing has been done; it advances at page boundaries, so a search that returns everything in one page reports 0 for its whole life.

### Search limits

`get_limits()` reports the organization's resolved search limits. Every one of these is otherwise discoverable only by hitting it: a refusal for concurrency does not say what the cap was, and a paginated search stops being resumable with no way to have known the window. Read it once and size the client to it.

```python
limits = search.get_limits()

print(limits["concurrency"]["maxConcurrentQueries"])   # how many may run at once
print(limits["retention"]["resumableForSeconds"])      # how long a search may be left paused
print(limits["pagination"]["resultsPerPage"])          # events per page

# A limit that is not enforced is None, never 0 - in a set of limits a zero
# would read as "nothing allowed".
deadline = limits["execution"]["maxQueryDurationSeconds"]
print(f"{deadline}s" if deadline is not None else "no query deadline enforced")

# Whether this deployment can report searches that are open but idle.
if limits["capabilities"]["openQueryListing"]:
    print(search.list_open_queries()["count"], "searches open")
```

`retention.pageResultsForSeconds` can be shorter than `resumableForSeconds`. That is not a shorter deadline: re-reading a page whose results have aged out recomputes it rather than failing, so it is a latency characteristic. Fields are additive - ignore ones you do not recognise, and treat an absent one as "not applicable to this deployment" rather than as zero.

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
