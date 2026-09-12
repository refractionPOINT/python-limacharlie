# Slack Audit Logs

[Slack audit logs](https://api.slack.com/admins/audit-logs) allow for ingestion of audit events in a Slack Enterprise Grid organization. Events can be ingested directly from the Slack API via a cloud-to-cloud or CLI Adapter.

Slack telemetry can be addressed via the `slack` platform.

**Note**: Audit Logs via API are only available to Slack workspaces on the Enterprise Grid plan.

## Adapter Deployment

Slack Audit Logs can be collected directly from the Slack API, via a cloud-to-cloud Adapter, or via the CLI Adapter. You will need a Slack App OAuth token prior to deploying this Adapter. More information on generating Slack OAuth tokens can be found [at this link](https://api.slack.com/authentication/token-types).

### Cloud-to-Cloud Adapter

Slack API telemetry can be configured directly from the LimaCharlie web application. Under `Sensors List`, select `+ Add Sensor > Slack Audit Logs`. After providing an Installation Key will be prompted to provide an Adapter Name and a Slack App OAuth Token.

### Deploying via the CLI Adapter

The LimaCharlie CLI Adapter can also be used to ingest Slack events, if you do not wish to create a cloud-to-cloud connector. The following sample configuration can be used to create a Slack CLI Adapter:

```yaml
slack:
  client_options:
    hostname: slack-audit
    identity:
      installation_key: <INSTALLATION_KEY>
      oid: <OID>
    platform: slack
    sensor_seed_key: super-special-seed-key
  token: <SLACK OAUTH TOKEN>
```
