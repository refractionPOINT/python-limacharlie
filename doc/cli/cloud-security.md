[Documentation](../README.md) > [CLI](README.md) > Cloud Security

# Cloud Security (CNAPP)

Commands for the LimaCharlie Cloud Security surface: the merged, risk-ranked findings worklist (CSPM misconfigurations + attack paths + CIEM), the cloud resource inventory and security graph, compliance assessment, the risk overview, CAASM (third-party asset attack surface), sensor↔cloud-asset resolution, finding triage, CSV exports, and the multi-org fleet overview.

Reads require the `cloudsec.get` permission and writes require `cloudsec.set`. Every command requires the org to be subscribed to the `ext-cloud-security` extension:

```bash
limacharlie extension subscribe --name ext-cloud-security
```

Provider credentials and the cloudsec policies are hive records — manage them with the hive commands (`limacharlie hive list cloudsec_provider`, `... cloudsec_policy`, `... cloudsec_query`).

Every command supports `--ai-help` for a detailed description with examples.

## Overview & posture

```bash
limacharlie cloudsec overview --trend-days 90     # composed risk overview
limacharlie cloudsec risk-trend --trend-days 90   # score history (sparkline)
limacharlie cloudsec changes --limit 100          # recent created/closed findings
limacharlie cloudsec scan-status --provider aws   # collection sweep status
limacharlie cloudsec chokepoint list              # shared attack-path hops
limacharlie cloudsec chokepoint dismiss "lcrn:..." --reason "planned decom"
limacharlie cloudsec chokepoint restore "lcrn:..."
```

## Fleet (multi-org, MSSP)

One posture row per authorized org, plus cross-tenant rollups on the first page. With user-scoped credentials the CLI mints a temporary multi-org token, so the fleet is not limited to the configured `--oid`.

```bash
limacharlie cloudsec fleet overview
limacharlie cloudsec fleet overview --group <GROUP_ID> --trend-days 90
limacharlie cloudsec fleet overview --oid <OID1> --oid <OID2>
```

## Findings

Repeatable filters are OR within a key and AND across keys. Finding classes: `toxic_combination`, `public_exposure`, `ciem_risk`, `privilege_escalation`, `vulnerability`, `misconfig`, `malware`, `secret`, `scan_finding`, `coverage_gap`. Sort keys: `lc_risk` (default), `severity`, `first_seen`.

```bash
limacharlie cloudsec finding list --severity CRITICAL --severity HIGH
limacharlie cloudsec finding list --class public_exposure --kev
limacharlie cloudsec finding facets --status open
limacharlie cloudsec finding get fnd_0123abcd

# Triage
limacharlie cloudsec finding resolve fnd_abc --kind mitigated --reason "SG tightened"
limacharlie cloudsec finding resolve fnd_abc --kind open        # reopen
limacharlie cloudsec finding bulk-resolve --finding-id fnd_a --finding-id fnd_b --kind false_positive
limacharlie cloudsec finding set-owner fnd_abc --owner alice@corp.com
limacharlie cloudsec finding set-ticket fnd_abc --ticket JIRA-123
```

## Attack paths & CIEM

```bash
limacharlie cloudsec attack-path list --severity CRITICAL
limacharlie cloudsec ciem public-access    # public/external access to sensitive resources
limacharlie cloudsec ciem facets           # identity facet counts
```

## Inventory, resources & data security

```bash
limacharlie cloudsec inventory list --type gcp_bucket --region us-central1
limacharlie cloudsec inventory list --provider okta      # scope to one provider's sweep
limacharlie cloudsec inventory facets
limacharlie cloudsec data-security facets                # DSPM data-store rollup
limacharlie cloudsec resource get "lcrn:gcp:...:bucket/prod-data"
```

## Security graph & queries

```bash
limacharlie cloudsec graph neighbors "lcrn:...instance/web-1" --limit 500
limacharlie cloudsec query list
limacharlie cloudsec query run --named public-buckets
limacharlie cloudsec query run --text "public bucket with sensitive data"
```

## Compliance

```bash
limacharlie cloudsec compliance frameworks
limacharlie cloudsec compliance report --framework cis-aws
limacharlie cloudsec compliance assignments              # scoped assignments
limacharlie cloudsec compliance report --assignment prod-scope
```

## CSV exports

The server walks the full filtered set (no pagination), capped at 100k rows; a trailing `#` comment row marks a truncated export.

```bash
limacharlie cloudsec export findings -o findings.csv --severity CRITICAL
limacharlie cloudsec export inventory -o inventory.csv --provider gcp
limacharlie cloudsec export compliance -o cis-gcp.csv
limacharlie cloudsec export query --named public-buckets -o rows.csv
```

## Sensor ↔ cloud asset resolution

```bash
limacharlie cloudsec resolve sensors <SID1> <SID2>       # sensor -> cloud asset
limacharlie cloudsec resolve assets "lcrn:...instance/web-1"  # asset -> sensors
```

## CAASM (third-party asset attack surface)

```bash
limacharlie cloudsec caasm assets -q laptop --limit 50
limacharlie cloudsec caasm coverage --status open --severity HIGH
limacharlie cloudsec caasm policy get
limacharlie cloudsec caasm policy set --input-file policy.yaml
limacharlie cloudsec caasm ingest --source okta --records-file users.json
```

Ingest sources today: `sentinelone`, `crowdstrike`, `defender`, `okta`, `entraid`, `ms_graph`, `wiz` (the registry grows and is validated server-side).

## Providers

```bash
limacharlie cloudsec provider test --input-file provider.yaml   # credential preflight (ephemeral)
limacharlie cloudsec provider manifest                          # coverage manifests, all providers
limacharlie cloudsec provider manifest --type gcp
```

Saved provider configs live in the `cloudsec_provider` hive:

```bash
limacharlie hive set --hive-name cloudsec_provider --key my-gcp --input-file provider.json --enabled
```
