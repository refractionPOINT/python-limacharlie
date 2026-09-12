# CrowdStrike Falcon Cloud

## Overview

This Adapter allows you to connect to CrowdStrike Falcon Cloud to stream events as they happen in the CrowdStrike Falcon Console.

## Deployment Configurations

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: the type of data ingested through this adapter, like `text`, `json`, `gcp`, `carbon_black`, etc.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from, see below.

### Adapter-specific Options

Adapter Type: `falconcloud`

- `client_id`: your CrowdStrike Falcon Cloud client ID
- `client_secret`: your CrowdStrike Falcon Cloud client secret

### Manual Deployment

[Adapter downloads](../deployment.md) are available on the deployment page.

```bash
chmod +x /path/to/lc_adapter

/path/to/lc_adapter falconcloud client_options.identity.installation_key=$INSTALLATION_KEY \
client_options.identity.oid=$OID \
client_options.platform=json \
client_options.sensor_seed_key=$SENSOR_NAME \
client_options.hostname=$SENSOR_NAME \
client_options.mappings.event_type_path=metadata/eventType \
client_id=$CLIENT_ID \
client_secret=$CLIENT_SECRET
```

### Infrastructure as Code Deployment

```python
sensor_type: "falconcloud"
  falconcloud:
    client_id: "YOUR_CROWDSTRIKE_FALCON_API_CLIENT_ID"
    client_secret: "YOUR_CROWDSTRIKE_FALCON_API_CLIENT_SECRET"
    client_options:
      identity:
        oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        installation_key: "YOUR_LC_INSTALLATION_KEY_FALCONCLOUD"
      hostname: "crowdstrike-falcon-adapter"
      platform: "falconcloud"
      sensor_seed_key: "falcon-cloud-sensor"
      indexing: []
    # Optional configuration
    write_timeout_sec: 600  # Default: 10 minutes
    is_using_offset: false  # Default: false (recommended)
    offset: 0               # Only used if is_using_offset is true
```

## API Doc

See the official [documentation](https://developer.crowdstrike.com/docs/openapi/) and [additional docs on the library used to access the Falcon APIs](https://github.com/CrowdStrike/gofalcon).
