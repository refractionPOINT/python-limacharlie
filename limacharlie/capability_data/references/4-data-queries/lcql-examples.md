# LCQL Examples

LimaCharlie Query Language (LCQL) lets you write well-structured queries to search across telemetry within LimaCharlie. The following examples can help you perform targeted searches or hunts across your telemetry, as well as modify them to build your own. Example queries are sorted by *source*, however can be adjusted for your environment.

Got a Unique Query?

If you've written a unique query or have one you'd like to share with the community, please join us in the [LimaCharlie Community](https://community.limacharlie.com/)!

## Time Range

Every LCQL query is scoped to a time range. Where that range comes from depends on the interface you use:

| Interface | How the time range is set |
|-----------|---------------------------|
| Replay API and raw LCQL query strings | The **first component of the query string**, before the first `\|` (for example `-24h \| ...`). |
| Query Console (web UI) | The **time picker** above the query editor, not the query text. |
| Search API | The **`startTime` and `endTime`** body parameters, in Unix epoch seconds. |
| CLI (`limacharlie search run`) | The **`--start` and `--end`** flags, in Unix epoch seconds. |

!!! note
    In the Search API, the CLI, and the Query Console, the explicit range (the picker, `startTime` / `endTime`, or `--start` / `--end`) always wins: any time prefix written into the query string is stripped and replaced. The examples on this page include the leading time component (`-24h |`) because they are written as raw LCQL, where the time range is the first component of the query string.

### Time Formats in the Query String

When the time range is part of the query (raw LCQL and the Replay API), the first component accepts relative durations, absolute date/times, or a bounded range.

**Relative durations** count backwards from now using Go [duration syntax](https://pkg.go.dev/time#ParseDuration). The units are `h`, `m`, and `s`; there is no day or week unit, so express longer windows in hours (`-168h` is 7 days).

| Value | Meaning |
|-------|---------|
| `-24h` | Last 24 hours |
| `-90m` | Last 90 minutes |
| `-1h30m` | Last 1 hour and 30 minutes |

**Absolute date/times** accept common formats such as `2025-01-16 08:52:54` or `2025-01-16`. When you need precise control, include a timezone offset (for example a trailing `Z` or `+02:00`); a time given without one is interpreted as UTC.

**Bounded ranges** join two values with `to`. Each side may be relative or absolute, and the two can be mixed. A single value with no `to` means "from that time until now".

```lcql
-24h to -12h | plat == windows | NEW_PROCESS | event/FILE_PATH ends with ".exe"
```

## General Queries

Search *all* event types across *all* Windows systems for a particular string showing up in *any* field. The `event/*` selector is a subtree wildcard: it tests the value against every field in the event.

```lcql
-24h | plat == windows | * | event/* contains 'psexec'
```

!!! warning "`event/*` is powerful but slow"
    A subtree wildcard has to test every field of every event, and pairing it with the `*` event-type selector scans every event type - the most expensive shape of query. Use it for broad, exploratory hunts, then narrow to a specific event type and field (for example `NEW_PROCESS | event/COMMAND_LINE contains 'psexec'`) once you know where the value lives. See [Query Limits & Performance](query-limits-and-performance.md#writing-efficient-and-performant-queries).

You can also scope the wildcard to a specific *subtree* instead of the whole event, which is far cheaper than `event/*`. Windows Event Log records nest many fields under `event/EVENT/EventData`; this matches a username in any of those fields without touching the rest of the event:

```lcql
-24h | plat == windows | WEL | event/EVENT/EventData/* contains "administrator"
```

## GitHub Telemetry

GitHub logs can be an excellent source of telemetry to identify potential repository or account abuse or misuse. When ingested properly, GitHub log data can be observed via `plat == github`.

### GitHub Protected Branch Override

Show me all the GitHub branch protection override (force pushing to repo without all approvals) in the past 12h that came from a user outside the United States, with the repo, user and number of infractions.

```lcql
-12h | plat == github | protected_branch.policy_override | event/public_repo is false and event/actor_location/country_code is not "us" | event/repo as repo event/actor as actor COUNT(event) as count GROUP BY(repo actor)
```

which could result in:

| actor    |   count | repo                               |
|----------|---------|------------------------------------|
| alice    |      11 | example-org/frontend               |
| bob      |      11 | example-org/analytics              |
| carol    |       3 | example-org/devops                 |

## Network Telemetry

Network details recorded on endpoints, such as new connections or DNS requests, allow for combined insight. We can also query this data for aggregate details, and display data in an easily-consumed manner.

### Domain Count

Show me all domains resolved by Windows hosts that contain "google" in the last 10 minutes and the number of times each was resolved.

```lcql
-10m | plat == windows | DNS_REQUEST | event/DOMAIN_NAME contains 'google' | event/DOMAIN_NAME as domain COUNT(event) as count GROUP BY(domain)
```

which could result in:

|   count | domain                     |
|---------|----------------------------|
|      14 | logging.googleapis.com     |
|      36 | logging-alv.googleapis.com |

### Domain Prevalence

Show me all domains resolved by Windows hosts that contain "google" in the last 10 minutes and the number of unique Sensors that have resolved them.

```lcql
-10m | plat == windows | DNS_REQUEST | event/DOMAIN_NAME contains 'google' | event/DOMAIN_NAME as domain COUNT_UNIQUE(routing/sid) as count GROUP BY(domain)
```

which could result in:

|   count | domain                     |
|---------|----------------------------|
|       4 | logging.googleapis.com     |
|       3 | logging-alv.googleapis.com |

## Process Activity

### Unsigned Binaries

Grouped and counted.

```lcql
-24h | plat == windows | CODE_IDENTITY | event/SIGNATURE/FILE_IS_SIGNED != 1 | event/FILE_PATH as Path event/HASH as Hash event/ORIGINAL_FILE_NAME as OriginalFileName COUNT(event) as Count GROUP BY(Path Hash OriginalFileName)
```

### Process Command Line Args

```lcql
-1h | plat == windows | NEW_PROCESS EXISTING_PROCESS | event/COMMAND_LINE contains "psexec" | event/FILE_PATH as path event/COMMAND_LINE as cli routing/hostname as host
```

### Stack Children by Parent

```lcql
-12h | plat == windows | NEW_PROCESS | event/PARENT/FILE_PATH contains "cmd.exe" | event/PARENT/FILE_PATH as parent event/FILE_PATH as child COUNT_UNIQUE(event) as count GROUP BY(parent child)
```

## Windows Event Log (WEL)

When ingested with EDR telemetry, or as a separate Adapter, `WEL` type events are easily searchable via LimaCharlie. Sample queries are organized alphabetically, with threat/technique details provided where applicable.

### %COMSPEC% in Service Path

```lcql
-12h | plat == windows | WEL | event/EVENT/System/EventID == "7045" and event/EVENT/EventData/ImagePath contains "COMSPEC" | event/EVENT/EventData/ImagePath as ImagePath routing/hostname as Host
```

### Overpass-the-Hash

```lcql
-12h | plat == windows | WEL | event/EVENT/System/EventID == "4624" and event/EVENT/EventData/LogonType == "9" and event/EVENT/EventData/AuthenticationPackageName == "Negotiate" and event/EVENT/EventData/LogonProcess == "seclogo" | event/EVENT/EventData/TargetUserName as User event/EVENT/EventData/IpAddress as SrcIP routing/hostname as Host
```

### Taskkill from a Non-System Account

#### Requires process auditing to be enabled

```lcql
-12h | plat == windows | WEL | event/EVENT/System/EventID == "4688" and event/EVENT/EventData/NewProcessName contains "taskkill" and event/EVENT/EventData/SubjectUserName not ends with "!" | event/EVENT/EventData/NewProcessName as Process event/EVENT/EventData/SubjectUserName as User routing/hostname as Host
```

### Logons by Specific LogonType

```lcql
-24h | plat == windows | WEL | event/EVENT/System/EventID == "4624" AND event/EVENT/EventData/LogonType == "10" | event/EVENT/EventData/TargetUserName as User event/EVENT/EventData/IpAddress as SrcIP routing/hostname as Host
```

### Stack/Count All LogonTypes by User

```lcql
-24h | plat == windows | WEL | event/EVENT/System/EventID == "4624" | event/EVENT/EventData/LogonType AS LogonType event/EVENT/EventData/TargetUserName as UserName COUNT_UNIQUE(event) as Count GROUP BY(UserName LogonType)
```

### Failed Logons

```lcql
-1h | plat == windows | WEL | event/EVENT/System/EventID == "4625" | event/EVENT/EventData/IpAddress as SrcIP event/EVENT/EventData/LogonType as LogonType event/EVENT/EventData/TargetUserName as Username event/EVENT/EventData/WorkstationName as SrcHostname
```

---

## Common Operators and Patterns

The filter (the clause before the projection) is a full detection-style expression. These snippets show the operators and patterns you will use most often; combine them with the projection, aggregation, sorting, and limiting clauses shown elsewhere on this page. For the broad `event/*` subtree wildcard, see [General Queries](#general-queries) above.

### String matching

Double-quoted values are case-insensitive; single-quoted values are case-sensitive.

- Contains (case-insensitive): `event/FILE_PATH contains "temp"`
- Contains (case-sensitive): `event/FILE_PATH contains 'Temp'`
- Prefix / suffix: `event/FILE_PATH starts with "c:\\windows"` and `event/FILE_PATH ends with ".exe"`
- Regular expression: `event/COMMAND_LINE matches "(?i)invoke-\\w+"`
- Negation: `event/FILE_PATH not contains "system32"`

Combined example - executables launched from outside `system32`:

```lcql
-1h | plat == windows | NEW_PROCESS | event/FILE_PATH ends with ".exe" and event/FILE_PATH not contains "system32" | event/FILE_PATH as Path event/COMMAND_LINE as CommandLine routing/hostname as Host
```

### Numeric comparison

Use `>` / `<` (or the words `is greater than` / `is lower than`):

```lcql
-1h | * | NETWORK_CONNECTIONS | event/PORT > 1024
```

### IP address and CIDR

- Match a CIDR range: `event/IP_ADDRESS cidr "10.0.0.0/8"`
- Public vs private address: `event/IP_ADDRESS is public address` (also `is private address`)

Example - outbound connections to public IPs on high ports:

```lcql
-1h | * | NETWORK_CONNECTIONS | event/IP_ADDRESS is public address and event/PORT > 1024 | event/IP_ADDRESS as IP event/PORT as Port routing/hostname as Host
```

### Field existence

`exists` matches events where a field is present, regardless of value:

```lcql
-1h | plat == windows | NEW_PROCESS | event/PARENT/FILE_PATH exists
```

### Boolean logic and grouping

Combine terms with `and`, `or`, and `not`, and use parentheses to control precedence:

```lcql
-1h | plat == windows | NEW_PROCESS | (event/FILE_PATH ends with "cmd.exe" or event/FILE_PATH ends with "powershell.exe") and event/COMMAND_LINE contains "-enc"
```

### Stateful correlation (with child / with descendant / with events)

Stateful operators match an event only when a *related* event also matches a nested filter (given in parentheses after the operator). They scan the whole time range, so scope them tightly (see [Query Types](query-limits-and-performance.md#query-types)).

**`with child`** matches when the event has a **direct child** matching the nested filter. For process events, "child" means a directly-spawned process. This query looks for `cmd.exe` directly spawning `calc.exe`:

```lcql
-6h | plat == windows | NEW_PROCESS | event/FILE_PATH ends with "cmd.exe" with child (event/FILE_PATH ends with "calc.exe")
```

Against the process trees below it matches the first but not the second, because there `calc.exe` is a grandchild, not a direct child:

```text
cmd.exe --> calc.exe                    (match)
cmd.exe --> firefox.exe --> calc.exe    (no match)
```

**`with descendant`** works exactly like `with child` but matches at **any depth** (child, grandchild, and deeper). Swapping the operator makes both trees above match:

```lcql
-6h | plat == windows | NEW_PROCESS | event/FILE_PATH ends with "cmd.exe" with descendant (event/FILE_PATH ends with "calc.exe")
```

**`with events`** correlates **proximal events on the same sensor** that need not be in a parent/child relationship - it simply requires that another event matching the nested filter also occurred. This example flags a host that ran a credential-dumping command line and, separately, a lateral-movement tool:

```lcql
-6h | plat == windows | NEW_PROCESS | event/COMMAND_LINE contains "sekurlsa" with events (event/COMMAND_LINE contains "psexec")
```

!!! tip "Repetition thresholds (count / within)"
    To match *repeated* events - for example 5 failed logons within 60 seconds - use the `count` and `within` modifiers. Those are available in [D&R stateful rules](../3-detection-response/stateful-rules.md) (YAML), which use the same `with child` / `with descendant` / `with events` model and include additional sample data.

### Target specific sensors

The sensor field accepts `*` (whole org), a [Sensor Selector](../8-reference/sensor-selector-expressions.md) expression, or a space-separated list of sensor IDs:

```lcql
-1h | 1a2b3c4d-1111-2222-3333-444455556666 5f6e7d8c-9999-8888-7777-666655554444 | NEW_PROCESS | event/FILE_PATH ends with ".exe"
```

!!! note "Aggregation functions"
    LCQL provides two aggregation functions: `COUNT(...)` (number of matching rows) and `COUNT_UNIQUE(...)` (number of distinct values of a field). There is no `SUM`, `AVG`, `MIN`, or `MAX`.

    - Do not wrap a field in `COUNT_UNIQUE` that is also a `GROUP BY` key - the result is always 1.
    - Avoid `GROUP BY` on high-cardinality fields (for example a full command line, a file hash, or a raw timestamp). It produces a very large number of groups, is inefficient, and rarely yields useful insight - group by a coarser field instead.

---

## Sorting and Limiting Results

The projection clause supports `ORDER BY(...)` for sorting and `LIMIT N` for capping the result set. These are evaluated after aggregation, so they apply to both raw projections and `GROUP BY` summaries.

### ORDER BY Syntax

```text
ORDER BY(<field> [asc|desc])
ORDER BY(<field>)                       # direction omitted; defaults to ascending
```

The parentheses are mandatory - they delimit the operator's arguments inside the space-delimited projection clause. Direction keywords are case-insensitive but the canonical form is lowercase `asc` / `desc`. Sort keys may reference either raw selectors (e.g. `event/PORT`) or projection aliases (e.g. `Port`).

!!! note
    `ORDER BY` currently sorts on a single key. Multi-key sort expressions are not supported by the backend at this time.

### LIMIT Syntax

```text
LIMIT <N>
```

`LIMIT` caps the number of rows returned. It appears at the end of the projection clause, after any `ORDER BY`.

### Top N Noisiest Destination Ports

Sort raw events by a numeric field, no aggregation:

```lcql
-1h | * | NETWORK_CONNECTIONS | event/PORT > 1000 | event/IP_ADDRESS as IP event/PORT as Port ORDER BY(Port desc) LIMIT 100
```

### Top 50 Failed-Logon Source IPs

Sort an aggregated count, descending:

```lcql
-24h | plat == windows | WEL | event/EVENT/System/EventID == "4625" | event/EVENT/EventData/IpAddress as SourceIP COUNT(event) as FailedAttempts GROUP BY(SourceIP) ORDER BY(FailedAttempts desc) LIMIT 50
```

---

## See Also

- [LCQL Overview](index.md)
- [Query Console](query-console-ui.md)
- [Query Limits & Performance](query-limits-and-performance.md)
- [EDR Events](../8-reference/edr-events.md)
