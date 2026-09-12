# Microsoft Defender

## Overview

LimaCharlie can ingest [Microsoft 365 Defender logs](https://learn.microsoft.com/en-us/microsoft-365/security/defender/microsoft-365-defender?view=o365-worldwide) via three methods [Azure Event Hub](azure-event-hub.md) Adapter, the [Microsoft Defender API](https://learn.microsoft.com/en-us/defender-endpoint/api/exposed-apis-create-app-nativeapp), or a Custom Webhook

Microsoft has [documentation for creating an Event Hub](https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-create).

Telemetry Platform: `msdefender`

> Use `client_options.platform: msdefender` for **both** ingestion methods. The `msdefender` parser understands the Streaming API `records` envelope (Event Hub) as well as bare Graph `alerts_v2` alert objects (API adapter), extracting event types and timestamps automatically and mapping raw device telemetry to native LimaCharlie event types (`NEW_PROCESS`, `NETWORK_CONNECTIONS`, etc.) with one sensor per Defender device. Do not substitute `json` — it bypasses this parser and requires manual field mappings.

## Data Collected

### API vs Event Hub Comparison

| Method | Data Source | What You Get | Use Case |
|--------|-------------|--------------|----------|
| **Defender API** | Microsoft Graph API | Security Alerts only | Alert-focused monitoring |
| **Azure Event Hub** | Defender Streaming API | Raw telemetry events | Full visibility into endpoint activity |

### Microsoft Defender API

The API adapter polls Microsoft Graph's `/security/alerts_v2` endpoint every 30 seconds. This provides **security alerts** from Microsoft Defender products including:

- Defender for Endpoint
- Defender for Office 365
- Defender for Identity
- Defender for Cloud Apps

These are curated, high-fidelity alerts that Microsoft has already correlated and enriched.

For alert schema details, see [Microsoft's alerts_v2 API documentation](https://learn.microsoft.com/en-us/graph/api/resources/security-alert).

### Azure Event Hub (Streaming API)

When using Event Hub with Defender, you receive **raw telemetry** via the Defender Streaming API. This includes detailed event tables such as:

- **DeviceProcessEvents** - Process creation and execution
- **DeviceNetworkEvents** - Network connections
- **DeviceFileEvents** - File operations
- **DeviceLogonEvents** - Authentication events
- **DeviceRegistryEvents** - Registry modifications
- **DeviceEvents** - Miscellaneous security events

This provides full endpoint telemetry for custom detection rules and threat hunting.

For the complete list of supported streaming event types, see [Microsoft's Defender XDR streaming event types documentation](https://learn.microsoft.com/en-us/defender-xdr/supported-event-types).

### Defender API Configuration

To collect data via the Microsoft Defender API, configure an App Registration in Azure with the following permission:

- `SecurityAlert.Read.All`

Then create a Defender adapter in LimaCharlie with:

- Tenant ID
- Client ID
- Client Secret
- Endpoint (optional) — see below

#### National clouds (GCC High, DoD)

US Government tenants are network-isolated from the commercial cloud: they authenticate against a different identity host and call a different Microsoft Graph service root, and an access token issued by one deployment is **not** valid against another. The optional `endpoint` option selects the deployment:

| `endpoint` | Deployment | Identity host | Microsoft Graph |
|------------|------------|---------------|-----------------|
| `enterprise` (default) | Global / commercial | `login.microsoftonline.com` | `graph.microsoft.com` |
| `gcc-gov` | Microsoft 365 GCC (moderate) | `login.microsoftonline.com` | `graph.microsoft.com` |
| `gcc-high-gov` | US Government GCC High (L4) | `login.microsoftonline.us` | `graph.microsoft.us` |
| `dod-gov` | US Government DoD (L5) | `login.microsoftonline.us` | `dod-graph.microsoft.us` |

Leaving `endpoint` empty keeps the commercial endpoints, so existing adapters need no change. Microsoft 365 GCC (moderate) runs on the worldwide endpoints — `gcc-gov` exists so the deployment can be named explicitly and behaves identically to `enterprise`. Register the application in the government portal (`portal.azure.us`) rather than `portal.azure.com`.

The same four values are used by the [Microsoft Entra ID](microsoft-entra-id.md) adapter, where `endpoint` is likewise optional, and by the [Microsoft 365](microsoft-365.md) adapter, where it is **required** (that adapter calls the Office 365 Management Activity API, which has a distinct host per deployment including GCC moderate).

## Deployment Configurations

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: the type of data ingested through this adapter, like `text`, `json`, `gcp`, `carbon_black`, etc.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from, see below.

### Adapter-specific Options

- `connection_string` - The connection string provided in Azure for connecting to the Azure Event Hub, including the `EntityPath=...` at the end which identifies the Hub Name (this component is sometimes now shown in the connection string provided by Azure).
- `endpoint` - API adapter only. The Microsoft national cloud the tenant lives in: `enterprise` (default), `gcc-gov`, `gcc-high-gov` or `dod-gov`. See [National clouds](#national-clouds-gcc-high-dod).

## Guided Deployment

In the LimaCharlie web app, you can find a Microsoft Defender helper for connecting to an existing Azure Event Hub and ingesting Microsoft Defender logs.

### CLI Deployment

The following example configuration ingests Microsoft Defender logs from an Azure Event Hub to LimaCharlie.

```bash
./lc_adapter azure_event_hub client_options.identity.installation_key=<INSTALLATION_KEY> \
client_options.identity.oid=<OID> \
client_options.platform=msdefender \
client_options.sensor_seed_key=<SENSOR_SEED_KEY> \
client_options.hostname=msdefender \
"connection_string=Endpoint=sb://mynamespace.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=fnaaaaaaaaaaaaaaak0g54alYbbbbbbbbbbbbbbbALQ=;EntityPath=lc-stream"
```

### Infrastructure as Code Deployment

```python
# For cloud sensor deployment, store credentials as hive secrets:

#   tenant_id: "hive://secret/azure-tenant-id"
#   client_id: "hive://secret/defender-client-id"
#   client_secret: "hive://secret/defender-client-secret"

sensor_type: "defender"
defender:
  tenant_id: "hive://secret/azure-tenant-id"
  client_id: "hive://secret/azure-defender-client-id"
  client_secret: "hive://secret/azure-defender-client-secret"
  # Optional; omit for a commercial tenant. One of enterprise (default),
  # gcc-gov, gcc-high-gov, dod-gov.
  endpoint: "enterprise"
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_DEFENDER"
    hostname: "ms-defender-adapter"
    platform: "msdefender"
    sensor_seed_key: "defender-sensor"
    indexing: []
```
