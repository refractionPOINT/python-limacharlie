# Azure Storage Blob

Output events and detections to a Blob Container in Azure Storage Blobs.

- `secret_key`: the secret access key for the Blob Container.
- `blob_container`: the name of the Blob Container to upload to.
- `account_name`: the account name used to authenticate in Azure.

Example:

```text
blob_container: testlcdatabucket
account_name: lctestdata
secret_key: dkndsgnlngfdlgfd
```

## Related articles

- [Azure Kubernetes Service (AKS)](../../../2-sensors-deployment/adapters/types/azure/kubernetes-service.md)
- [Azure Monitor](../../../2-sensors-deployment/adapters/types/azure/monitor.md)
- [Azure Network Security Group](../../../2-sensors-deployment/adapters/types/azure/network-security-group.md)
- [Azure SQL Audit Logs](../../../2-sensors-deployment/adapters/types/azure/sql-audit-logs.md)
- [Azure Event Hub](../../../2-sensors-deployment/adapters/types/azure-event-hub.md)
- [Microsoft Entra ID](../../../2-sensors-deployment/adapters/types/microsoft-entra-id.md)
- [Azure](../../extensions/cloud-cli/azure.md)
- [Elastic](elastic.md)
