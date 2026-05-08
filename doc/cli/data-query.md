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
```

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
