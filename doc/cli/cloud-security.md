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
limacharlie cloudsec free-tier                    # tier + provider usage vs the limits
```

`free-tier` only DESCRIBES the free-tier limits — the collector and the provider-record validator enforce them, so a limit applies whether or not you ask. `enabled_providers` is omitted rather than zeroed when the count could not be read, so an absent field means "unknown", never "none configured". There is no trial countdown: the authoritative clock lives in the datacenter, and a gated collection reports its reason through `scan-status`.

## Fleet (multi-org, MSSP)

One posture row per authorized org, plus cross-tenant rollups on the first page. With user-scoped credentials the CLI mints a temporary multi-org token, so the fleet is not limited to the configured `--oid`.

```bash
limacharlie cloudsec fleet overview
limacharlie cloudsec fleet overview --group <GROUP_ID> --trend-days 90
limacharlie cloudsec fleet overview --oid <OID1> --oid <OID2>
```

## Findings

Repeatable filters are OR within a key and AND across keys. Finding classes: `toxic_combination`, `public_exposure`, `ciem_risk`, `privilege_escalation`, `vulnerability`, `misconfig`, `coverage_gap`. Sort keys: `lc_risk` (default), `severity`, `first_seen`.

`--owner` filters by assigned owner and `--unassigned` selects the untriaged bucket; they combine, so "mine or nobody's" is one filter with both. On `finding facets` the `owner` facet is capped at the top 50 owners by count (`owner_truncated` reports whether any were dropped) — `--owner-pin` keeps named owners in it even when they would not rank in, and filters nothing. That is bounded by the same cap: pins share the 50 slots with any `--owner` values, so past ~50 combined a pin can still be dropped and `owner_truncated` will not say so.

`finding causes` groups findings by the mutable object whose single edit resolves all of them, so a worklist can be worked by fix instead of by row. It takes the same filters as `finding list`; `distinct` is the total number of matching causes, so you can see how much tail the ranked head hides.

```bash
limacharlie cloudsec finding list --severity CRITICAL --severity HIGH
limacharlie cloudsec finding list --class public_exposure --kev
limacharlie cloudsec finding list --owner alice@corp.com --unassigned
limacharlie cloudsec finding facets --status open
limacharlie cloudsec finding facets --owner-pin me@corp.com
limacharlie cloudsec finding causes --severity CRITICAL --limit 5
limacharlie cloudsec finding causes --cause "lcrn:...:firewalls/allow-all"
limacharlie cloudsec finding get fnd_0123abcd

# Triage
limacharlie cloudsec finding resolve fnd_abc --kind mitigated --reason "SG tightened"
limacharlie cloudsec finding resolve fnd_abc --kind open        # reopen
limacharlie cloudsec finding bulk-resolve --finding-id fnd_a --finding-id fnd_b --kind false_positive
limacharlie cloudsec finding set-owner fnd_abc --owner alice@corp.com
limacharlie cloudsec finding set-ticket fnd_abc --ticket JIRA-123
```

## Attack paths & CIEM

`ciem facets` and `ciem identities` take the SAME cross-filter, so the rail's counts always describe the population the list returns. The boolean filters are tri-state: omitting one leaves the dimension unconstrained, which is not the same as pinning it false. `--mfa unknown` is everyone the MFA question does not apply to (no identity-provider observation, or non-human) — it is not `off`.

`--risk-band` and `--criticality` are closed vocabularies (`critical`, `high`, `medium`, `low`) validated client-side, because the backend fails closed: an unrecognized value would return zero rows with a successful exit. `--unclassified` selects identities with no tier assigned and combines with `--criticality`.

```bash
limacharlie cloudsec attack-path list --severity CRITICAL
limacharlie cloudsec ciem public-access    # public/external access to sensitive resources
limacharlie cloudsec ciem facets --kind service_account --admin
limacharlie cloudsec ciem identities --limit 50            # ranked, paginated population
limacharlie cloudsec ciem identities --external --with-sensitive
limacharlie cloudsec ciem identities --mfa off --admin
limacharlie cloudsec ciem identities --risk-band critical --unclassified
limacharlie cloudsec ciem identity "lcrn:gcp:...:serviceAccount/deploy"   # one identity
```

## Inventory, resources & data security

`data-security facets` and `data-security stores` share their selectors for the same reason. `--sensitive` / `--public` are tri-state (`--no-sensitive` / `--no-public` pin them false). `--tier` takes the same closed tier vocabulary as `--criticality` above, with `--unclassified` for stores that have none.

```bash
limacharlie cloudsec inventory list --type gcp_bucket --region us-central1
limacharlie cloudsec inventory list --provider okta      # scope to one provider's sweep
limacharlie cloudsec inventory facets
limacharlie cloudsec data-security facets                # DSPM data-store rollup
limacharlie cloudsec data-security stores --sensitive --public
limacharlie cloudsec data-security stores --store-kind bucket --data-class pii
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
limacharlie cloudsec export findings --owner alice@corp.com   # same filters as 'finding list'
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
