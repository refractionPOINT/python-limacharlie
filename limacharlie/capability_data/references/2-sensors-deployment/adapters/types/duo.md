# Duo

## Overview

This Adapter allows you to connect to the Duo Admin API and fetch logs from it.

## Configurations

Adapter Type: `duo`

- `client_options`: see [common adapter configuration](../usage.md).
- `integration_key`: an integration key created from within Duo that associated with your "app".
- `secret_key`: the secret key for your "app".
- `api_hostname`: the DNS for your "app", a value given to you by Duo.

### Infrastructure as Code Deployment

```python
# For cloud sensor deployment, store credentials as hive secrets:
#   integration_key: "hive://secret/duo-integration-key"
#   secret_key: "hive://secret/duo-secret-key"

sensor_type: "duo"
  duo:
    integration_key: "YOUR_DUO_INTEGRATION_KEY_DIXXXXXXXXXXXXXXXXXX"
    secret_key: "YOUR_DUO_SECRET_KEY_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
    api_hostname: "api-xxxxxxxx.duosecurity.com"
    client_options:
      identity:
        oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
        installation_key: "YOUR_LC_INSTALLATION_KEY_DUO"
      hostname: "duo-security-adapter"
      platform: "duo"
      sensor_seed_key: "duo-sensor-prod"
```

## API Doc

See the [official documentation](https://duo.com/docs/adminapi).
