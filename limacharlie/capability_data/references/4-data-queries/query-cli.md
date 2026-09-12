# Query with CLI

The command line interface found in the Python CLI/SDK can be invoked like `limacharlie search` once installed (`pip install limacharlie`).

## Context

To streamline day to day usage, the first 3 components of the query are set seperatly and remain between queries.
 These 3 component can be set through the following commands:

1. `set_time` to set the timeframe of the query, like `set_time -3h` based on the [ParseDuration()](https://pkg.go.dev/time#ParseDuration) strings.
2. `set_sensors` to set the sensors who's data is queried, like `set_sensors plat == windows`, based on the [sensor selector](../8-reference/sensor-selector-expressions.md) grammar.
3. `set_events` to set the events that should be queried, space separated like `NEW_PROCESS DNS_REQUEST`. This command supports tab completion.

Once set, you can specify the last component(s): the Filter, and the Projection.

Several other commands are avaible to make your job easier:

- `set_limit_event` to set a maximum number of events to scan during the query.
- `set_output` to mirror the queries and their results to a file.
- `set_format` to display results either in `json` or `table`.
- `stats` to display the total costs incurred from the queries during this session.

## Querying

### Paged Mode

The main method of running a query as described above (in paged mode) is to use the `q` (for "query") command.

Paged mode means that an initial subset of the results will be returned (usually in the 1000s of elements) and if you want to fetch more of the results, you can use the `n` (for "next") command to fetch the next page.

Some queries cannot be done in paged mode, like queries that do aggregation or queries that use a stateful filter (like `with child`). In those cases, all results over the entire timeline are computed.

For example:
`q event/DOMAIN_NAME contains 'google' | event/DOMAIN_NAME as domain COUNT_UNIQUE(routing/sid) as count GROUP BY(domain)`

This command supports tab completion for elements of the query, like `event/DO` + "tab" will suggest `event/DOMAIN_NAME` or other relevant elements that exist as part of the schema.

### Non Paged Mode

You can also force a full query over all the data (no paging) by using the "query all" (`qa`) command like:

`qa event/DOMAIN_NAME contains 'google' | event/DOMAIN_NAME as domain COUNT_UNIQUE(routing/sid) as count GROUP BY(domain)`

### Dry Run

To simulate running a query, use the `dryrun` command. This will query the LimaCharlie API and return to you an aproximate worst case cost for the query (assuming you fetch all pages over its entire time range).

For example:
`dryrun event/COMMAND_LINE contains "powershell" and event/FILE_PATH not contains "powershell"`
