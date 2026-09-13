---
name: search-evidence
description: "Query telemetry and detections, inspect event schemas, run bounded LCQL searches and retrieve IOC evidence."
---

# Search and telemetry evidence

Choose the method before writing a query. Known executable names, file paths, hashes,
domains and IPs belong in indexed IOC search first. Example: `ioc search --type file_name
--value java.exe --info locations --case-insensitive --oid OID --output json`.
For multiple exact values, `ioc batch-search --input-file indicators.json --info locations`
accepts `{"file_name": ["java", "java.exe", "javaw", "javaw.exe"]}`. Inspect its help for
matching semantics; do not assume batch search shares single-search case/wildcard flags.
IOC results identify observed indicators/sensors, not necessarily currently running processes.
Report indexed coverage and location caps; no matches do not exclude renamed or embedded JVMs.
Use endpoint tasking for current state and LCQL for historical predicates, sequences or aggregation
that the index cannot answer. Explain the coverage need before broadening to an expensive scan.

LCQL has sensor, event and predicate stages, e.g. `* | NEW_PROCESS | event/FILE_PATH ends with "java.exe"`.
For syntax/examples use `search run --explain`. Do not invent a query from D&R syntax.

Establish organization, absolute UTC time window, event source and requested output before searching. Compute timestamps with a date library or shell; confirm each API's units. Event timestamps commonly use milliseconds while query parameters commonly use seconds. Treat retention gaps and partial coverage explicitly.

Inspect `event types`, `event schema` or `schema` and a small representative event. Use the documented LCQL syntax; `ai generate-query` can draft it. Run `search validate` and inspect the result before execution, including after every edit. Use server-side time, sensor and field filters and aggregation when the question needs counts. Inspect `search estimate` when available for a broad query; narrow before repeated expensive scans.

Paginate using the returned cursor until absent or the stated budget is reached; a short page is not necessarily final. Record query, window, source IDs, truncation and coverage. Keep bulky events in artifacts and return concise evidence with stable identifiers. Use event ancestry/timeline commands for relationships rather than inventing a parent from similar process names. Bound streaming duration. IOC enrichments are source assertions with timestamps, not proof of compromise.

## References

Read the relevant bundled documentation before using unfamiliar schemas or operations. Paths are relative to the documentation docs root.

- `4-data-queries/query-cli.md`
- `4-data-queries/query-limits-and-performance.md`
- `4-data-queries/lcql-examples.md`
- `8-reference/event-schemas.md`
- `8-reference/authentication-resource-locator.md`
