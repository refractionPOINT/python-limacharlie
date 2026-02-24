# LimaCharlie Python SDK & CLI Documentation

## Getting Started

- [Installation, Quick Start & First Steps](getting-started.md)
- [Authentication](authentication.md) — API keys, OAuth, environments, credential resolution

## CLI Reference

- [CLI Overview](cli/README.md) — Command pattern, global options, output formats, filtering, discovery

| Guide | Commands |
|---|---|
| [Sensor Management](cli/sensor-management.md) | sensor, tag, endpoint-policy, task, download, installation-key |
| [Detection & Response](cli/detection-response.md) | dr, fp, replay, detection, ai |
| [Data & Query](cli/data-query.md) | search, ioc, event, stream |
| [Platform Administration](cli/platform-admin.md) | org, user, group, api-key, ingestion-key, billing, audit |
| [Hive & Data Stores](cli/hive-data.md) | hive, secret, lookup, playbook, note, sop, adapter, cloud-sensor, extension |
| [Infrastructure](cli/infrastructure.md) | sync, output, artifact, payload, yara, integrity, logging, exfil |
| [Other Commands](cli/other-commands.md) | api, arl, usp, spotcheck, job, schema, completion, help/discover |

## SDK Reference

- [SDK Overview](sdk/README.md) — Architecture, setup, class reference

| Guide | Classes |
|---|---|
| [Organization](sdk/organization.md) | Organization |
| [Sensors](sdk/sensors.md) | Sensor, listing, events |
| [Detection Rules](sdk/detection-rules.md) | DRRules, FPRules, Replay |
| [Hive](sdk/hive.md) | Hive, HiveRecord, transactions |
| [Search & Insight](sdk/search-insight.md) | Search (LCQL), Insight (IOC) |
| [Streaming](sdk/streaming.md) | Spout, Firehose |
| [Configuration Sync](sdk/configs.md) | Configs (IaC) |
| [Other Classes](sdk/other-classes.md) | Extensions, Artifacts, Payloads, Outputs, AI, Billing, etc. |

## External Resources

- [LimaCharlie Platform Documentation](https://doc.limacharlie.io/)
- [REST API Reference](https://api.limacharlie.io)
- [GitHub Repository](https://github.com/refractionPOINT/python-limacharlie)
