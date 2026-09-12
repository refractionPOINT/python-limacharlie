# Google Cloud

Collects the Google Cloud estate across every project in scope — compute,
serverless (Cloud Run and Cloud Functions), storage, networking, IAM, KMS,
databases, secrets, Pub/Sub — plus CIEM (who can reach what), Vertex AI
inventory, and agentless workload vulnerabilities from VM Manager.

**Auth model:** a **service-account key** (JSON) granted read-only roles at the
**organization**, **folder**, or **project** you want enumerated. The collector
discovers every active project underneath that node by itself.

## Prerequisites

1. A GCP **project** to own the service account (any project you control — it
   does not have to be one being scanned).
2. Permission to grant IAM roles at the scope you intend to connect
   (Organization Admin / Folder Admin / Project IAM Admin).
3. The **APIs enabled** on the service account's own project — the client APIs
   the collector calls:

    ```bash
    gcloud services enable \
      cloudresourcemanager.googleapis.com \
      serviceusage.googleapis.com \
      iam.googleapis.com \
      compute.googleapis.com \
      storage.googleapis.com \
      secretmanager.googleapis.com \
      cloudkms.googleapis.com \
      bigquery.googleapis.com \
      sqladmin.googleapis.com \
      pubsub.googleapis.com \
      apikeys.googleapis.com \
      osconfig.googleapis.com \
      containeranalysis.googleapis.com \
      run.googleapis.com \
      cloudfunctions.googleapis.com \
      aiplatform.googleapis.com \
      notebooks.googleapis.com \
      recommender.googleapis.com \
      policyanalyzer.googleapis.com \
      cloudidentity.googleapis.com \
      --project "$SA_PROJECT"
    ```

!!! info "APIs must also be on in the projects being scanned"
    A scanned project with a service API disabled is **skipped for that
    service** — treated as *covered, empty*, never as a permission failure.
    That is usually what you want. `provider test` reports a disabled API as a
    passing check with an explanatory note, precisely so you do not mistake it
    for a missing grant.

!!! warning "Only some of these surfaces have a preflight check"
    The preflight probes the surfaces listed in the
    [check table](#verify) below. The rest — KMS, BigQuery, Cloud SQL, Pub/Sub,
    API keys, Workbench notebooks — are exercised only during the sweep. If one
    of their APIs is disabled, that inventory type simply comes back **empty**
    while the provider test stays green, so enable the full list above rather
    than trimming it to what the test covers.

## Required roles

Grant at the **scope node** (organization, folder, or project). Roles are
inherited down the hierarchy, so an org-level grant covers every project.

| Role | Why | Preflight check |
|---|---|---|
| `roles/viewer` | The read surface for every resource type (compute, storage, networking, databases, Pub/Sub, KMS, …) | `compute`, `storage`, `projects` |
| `roles/iam.securityReviewer` | `*.getIamPolicy` across services — the CIEM graph (who can access what) | `iam` |

!!! tip "Prefer a tighter grant?"
    `roles/viewer` is the simple, well-understood baseline. A least-privilege
    alternative is `roles/browser` (hierarchy traversal) plus the per-service
    viewer roles you care about, still with `roles/iam.securityReviewer`. Use
    `provider test` to confirm the result — it names every surface that is
    still denied.

## Optional roles

Each adds one inventory or analysis surface. Skipping one leaves that surface
*unobserved*; the sweep still succeeds.

| Role | Unlocks | Preflight check |
|---|---|---|
| `roles/secretmanager.viewer` | Secret **metadata** inventory (names/rotation posture — never secret values) | `secret_manager` |
| `roles/osconfig.vulnerabilityReportViewer` | Agentless workload vulnerabilities from VM Manager | `osconfig_vuln` |
| `roles/osconfig.inventoryViewer` | The OS-inventory join that attaches package name + installed/fixed version to each CVE | *(not probed — exercised during the sweep)* |
| `roles/containeranalysis.occurrences.viewer` | **Container image** vulnerabilities from Artifact Analysis, for images in Artifact Registry and Container Registry | `artifact_analysis` |
| `roles/recommender.iamViewer` | Unused-privilege findings (activity-based CIEM) | `activity_ciem` |
| `roles/policyanalyzer.activityAnalysisViewer` | Dormant-identity / last-authentication findings | `activity_ciem` |
| `roles/aiplatform.viewer` | Vertex AI endpoint and model inventory | `vertex_ai` |
| `roles/run.viewer` | Cloud Run service inventory **and its public-access verdict** (`run.services.list` + `run.services.getIamPolicy`) | `serverless` |
| `roles/cloudfunctions.viewer` | Cloud Functions inventory (1st and 2nd gen) plus their invoker policies (`cloudfunctions.functions.list` + `cloudfunctions.functions.getIamPolicy`) | `serverless` |
| `roles/cloudidentity.groups.readonly` | Google-group **membership expansion**, so `group:` IAM bindings resolve to real people | `cloud_identity` |

!!! note "What container image scanning gives you, and what it does not"
    With `roles/containeranalysis.occurrences.viewer` granted **and** Artifact
    Analysis enabled in the project, each vulnerable image is reported against
    its **digest**, so one image is one finding subject however many tags point
    at it — the same shape we use for Amazon ECR and Azure Container Registry, so
    an image is one thing to triage across clouds.

    Three limits are worth knowing up front:

    - **Images are not inventoried yet.** A vulnerable image appears as a
      finding subject, not in Inventory or the topology, and nothing links it to
      the workloads that run it.
    - **An enabled verdict is about the API, not every repository.** We read
      whether Artifact Analysis answers for the project. That does not prove
      on-push scanning is configured for every repository.
    - **Very large registries are skipped whole, not truncated.** A project
      whose registries hold more scan results than our per-project ingestion
      budget reports **none** of them rather than an arbitrary subset — a
      truncated set would look like a shrinking estate. A busy CI project that
      keeps every historical build image is the case that hits this. The
      results are not lost on Google's side; we simply do not ingest them yet.

!!! note "Serverless already works on the required baseline"
    The required `roles/viewer` + `roles/iam.securityReviewer` pair **already**
    grants both the list and the `getIamPolicy` reads for Cloud Run and Cloud
    Functions, so you do not need to add anything for serverless coverage. The
    two roles above exist for the least-privilege alternative (`roles/browser`
    plus per-service viewers), where they are what turns serverless coverage on.

    Both halves of each grant matter, and the second is the one that gets
    missed: without `getIamPolicy` we can list a service but cannot tell whether
    it is invocable by *anyone on the internet*. In that case we report no
    verdict rather than guess — so serverless exposure findings are **absent,
    not empty**, which is a different thing from "you have none".

!!! note "Services published only through a load balancer"
    A Cloud Run service or function whose ingress is **internal and Cloud Load
    Balancing** cannot be reached at its own `run.app` URL, but it *can* be
    published to the internet through an external load balancer in front of it.
    We do not yet collect load balancers, so such a service is inventoried but
    is **not** reported as internet-facing. Services reachable directly at their
    own URL are assessed normally.

!!! note "2nd-gen functions are authorized as Cloud Run services"
    A 2nd-gen Cloud Function runs on Cloud Run, and its **invoker** permission
    lives on the underlying Cloud Run service (`roles/run.invoker`) rather than
    on the function (`roles/cloudfunctions.invoker` is the 1st-gen role). So
    assessing a 2nd-gen function's public access reads the **Cloud Run** side,
    not the Cloud Functions side.

    If you are assembling a least-privilege grant rather than using the required
    baseline, grant both `roles/run.viewer` and `roles/cloudfunctions.viewer` and
    let `provider test` confirm it: the `serverless` check exercises both APIs and
    reports each separately, so it will tell you if one half is missing rather
    than leaving you to reason about role contents.

!!! note "`osconfig_vuln` does not prove the inventory join"
    The `osconfig_vuln` check probes the vulnerability-report read only, so it
    passes with `roles/osconfig.vulnerabilityReportViewer` alone. If
    `roles/osconfig.inventoryViewer` is missing, the sweep still records the
    CVEs but skips the OS-inventory join and moves on — the symptom is
    vulnerability rows with **no package name and no fixed version**, not a
    failing check.

!!! note "Workbench notebooks are a separate API"
    Vertex AI Workbench notebook inventory comes from the Notebooks API
    (`notebooks.googleapis.com`), not from the Vertex AI API, and it is not
    covered by the `vertex_ai` check. Enable that API too if you want notebooks
    inventoried.

!!! note "Recommender needs only the list permission"
    Google's own walkthrough for *reviewing* role recommendations in the
    console also asks for `roles/iam.roleViewer` and a resource IAM-admin role.
    Those cover applying recommendations interactively; this connector only
    **lists** them, and the `roles/viewer` baseline already covers the
    role-metadata reads.

!!! note "Cloud Identity groups are granted elsewhere"
    `roles/cloudidentity.groups.readonly` (or the **Groups Reader** role) is
    granted at the **Cloud Identity account/customer** level in the Google
    Admin console, not on a GCP project. Without it, IAM bindings to groups
    remain visible but their membership is not expanded, so
    "which humans can reach this bucket" stops at the group.

## Create the service account

```bash
SA_PROJECT=my-security-project
ORG_ID=123456789                     # or use --folder / --project instead

gcloud iam service-accounts create lc-cloudsec \
  --display-name "LimaCharlie Cloud Security" \
  --project "$SA_PROJECT"

SA="lc-cloudsec@${SA_PROJECT}.iam.gserviceaccount.com"

# Required
for ROLE in roles/viewer roles/iam.securityReviewer; do
  gcloud organizations add-iam-policy-binding "$ORG_ID" \
    --member "serviceAccount:${SA}" --role "$ROLE"
done

# Optional surfaces
for ROLE in roles/secretmanager.viewer \
            roles/osconfig.vulnerabilityReportViewer \
            roles/osconfig.inventoryViewer \
            roles/recommender.iamViewer \
            roles/policyanalyzer.activityAnalysisViewer \
            roles/aiplatform.viewer \
            roles/containeranalysis.occurrences.viewer \
            roles/run.viewer \
            roles/cloudfunctions.viewer; do
  gcloud organizations add-iam-policy-binding "$ORG_ID" \
    --member "serviceAccount:${SA}" --role "$ROLE"
done

gcloud iam service-accounts keys create sa-key.json \
  --iam-account "$SA" --project "$SA_PROJECT"
```

For a folder scope use `gcloud resource-manager folders add-iam-policy-binding
<FOLDER_ID>`; for a single project use `gcloud projects add-iam-policy-binding
<PROJECT_ID>`.

!!! note "In the console"
    **IAM & Admin → Service Accounts → Create service account**, then
    **IAM & Admin → IAM → Grant access** at the organization/folder/project and
    add the roles above. Create the key under the service account's **Keys →
    Add key → Create new key → JSON**.

## Create the credentials secret

The secret value is the **service-account key JSON itself** — no wrapper.

```bash
python3 -c 'import json,sys;print(json.dumps({"secret":open("sa-key.json").read()}))' \
  > gcp-secret.json

limacharlie hive set --hive-name secret --key gcp-collector-sa \
    --input-file gcp-secret.json --enabled
```

Or in the web app: **Organization Settings → Secrets Manager → Add**, name it
`gcp-collector-sa`, and paste the key JSON.

## Create the provider record

`provider.yaml`:

```yaml
provider_type: gcp
gcp_scope: organizations/123456789      # or folders/456 or projects/my-project
credentials: hive://secret/gcp-collector-sa
internal_domains: [example.com]
refresh: 6h
```

| Field | Meaning |
|---|---|
| `gcp_scope` | The node to enumerate: `organizations/{id}`, `folders/{id}`, or `projects/{id}`. Every **active** project underneath is swept. |
| `gcp_project` | Alternative to `gcp_scope` for a single project. Supply one or the other. |

In the web app: **Add provider → GCP**, then set the **scope**, **Credentials**,
and the **Sync cadence** (pick a preset, or **Custom interval** for a duration of
your own).

## Verify

```bash
limacharlie cloudsec provider test --input-file provider.yaml
```

The report opens with the `config` and `credential` checks common to every
provider, [documented once in Provider Setup](index.md#the-two-checks-every-provider-reports-first);
the GCP-specific checks follow.

| Check | Required | Meaning if it fails |
|---|:--:|---|
| `auth` | ✅ | The key could not mint a token, or the scope node is unreachable. Nothing else can be probed. |
| `projects` *(folder/org scope only)* | ✅ | `resourcemanager.projects.list` denied — no project can be discovered under the scope. A single-project scope has nothing to enumerate, so this check is not reported at all. |
| `compute` | ✅ | `compute.instances.list` denied — no compute inventory. |
| `storage` | ✅ | `storage.buckets.list` denied — no storage inventory. |
| `iam` | ✅ | `getIamPolicy` and/or `serviceAccounts.list` denied — the CIEM access graph cannot be built. |
| `secret_manager` | — | Secret-store inventory unavailable. |
| `activity_ciem` | — | Unused-privilege and dormant-identity findings unavailable. |
| `osconfig_vuln` | — | Workload vulnerability findings unavailable. |
| `vertex_ai` | — | Vertex AI endpoint inventory unavailable. |
| `serverless` | — | Cloud Run / Cloud Functions inventory unavailable, and with it the "invocable by anyone on the internet" verdict for that tier. Reported per API, so a partial grant names the half that is missing. |
| `cloud_identity` | — | Group membership is not expanded; `group:` bindings do not resolve to people. |

!!! tip "Org-scope tests probe one representative project"
    For a folder/organization scope the preflight picks the first active
    project under the node and probes there — IAM grants are inherited, so one
    project answers "is this granted". If that project happens to have a
    service API disabled, the check passes with a note saying the grant was
    neither proven nor disproven.

## Troubleshooting

| `provider test` result | Cause | Fix |
|---|---|---|
| `auth` fails: `PERMISSION_DENIED` on the scope | The service account has no binding at that org/folder/project | Grant `roles/viewer` at the scope node (not just on the SA's own project) |
| `auth` fails: *"Cloud Resource Manager API has not been used in project `<number>`"* on an **organization** or **folder** scope | An org/folder has no project of its own, so the API-enablement check is billed to the **caller's** project — `<number>` is the **service account's** project, not a project being scanned. The console only offers to enable APIs per project, which makes this look unresolvable at the org level | `gcloud services enable cloudresourcemanager.googleapis.com --project "$SA_PROJECT"` (see [Prerequisites](#prerequisites)) |
| `projects` fails | Missing `resourcemanager.projects.list` | `roles/viewer` or `roles/browser` at the scope node |
| `iam` fails on `getIamPolicy` | `roles/viewer` alone does not cover every `getIamPolicy` | Add `roles/iam.securityReviewer` |
| A check passes with *"API not enabled on the probed project"* | Benign — the sweep skips API-disabled projects | Enable the named API if you want that surface; otherwise ignore |
| `activity_ciem` fails with *Recommender API not enabled* | Recommender / Policy Analyzer not enabled on the probed project | Enable `recommender.googleapis.com` and `policyanalyzer.googleapis.com` |
| `serverless` fails on `run` only | The grant reaches Cloud Functions but not Cloud Run | Add `roles/run.viewer`. 2nd-gen functions are authorized as Cloud Run services, so without that read they list with no public-access verdict |
| Cloud Run services appear but none is ever flagged public | `getIamPolicy` is denied on Cloud Run, so the invoker verdict is unobserved rather than negative | Add `roles/iam.securityReviewer` (or `roles/run.viewer`) and re-run the sweep |
| Inventory is missing whole projects | Those projects are not `ACTIVE`, or the grant is on a narrower node | Confirm project state, and that the binding is at the scope you configured |
