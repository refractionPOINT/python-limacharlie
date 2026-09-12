# Azure SQL Audit Logs

Microsoft Azure SQL is a scalable, cloud-hosted database that integrates with the Azure ecosystem. See Microsoft's [Azure SQL Database product page](https://azure.microsoft.com/en-us/products/azure-sql/database) for more detail.

LimaCharlie can ingest and natively parse Azure SQL Server audit logs.

## Log Ingestion

Azure SQL Server audit logs can be ingested via:

- [Azure Event Hub](../azure-event-hub.md)
- LimaCharlie [Webhooks](../../tutorials/webhook-adapter.md)

When configuring the adapter, set `client_options.platform: azure_sql_audit` to select the dedicated parser. Upon ingestion, the log `category` field is used to define the Event Type and the `time` field provides the event timestamp.
