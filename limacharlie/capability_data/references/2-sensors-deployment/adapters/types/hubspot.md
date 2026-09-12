# HubSpot

## Overview

This Adapter allows you to connect to HubSpot to fetch [account activity logs](https://developers.hubspot.com/docs/guides/api/settings/account-activity-api).

## Deployment Configurations

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: the type of data ingested through this adapter, like `text`, `json`, `gcp`, `carbon_black`, etc.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from, see below.

### Adapter-specific Options

Adapter Type: `hubspot`

- `access_token`: your HubSpot access token

### Manual Deployment

[Adapter downloads](../deployment.md) are available on the deployment page.

```bash
chmod +x /path/to/lc_adapter

/path/to/lc_adapter hubspot client_options.identity.installation_key=$INSTALLATION_KEY \
client_options.identity.oid=$OID \
client_options.platform=json \
client_options.sensor_seed_key=$SENSOR_NAME \
client_options.hostname=$SENSOR_NAME \
client_options.mappings.event_type_path=category \
access_token=$ACCESS_TOKEN
```

### Infrastructure as Code Deployment

```python
sensor_type: hubspot
  hubspot:
    access_token: "YOUR_HUBSPOT_PRIVATE_APP_ACCESS_TOKEN"
    client_options:
      identity:
        oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        installation_key: "YOUR_LC_INSTALLATION_KEY_HUBSPOT"
      destination:
        hostname: "input.limacharlie.io"
        port: 443
        is_tls: true
      net:
        identity_timeout: 30
        request_timeout: 30
        heartbeat_timeout: 120
      indexing: []
```

## API Doc

See the official [documentation](https://developers.hubspot.com/docs/reference/api/settings/account-activity-api).
