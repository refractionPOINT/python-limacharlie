# GitHub

Collects a GitHub organization: org settings, members (including outside
collaborators) and teams (identities), repositories and their branch protection
(data stores), installed GitHub Apps, deploy keys and Actions secrets (machine
identities), and the Actions OIDC subject configuration that lets workflows
assume cloud roles.

**Auth model:** a **GitHub App installed on the organization**, with a
read-only permission set. The App's private key is used to mint short-lived
installation tokens — no personal access token, no user account in the loop.

## Prerequisites

- **Organization owner** access (creating and installing an org-owned App).
- The org **slug** (its login, e.g. `example-org`).

## Required permissions

Create the App with **read-only** access on the following. All are
*Repository* or *Organization* permissions set to **Read**:

| Permission | Scope | Why | Preflight check |
|---|---|---|---|
| **Members** | Organization | Org members and teams — the identity inventory | `members`, `teams` |
| **Metadata** | Repository | Repository inventory | `repos` |

## Optional permissions

| Permission | Scope | Unlocks | Preflight check |
|---|---|---|---|
| **Administration** | Organization | Installed-App inventory → over-privileged-app findings; the org's **MFA-required** posture; the per-member MFA-enrollment cross-check | `installed_apps` |
| **Secrets** | Organization | Organization Actions-secret inventory (**names only**, never values) | `org_secrets` |
| **Administration** | Repository | Branch-protection posture and deploy-key inventory (deploy keys are also the one activity signal — see [Known limitations](#known-limitations)) | *(collected during the sweep)* |
| **Secrets** | Repository | Whether a repository has Actions secrets at all — an existence flag, not a name list (org-level secrets are the ones inventoried by name) | *(collected during the sweep)* |
| **Contents** | Repository | [Code Scanning](../code-scanning.md) — dependencies, secrets, infrastructure-as-code, container images, code weaknesses and licenses. Without it the connector inventories repositories but cannot read them | `code_contents` |
| **Dependabot alerts** | Repository | GitHub's own **Dependabot** alerts, ingested as findings and deduplicated against LimaCharlie's own dependency scanning; and whether each repository has Dependabot alerts **enabled** | `dependabot_alerts` |
| **Code scanning alerts**, **Secret scanning alerts** | Repository | GitHub's own **code-scanning** and **secret-scanning** alerts, ingested as findings and deduplicated against LimaCharlie's own analysis | `security_events` |

### GitHub's own alerts, and what happens to them

With the two alert permissions granted, GitHub's own security products become a second
*source* rather than a second worklist:

- A **Dependabot** alert for an advisory LimaCharlie already found in the same repository
  and package is folded into that one finding, which then lists both sources and links to
  the GitHub alert. It does not appear twice, and its state follows LimaCharlie's scan.
- The same applies to **secret-scanning** and **code-scanning** alerts that describe the
  same credential, or the same rule in the same file, as a finding of our own.
- An alert about a repository LimaCharlie is **not** scanning stays a finding of its own —
  that is the coverage this ingest adds.

**Secret values are never read.** Secret-scanning alerts are requested with GitHub's
`hide_secret` option, and there is no field anywhere in the pipeline to store a credential
value. What is stored is the credential's type, GitHub's own validity verdict (whether the
token is still live), and where it was found.

**If the permissions are not granted, nothing breaks.** The alert surfaces are simply not
collected, the connection stays healthy, and the reason is recorded on the provider's scan
status rather than reported as a failure. Whether each repository has **secret scanning**
and **code scanning** enabled additionally depends on the organization **Administration**
read: where GitHub does not expose it, that state is reported as *not observed* rather than
as disabled, and the corresponding checks stay silent instead of flagging every repository
for a setting nobody could see.

!!! note "The setup wizard asks for Administration as required"
    The in-product **Add provider** wizard lists both Administration grants
    (organization and repository) as required rather than optional. Collection
    still succeeds without them — the required permissions above are what gate
    the connection — but most of the useful posture depends on them (org MFA,
    per-member MFA, branch protection, deploy keys, installed Apps), so the
    wizard asks for them up front. Grant them unless you have a reason not to.

## Create the GitHub App

1. **Organization → Settings → Developer settings → GitHub Apps → New GitHub
   App.**
2. Name it (e.g. `LimaCharlie Cloud Security`), set a homepage URL, and
   **uncheck Webhook → Active** (the collector polls; it needs no callback).
3. Under **Permissions**, set each permission above to **Read-only**.
4. Under **Where can this GitHub App be installed?**, choose **Only on this
   account**.
5. **Create GitHub App**, then note the **App ID** at the top of the page.
6. Scroll to **Private keys → Generate a private key**. A `.pem` file
   downloads — this is shown once.
7. Click **Install App**, install it on your organization, and choose **All
   repositories** (or a subset, accepting reduced coverage).

### Get the installation ID

After installing, the browser URL of the installation settings page ends in the
installation ID:
`https://github.com/organizations/<org>/settings/installations/<INSTALLATION_ID>`.

With the `gh` CLI, as an org owner:

```bash
gh api /orgs/<org>/installations --jq '.installations[] | {id, app_slug}'
```

## Create the credentials secret

The secret carries **only** the private key; the App ID and installation ID
live on the provider record.

```json
{"private_key": "-----BEGIN RSA PRIVATE KEY-----\n...\n-----END RSA PRIVATE KEY-----\n"}
```

The key is a multi-line PEM, so JSON-escape it rather than pasting it by hand:

```bash
python3 -c 'import json;print(json.dumps({"private_key":open("app.private-key.pem").read()}))' \
  > gh-key.json

limacharlie secret set --key github-app-key \
    --value "$(cat gh-key.json)" --enabled
```

`secret set` wraps whatever you pass in `--value` into the secret record's
`{"secret": "..."}` shape for you.

## Create the provider record

`provider.yaml`:

```yaml
provider_type: github
github_org: "example-org"
github_app_id: "1234567"
github_installation_id: "89012345"
credentials: hive://secret/github-app-key
internal_domains: [example.com]
refresh: 6h
```

Both IDs are the **numeric** values, as strings. `github_org` is the bare org
slug — no URL, no owner prefix.

In the web app: **Add provider → GitHub**, then set **Organization**, **App
ID**, **Installation ID**, **Credentials**, and **Refresh interval**.

## Verify

```bash
limacharlie cloudsec provider test --input-file provider.yaml
```

| Check | Required | Meaning if it fails |
|---|:--:|---|
| `auth` | ✅ | The App could not mint an installation token, or the installation cannot see the org. Nothing else is probed. |
| `members` | ✅ | Organization members unreadable — no identity inventory. |
| `repos` | ✅ | Repository inventory unavailable. |
| `teams` | — | Team and team-membership edges unavailable. |
| `installed_apps` | — | Installed-App inventory (over-privileged-app findings) unavailable. |
| `org_secrets` | — | Organization Actions-secret inventory unavailable. |
| `sso_identities` | — | SAML/SCIM external identities unavailable; identity unification falls back to verified-domain and public-profile emails. Passes with a note when the org has no SAML SSO. |

## Troubleshooting

| `provider test` result | Cause | Fix |
|---|---|---|
| `auth` fails: `Bad credentials` / JWT rejected | Wrong App ID, or the private key does not belong to that App | Confirm the App ID on the App settings page and regenerate the key if unsure |
| `auth` fails: `Not Found` on the org | The installation ID belongs to a different account, or the App is not installed on this org | Re-read the installation ID from the installation settings URL |
| `repos` passes but repositories are missing | The installation was scoped to selected repositories | Re-install with **All repositories**, or accept partial coverage |
| First sweep takes many minutes | Large orgs need per-repository calls for branch protection, deploy keys and the Actions-secret check | Expected; subsequent sweeps are incremental |
| A permission was added after installing | GitHub requires the installation to accept new permissions | Approve the permission request on the org's installation page |

## Known limitations

- **Activity data** is limited to deploy-key last-used timestamps. GitHub App
  installation tokens expose no per-permission last-use, so used-vs-granted
  analysis is unavailable.
- **Fine-grained personal access tokens** cannot be enumerated org-wide by an
  App, so they are not inventoried.
- **Webhooks are not inventoried.** Organization and repository webhooks are
  out of scope for this connector, so webhook data-egress endpoints do not
  appear in the graph.
- **Enterprise-level SAML SSO is not readable.** App installation tokens cannot
  read enterprise-level SAML identities (a documented GitHub limit), so members
  of an enterprise-SSO or managed-user org resolve through verified-domain and
  public-profile emails only. Organization-level SSO is read normally.
- An **Actions OIDC trust** with no corresponding cloud-side role is reported
  as a dangling trust rather than a fabricated "can assume" edge.

## Scanning repository contents

Granting **Contents → Read-only** turns on [Code Scanning](../code-scanning.md)
for the repositories a `code_scanning` policy selects. The permission is an
increase on an existing installation, so GitHub requires an organization owner to
**approve the permission request** on the installation page before it takes
effect; until then, selected repositories report
`github_app_missing_contents_permission` on the code scan status rather than
failing silently.

Code is read inside an ephemeral sandbox and never persisted — only the
normalized finding report leaves it, and discovered secrets are stored as a
salted hash. **This App stays read-only.** Nothing in the collection or scanning
path writes to your repositories.

### The separate write App, if you want checks or fix pull requests

Publishing a pull-request check, commenting on a pull request or opening a
dependency fix pull request needs write access, and that is deliberately **not**
this App. It is a second, opt-in App — "LimaCharlie Code Actions" — that you
create, install on the repositories you choose, and name on the provider record
with `github_actions_app_id`, `github_actions_installation_id` and
`actions_credentials`. The record is refused if it points at the same App, or the
same secret, as the read connection.

Its manifest, the permission union it needs and the wiring are in
[Code Scanning](../code-scanning.md#pull-request-checks-and-merge-gating).
