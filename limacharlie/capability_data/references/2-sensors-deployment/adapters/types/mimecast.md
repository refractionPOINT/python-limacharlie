# Mimecast

## Overview

This Adapter allows you to connect to the Mimecast API to stream audit events as they happen.

## Deployment Configurations

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: the type of data ingested through this adapter, like `text`, `json`, `gcp`, `carbon_black`, etc.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from, see below.

### Adapter-specific Options

Adapter Type: `mimecast`

- `client_id`: your Mimecast client ID
- `client_secret`: your Mimecast client secret

### CLI Deployment

[Adapter downloads](../deployment.md) are available on the deployment page.

```bash
chmod +x /path/to/lc_adapter

/path/to/lc_adapter mimecast client_options.identity.installation_key=$INSTALLATION_KEY \
client_options.identity.oid=$OID \
client_options.platform=json \
client_options.sensor_seed_key=$SENSOR_NAME \
client_options.hostname=$SENSOR_NAME \
client_options.mappings.event_type_path=category \
client_id=$CLIENT_ID client_secret=$CLIENT_SECRET
```

### Infrastructure as Code Deployment

```python
# For cloud sensor deployment, store credentials as hive secrets:

#   client_id: "hive://secret/mimecast-client-id"
#   client_secret: "hive://secret/mimecast-client-secret"

sensor_type: "mimecast"
mimecast:
  client_id: "hive://secret/mimecast-client-id"
  client_secret: "hive://secret/mimecast-client-secret"
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_MIMECAST"
    hostname: "mimecast-logs-adapter"
    platform: "json"
    sensor_seed_key: "mimecast-audit-sensor"
    mapping:
      sensor_hostname_path: "sender"
      event_type_path: "eventType"
      event_time_path: "eventTime"
    indexing: []
```

## API Doc

See the official [documentation](https://developer.services.mimecast.com/docs/auditevents/1/routes/api/audit/get-audit-events/post).
