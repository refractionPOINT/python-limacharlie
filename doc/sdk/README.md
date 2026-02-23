[Documentation](../README.md) > SDK Overview

# SDK Overview

The v2 SDK is organized into domain-specific classes under `limacharlie.sdk`. All classes take an `Organization` instance which handles authentication and API routing.

## Architecture

```
Client(oid=..., api_key=...)  →  Organization(client)  →  domain classes
```

- **`Client`** — HTTP layer with JWT auth, retry, and rate limiting. Uses `urllib` (not `requests`).
- **`Organization`** — Main entry point for all org-scoped operations. Passed to domain classes.
- **Domain classes** — One per domain (sensors, rules, hive, search, etc.).

## Basic Setup

```python
from limacharlie.client import Client
from limacharlie.sdk.organization import Organization

# Uses default credentials (~/.limacharlie or env vars)
# Works with both API key and OAuth credentials
client = Client()
org = Organization(client)

# Or with explicit API key
client = Client(oid="your-org-id", api_key="your-api-key")
org = Organization(client)

# With a pre-generated JWT
client = Client(oid="your-org-id", jwt="your-jwt-token")
org = Organization(client)
```

## Class Reference

| Class | Import | Description |
|---|---|---|
| `Client` | `limacharlie.client` | HTTP client with JWT auth, retry, rate limiting |
| `Organization` | `limacharlie.sdk.organization` | Org-level operations (sensors, rules, users, etc.) |
| `Sensor` | `limacharlie.sdk.sensor` | Single sensor: tasking, tagging, events, isolation |
| `DRRules` | `limacharlie.sdk.dr_rules` | Detection & Response rules |
| `FPRules` | `limacharlie.sdk.fp_rules` | False positive rules |
| `Hive` / `HiveRecord` | `limacharlie.sdk.hive` | Key-value store with etag transactions |
| `Search` | `limacharlie.sdk.search` | LCQL query execution |
| `Insight` | `limacharlie.sdk.insight` | IOC search and enrichment |
| `Spout` | `limacharlie.sdk.spout` | Live event/detection streaming |
| `Firehose` | `limacharlie.sdk.firehose` | High-volume data streaming |
| `Replay` | `limacharlie.sdk.replay` | Rule testing against historical/sample data |
| `Extensions` | `limacharlie.sdk.extensions` | Extension management and requests |
| `Artifacts` | `limacharlie.sdk.artifacts` | Artifact upload, download, listing |
| `Payloads` | `limacharlie.sdk.payloads` | Executable/script deployment |
| `downloads` | `limacharlie.sdk.downloads` | Sensor installer & adapter binary downloads |
| `Outputs` | `limacharlie.sdk.outputs` | Data routing outputs |
| `Configs` | `limacharlie.sdk.configs` | Infrastructure-as-code sync (via ext-infrastructure) |
| `Users` | `limacharlie.sdk.users` | User management |
| `Investigations` | `limacharlie.sdk.investigations` | Investigation tracking |
| `AI` | `limacharlie.sdk.ai` | AI-assisted rule/query generation |
| `Billing` | `limacharlie.sdk.billing` | Billing and usage details |

## Detailed Guides

| Guide | Topics |
|---|---|
| [Organization](organization.md) | Org info, stats, config, MITRE |
| [Sensors](sensors.md) | Listing, tasking, tagging, events, isolation |
| [Detection Rules](detection-rules.md) | DRRules, FPRules, Replay |
| [Hive](hive.md) | Key-value store, transactions |
| [Search & Insight](search-insight.md) | LCQL queries, IOC search, enrichment |
| [Streaming](streaming.md) | Spout, Firehose |
| [Configuration Sync](configs.md) | Infrastructure-as-code |
| [Other Classes](other-classes.md) | Extensions, Artifacts, Payloads, Outputs, AI, Billing |

## See Also

- [Authentication](../authentication.md) — Credential setup and resolution order
- [CLI Overview](../cli/README.md) — Using the command-line interface
