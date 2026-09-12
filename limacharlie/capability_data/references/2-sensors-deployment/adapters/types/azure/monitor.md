# Azure Monitor

Azure Monitor Logs are a feature of Azure Monitor that collect and organize log and performance data from monitored resources. See Microsoft's [Azure Monitor Logs reference](https://learn.microsoft.com/en-us/azure/azure-monitor/logs/data-platform-logs) for more detail.

LimaCharlie can ingest and natively parse Azure Monitor Logs.

## Log Ingestion

Azure Monitor logs can be ingested via:

- [Azure Event Hub](../azure-event-hub.md)
- LimaCharlie [Webhooks](../../tutorials/webhook-adapter.md)

When configuring the adapter, set `client_options.platform: azure_monitor` to select the dedicated parser. Upon ingestion, the log `category` field is used to define the Event Type and the `time` field provides the event timestamp.
