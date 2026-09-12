# Zendesk

## Overview

This Adapter allows you to connect to Zendesk to fetch [account activity logs](https://developer.zendesk.com/api-reference/ticketing/account-configuration/audit_logs/#list-audit-logs).

## Deployment Configurations

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: the type of data ingested through this adapter, like `text`, `json`, `gcp`, `carbon_black`, etc.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from, see below.

### Adapter-specific Options

Adapter Type: `zendesk`

- `api_token`: your Zendesk API token
- `zendesk_domain`: your Zendesk domain, like `initech.zendesk.com`
- `zendesk_email`: your Zendesk email address that created the API token

### CLI Deployment

[Adapter binaries](../deployment.md#adapter-binaries) are available on the deployment page.

```bash
chmod +x /path/to/lc_adapter

/path/to/lc_adapter zendesk client_options.identity.installation_key=$INSTALLATION_KEY \
client_options.identity.oid=$OID \
client_options.platform=json \
client_options.sensor_seed_key=$SENSOR_NAME \
client_options.hostname=$SENSOR_NAME \
client_options.mappings.event_type_path=action \
api_token=$API_TOKEN \
zendesk_domain='$YOUR_COMPANY.zendesk.com' \
zendesk_email=you@yourcompany.com
```

### Infrastructure as Code Deployment

```python
# For cloud sensor deployment, store credentials as hive secrets:
#   api_token: "hive://secret/zendesk-api-token"
#   zendesk_email: "hive://secret/zendesk-email"

sensor_type: "zendesk"
zendesk:
  api_token: "hive://secret/zendesk-api-token"
  zendesk_domain: "yourcompany.zendesk.com"
  zendesk_email: "hive://secret/zendesk-api-email"
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_ZENDESK"
    hostname: "zendesk-support-adapter"
    platform: "json"
    sensor_seed_key: "zendesk-audit-sensor"
    mapping:
      sensor_hostname_path: "actor_name"
      event_type_path: "action"
      event_time_path: "created_at"
    indexing: []
```

## API Doc

See the official [documentation](https://developer.zendesk.com/api-reference/ticketing/account-configuration/audit_logs/#list-audit-logs).
