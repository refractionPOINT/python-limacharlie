# Adapters

Adapters enable log ingestion from external sources into LimaCharlie. They transform various log formats into normalized LimaCharlie events.

## Deployment Options

- [Deployment Guide](deployment.md) - How to deploy adapters
- [Adapters as a Service](as-a-service.md) - Cloud-managed adapter deployment
- [Usage & Configuration](usage.md) - Configuration options and best practices

## Adapter Types

### Cloud Providers

- [AWS CloudTrail](types/aws-cloudtrail.md)
- [AWS GuardDuty](types/aws-guardduty.md)
- [AWS S3](types/s3.md)
- [Azure Event Hub](types/azure-event-hub.md)
- [GCP Pub/Sub](types/google-cloud-pubsub.md)
- [GCP Storage](types/google-cloud-storage.md)

### Identity & Access

- [Okta](types/okta.md)
- [Microsoft Entra ID](types/microsoft-entra-id.md)
- [Duo](types/duo.md)
- [1Password](types/1password.md)

### Security Tools

- [Check Point Harmony](types/checkpoint-harmony.md)
- [CrowdStrike](types/crowdstrike.md)
- [Microsoft Defender](types/microsoft-defender.md)
- [SentinelOne](types/sentinelone.md)
- [Sophos](types/sophos.md)
- [Carbon Black](types/carbon-black.md)
- [ThreatLocker](types/threatlocker.md)

### IT & Business Platforms

- [ServiceNow](types/servicenow.md)

### Generic Formats

- [Syslog](types/syslog.md)
- [JSON](types/json.md)
- [File](types/file.md)
- [Windows Event Log](types/windows-event-log.md)
- [EVTX](types/evtx.md)

## Tutorials

- [Creating a Webhook Adapter](tutorials/webhook-adapter.md)
- [Ingesting Google Cloud Logs](tutorials/google-cloud-logs.md)

---

## See Also

- [Adapter Deployment](deployment.md)
- [Adapters as a Service](as-a-service.md)
- [Outputs](../../5-integrations/outputs/index.md)
