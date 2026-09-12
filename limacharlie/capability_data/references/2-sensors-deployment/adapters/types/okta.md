# Okta

## Overview

This Adapter allows you to connect to Okta to fetch system logs.

## Deployment Configurations

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: the type of data ingested through this adapter, like `text`, `json`, `gcp`, `carbon_black`, etc.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from, see below.

### Adapter-specific Options

Adapter Type: `okta`

- `apikey`: your Okta API key/token
- `url`: your Okta URL (ex: `https://dev-003462479.okta.com`)

### CLI Deployment

[Adapter downloads](../deployment.md) are available on the deployment page.

```bash
chmod +x /path/to/lc_adapter

/path/to/lc_adapter okta client_options.identity.installation_key=$INSTALLATION_KEY \
client_options.identity.oid=$OID \
client_options.platform=json \
client_options.sensor_seed_key=$SENSOR_NAME \
client_options.hostname=$SENSOR_NAME \
apikey=$API_KEY url=$URL
```

### Infrastructure as Code Deployment

```python
# For cloud sensor deployment, store credentials as hive secrets:

#   apikey: "hive://secret/okta-api-token"

sensor_type: "okta"
okta:
  apikey: "hive://secret/okta-api-key"
  url: "https://your-company.okta.com"
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_OKTA"
    hostname: "okta-systemlog-adapter"
    platform: "json"
    sensor_seed_key: "okta-system-logs-sensor"
    mapping:
      sensor_hostname_path: "client.device"
      event_type_path: "eventType"
      event_time_path: "published"
    indexing: []
```

## API Doc

See the official [documentation](https://developer.okta.com/docs/reference/api/system-log/).
