# Query Limits & Performance

This page describes the operational limits that apply to Query Console and LCQL searches - how many queries you can run at once and how long a query may run - along with guidance on how large an aggregation can reasonably get and how to write efficient queries that stay within those limits and cost less. It also covers the different query types, since how a query executes determines how it behaves against these limits.

## Query Types

How a query executes - and therefore how it behaves against the limits below - depends on what it does. LCQL queries fall into four kinds:

| Query type | What it does | Execution |
|------------|--------------|-----------|
| **Stateless** | Evaluates each event independently against the filter and returns the matching events. This is the default. | Paged: results come back a page at a time, and you fetch more on demand. |
| **Projection** | Adds a projection clause at the end of the query to return only selected or renamed fields instead of whole events. | Paged, as long as it only selects or renames fields; `GROUP BY`, `ORDER BY`, or an aggregation function make it whole-timeline. |
| **Aggregation** | Uses aggregation functions in the projection (`COUNT`, `COUNT_UNIQUE`, `GROUP BY`, and similar) to summarize matching events. | Whole timeline: the entire selected time range is scanned before any result is returned. |
| **Stateful** | Uses a filter that correlates across events, such as `with child`, so a match depends on more than one event. | Whole timeline: the entire selected time range is scanned before any result is returned. |

**Paged** queries (a stateless filter, or a projection that only selects fields) stream results incrementally and rarely run long. **Whole-timeline** queries (anything that sorts, groups, aggregates, or correlates across events) must scan the full range before returning, so they consume the most resources and are the ones that can reach the [query timeout](#query-timeouts).

## Data Sources (Streams)

Every query runs against one data *stream*, chosen with the Source dropdown in the Query Console or the `stream` parameter in the API, CLI, and SDKs. The stream determines which kind of records the query scans:

| Stream | Console label | Contains |
|--------|---------------|----------|
| `event` | Events | Raw telemetry collected from endpoints, adapters, and other sensors. This is the default. |
| `detection` | Detections | Detections produced by your D&R rules. |
| `audit` | Platform Audit | Platform audit records, such as configuration changes and user actions. |

A query only sees data from the stream it targets - a query on the `event` stream will not match detections, and vice versa. When the `stream` parameter is omitted it defaults to `event`. If a query returns nothing you expected to see, confirm you are searching the intended stream.

## Concurrent Queries

Each organization can run several queries at the same time. Every organization is guaranteed a minimum of **10 concurrent queries**, and the effective limit may be higher depending on your region and plan.

Both interactive Query Console searches and searches issued through the API, CLI, or SDKs count toward this limit. A paginated query counts as active for the entire time it is fetching pages, not only at the moment it starts.

When the limit is reached, additional queries are rejected with an `HTTP 429` (too many concurrent queries) response until one of the in-flight queries finishes. Retry the rejected query once an earlier one completes.

!!! tip
    If you regularly run automation or dashboards that need more headroom, contact support to request a higher concurrent-query limit for your organization.

### Seeing What Is Using Your Limit

When queries start being rejected, the question is which ones are responsible. `GET /v1/search/{oid}/queries` lists the queries your organization currently has open, and reports how many of them are consuming the limit.

Those are two different numbers, and the response reports them separately:

- **`slotsHeld`** is how many queries are consuming concurrency right now. This is what the limit applies to.
- **`count`** is how many queries are open in total, including ones that are paused between pages.

A paginated query is open from the moment it is submitted until it finishes, is cancelled, or its state expires - but it only consumes a slot while a page is actually running. A client that fetched a page and has not asked for the next one holds no slot, so an organization can legitimately have many queries open while few of them count against the limit.

Every entry says which case it falls into:

| `state` | Consumes a slot | Meaning |
|---------|-----------------|---------|
| `executing` | Yes | A page of this query is running. |
| `queued` | Yes | A slot is held but the work has not started yet. Many of these at once indicates a backlog. |
| `idle` | No | The query is open and can be resumed, but nothing is running. |
| `unknown` | Not reported | Per-query slot tracking is not available in this deployment. |

Each entry also carries the query text and time range as submitted, who submitted it and from which client (`submittedBy`, `userAgent`), how long the current page has been running (`runningForMs`), how far along it is (`batchesCompleted` / `batchesInScope` and `progressPercent`), how much it has scanned and been billed for (`eventsScanned`, `billedEvents`), and two separate expiries: `slotExpiresAt` for the concurrency slot, and `resumableUntil` for how long the query can still be resumed.

The `?state=` parameter accepts `all` (the default), `executing` for only what is consuming the limit, and `idle` for what is open but consuming nothing. Page with `?limit=` (default 50, maximum 200) and `?offset=`.

!!! info "Prerequisites"
    This endpoint requires an API key with the `insight.evt.get` permission. See [API Keys](../7-administration/access/api-keys.md) for setup. The REST examples use `$LC_JWT` for your JWT and `$SEARCH_HOST` for your organization's search endpoint; see [Search API Endpoint](index.md#search-api-endpoint) for how to discover the host once and reuse it.

=== "CLI"

    ```bash
    limacharlie search queries                    # Everything this org has open
    limacharlie search queries --state executing  # Only what is using a slot
    ```

=== "Python SDK"

    ```python
    --8<-- "snippets/python/open_queries.py"
    ```

=== "Go SDK"

    ```go
    --8<-- "snippets/golang/open_queries/main.go"
    ```

=== "REST"

    ```bash
    # Who is using the limit right now, worst offender first.
    curl -s "https://$SEARCH_HOST/v1/search/YOUR_OID/queries?state=executing" \
      -H "Authorization: Bearer $LC_JWT" \
      | jq '{slots: .slotsHeld, limit: .limit, open: .count,
             queries: [.queries[] | {queryId, submittedBy, runningForMs,
                                     progressPercent, eventsScanned, query}]
                      | sort_by(-.eventsScanned)}'
    ```

The CLI prints the two numbers first and then one row per open query, which is enough to tell at a glance whether the limit is genuinely saturated or merely has queries parked against it:

```text
1 of 10 concurrency slots in use; 2 search(es) open.
queryId                               state      slot    progress      pages  scanned      running    submittedBy
------------------------------------  ---------  ------  ----------  -------  -----------  ---------  -------------------
9f1c0a7e-3d51-4c8a-9f2b-7d6e5a4b3c21  executing  yes     37%               4  184,320,000  26s        analyst@example.com
2b4d6f80-11ac-4e39-8a55-c0de1f2a3b44  idle       no                        2  41,200,000              dashboard-key
(1 more field hidden, use -W to show all or --output json for full data)
```

A representative response, with one query running and one parked between pages:

```json
{
  "oid": "YOUR_OID",
  "limit": 10,
  "slotsHeld": 1,
  "count": 2,
  "truncated": false,
  "queries": [
    {
      "queryId": "9f1c0a7e-3d51-4c8a-9f2b-7d6e5a4b3c21",
      "state": "executing",
      "holdsSlot": true,
      "page": "b7c19f42",
      "query": "-24h | * | NEW_PROCESS | event/FILE_PATH contains 'powershell'",
      "stream": "event",
      "startTime": "1753500000",
      "endTime": "1753586400",
      "submittedBy": "analyst@example.com",
      "userAgent": "limacharlie-python/5.5.1",
      "submittedAt": "2026-07-26T18:31:04Z",
      "startedAt": "2026-07-26T18:33:12Z",
      "runningForMs": 26400,
      "lastActivityAt": "2026-07-26T18:33:10Z",
      "pagesCompleted": 4,
      "hasMorePages": true,
      "batchesCompleted": 740,
      "batchesInScope": 2000,
      "progressPercent": 37,
      "eventsScanned": 184320000,
      "billedEvents": 184320000,
      "slotExpiresAt": "2026-07-26T18:38:12Z",
      "resumableUntil": "2026-07-27T18:31:04Z"
    },
    {
      "queryId": "2b4d6f80-11ac-4e39-8a55-c0de1f2a3b44",
      "state": "idle",
      "holdsSlot": false,
      "query": "-7d | plat == windows | WEL | event/EVENT/System/EventID == '4625'",
      "stream": "event",
      "startTime": "1752981600",
      "endTime": "1753586400",
      "submittedBy": "dashboard-key",
      "userAgent": "curl/8.5.0",
      "submittedAt": "2026-07-26T17:02:41Z",
      "lastActivityAt": "2026-07-26T17:04:55Z",
      "pagesCompleted": 2,
      "batchesCompleted": 120,
      "batchesInScope": 0,
      "eventsScanned": 41200000,
      "billedEvents": 39900000,
      "resumableUntil": "2026-07-27T17:02:41Z"
    }
  ]
}
```

Two queries are open, but only the executing one holds a slot - which is why `slotsHeld` is `1` while `count` is `2`. The envelope also carries `limit` (your organization's concurrent-query limit) and `truncated`. `truncated` is computed against the unfiltered listing, so a request filtered to `idle` can legitimately report `true` alongside an empty `queries` array.

What each query entry means:

| Field | Meaning |
| --- | --- |
| `queryId` | Identifier of the query. This is what you pass to the cancel endpoint below. |
| `state` | `executing`, `queued`, `idle` or `unknown`, as described in the table above. |
| `holdsSlot` | Whether this query is counted against the concurrency limit. It is `null` **only** when `state` is `unknown`, which means slot tracking is unavailable rather than that the query holds no slot. An `idle` query is always `false`. |
| `page` | Which page holds the slot, for a paginated query past its first. A digest of the continuation token, never the token itself. |
| `query`, `stream`, `startTime`, `endTime` | Echoed back as submitted, and absent once the query's record has expired. A long query is shortened by the server and marked with a trailing `...`. |
| `submittedBy`, `userAgent` | The authenticated identity that submitted the query, and the client it arrived from. |
| `submittedAt`, `startedAt`, `lastActivityAt` | When the query was submitted, when the current page started (absent when nothing is running), and when the server last finished producing a page. `lastActivityAt` is absent until one has completed, and polling for results does not move it. |
| `runningForMs` | How long the current page has been running. Absent when nothing is running, so an idle query has no value here. |
| `pagesCompleted` | Pages successfully produced, not pages a client collected. A failed page is not counted, and a page still executing counts only once it completes. |
| `hasMorePages` | Whether more pages remain. **Absent until a page has completed**, because that is when the answer is known - absent means "not yet determined", not "no more pages". |
| `batchesCompleted`, `batchesInScope` | The progress pair, both advancing at page boundaries. **`batchesInScope` of `0` means the scope estimate was unavailable**, so progress cannot be computed - it does not mean no work has been done. |
| `progressPercent` | The pair above as a percentage, clamped to 0-100. Absent when there is no denominator to divide by. |
| `eventsScanned`, `billedEvents` | The total scanned so far and the charged portion of it, both cumulative across pages. In practice the most actionable pair: the query worth cancelling is usually the one that has scanned the most. |
| `slotExpiresAt` | When the concurrency slot is reclaimed if the query neither finishes nor is cancelled. Absent when no slot is held. |
| `resumableUntil` | When the query's state expires and it can no longer be resumed. Unrelated to `slotExpiresAt`, which is why they are separate fields. |

To free a slot, cancel the query with `DELETE /v1/search/{queryId}`, using the `queryId` from the listing. Cancelling is available through the REST API only; there is no CLI command for it.

```bash
curl -s -X DELETE "https://$SEARCH_HOST/v1/search/$QUERY_ID" \
  -H "Authorization: Bearer $LC_JWT"
```

!!! note
    `progressPercent` advances at page boundaries, so a query that returns everything in one response - any aggregation, which does not paginate - reports `0` for its whole life and then leaves the listing. It is absent entirely when the scope estimate was unavailable, which means progress cannot be computed rather than that no work has been done.

## Reading Your Limits Directly

Rather than discovering a limit by hitting it, ask for it. `GET /v1/search/{oid}/limits` reports the limits actually in effect for your organization: how many queries may run at once, the shape of a page, how long results stay resumable, and any enforced execution deadlines.

!!! info "Prerequisites"
    This endpoint requires an API key with the `insight.evt.get` permission. See [API Keys](../7-administration/access/api-keys.md) for setup. The REST example uses `$LC_JWT` for your JWT and `$SEARCH_HOST` for your organization's search endpoint; see [Search API Endpoint](index.md#search-api-endpoint) for how to discover the host once and reuse it.

=== "CLI"

    ```bash
    limacharlie search limits
    ```

=== "Python SDK"

    ```python
    --8<-- "snippets/python/search_limits.py"
    ```

=== "Go SDK"

    ```go
    --8<-- "snippets/golang/search_limits/main.go"
    ```

=== "REST"

    ```bash
    curl -s "https://$SEARCH_HOST/v1/search/YOUR_OID/limits" \
      -H "Authorization: Bearer $LC_JWT"
    ```

A representative response:

```json
{
  "oid": "YOUR_OID",
  "concurrency": { "maxConcurrentQueries": 10 },
  "pagination": {
    "resultsPerPage": 200,
    "maxPageDurationSeconds": 30,
    "maxCursorBytes": 4096
  },
  "retention": {
    "resumableForSeconds": 86400,
    "pageResultsForSeconds": 900
  },
  "execution": {
    "maxQueryDurationSeconds": 480,
    "maxAggregationDurationSeconds": 540,
    "maxResponseBytes": null
  },
  "request": { "maxRequestBodyBytes": 102400 },
  "capabilities": { "openQueryListing": true }
}
```

What the groups mean:

| Field | Meaning |
| --- | --- |
| `concurrency.maxConcurrentQueries` | How many queries may be **executing** at once. A paginated query parked between pages consumes nothing, so this is not a cap on how many you may have open. |
| `pagination.resultsPerPage` | Events returned per page before you get a continuation token. |
| `pagination.maxPageDurationSeconds` | How long the server spends on one page before returning what it has plus a token. Reaching it is normal for a broad query and does not mean the query failed. |
| `pagination.maxCursorBytes` | The largest continuation token the server accepts back when you ask for the next page. |
| `retention.resumableForSeconds` | How long a query can be resumed for, measured from when it was submitted and never extended by activity. Leave a paginated query paused longer than this and it cannot be continued. |
| `retention.pageResultsForSeconds` | How long a page's results are kept. Can be shorter than the above, in which case re-reading an older page recomputes it rather than failing - a latency characteristic, not a deadline. |
| `execution.maxQueryDurationSeconds` | The deadline for a non-aggregation query. |
| `execution.maxAggregationDurationSeconds` | The deadline for an aggregation, which gets its own budget because it cannot return partial pages. |
| `execution.maxResponseBytes` | The ceiling on a single response's accumulated size. The `null` above is the common case and means no ceiling is enforced, as described in the warning below. |
| `request.maxRequestBodyBytes` | The largest request body accepted, which in practice bounds query length and how many sensors you may name. |
| `capabilities.openQueryListing` | Whether the open-query listing above can report queries that are open but idle on your deployment. |

!!! warning "`null` means unlimited, not zero"
    A limit that is not enforced is reported as `null`, never `0`. In a document of limits a zero would read as "nothing allowed", which is the opposite. Treat `null` as "no limit applies", and treat a field you do not recognise as not applicable rather than as zero - the response is additive and gains fields over time.

## Query Timeouts

A single query has a maximum execution time of roughly **8 to 9 minutes**. If a query exceeds this deadline it returns an error rather than partial results.

**Paged queries (a stateless filter or a field-only projection).** Each page fetches a bounded number of events and returns quickly, so paged queries should effectively never reach the timeout. When you need more results, fetch the next page rather than trying to widen a single request.

**Whole-timeline queries (sorting, aggregation, and stateful).** Sorting (`ORDER BY`), aggregations (`COUNT`, `COUNT_UNIQUE`, `GROUP BY`), and stateful filters (such as `with child`) must scan the entire selected time range before they can return results, because the outcome is only complete once every matching event has been evaluated. Over a very large time range or a high volume of data, the scan can exceed the timeout and the query returns an error. See [Query Types](#query-types) for the distinction.

!!! note "Working around whole-timeline timeouts"
    If a large aggregation times out, narrow the time range and split the work into several smaller queries that each cover an incremental slice of the range, then combine the results yourself.

    For example, instead of a single 24-hour aggregation, run the same aggregation over 24 consecutive one-hour windows and add the per-window counts together for the full-range total. Keep the query identical and only change the time range for each run:

    ```lcql
    plat == windows | WEL | event/EVENT/System/EventID == "4625" | COUNT(event) as FailedAttempts
    ```

    Each one-hour window stays well under the timeout. Set the time range per run using the Console time picker (absolute from/to), the CLI `set_time`, or the API `startTime` / `endTime` parameters.

    Splitting and summing works for additive aggregations like `COUNT`; a `COUNT_UNIQUE` result cannot simply be added across windows. For stateful queries (`with child`), narrow the scope instead, since splitting can miss correlations that span a window boundary.

## Aggregation Limits

Aggregations build in-memory groupings as they scan, so very high-cardinality aggregations become slow and unreliable. Treat the following as recommended guardrails for dependable results:

- `GROUP BY` distinct groups: keep well under **~1,000,000** distinct groups.
- `COUNT_UNIQUE` distinct values per field per group: keep well under **~5,000,000** distinct values.

The usual cause of blowing past these numbers is grouping by a near-unique field (see [Anti-patterns](#anti-patterns) below). Group by a coarser field, or narrow the scope, so the number of groups stays bounded.

!!! tip
    Add `ORDER BY(...) LIMIT N` to bound the output, and project only the fields you need to shrink each row. See [Writing Efficient and Performant Queries](#writing-efficient-and-performant-queries) below.

## Query Progress and Cost Reporting

Because a query can scan a large amount of data, the API reports both a pre-flight estimate before you run it and the actual progress and cost as results stream back. A query scans stored telemetry in discrete units called *batches*; the batch counts below are what drive a progress bar.

### Pre-flight estimate (validate)

The [validate endpoint](index.md#validate-query-syntax) returns an estimate of how much work a query represents before you run it:

- `batchesInScope` - the total number of batches the query will scan. This is the denominator for a progress bar.
- `eventsInScope` / `bytesInScope` - the estimated number of events and bytes in scope.
- `estimatedPrice` - the estimated cost, derived from the events in scope.

### Progress while paging

Each page of a running search reports how much of the query is complete so far in its `cumulativeStats`:

- `batchesInScope` - the total batches in scope (denominator); the same value for every page of the search.
- `batchesCompleted` - the batches processed so far across all pages (numerator).

Render progress as `batchesCompleted / batchesInScope`, clamped to 0-100%. This is exactly how the Query Console progress bar is computed. The per-page `batchesProcessed` field reports the batches handled by that single page. Byte- and event-weighted ratios (`bytesScanned / bytesInScope`, `eventsScanned / eventsInScope`) are also available as a smoother signal, but the batch ratio is the reliable one; guard against a zero denominator.

### Actual cost per page

Every page also returns the actual billing for the data it processed, so you do not have to trust the estimate for cost:

- `billedEvents` / `freeEvents` - the events on this page that were billed versus covered by a free-tier window (`billedEvents + freeEvents == eventsScanned`).
- `estimatedPrice` - the price for this page, derived from the actual `billedEvents`. The running totals across all pages are carried in `cumulativeStats`.

!!! warning "Estimates are approximate - rely on the per-page billing for cost"
    The pre-flight `estimatedPrice`, `eventsInScope`, and related validate estimates are approximations. Their accuracy varies with the query type and with internal optimizations that reduce how much data actually has to be scanned, which are not always reflected in the estimate. Treat the estimate as a planning aid only and never rely on it as the exact cost. The authoritative cost is the actual billing (`billedEvents` and the `estimatedPrice` derived from it) returned with each page and accumulated in `cumulativeStats`.

### Building a Progress Bar

The Query Console renders its progress bar with this formula:

```text
progress = clamp(batchesCompleted / batchesInScope, 0, 100%)
```

Use `batchesInScope` as the denominator - from the [validate response](#pre-flight-estimate-validate) before the search starts, or from each page's `cumulativeStats` once it is running - and the per-page `cumulativeStats.batchesCompleted` as the numerator. Two rules keep the bar well-behaved:

- **Guard the denominator.** `batchesInScope` is `0` (or absent) until the scope is known, so treat progress as unavailable rather than dividing by zero.
- **Clamp the ratio.** `batchesCompleted` can briefly exceed `batchesInScope` when a batch is re-opened across page boundaries, so clamp to 100%. A page's `completed` flag is the authoritative "done" signal.

The examples below take one Search API page response (a parsed `SearchResponse`) and return a percentage in the range 0-100.

=== "Python"

    ```python
    --8<-- "snippets/python/progress_bar.py"
    ```

=== "Go"

    ```go
    --8<-- "snippets/golang/progress_bar/main.go"
    ```

=== "Bash (curl + jq)"

    ```bash
    # Denominator only, from the pre-flight validate response (before running):
    curl -s -X POST "https://$SEARCH_HOST/v1/search/validate" \
      -H "Authorization: Bearer $LC_JWT" -H "Content-Type: application/json" \
      -d '{"oid":"YOUR_OID","query":"...","startTime":"'"$START"'","endTime":"'"$END"'"}' \
      | jq '.stats.batchesInScope'

    # Progress from a running search page: clamp batchesCompleted/batchesInScope
    # to 0-100%, and treat a completed page as 100%.
    curl -s -X POST "https://$SEARCH_HOST/v1/search" \
      -H "Authorization: Bearer $LC_JWT" -H "Content-Type: application/json" \
      -d '{"oid":"YOUR_OID","query":"...","startTime":"'"$START"'","endTime":"'"$END"'","stream":"event"}' \
      | jq '
        ([.results[].stats.cumulativeStats | select(. != null)] | first) as $c
        | if .completed then 100
          elif ($c.batchesInScope // 0) > 0
          then ([100 * $c.batchesCompleted / $c.batchesInScope, 100] | min)
          else 0
          end'
    ```

See [Run an LCQL Query](index.md#run-an-lcql-query) for how to discover `$SEARCH_HOST` and obtain a JWT.

## Writing Efficient and Performant Queries

Query cost is measured by the amount of data churned (billed per 200,000 events evaluated), and speed tracks the same factor: the fewer events a query has to scan and the less data it has to return, the faster and cheaper it is. The patterns below reduce both.

### Prefer Projections (Select Only the Fields You Need)

By default a query returns whole events. Adding a projection clause (the segment after the final `|`) returns only the fields you name, which reduces the data transferred, speeds up the query, and lowers cost.

Non-aggregation query. Instead of returning every field of each matching event:

```lcql
-1h | * | NETWORK_CONNECTIONS | event/PORT > 1000
```

project just the two fields you actually care about:

```lcql
-1h | * | NETWORK_CONNECTIONS | event/PORT > 1000 | event/IP_ADDRESS as IP event/PORT as Port
```

Aggregation query. Projections also define what an aggregation emits. This returns only the source IP and its failed-logon count, sorted and capped:

```lcql
-24h | plat == windows | WEL | event/EVENT/System/EventID == "4625" | event/EVENT/EventData/IpAddress as SourceIP COUNT(event) as FailedAttempts GROUP BY(SourceIP) ORDER BY(FailedAttempts desc) LIMIT 50
```

### Narrow the Scope Early

Restrict what the query has to scan before it reaches the filter:

- Use the [Sensor Selector](../8-reference/sensor-selector-expressions.md) instead of `*` so only relevant sensors are searched (see below).
- Set the Event Type to the specific events you need rather than searching all event types.
- Use the tightest time range that answers your question.

Each of these lowers the number of events churned, which makes the query both faster and cheaper.

**Targeting sensors by ID.** When you know exactly which sensors you care about, matching on `sid` is the most efficient selector of all, because it narrows the scan to specific sensors before any events are read:

- A single sensor: `sid == "<sensor-id>"`.
- A specific set of sensors: combine terms with `or`, as in `sid == "<sid1>" or sid == "<sid2>" or sid == "<sid3>"`.

When you do not know the IDs, select by attribute instead - for example `plat == windows`, `"prod" in tags`, or by `hostname`. Sensor IDs are UUIDs, and a selector value that starts with a number must be backtick-quoted; see the [Sensor Selector reference](../8-reference/sensor-selector-expressions.md) for the full operator list and quoting rules.

### Bound Output with ORDER BY and LIMIT

For "top N" style questions, always add `ORDER BY(...) LIMIT N` so the result set is capped instead of returning every matching row. See [Sorting and Limiting Results](lcql-examples.md#sorting-and-limiting-results) for the full syntax.

### Aggregate Instead of Pulling Raw Events

When you only need counts or summaries, use `COUNT`, `COUNT_UNIQUE`, and `GROUP BY` rather than downloading raw events and counting them yourself. Aggregating in the query returns a small summary instead of a large event stream.

### Split Large Aggregations

If an aggregation over a wide time range is slow or times out, break it into smaller incremental time windows and combine the results, as described in [Working around whole-timeline timeouts](#query-timeouts) above.

### Anti-patterns

!!! warning "Avoid these patterns"
    - `*` sensor selector with no Event Type filter over a wide time range - this scans everything and is the slowest, most expensive shape of query.
    - Returning whole events when you only need a few fields - add a projection instead.
    - Grouping by a near-unique field such as a full command line, a raw timestamp, or a per-event identifier - this produces millions of groups and blows past the aggregation guardrails. Group by a coarser field.
    - Unbounded aggregations with no `LIMIT` - cap the output with `ORDER BY(...) LIMIT N`.

## Troubleshooting

### The query is rejected before it runs

[Validate the query](index.md#validate-query-syntax) first - the validate endpoint reports syntax errors without scanning any data. Common causes:

- **Field paths use `/`, not dots.** Write `event/FILE_PATH`, not `event.FILE_PATH`. Nested fields chain with slashes, as in `event/PARENT/FILE_PATH`.
- **A selector value that starts with a number must be backtick-quoted**, for example `` plat == `1password` ``.
- **Projection and aggregation go in the final clause**, after the last `|`. See [LCQL Examples](lcql-examples.md).

### The query returns no results

- **Wrong stream.** A query only sees the stream it targets. If you expected detections, query the `detection` stream rather than `event`. See [Data Sources (Streams)](#data-sources-streams).
- **Time range.** Confirm the range actually covers the data. In the Query Console, times use the timezone from your User Settings; API, CLI, and SDK times are Unix epoch seconds.
- **Selector too narrow.** An overly specific Sensor Selector or Event Type can exclude the data you want - widen it and re-run.
- **Field name.** A misspelled or non-existent field simply never matches. Use the Available Fields panel or the [event schema](../8-reference/event-schemas.md) to confirm field names.

### The query is rejected as too busy or times out

- **`HTTP 429` (too many concurrent queries).** You have reached the [concurrent-query limit](#concurrent-queries). Confirm what that limit actually is with `limacharlie search limits` (see [Reading Your Limits Directly](#reading-your-limits-directly)), then list what is holding the slots with `limacharlie search queries --state executing` (see [Seeing What Is Using Your Limit](#seeing-what-is-using-your-limit)). Cancelling is available through the REST API only - there is no CLI command for it - so free a slot with a `DELETE` against a `queryId` from that listing:

    ```bash
    curl -s -X DELETE "https://$SEARCH_HOST/v1/search/$QUERY_ID" \
      -H "Authorization: Bearer $LC_JWT"
    ```

    If nothing in the listing looks unexpected, nothing needs cancelling: wait for an in-flight query to finish and retry.

- **Timeout.** Long-running aggregations over large ranges can hit the [query timeout](#query-timeouts). Narrow the range or split the query into smaller windows.

### A paginated query cannot be resumed

The continuation token stopped working, or the query disappeared from the open-query listing. A query stays resumable for a fixed window measured from when it was **submitted**, not from its last page, so one left paused long enough expires even if it was producing pages recently. Read the window with `limacharlie search limits` (`retention.resumableForSeconds`) and page through faster than it, or re-run the query.

This is distinct from `retention.pageResultsForSeconds`, which is shorter on some deployments: re-reading a page whose results have aged out recomputes it rather than failing, so that shows up as a slow page, not a broken one.

## See Also

- [LCQL Examples](lcql-examples.md)
- [Query Console UI](query-console-ui.md)
- [Query with CLI](query-cli.md)
