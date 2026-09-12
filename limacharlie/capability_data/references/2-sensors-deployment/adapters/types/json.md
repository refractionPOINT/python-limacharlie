# JSON

## Overview

This Adapter allows you to ingest JSON-formatted logs from a file. It uses the [File](file.md) adapter with `client_options.platform` set to `json`.

When ingesting JSON data, each line of the file is expected to contain a complete JSON object (one object per line). For JSON objects that span multiple lines, use the `multi_line_json: true` option.

Adapter type: `file`

## Configuration

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: set to `json` for JSON-formatted logs.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from.

Since this adapter uses the file adapter under the hood, all [File adapter options](file.md) are available, including `no_follow`, `backfill`, `poll`, `multi_line_json`, and others.

### Configuration File Example

```yaml
file:
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "json"
    sensor_seed_key: "json-logs"
    hostname: "app-server-01"
    mapping:
      event_type_path: "event_type"
      event_time_path: "timestamp"
  file_path: "/var/log/app/*.json"
```

For multi-line JSON (where a single JSON object spans multiple lines):

```yaml
file:
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "json"
    sensor_seed_key: "json-logs"
    mapping:
      event_type_path: "action"
  file_path: "/var/log/app/events.json"
  multi_line_json: true
```

## CLI Deployment

[Adapter downloads](../deployment.md) are available on the deployment page.

```bash
chmod +x /path/to/lc_adapter

/path/to/lc_adapter file client_options.identity.installation_key=$INSTALLATION_KEY \
client_options.identity.oid=$OID \
client_options.platform=json \
client_options.sensor_seed_key=$SENSOR_NAME \
client_options.hostname=$SENSOR_NAME \
file_path=/path/to/file
```
