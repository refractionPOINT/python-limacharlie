# Azure Event Hub

## Overview

This Adapter allows you to connect to an Azure Event Hub to fetch structured data stored there.

[Azure Event Hubs](https://azure.microsoft.com/en-us/products/event-hubs) are fully managed, real-time data ingestion services that allow for event streaming from various Microsoft Azure services. LimaCharlie can ingest either structured known data (such as JSON or XML) *or* known Microsoft data types, including:

- Azure Monitor (Platform: `azure_monitor`)
- Entra ID [formerly Azure AD] (Platform: `azure_ad`)
- Microsoft Defender (Platform: `msdefender`)
- Azure Key Vault (Platform: `azure_key_vault`)
- Azure Kubernetes Service (Platform: `azure_kubernetes_service`)
- Azure Network Security Group (Platform: `azure_network_security_group`)
- Azure SQL Audit (Platform: `azure_sql_audit`)

> **Choosing the platform:** the Event Hub is only a transport — `client_options.platform` selects the LimaCharlie parser and must match the data being streamed **into** the hub (see the list above). Use `json` only for custom or unknown data, in which case you must supply your own `mapping`. Note that `azure_event_hub_namespace` is **not** a generic value for "data arriving via Event Hub": it is used solely for ingesting an Event Hub namespace's own diagnostic logs.

Microsoft has [documentation for creating an Event Hub](https://learn.microsoft.com/en-us/azure/event-hubs/event-hubs-create).

## Configuring Data Streams

When using Azure Event Hub, you must configure the source service to stream data to your Event Hub. The data you receive depends entirely on what you configure in Azure.

### For Entra ID (`azure_ad`)

Configure **Azure AD Diagnostic Settings** to stream to your Event Hub:

1. In Azure Portal, go to **Entra ID** > **Diagnostic settings**
2. Add a diagnostic setting and select your Event Hub
3. Choose which logs to stream (SignInLogs, AuditLogs, etc.)

See: [Stream Entra ID logs to Event Hub](https://learn.microsoft.com/en-us/entra/identity/monitoring-health/howto-stream-logs-to-event-hub)

### For Microsoft Defender (`msdefender`)

Configure **Defender Streaming API** to export raw telemetry:

1. In Microsoft Defender portal, go to **Settings** > **Streaming API**
2. Add your Event Hub connection
3. Select which event types to stream (DeviceProcessEvents, DeviceNetworkEvents, etc.)

See: [Defender XDR streaming event types](https://learn.microsoft.com/en-us/defender-xdr/supported-event-types)

### For Azure Monitor (`azure_monitor`)

Configure **Diagnostic Settings** on individual Azure resources:

1. Navigate to the Azure resource you want to monitor
2. Go to **Diagnostic settings** and add a setting
3. Select your Event Hub and choose logs/metrics to stream

See: [Stream Azure platform logs to Event Hub](https://learn.microsoft.com/en-us/azure/azure-monitor/essentials/stream-monitoring-data-event-hubs)

## Deployment Configurations

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: the type of data ingested through this adapter, like `text`, `json`, `gcp`, `carbon_black`, etc.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from, see below.

### Adapter-specific Options

- If using a binary Adapter, `azure_event_hub` will be the ingestion type.
- `connection_string` - The connection string provided in Azure for connecting to the Azure Event Hub, including the `EntityPath=...` at the end which identifies the Hub Name (this component is sometimes now shown in the connection string provided by Azure).

## Guided Deployment

Azure Event Hub data can be pulled via either a cloud or binary Adapter.

### Cloud-to-Cloud

LimaCharlie offers several helpers within the webapp that allow you to ingest Microsoft data, such as Entra ID or Microsoft Defender, from Azure Event Hubs.

### CLI Deployment

The following example configures a binary Adapter to collect Microsoft Defender data from an Azure Event Hub:

```bash
./lc_adapter azure_event_hub client_options.identity.installation_key=<INSTALLATION_KEY> \
client_options.identity.oid=<OID> \
client_options.platform=msdefender \
client_options.sensor_seed_key=<SENSOR_SEED_KEY> \
client_options.hostname=<HOSTNAME> \
"connection_string=Endpoint=sb://mynamespace.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=fnaaaaaaaaaaaaaaak0g54alYbbbbbbbbbbbbbbbALQ=;EntityPath=lc-stream"
```

### Infrastructure as Code Deployment

```python
sensor_type: "azure_event_hub"
azure_event_hub:
  connection_string: "Endpoint=sb://your-eventhub-namespace.servicebus.windows.net/;SharedAccessKeyName=RootManageSharedAccessKey;SharedAccessKey=YOUR_EVENT_HUB_SHARED_ACCESS_KEY_HERE;EntityPath=your-actual-event-hub-name"
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_FOR_AZURE"
    hostname: "azure-eventhub-adapter"
    # Match the feed streamed into the hub: msdefender, azure_ad, azure_monitor, etc.
    # Only use "json" for custom data, together with a manual mapping.
    platform: "msdefender"
    sensor_seed_key: "azure-eventhub-prod-sensor"
    indexing: []
```
