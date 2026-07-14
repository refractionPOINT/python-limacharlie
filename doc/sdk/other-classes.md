[Documentation](../README.md) > [SDK](README.md) > Other Classes

# Other Classes

Additional SDK classes for extensions, artifacts, payloads, outputs, AI, billing, cases, and more.

## Extensions

```python
from limacharlie.sdk.extensions import Extensions

ext = Extensions(org)
subscribed = ext.list_subscribed()
ext.subscribe("my-extension")
result = ext.request("my-extension", "do-action", {"key": "value"})
```

## Artifacts

```python
from limacharlie.sdk.artifacts import Artifacts

artifacts = Artifacts(org, access_token="your-ingestion-key")
artifacts.upload("/path/to/file", source="my-source", retention_days=30)
artifact_list = artifacts.list()
```

## Payloads

```python
from limacharlie.sdk.payloads import Payloads
```

See `limacharlie.sdk.payloads` for upload, download, listing, and deletion.

## Outputs

```python
from limacharlie.sdk.outputs import Outputs
```

Outputs can also be managed directly from the `Organization` class:

```python
outputs = org.get_outputs()
org.add_output("my-output", "syslog", "event", dest_host="1.2.3.4:514")
org.delete_output("my-output")
```

## AI

```python
from limacharlie.sdk.ai import AI
```

AI-assisted generation of rules, queries, selectors, and playbooks.

## Billing

```python
from limacharlie.sdk.billing import Billing
```

Billing status and detailed usage breakdowns.

## Users

```python
from limacharlie.sdk.users import Users
```

User invitation, removal, and permission management.

## Investigations

```python
from limacharlie.sdk.investigations import Investigations
```

Investigation tracking and management.

## Downloads

```python
from limacharlie.sdk.downloads import downloads
```

Sensor installer and adapter binary downloads.

## Cases

```python
from limacharlie.sdk.cases import Cases

cases = Cases(org)

# Create a case (with or without a detection)
cases.create_case(severity="high")
cases.create_case(detection=detection_dict, severity="critical")

# List/filter cases
cases.list_cases(status=["new", "acknowledged"], severity=["high", "critical"])
cases.list_cases(assignee="analyst@company.com", tag=["apt", "ransomware"])
cases.list_cases(sensor_id="sid-1234", search="mimikatz")

# Update case fields (status, severity, assignee, classification, tags, etc.)
cases.update_case(42, status="in_progress", assignee="analyst@company.com")
cases.bulk_update([42, 43, 44], status="resolved", classification="true_positive")
cases.merge(target_case_number=42, source_case_numbers=[43, 44])

# Notes (types: general, analysis, remediation, escalation, handoff, to_stakeholder, from_stakeholder)
cases.add_note(42, "Initial triage complete.", note_type="analysis")

# Entities / IOCs (types: ip, domain, hash, url, user, email, file, process, registry, other)
cases.add_entity(42, "ip", "10.0.0.1", verdict="malicious")
cases.list_entities(42)
cases.search_entities("domain", "evil.com")

# Telemetry links
cases.add_telemetry(42, event_dict, event_summary="Lateral movement observed")
cases.list_telemetry(42)

# Artifacts
cases.add_artifact(42, "memory_dump", description="LSASS dump from host-01")
cases.list_artifacts(42)

# Detections
cases.add_detection(42, detection_dict)
cases.list_detections(42)

# Export (bundles case + detections + entities + telemetry + artifacts)
full_case = cases.export_case(42)

# Dashboard and reporting
cases.dashboard_counts()
cases.report_summary(time_from="2026-01-01T00:00:00Z", time_to="2026-03-01T00:00:00Z")

# Configuration
cases.get_config()
cases.set_config({"auto_acknowledge_minutes": 30})

# Assignees
cases.list_assignees()
```

SOC case lifecycle management, investigation tracking (entities, telemetry, artifacts), reporting with MTTA/MTTR metrics, and configuration.

## CloudSec

```python
from limacharlie.sdk.cloudsec import CloudSec

cs = CloudSec(org)

# Findings worklist + triage
cs.list_findings(severity=["CRITICAL"], status=["open"])
cs.get_finding("fnd_abc")
cs.set_finding_status("fnd_abc", "mitigated", reason="SG tightened")

# Inventory, graph, compliance, overview
cs.list_inventory(provider="gcp", resource_type="Bucket")
cs.run_query(named="public-buckets")
cs.get_compliance(framework="cis-gcp")
cs.get_overview(trend_days=90)

# Multi-org fleet posture (MSSP)
cs.get_fleet_overview(group="my-group-id")

# CSV exports (full filtered set, 100k-row cap)
csv_text = cs.export_findings_csv(severity=["CRITICAL"])

# Providers
cs.test_provider({"provider_type": "gcp", "credentials": "hive://secret/gcp-sa"})
cs.get_provider_manifests(provider_type="gcp")
```

The Cloud Security (CNAPP) surface: findings (CSPM + attack paths + CIEM), resource inventory, security graph queries, compliance, DSPM facets, CAASM ingest/coverage, sensor↔asset resolution, fleet overview, and CSV exports. See [CLI: cloudsec](../cli/cloud-security.md) for the command-line equivalents.

## See Also

- [CLI: case](../cli/other-commands.md#case) — Case CLI commands
- [CLI: extension](../cli/hive-data.md#extension) — Extension CLI commands
- [CLI: artifact, payload, output](../cli/infrastructure.md) — Infrastructure CLI commands
- [Organization](organization.md) — Outputs and rules via Organization class
