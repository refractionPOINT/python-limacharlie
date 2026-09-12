# Cloud Security

LimaCharlie Cloud Security is an agentless cloud-native application protection
platform (CNAPP) built into the same tenant, permission model, and automation
surface as the rest of LimaCharlie. It continuously enumerates your cloud,
identity, SaaS, and AI estate, builds a security graph out of it, and turns what
it finds into a single risk-ranked worklist — connected to the sensors, D&R
rules, Cases, and Outputs you already use.

!!! tip "In one sentence"
    Connect a cloud account, identity provider, or AI platform with a read-only
    credential, and LimaCharlie shows you what you own, what is exposed, who can
    reach what, and exactly which fix breaks the most attack paths — with every
    finding automatable through the standard LimaCharlie event pipeline.

## What it covers

| Capability | What you get |
|---|---|
| **Inventory (CSPM)** | A continuously refreshed system-of-record of your cloud resources — compute, storage, networking, identities — with misconfiguration findings per resource. |
| **Attack paths** | Toxic combinations across resources: an internet-exposed workload with a known-exploited vulnerability that can reach sensitive data is one finding, not three disconnected ones. |
| **Identity (CIEM)** | Who — human or service — can access what: public/external access to sensitive resources, privilege-escalation edges, dormant privileged identities. Access is scored by the *capability* a grant actually confers, not by the mere existence of a grant. |
| **Data security (DSPM)** | Which data stores exist, which are sensitive (you declare it by policy), and which sensitive stores are exposed. |
| **AI security (AISPM)** | Your OpenAI and Anthropic organizations as first-class estate: members, API keys, projects, and posture — with the same findings and compliance lenses (`nist-ai-rmf`, `owasp-llm`). |
| **Compliance** | Per-control pass/fail assessment of frameworks over the live estate, whole-estate or scoped to named assignments. |
| **CAASM** | A merged third-party asset inventory (EDR / IdP / MDM / scanner sources, including LimaCharlie's own sensors) with coverage-gap and device-posture findings — "seen by the identity provider, no EDR". |
| **Security graph & topology** | An explorable graph of resources, identities, and their relationships (`can_reach`, `exposed_to`, `has_permission_on`, `can_assume`, …) plus an aggregated estate topology view, with a query language and saved queries. |
| **Runtime fusion** | Bidirectional resolution between LimaCharlie sensors and the cloud assets they run on — pivot from a cloud finding to the live endpoint and back. |
| **Code security** | Scan connected repositories in the hosted service, run the LimaCharlie scanner inside your own environment, or push existing SARIF and CycloneDX results into the same findings worklist. |
| **Your own detections** | Author your own CSPM rules — in the same detection format as the built-in pack — and disable, re-severity, or replace any built-in rule for your organization. |
| **Remediation SLAs** | Declare how long a finding may stay open, per severity, class, account, or owner, and work the worklist by deadline as well as by risk. |
| **MSSP fleet** | A cross-tenant fleet board that rolls up risk across every organization you manage. |

## Supported providers

Thirteen connectors across five surfaces, all agentless and read-only:

- **Cloud infrastructure** — Google Cloud (`gcp`, including folders/organizations),
  AWS (`aws`, including multi-account AWS Organizations), Azure (`azure`).
- **Identity** — Okta (`okta`), Microsoft Entra ID (`entra`), Google Workspace
  (`google_workspace`), 1Password (`1password`), Auth0 (`auth0`).
- **SaaS** — Cloudflare (`cloudflare`), GitHub (`github`).
- **AI** — OpenAI (`openai`), Anthropic (`anthropic`).
- **LimaCharlie** — your own LimaCharlie tenancy as a self-inventoried estate
  (`limacharlie`), including the MSSP fleet case.

You grant a scoped read credential (stored as a LimaCharlie
[secret](../7-administration/config-hive/secrets.md), referenced — never inlined —
from the provider record), and the platform sweeps the estate on a schedule, on
demand, or continuously from a change feed. See
[Connecting Providers](providers.md) for the per-provider setup.

## How it works

1. **Enable** the organization for the `ext-cloud-security` extension — the
   subscription is the product's enable (and billing) gate. Subscribe from
   **Extensions → Cloud Security** in the console or with
   `limacharlie extension subscribe --name ext-cloud-security`.
2. **Connect providers**: one `cloudsec_provider` Hive record per cloud
   account / IdP tenant / AI org. A pre-save credential test probes every
   permission the collector needs and reports which are missing.
3. **Sweeps build the graph**: each enumeration updates the resource
   system-of-record and the security graph, then re-derives findings.
   Closed conditions close their findings automatically.
4. **You work the findings**: one worklist ordered by `lc_risk`, with
   dispositions (mitigated / accepted / false positive), owners, tickets,
   chokepoint analysis, and full automation through `cloud_finding.*`
   events.

Nearly everything the console shows is also available through the
[REST API](api-reference.md), the [CLI](cli.md), and — for configuration —
plain [Hive records](configuration.md), so a fleet of tenants can be
onboarded and governed as code. (A few surfaces are console-only, notably the
printable posture report.)

## In the console

Cloud Security is a top-level workspace in the organization sidebar. Its pages
map onto the capabilities above:

| Page | What it is |
|---|---|
| **Overview** | The risk overview: score, severity distribution, top attack paths and the marquee chokepoint. |
| **Risks** | The findings worklist, with lenses (All risks / Public exposure & misconfig / Identity / Vulnerabilities / Data) and per-finding triage. |
| **Attack Surface** | The toxic-combination paths, grouped by shared fix, on an interactive graph canvas — plus a **Query console** tab for ad-hoc graph queries and saved queries. |
| **Identity & Access** | CIEM — who can reach what, with a per-identity drill-down (**Grants** and **Access map** tabs). |
| **Data Security** | DSPM — data-store posture and exposure. |
| **Code** | Repository scan status, code findings, SBOM downloads, and results from hosted or customer-run scanners. |
| **Inventory** | The estate itself, in four views: **Topology** (the landing view — an aggregated diagram of the estate), **Resources** (the resource system-of-record), **Third-party assets**, and **Sensor coverage** (CAASM). |
| **Compliance** | Per-control framework assessment and scoped assignments. |
| **Report** | A print-optimized posture report over the current estate, also reachable from **Overview → View report**. |
| **Policies** | Data classification (crown jewels), coverage, asset coverage, exclusions, and suppression. |
| **Settings** | Provider connections and the Cases integration. |

A separate cross-tenant **Cloud Security Fleet** board rolls risk up across every
organization you manage.

## Permissions

!!! info "Permissions"
    - `cloudsec.get` — read access to every Cloud Security view (findings,
      inventory, graph, topology, identity, compliance, CAASM) and the
      read-only policy previews.
    - `cloudsec.set` — finding triage and other writes (dispositions,
      owners/tickets, chokepoint dismissal, CAASM policy/ingest, provider
      credential tests).
    - `cloudsec_provider.get` / `.set` / `.del` — manage provider
      connection records in the Hive.
    - `cloudsec_provider.get.mtd` / `.set.mtd` — read and write the records'
      user metadata (tags, comments, enabled state).

    Every route additionally requires the organization to be subscribed to
    `ext-cloud-security`. API calls from an unsubscribed organization return
    `403`; in the console the Cloud Security pages render an "enable Cloud
    Security" screen instead of the product.

## Documentation

- [Getting Started](getting-started.md) — enable the product, connect a
  provider, run your first sweep.
- [Connecting Providers](providers.md) — the thirteen connectors, their
  credentials, and what each collects.
- [Code Scanning & Pushed Results](code-scanning.md) — scan a local checkout,
  ingest SARIF or CycloneDX, and run the workflow in GitHub Actions.
- [Provider Setup](provider-setup/index.md) — onboarding walkthrough for every
  platform: exact scopes, how to create the credential, credential-secret
  formats, and first-run troubleshooting.
- [Findings & Triage](findings.md) — the worklist, finding classes,
  dispositions, chokepoints.
- [Remediation SLAs](remediation-sla.md) — due dates on findings, the derived
  states, and breach events.
- [Security Graph & Queries](graph.md) — attack paths, topology, graph
  queries, CIEM, DSPM, sensor↔asset resolution.
- [Compliance](compliance.md) — frameworks, reports, scoped assignments.
- [CAASM](caasm.md) — third-party asset inventory, coverage gaps, device posture.
- [Custom Posture Rules](custom-rules.md) — author your own CSPM detections and
  retune the built-in ones.
- [Configuration Reference](configuration.md) — the `cloudsec_provider`,
  `cloudsec_policy`, and `cloudsec_query` Hive records.
- [Command Line Interface](cli.md) — the `limacharlie cloudsec` command
  group.
- [API Reference](api-reference.md) — the `/cloudsec` REST surface.
- [Automation & IaC](automation.md) — onboarding recipes, CSV exports, fleet
  management, and the findings↔Cases loop.
