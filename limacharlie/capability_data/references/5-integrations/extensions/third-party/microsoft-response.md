# Microsoft Response

The Microsoft Response LimaCharlie Extension exposes the incident-response and investigation surface of Microsoft's cloud security platforms — **Microsoft Graph** (Entra ID identities, Identity Protection, groups, Intune devices, audit logs, and the Defender XDR security API for cross-product alerts, incidents, and advanced hunting) and **Microsoft Defender for Endpoint** (machine isolation, scans, forensics, file quarantine, alerts, file intelligence, custom indicators) — to D&R rules and AI agents. It enables automated investigation and containment of account and endpoint compromise directly from detections.

The extension provides two layers:

- **Typed actions** for the common containment, triage, and investigation workflows, with friendly parameter names and built-in safety rails.
- A generic **`api_call`** passthrough for any Graph or Defender endpoint not covered by a typed action.

Authentication is OAuth2 **client credentials** against an Entra app registration — no user interaction, no delegated tokens.

## Setup

### 1. Create an Entra app registration

In the Azure portal (**Entra ID → App registrations → New registration**), create an app registration and note its **Application (client) ID** and your **Directory (tenant) ID**. Create a **client secret** under *Certificates & secrets*.

### 2. Grant application permissions

Under *API permissions*, add **application** permissions (not delegated) and grant **admin consent**. The least-privilege set per capability:

| Capability | Permission | API |
| --- | --- | --- |
| List/read users | `User.Read.All` | Microsoft Graph |
| Disable / enable account | `User.EnableDisableAccount.All` | Microsoft Graph |
| Revoke sign-in sessions | `User.RevokeSessions.All` | Microsoft Graph |
| Reset password | `User-PasswordProfile.ReadWrite.All` | Microsoft Graph |
| List authentication methods | `UserAuthenticationMethod.Read.All` | Microsoft Graph |
| User group/role memberships (`list_user_groups`) | `Directory.Read.All` | Microsoft Graph |
| Risky users (read / confirm / dismiss) | `IdentityRiskyUser.ReadWrite.All` (`IdentityRiskyUser.Read.All` suffices for reads) | Microsoft Graph |
| Risk detections (`list_risk_detections`) | `IdentityRiskEvent.Read.All` | Microsoft Graph |
| Groups read / membership change | `GroupMember.ReadWrite.All` (`GroupMember.Read.All` suffices for reads) | Microsoft Graph |
| Sign-in & directory audit logs | `AuditLog.Read.All` | Microsoft Graph |
| Defender XDR alerts (read / update + comment) | `SecurityAlert.Read.All` / `SecurityAlert.ReadWrite.All` | Microsoft Graph |
| Defender XDR incidents (read / update) | `SecurityIncident.Read.All` / `SecurityIncident.ReadWrite.All` | Microsoft Graph |
| Advanced hunting (`run_hunting_query`) | `ThreatHunting.Read.All` | Microsoft Graph |
| Intune device actions | `DeviceManagementManagedDevices.PrivilegedOperations.All` (+ `DeviceManagementManagedDevices.Read.All` to list/get) | Microsoft Graph |
| Machine isolation | `Machine.Isolate` | WindowsDefenderATP |
| Antivirus scan | `Machine.Scan` | WindowsDefenderATP |
| Restrict app execution | `Machine.RestrictExecution` | WindowsDefenderATP |
| Collect investigation package | `Machine.CollectForensics` | WindowsDefenderATP |
| Stop & quarantine file | `Machine.StopAndQuarantine` | WindowsDefenderATP |
| List/get machines, machine actions, find-by-IP, package URI | `Machine.ReadWrite.All` | WindowsDefenderATP |
| Defender alerts (list/get/update) | `Alert.ReadWrite.All` (no app-only read-only permission exists) | WindowsDefenderATP |
| Logged-on users (`list_machine_logon_users`) | `User.Read.All` | WindowsDefenderATP |
| File profiles (`get_file_info`, file machines/alerts) | `File.Read.All` | WindowsDefenderATP |
| Advanced hunting (`run_advanced_query`) | `AdvancedQuery.Read.All` | WindowsDefenderATP |
| Custom indicators (IoCs) | `Ti.ReadWrite.All` | WindowsDefenderATP |

Only add what you will use — every action degrades independently with a `403` if its permission is missing.

> **Privileged user writes need a directory role too.** For `disable_user`, `enable_user`, and `reset_user_password`, Graph permissions alone are not sufficient: the app's service principal must also hold an Entra **directory role** (e.g. *User Administrator*) covering the target user. A `403` on these actions is a consent/role problem, not a bug.
>
> **Identity Protection requires Entra ID P2.** `list_risky_users`, `get_user_risk`, `confirm_user_compromised`, and `dismiss_user_risk` return `403` on tenants without a P2 license. `list_risk_detections` and the sign-in log (`list_sign_ins`, `get_signin_history`) require P1 or P2.

### 3. Subscribe to the extension

Subscribe to `ext-microsoft-response` from the LimaCharlie **Marketplace** (Extensions → Add-Ons).

### 4. Store the client secret

In **Secrets Manager**, create a new secret (for example `msft-response-client-secret`) and paste the client secret as its value.

### 5. Configure the extension

In **Extensions → ext-microsoft-response → Configuration**, fill in:

| Field | Required | Value |
| --- | --- | --- |
| `tenant_id` | yes | Entra (Azure AD) tenant ID (GUID) or a verified domain name. |
| `client_id` | yes | App registration Application (client) ID. |
| `client_secret` | yes | Reference to the secret created in step 4, e.g. `hive://secret/msft-response-client-secret`. |
| `login_base_url` | no | OAuth endpoint override for sovereign clouds. Default `https://login.microsoftonline.com`. |
| `graph_base_url` | no | Microsoft Graph base override. Default `https://graph.microsoft.com/v1.0`. |
| `defender_base_url` | no | Defender for Endpoint base override. Default `https://api.securitycenter.microsoft.com/api`. |

The three base-URL overrides support sovereign clouds (US Government GCC High / DoD, China 21Vianet); leave them empty for the public cloud.

## Actions

Every action that targets an entity requires an explicit selector (`user_id`, `device_id`, `machine_id`, …) — the extension refuses to run without one, preventing accidental fleet-wide containment.

### Common list parameters

The `list_*` actions share an OData query schema and return `{data: [...], pagination: {next_link}}`:

| Field | Type | Notes |
| --- | --- | --- |
| `filter` | string | OData `$filter`, e.g. `accountEnabled eq false`. |
| `select` | string | OData `$select` — comma-separated fields. |
| `search` | string | Free-text `$search`, e.g. `displayName:alex` (Graph sets `ConsistencyLevel: eventual` automatically). |
| `order_by` | string | OData `$orderby`, e.g. `createdDateTime desc`. |
| `top` | int | Page size, default `100`, clamped to `999`. |
| `count` | bool | Request a `$count`. |
| `next_link` | string | Opaque `@odata.nextLink` from a previous response — pass it back to fetch the next page. |
| `extra_query` | object | Raw query params merged into the request (escape hatch). |

### Generic

#### `api_call`

Generic passthrough to Graph or Defender for Endpoint.

| Field | Type | Notes |
| --- | --- | --- |
| `service` | enum | `graph` (default) or `defender`. Token audience is handled automatically. |
| `method` | enum | `GET` (default), `POST`, `PATCH`, `PUT`, `DELETE`. |
| `path` | string | **Required.** Path relative to the service base (e.g. `users/{id}/revokeSignInSessions`) or a full `@odata.nextLink` URL. |
| `query` | object | Query-string parameters (`$filter`, `$select`, `$top`, …). |
| `headers` | object | Extra request headers, e.g. `{"ConsistencyLevel": "eventual"}`. |
| `body` | object | JSON body for `POST`/`PATCH`/`PUT`. Note Defender bodies use PascalCase keys (`IsolationType`, `Comment`, …). |

### Entra ID identities

| Action | Parameters | What it does |
| --- | --- | --- |
| `list_users` | common list params | List/search users. Add `accountEnabled` to `select` to read it (not returned by default). |
| `get_user` | `user_id`, `select` | Get one user. Defaults to an investigation-oriented `$select` (`accountEnabled`, `createdDateTime`, `lastPasswordChangeDateTime`, `signInSessionsValidFromDateTime`, `proxyAddresses`, `otherMails`, ...). |
| `disable_user` | `user_id` | Set `accountEnabled=false` — blocks new sign-ins immediately. Reverse with `enable_user`. |
| `enable_user` | `user_id` | Re-enable a disabled user. |
| `revoke_sign_in_sessions` | `user_id` | Invalidate all refresh tokens / sessions, forcing re-authentication everywhere. Takes a few minutes to fully propagate. |
| `reset_user_password` | `user_id`, `password`, `force_change_password_next_sign_in` (default `true`) | Set a new password via `passwordProfile`. Requires a directory role (see Setup). |
| `list_auth_methods` | `user_id` | List registered authentication methods — spot attacker-registered MFA. |
| `list_user_groups` | `user_id` + common list params | List the groups, directory roles, and administrative units the user is a direct member of — check whether a compromised user holds privileged roles. |

`user_id` accepts either the user object ID (GUID) or the userPrincipalName (UPN).

For full account containment, combine `disable_user` with `revoke_sign_in_sessions`: disabling blocks new sign-ins, revoking kills existing sessions.

### Identity Protection (Entra ID P2)

| Action | Parameters | What it does |
| --- | --- | --- |
| `list_risky_users` | common list params | Users flagged by Identity Protection (`riskLevel`, `riskState`, `riskDetail`). |
| `get_user_risk` | `user_id` | One user's riskyUser record. Accepts a GUID or a UPN (the UPN is resolved with one extra lookup). A `404` means the user has no risk record. |
| `list_risk_detections` | common list params | Individual risk detections (`riskEventType` like `passwordSpray`, `impossibleTravel`, `leakedCredentials`; `ipAddress`, `location`, `detectedDateTime`). P1 tenants see premium detections as `riskEventType=generic`. Page size caps at 500. |
| `confirm_user_compromised` | `user_ids` (list of GUIDs) | Mark users confirmed-compromised, raising risk to high (drives risk-based Conditional Access). |
| `dismiss_user_risk` | `user_ids` (list of GUIDs) | Clear the risk on users. Max 60 per call. |

### Directory & audit reads

| Action | Parameters | What it does |
| --- | --- | --- |
| `list_groups` | common list params | List groups (e.g. find a quarantine or privileged group). |
| `get_group` | `group_id`, `select` | Get one group by object id. |
| `list_group_members` | `group_id` + common list params | List a group's direct members — enumerate who sits in a privileged group. |
| `list_sign_ins` | common list params | Entra sign-in events. Always scope with a `createdDateTime` filter. |
| `get_signin_history` | `user_id`, `days` (default 7), `filter`, `top`, `next_link` | One user's sign-ins over a trailing window, newest first. Builds the `$filter` for you (GUID → `userId`, otherwise `userPrincipalName`); `filter` is AND-ed on top (e.g. `status/errorCode eq 0`). Key fields: `createdDateTime`, `ipAddress`, `location`, `deviceDetail`, `status.errorCode`, `riskLevelDuringSignIn`. |
| `list_directory_audits` | common list params | Directory audit log — who changed what. |

### Microsoft Defender XDR (Graph security API)

Cross-product alerts and incidents from Defender for Endpoint / Office 365 / Identity / Cloud Apps, Entra ID Protection, and Sentinel. Enum values here are **camelCase** (`new`, `inProgress`, `resolved`) — unlike the Defender for Endpoint API below.

| Action | Parameters | What it does |
| --- | --- | --- |
| `list_security_alerts` | `filter`, `top`, `next_link`, `extra_query` | List XDR alerts (`security/alerts_v2`). Filterable on `createdDateTime`, `severity`, `status`, `serviceSource`, `classification`, `determination`, `assignedTo`. Evidence is embedded in each alert. |
| `get_security_alert` | `alert_id` | One XDR alert with evidence (devices, files, processes, IPs, users), MITRE techniques, comments. |
| `update_security_alert` | `alert_id`, `status`, `classification`, `determination`, `assigned_to` | Triage an alert; only provided fields change. Returns the updated alert. |
| `add_security_alert_comment` | `alert_id`, `comment` | Append a comment (e.g. record the automated response taken). Returns the alert's full comment list. |
| `list_security_incidents` | `filter`, `top`, `next_link`, `extra_query` | List XDR incidents. Add `extra_query: {"$expand": "alerts"}` to embed each incident's alerts. |
| `get_security_incident` | `incident_id` | One incident (numeric-string id, e.g. `"29"`). |
| `update_security_incident` | `incident_id`, `status` (`active`/`resolved`/`redirected`), `classification`, `determination`, `assigned_to`, `resolving_comment`, `custom_tags` | Triage an incident. `custom_tags` **replaces** the tag list (an explicit empty list clears it). |
| `run_hunting_query` | `query`, `timespan` | Run a KQL query against the XDR advanced-hunting tables. Returns `{schema, results}`. Default lookback 30 days; max 100,000 rows. |

### Group containment

| Action | Parameters | What it does |
| --- | --- | --- |
| `add_group_member` | `group_id`, `user_id` | Add a user to a group — e.g. drop a compromised user into a Conditional-Access block/quarantine group. |
| `remove_group_member` | `group_id`, `user_id` | Remove a user from a group — e.g. strip a compromised user out of a privileged group. |

### Intune devices

| Action | Parameters | What it does |
| --- | --- | --- |
| `list_managed_devices` | common list params | List Intune-managed devices (`deviceName`, `complianceState`, `userPrincipalName`, …). |
| `get_managed_device` | `device_id`, `select` | Get one managed device (`osVersion`, `isEncrypted`, `lastSyncDateTime`, `azureADDeviceId`, …). |
| `wipe_device` | `device_id`, `keep_enrollment_data`, `keep_user_data`, `data` | Factory-reset a device. **Destructive.** |
| `retire_device` | `device_id` | Remove company data and MDM policies, leave personal data. |
| `remote_lock_device` | `device_id` | Remote-lock the device. |
| `reset_device_passcode` | `device_id` | Reset the device passcode. |
| `reboot_device` | `device_id` | Immediate reboot. |

`device_id` is the Intune `managedDevice` id from `list_managed_devices`.

### Defender for Endpoint investigation

Read-side actions against the Defender for Endpoint API. Enum values here are **PascalCase** (`New`, `InProgress`, `Resolved`) — unlike the Graph security API above.

| Action | Parameters | What it does |
| --- | --- | --- |
| `get_machine` | `machine_id` | One machine (`computerDnsName`, `lastIpAddress`, `lastExternalIpAddress`, `healthStatus`, `riskScore`, `exposureLevel`, `machineTags`). |
| `find_machines_by_ip` | `ip`, `timestamp` (default now) | Machines seen with an **internal** IP within ±15 minutes of the timestamp (last 30 days only). |
| `list_alerts` | `filter`, `top`, `next_link`, `extra_query` | List Defender for Endpoint alerts. Filterable on `alertCreationTime`, `status`, `severity`, `category`, `detectionSource`, `machineId`. Add `extra_query: {"$expand": "evidence"}` to embed evidence. |
| `get_alert` | `alert_id` | One alert (`title`, `severity`, `status`, `machineId`, `relatedUser`, `comments`, `mitreTechniques`). |
| `update_alert` | `alert_id`, `status`, `classification`, `determination`, `assigned_to`, `comment` | Triage an alert and/or add a comment; only provided fields change. |
| `list_machine_alerts` | `machine_id` | All alerts related to one machine. |
| `list_machine_logon_users` | `machine_id` | Users Defender saw log on to the machine (`accountName`, `firstSeen`/`lastSeen`, `logonTypes`, `isDomainAdmin`) — who else may be compromised. |
| `get_file_info` | `file_hash` (SHA1 or SHA256) | Defender's file profile: `globalPrevalence`, `signer`/`issuer`, `isValidCertificate`, `determinationType`/`determinationValue`. |
| `list_file_machines` | `sha1` | Machines a file was observed on — scope how far it spread. **SHA1 only**; unknown hash returns an empty list. |
| `list_file_alerts` | `sha1` | Alerts related to a file. **SHA1 only**. |
| `run_advanced_query` | `query` | Run a KQL query against the Defender for Endpoint hunting tables. Returns `{Schema, Results}`. 30-day window, max 100,000 rows. For cross-product tables prefer `run_hunting_query`. |
| `list_indicators` | `filter`, `top`, `next_link`, `extra_query` | The tenant's custom indicators (IoCs); use a returned `id` with `delete_indicator`. |

### Defender for Endpoint machines

Machine actions are **asynchronous**: they return a `machineAction` object with `status: Pending`, and the work completes in the background. Poll with `get_machine_action` until `Succeeded` / `Failed`. All take an optional `comment` recorded in the Defender action audit (default `Automated response via LimaCharlie`) and an optional `data` object merged into the payload.

| Action | Parameters | What it does |
| --- | --- | --- |
| `list_machines` | common list params | List Defender machines (`computerDnsName`, `riskScore`, `exposureLevel`, …). |
| `isolate_machine` | `machine_id`, `isolation_type` (`Full` default, or `Selective`) | Network-isolate a machine. `Selective` keeps Teams/Outlook working. |
| `unisolate_machine` | `machine_id` | Release from isolation. |
| `run_antivirus_scan` | `machine_id`, `scan_type` (`Quick` default, or `Full`) | Trigger a Defender AV scan. |
| `restrict_app_execution` | `machine_id` | Only Microsoft-signed binaries may run. |
| `unrestrict_app_execution` | `machine_id` | Remove the execution restriction. |
| `collect_investigation_package` | `machine_id` | Collect a forensics package. |
| `stop_and_quarantine_file` | `machine_id`, `sha1` | Stop running instances of a file (by SHA-1) and quarantine it. |
| `list_machine_actions` | common list params | The response-action audit/queue. |
| `get_machine_action` | `action_id` | Poll one machine action's status (`Pending` / `InProgress` / `Succeeded` / `Failed`). |
| `get_investigation_package_uri` | `action_id` | Short-lived SAS download URL for a **succeeded** `collect_investigation_package` action. A `404` usually means the collection hasn't finished. Rate-limited to 2 calls/minute. |

### Custom indicators

#### `create_indicator`

Create a Defender custom threat indicator to block or alert on an IoC across the tenant.

| Field | Type | Notes |
| --- | --- | --- |
| `indicator_value` | string | **Required.** The IoC value. |
| `indicator_type` | enum | **Required.** `FileSha1`, `FileSha256`, `FileMd5`, `IpAddress`, `DomainName`, `Url`, `CertificateThumbprint`. |
| `action` | enum | **Required.** `Alert`, `Warn`, `Block`, `Audit`, `BlockAndRemediate`, `AlertAndBlock`, `Allowed`. |
| `title` | string | **Required.** Indicator title. |
| `description` | string | **Required.** Indicator description. |
| `severity` | enum | `Informational`, `Low`, `Medium` (default), `High`. |
| `expiration_time` | string | ISO-8601 UTC expiry; omit for no expiry. |
| `recommended_actions` | string | Recommended-actions text shown with the alert. |
| `generate_alert` | bool | Generate an alert on match. **Required `true` when `action` is `Audit`.** |
| `data` | object | Extra fields merged into the payload (e.g. `rbacGroupNames`). |

#### `delete_indicator`

Delete one custom indicator by its `indicator_id` (from `list_indicators` or the `create_indicator` response) — e.g. to lift a block.

## Detection & Response

Example response action that isolates the Defender machine named in a detection:

```yaml
- action: extension request
  extension action: isolate_machine
  extension name: ext-microsoft-response
  extension request:
    machine_id: '{{ .event/machine_id }}'
    isolation_type: '{{ "Full" }}'
    comment: '{{ "Isolated by LimaCharlie D&R rule" }}'
```

> **Wrap literal strings in `{{ "..." }}`.**
> Values under `extension request` are evaluated as templates. A bare string without `{{ }}` is interpreted as a [gjson](https://github.com/tidwall/gjson) path against the event and, if it doesn't resolve, the key is silently dropped from the payload.

`extension request` actions are fire-and-forget — the rule engine does not surface the response back into the rule's evaluation context, so a `machineAction` id is not available to a subsequent action in the same rule. Workflows that chain (look up the machine, isolate it, poll the action, collect forensics) belong in a [Playbook](../limacharlie/playbook.md) or an AI agent, which can hold ids between calls.

## Notes

- Two alert/hunting surfaces are deliberately both exposed: the **Graph security API** actions (`*_security_alert`, `*_security_incident`, `run_hunting_query`) cover all of Defender XDR with camelCase enums, while the **Defender for Endpoint API** actions (`list_alerts`, `get_alert`, `update_alert`, `run_advanced_query`) are endpoint-only with PascalCase enums and machine-centric fields (`machineId`, `computerDnsName`).
- Graph and Defender use **separate token audiences**; the extension caches one token per service and renews it before expiry. A token rejected by the other service surfaces as `403`, not `401`.
- A single `401` is treated as a token-expiry race: the cached token is dropped and the request retried once with a fresh token. Rotating `client_secret` in Secrets Manager recovers the same way — the next auth failure evicts the cached client and re-reads the secret.
- Microsoft Graph throttling (`429`) is **not** retried by the extension; throttled requests surface to the caller.
- Error messages are formatted `microsoft <service> api <status> on <path>: <code>: <message>`, with query strings redacted.
- Unsubscribing from the extension preserves its saved configuration; re-subscribing restores it without reconfiguration.
