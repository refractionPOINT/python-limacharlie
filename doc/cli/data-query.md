[Documentation](../README.md) > [CLI](README.md) > Data & Query

# Data & Query

Commands for searching historical telemetry, IOC lookups, event retrieval, and live streaming.

## search

```bash
limacharlie search run --query '* | NEW_PROCESS | event/COMMAND_LINE contains "powershell"' --start 1704067200 --end 1704153600
limacharlie search validate --query '* | NEW_PROCESS | event/COMMAND_LINE contains "powershell"'
limacharlie search estimate --query '* | NEW_PROCESS | event/COMMAND_LINE contains "powershell"' --start 1704067200 --end 1704153600
limacharlie search saved-list                        # Saved queries
limacharlie search saved-create --name my-query --query '* | NEW_PROCESS | event/COMMAND_LINE contains "powershell"'
limacharlie search saved-run --name my-query
limacharlie search queries                           # What this org has open right now
limacharlie search queries --state executing         # Only what is using a concurrency slot
limacharlie search limits                            # This org's resolved search limits
```

`--mode` declares how you intend to consume a search. `interactive` favours time to first results; `batch` favours throughput over the whole result set, which means fewer and larger pages. Both return the same rows in the same order, so only where the page boundaries fall changes.

You rarely need to pass it. The default is `interactive`, and `batch` whenever the run is evidently a bulk retrieval rather than something you are reading: `--checkpoint` or `--resume`, stdout redirected to a file or piped, or `--output jsonl`, `csv` or `toon`. Anything those signals leave ambiguous stays `interactive`, because an over-large page in front of someone waiting at a terminal is worse than a chattier fetch nobody is watching. `--mode` overrides the default in every case.

```bash
limacharlie search run --query '* | * | *' --start 1704067200 --end 1704153600 --mode batch --output jsonl
```

It is a hint. The mode is enabled per organization and the server may also pick one itself, so a search can run as something other than what you asked for. The stats line on stderr reports the mode the page actually ran as, and `--output json` carries it as `searchMode` in each page's stats alongside `pageSize` and `paginatedByteCap`. It also only applies to a paginated search: a query that must process all the data before it can answer anything, such as one with `GROUP BY` or `ORDER BY`, is unaffected.

## ioc

```bash
limacharlie ioc search --type domain --value evil.com
limacharlie ioc search --type ip --value 1.2.3.4
limacharlie ioc search --type file_hash --value abc123...
limacharlie ioc batch-search --input-file iocs.json  # {"domain": ["evil.com"], "ip": ["1.2.3.4"]}
limacharlie ioc hosts --hostname workstation-01       # Find sensors by hostname
limacharlie ioc enrich --type domain --value evil.com # Object enrichment
limacharlie ioc batch-enrich --input-file indicators.json
```

## event

```bash
limacharlie event list --sid SENSOR_ID --start 1704067200 --end 1704153600
limacharlie event list --sid SENSOR_ID --start 1704067200 --end 1704153600 --event-type NEW_PROCESS
limacharlie event get --sid SENSOR_ID --atom ATOM_ID
limacharlie event children --sid SENSOR_ID --atom ATOM_ID
limacharlie event overview --sid SENSOR_ID --start 1704067200 --end 1704153600
```

## stream

```bash
limacharlie stream events --tag vip           # Live event stream
limacharlie stream detections                  # Live detection stream
limacharlie stream audit                       # Live audit log
limacharlie stream firehose                    # All data types
```

## See Also

- [Search & Insight SDK](../sdk/search-insight.md) — LCQL and IOC Python classes
- [Streaming SDK](../sdk/streaming.md) — Spout and Firehose classes
- [Sensor Management](sensor-management.md) — Sensor listing and tasking
