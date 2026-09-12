# Stdin

## Overview

This Adapter allows you to ingest data piped into the adapter's standard input. This is useful for integrating with tools or scripts that output log data to stdout, or for one-off ingestion of data from a command pipeline.

## Configurations

Adapter Type: `stdin`

- `client_options`: see [common adapter configuration](../usage.md).
- `write_timeout_sec`: number of seconds before a write to LimaCharlie times out (default: 600).

### Configuration File Example

```yaml
stdin:
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "text"
    sensor_seed_key: "stdin-collector"
    hostname: "log-source-01"
    mapping:
      parsing_grok:
        message: "%{SYSLOGTIMESTAMP:date} %{HOSTNAME:host} %{DATA:service}: %{GREEDYDATA:message}"
      event_type_path: "service"
```

## CLI Deployment

[Adapter downloads](../deployment.md) are available on the deployment page.

```bash
# Pipe journalctl output into the adapter
journalctl -f -q | /path/to/lc_adapter stdin \
  client_options.identity.installation_key=$INSTALLATION_KEY \
  client_options.identity.oid=$OID \
  client_options.platform=text \
  client_options.sensor_seed_key=$SENSOR_NAME \
  client_options.hostname=$SENSOR_NAME
```

```bash
# Pipe a log file for one-time ingestion
cat /var/log/auth.log | /path/to/lc_adapter stdin \
  client_options.identity.installation_key=$INSTALLATION_KEY \
  client_options.identity.oid=$OID \
  client_options.platform=text \
  client_options.sensor_seed_key=$SENSOR_NAME \
  client_options.hostname=$SENSOR_NAME
```
