# Microsoft Azure

Collects the Azure estate — VMs and scale sets, storage, Key Vault, SQL/Cosmos,
AKS, networking and NSGs, Azure OpenAI — plus the tenant's Entra ID directory
(users, groups, service principals, app registrations, roles) and, where
licensed, Conditional Access and sign-in activity.

**Auth model:** an **Entra ID app registration** (service principal) with a
**client secret**, granted the **Reader** RBAC role on your subscriptions and
**Microsoft Graph application permissions** on the tenant.

!!! tip "Directory only, no Azure subscription?"
    If you have Entra ID / Microsoft 365 but no Azure infrastructure to
    enumerate, use the [Entra ID](entra.md) provider instead — same app
    registration, none of the ARM setup.

## Prerequisites

- Permission to create an app registration in the tenant (**Application
  Developer** or higher).
- Permission to **grant tenant-wide admin consent** for Graph application
  permissions (**Privileged Role Administrator** or **Global Administrator**).
- **Owner** or **User Access Administrator** on each subscription you want
  read, to assign Reader.

## Required permissions

| Grant | Where | Why | Preflight check |
|---|---|---|---|
| **Reader** RBAC role | On each subscription (or a management group above them) | Reads every resource in the subscription, and the Defender/Resource Graph security views | `arm_reader` |
| **Directory.Read.All** (application) | Microsoft Graph | Users, groups, service principals, app registrations, domains, directory roles | `graph_directory` |

## Optional permissions

| Grant | Unlocks | Preflight check |
|---|---|---|
| **Policy.Read.All** (application) | Conditional Access policy posture | *(collected during the sweep)* |
| **AuditLog.Read.All** (application) | Two things: last-sign-in / dormancy enrichment on identities, and each identity's **MFA-registration state** (whether the user is MFA-registered / MFA-capable, from the authentication-methods registration report). **Requires an Entra ID P1 or P2 licence** — without the licence the reports are unavailable regardless of consent | `signin_activity` covers the sign-in half only |
| **RoleManagement.Read.Directory** (application) | Directory role assignments and PIM eligibility | *(collected during the sweep)* |
| **Application.Read.All** (application) | Fuller app-registration / service-principal credential detail | *(collected during the sweep)* |
| **AdministrativeUnit.Read.All** (application) | Administrative-unit scoping | *(collected during the sweep)* |
| **AgentIdentity.Read.All** (application) | Source-asserted AI-agent identities in the directory | *(collected during the sweep)* |
| *(covered by Reader)* | Defender for Cloud vulnerability assessments via Azure Resource Graph — **server** VMs and **container registry images** | `defender_vuln` |

A denied Graph permission 403s only its own collector — that surface goes
unobserved while everything else still collects.

!!! note "Container image vulnerabilities need the Defender for Containers plan"
    Reader is all the *permission* we need — the image findings come from the
    same Resource Graph security views as the server ones. What they also need
    is the **Defender for Containers** plan (or the retired standalone
    **Container Registry** plan) on the **Standard** tier for the subscription;
    on the Free tier Defender publishes no registry scan results and we report
    the subscription as having no container-image vulnerability source.

    **Defender for Kubernetes / KubernetesService is a different plan** and does
    not count: it buys runtime threat protection for the cluster, not image
    scanning, so a subscription paying only for that is still reported as having
    no image vulnerability source.

    Each vulnerable image is reported against its **digest**, so one image is
    one finding however many tags point at it — the same shape we use for
    Amazon ECR and GCP Artifact Registry. Two limits are worth knowing:

    - **Images are not inventoried yet.** An affected image is a finding
      subject, not an entry in Inventory or the topology, and nothing links it
      to the workloads that run it.
    - **Very large registries are skipped whole, not truncated.** A subscription
      whose registries hold more scan results than our per-subscription
      ingestion budget reports **none** of them rather than an arbitrary
      subset — a truncated set would look like a shrinking estate. A
      subscription that keeps every historical build image is the case that
      hits this.

!!! note "MFA-registration state has no preflight check of its own"
    The `signin_activity` check probes the sign-in report only. MFA-registration
    state is read during the sweep, so if that particular report is denied or
    unlicensed the provider test still passes and the symptom is identities with
    **no MFA-registration information** rather than a failing check.

## Create the app registration

```bash
TENANT_ID=$(az account show --query tenantId -o tsv)
SUB_ID=<your-subscription-id>

# 1. App registration + service principal
APP_ID=$(az ad app create --display-name lc-cloudsec --query appId -o tsv)
az ad sp create --id "$APP_ID"

# 2. Client secret (note the expiry you choose; --append preserves existing ones)
az ad app credential reset --id "$APP_ID" --years 2 --append \
  --display-name lc-cloudsec --query password -o tsv     # capture this once

# 3. RBAC Reader on the subscription (repeat per subscription)
az role assignment create --assignee "$APP_ID" --role Reader \
  --scope "/subscriptions/${SUB_ID}"

# 4. Microsoft Graph application permissions
GRAPH=00000003-0000-0000-c000-000000000000
az ad app permission add --id "$APP_ID" --api "$GRAPH" --api-permissions \
  7ab1d382-f21e-4acd-a863-ba3e13f7da61=Role   # Directory.Read.All
az ad app permission add --id "$APP_ID" --api "$GRAPH" --api-permissions \
  246dd0d5-5bd0-4def-940b-0421030a5b68=Role   # Policy.Read.All
az ad app permission add --id "$APP_ID" --api "$GRAPH" --api-permissions \
  b0afded3-3588-46d8-8b3d-9842eff778da=Role   # AuditLog.Read.All

# 5. Tenant-wide admin consent (needs a privileged admin)
az ad app permission admin-consent --id "$APP_ID"
```

!!! note "In the portal"
    **Microsoft Entra ID → App registrations → New registration** → then
    **Certificates & secrets → New client secret** (copy the *Value*, not the
    ID) → **API permissions → Add a permission → Microsoft Graph →
    Application permissions** → add the permissions above → **Grant admin
    consent for \<tenant\>** (the status column must read *Granted*) →
    finally **Subscriptions → \<sub\> → Access control (IAM) → Add role
    assignment → Reader → your app**.

!!! danger "`credential reset` clears existing secrets"
    Without `--append`, `az ad app credential reset` **removes every existing
    password and certificate** on the app before adding the new one. Always
    pass `--append` when the app already carries credentials something else
    depends on.

!!! danger "Application permissions, not delegated"
    Graph permissions must be added under **Application permissions**.
    Delegated permissions require a signed-in user and will leave the
    `graph_directory` check failing even after consent.

## Create the credentials secret

```json
{"client_id": "<application-client-id>", "client_secret": "<the-secret-value>"}
```

```bash
limacharlie secret set --key azure-sp \
    --value "$(cat azure-secret.json)" --enabled
```

`secret set` wraps the value into the secret record for you — the equivalent of
`limacharlie hive set --hive-name secret` with `{"secret": "<the credential JSON
as a string>"}`.

## Create the provider record

`provider.yaml`:

```yaml
provider_type: azure
azure_tenant_id: "<tenant-id>"
azure_client_id: "<application-client-id>"
azure_subscription_id: "<subscription-id>"
credentials: hive://secret/azure-sp
internal_domains: [example.com, example.onmicrosoft.com]
refresh: 6h
```

!!! info "`azure_subscription_id` is an anchor, not a limit"
    The collector enumerates **every subscription the service principal can
    see** (`subscriptions` check). Assign Reader on each subscription you want
    swept; the one named here is simply the anchor used for scoping and
    probing. If the tenant-wide `subscriptions` read is denied, the sweep falls
    back to the single configured subscription.

In the web app: **Add provider → Azure**, then set **Tenant ID**, **Client
ID**, **Subscription ID**, **Credentials**, and the **Sync cadence** (pick a
preset, or **Custom interval** for a duration of your own).

## Verify

```bash
limacharlie cloudsec provider test --input-file provider.yaml
```

The report opens with the `config` and `credential` checks common to every
provider, [documented once in Provider Setup](index.md#the-two-checks-every-provider-reports-first);
the Azure-specific checks follow.

| Check | Required | Meaning if it fails |
|---|:--:|---|
| `auth` | ✅ | The client ID/secret pair was rejected, or the secret expired. |
| `arm_reader` | ✅ | Reader is not assigned on the configured subscription — no resource inventory. |
| `graph_directory` | ✅ | `Directory.Read.All` not consented — no identity inventory. |
| `subscriptions` | — | Subscription fan-out disabled; only the configured subscription is swept. |
| `defender_vuln` | — | Workload **and container image** vulnerability findings unavailable — both are rows in the same Resource Graph table behind the same grant, so one check covers both. |
| `signin_activity` | — | Last-sign-in and dormancy enrichment unavailable (usually a missing Entra ID P1/P2 licence). |

## Troubleshooting

| `provider test` result | Cause | Fix |
|---|---|---|
| `auth` fails with `invalid_client` | The secret **ID** was stored instead of the secret **Value**, or the secret expired | Re-mint (`az ad app credential reset`) and store the new value |
| `graph_directory` fails after adding permissions | Admin consent not granted, or permissions added as *Delegated* | Grant tenant-wide admin consent; confirm the permissions are under *Application* |
| `arm_reader` fails | Reader assigned at the wrong scope, or not yet propagated | Assign Reader on the subscription (or a management group above it); retry after a minute |
| `signin_activity` fails with a licence error | Sign-in activity requires Entra ID P1/P2 | Either accept the degrade or add the licence |
| Directory data appears twice | An `azure` **and** an `entra` record both cover the tenant | This is handled automatically: the Azure connection defers its tenant-global directory collectors to the standalone [Entra](entra.md) record |
| A scale set / App Service is missing | The resource type may need quota or a supported SKU in that subscription | Confirm the resource is visible to the SP with `az resource list` under the same identity |
