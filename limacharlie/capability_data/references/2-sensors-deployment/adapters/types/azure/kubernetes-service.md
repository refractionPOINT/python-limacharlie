# Azure Kubernetes Service (AKS)

[Azure Kubernetes Service](https://azure.microsoft.com/en-us/products/kubernetes-service) (AKS) is a quick way to start developing and deploying cloud-native apps in Azure. LimaCharlie can ingest Azure Kubernetes Service logs.

Microsoft has [more information about Azure Kubernetes logs and metrics](https://learn.microsoft.com/en-us/azure/azure-monitor/containers/container-insights-livedata-overview).

## Log Ingestion

AKS logs can be ingested via:

- [Azure Event Hub](../azure-event-hub.md)
- LimaCharlie [Webhooks](../../tutorials/webhook-adapter.md)

When configuring the adapter, set `client_options.platform: azure_kubernetes_service` to select the dedicated parser. Upon ingestion, the log `category` field is used to define the Event Type and the `time` field provides the event timestamp.
