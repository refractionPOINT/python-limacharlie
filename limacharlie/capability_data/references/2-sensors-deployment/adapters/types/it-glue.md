# IT Glue

## Overview

This Adapter allows you to connect to IT Glue to fetch activity logs.

## Deployment Configurations

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: the type of data ingested through this adapter, like `text`, `json`, `gcp`, `carbon_black`, etc.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from, see below.

### Adapter-specific Options

Adapter Type: `itglue`

- `token`: your API key/token for IT Glue

### Infrastructure as Code Deployment

```python
# For Cloud Sensor configurations, use:
#        token: "hive://secret/itglue-api-token"

sensor_type: "itglue"
itglue:
  token: "hive://secret/itglue-api-token"
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_ITGLUE"
    hostname: "itglue-adapter"
    platform: "json"
    sensor_seed_key: "itglue-audit-sensor"
    mapping:
      sensor_hostname_path: "attributes.resource_name"
      event_type_path: "attributes.action"
      event_time_path: "attributes.created_at"
    indexing: []
```

## API Doc

See the official [documentation](https://api.itglue.com/developer/).
