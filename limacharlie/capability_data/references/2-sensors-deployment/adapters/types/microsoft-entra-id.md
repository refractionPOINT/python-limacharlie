# Microsoft Entra ID

[Microsoft Entra ID](https://www.microsoft.com/en-us/security/business/identity-access/microsoft-entra-id), formerly Azure Active Directory, is an identity and access management solution from Microsoft that helps organizations secure and manage identities for hybrid and multicloud environments.

The Entra ID API Adapter polls Microsoft Graph directly and can collect three streams: Identity Protection **risk detections**, **sign-in logs** and **directory audit logs**. Because it only needs an Entra app registration — no Azure subscription or Event Hub — it is the lowest-friction way to standardize Entra telemetry collection across tenants. Data received via an Azure Event Hub or Webhook will be unique to your custom output parameters.

Entra ID data uses one of two platform values depending on the ingestion method — they are **not** interchangeable:

- **Azure Event Hub / Webhook** (diagnostic settings log stream — SignInLogs, AuditLogs, etc.): `client_options.platform: azure_ad`
- **Entra ID API** (risk detections, sign-in logs and directory audit logs polled from Microsoft Graph): `client_options.platform: entraid`

> **Note on naming:** The platform identifier `azure_ad` reflects the legacy product name (Azure Active Directory). Microsoft renamed this product to Microsoft Entra ID in 2023. Despite naming the same product, `azure_ad` and `entraid` select different parsers: `azure_ad` parses the Azure diagnostic-stream `records` envelope (event type from `category`, timestamp from `time`), while `entraid` parses the Graph objects directly (event type from `activity`/`category`, or `SignIn` for sign-in records; timestamp from `detectedDateTime`/`activityDateTime`/`createdDateTime` depending on the stream). Crossing them silently breaks event-type and timestamp extraction.
>
> **Choosing by data need:** Directory audit events — app consent (`Consent to application`), OAuth2 permission grants (`Add OAuth2PermissionGrant`), app role assignments, user/group/role changes — are available from the API adapter's `audit_logs` stream, from the diagnostic-stream **AuditLogs** category (Event Hub, platform `azure_ad`), or from the Microsoft 365 unified audit log ([`office365` adapter](microsoft-365.md), `Audit.AzureActiveDirectory` content type, where operation names carry a trailing period). Also prefer `azure_ad` over `azure_monitor` for Entra streams: both parse the same envelope, but the platform value tags the sensor and drives `is platform` / LCQL targeting and shared detection rules.

## Data Collected

### API vs Event Hub vs Webhook Comparison

| Method | Data Source | What You Get | Platform |
|--------|-------------|--------------|----------|
| **Entra ID API** | Microsoft Graph API | Risk detections, sign-in logs, directory audit logs (selectable streams) | `entraid` |
| **Azure Event Hub** | Azure Diagnostic Settings | Whatever logs you configure (sign-in, audit, etc.) | `azure_ad` |
| **Webhook** | Your configuration | Whatever you send to the webhook URL | `azure_ad` (if relaying the diagnostic-stream format) |

### Entra ID API

The API adapter polls Microsoft Graph every 30 seconds. The `streams` option selects which collections it polls, as comma separated values:

| Stream | Graph endpoint | What You Get | LimaCharlie event type |
|--------|----------------|--------------|------------------------|
| `risk_detections` (default) | `/identityProtection/riskDetections` | Identity Protection risk detection alerts (risky sign-ins, leaked credentials, anonymous IPs, malware-linked IPs, …) | the detection's `activity` (e.g. `signin`) |
| `sign_ins` | `/auditLogs/signIns` | Interactive sign-in events (user, app, IP, location, device, conditional access result) | `SignIn` |
| `audit_logs` | `/auditLogs/directoryAudits` | Directory changes: user/group/role management, app registrations, app consent and OAuth2 permission grants | the audit's `category` (e.g. `UserManagement`, `ApplicationManagement`) |

For example, `streams: risk_detections,sign_ins,audit_logs` collects everything; leaving the option empty collects risk detections only, matching the historical behavior of existing deployments.

For the full list of risk detection types, see [Microsoft's documentation](https://learn.microsoft.com/en-us/entra/id-protection/concept-identity-protection-risks).

**Requirements per stream:**

- `risk_detections` requires the `IdentityRiskEvent.Read.All` application permission. Note the tenant only produces risk detections with Entra ID Identity Protection (P2 for the full detection set).
- `sign_ins` requires the `AuditLog.Read.All` and `Directory.Read.All` application permissions, and the tenant must hold an Entra ID P1 (or P2) license — a Microsoft Graph requirement, the same one that applies to streaming SignInLogs to an Event Hub.
- `audit_logs` requires the `AuditLog.Read.All` application permission.

#### National clouds (GCC High, DoD)

US Government tenants are network-isolated from the commercial cloud: they authenticate against a different identity host and call a different Microsoft Graph service root, and an access token issued by one deployment is **not** valid against another. The optional `endpoint` option selects the deployment:

| `endpoint` | Deployment | Identity host | Microsoft Graph |
|------------|------------|---------------|-----------------|
| `enterprise` (default) | Global / commercial | `login.microsoftonline.com` | `graph.microsoft.com` |
| `gcc-gov` | Microsoft 365 GCC (moderate) | `login.microsoftonline.com` | `graph.microsoft.com` |
| `gcc-high-gov` | US Government GCC High (L4) | `login.microsoftonline.us` | `graph.microsoft.us` |
| `dod-gov` | US Government DoD (L5) | `login.microsoftonline.us` | `dod-graph.microsoft.us` |

Leaving `endpoint` empty keeps the commercial endpoints, so existing adapters need no change. Microsoft 365 GCC (moderate) runs on the worldwide endpoints — `gcc-gov` exists so the deployment can be named explicitly and behaves identically to `enterprise`.

All three streams (`risk_detections`, `sign_ins`, `audit_logs`) are available in both US Government L4 and L5. Register the application in the government portal (`portal.azure.us`) rather than `portal.azure.com`; the app registration, permissions and admin consent steps below are otherwise the same.

The same four values are used by the [Microsoft Defender](microsoft-defender.md) adapter, where `endpoint` is likewise optional, and by the [Microsoft 365](microsoft-365.md) adapter, where it is **required** (that adapter calls the Office 365 Management Activity API, which has a distinct host per deployment including GCC moderate).

### Azure Event Hub

When using Event Hub, you receive whatever data you configure Azure to stream. You must configure **Azure Diagnostic Settings** in Entra ID to send logs to your Event Hub. Common log types include:

- **Sign-in logs** - Interactive and non-interactive authentication events
- **Audit logs** - Directory changes (user/group management, app registrations, app consent and OAuth2 permission grants)
- **Provisioning logs** - User provisioning to SaaS apps
- **Risky users/sign-ins** - Identity Protection detections (alternative to API)

In the `azure_ad` stream the LimaCharlie event type is the log *category* (e.g. `AuditLogs`, `SignInLogs`), so detection rules targeting a specific operation match on the `event/operationName` field.

See [Microsoft's documentation on streaming Entra ID logs](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/howto-stream-logs-to-event-hub).

## Adapter Deployment

Microsoft Entra ID logs are ingested into LimaCharlie via:

1. Azure Event Hub
2. Entra ID API
3. Webhooks

### Azure Event Hub

Within the LimaCharlie web app, there is a helper that can be used to easily configure receiving Entra ID events via an Azure Event Hub.

If utilizing the helper, only two fields are required:

- Name for the adapter
- Connection string to the Azure Event Hub

See the [Azure Event Hub Adapter documentation](azure-event-hub.md) for more information.

Microsoft has [documentation for creating an Event Hub](https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-create).

### Entra ID API

To collect data via the Entra ID API, you'll need to configure an App Registration in Azure and ensure it has the correct permissions.

1. In Azure, navigate to the Entra ID Overview page. Select **App Registrations** and click `+ New Registration`.
2. Name the application, and select the **Supported account types**.
3. After registering an App, you'll be provided metadata for that application. Take note of the `Application (client) ID` and `Directory (tenant) ID` fields, as you will need them for configuration.
4. Select **Add a certificate or secret,** and create a new client secret. Provide a description and select an applicable Expiration time. *Note: You will need to refresh the Secret in LimaCharlie once it expires!*
5. After creating the secret, copy the `Secret Value`. You will need this to configure the LimaCharlie Adapter.
6. Navigate to the **Manage** > **API permissions** menu for your newly-created application. Grant the **Application** permissions required by the streams you plan to collect (see [Requirements per stream](#entra-id-api)):

   1. IdentityRiskEvent.Read.All (`risk_detections`)
   2. AuditLog.Read.All (`sign_ins`, `audit_logs`)
   3. Directory.Read.All (`sign_ins`)
   4. User.Read (default)

7. Click **Grant admin consent** for the tenant — application permissions have no effect until an admin consents.

Create a new Adapter within LimaCharlie, and select Microsoft Entra ID. Select `Microsoft Entra ID API` as the ingestion method.

1. Name the Adapter and provide the following details:

   1. Tenant ID
   2. Client ID
   3. Client Secret
   4. Streams (optional): comma separated values among `risk_detections`, `sign_ins` and `audit_logs`; empty means `risk_detections` only
   5. Endpoint (optional): the Microsoft national cloud the tenant lives in — `enterprise`, `gcc-gov`, `gcc-high-gov` or `dod-gov`. Leave it empty for a commercial tenant; see [National clouds](#national-clouds-gcc-high-dod)
   6. *Note: You can use the Secrets Manager for these values if you wish!*

Click **Complete Cloud Installation**, and the Adapter should be created successfully. Monitor the **Platform Logs** for any errors.

**Note:** Collection starts from the moment the Adapter is created (there is no historical backfill), so a stream only produces events as new ones occur. For `risk_detections` in particular, silence after creation usually just means no risky events have happened yet!

### Webhooks

Within the LimaCharlie web app, there is a helper that can be used to easily configure receiving Entra ID events.

If utilizing the helper, only two fields are required:

- Name for the adapter
- Secret component of the URL for the webhook

More information about creating a webhook and obtaining the completed URL, utilizing the secret component, [can be found here](../tutorials/webhook-adapter.md).
