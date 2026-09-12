# EVTX

## Overview

This Adapter allows you to ingest and convert a `.evtx` file into LimaCharlie. The `.evtx` files are the binary format used by Microsoft for Windows Event Logs. This is useful to ingest historical Windows Event Logs, for example during an Incident Response (IR) engagement.

For real-time collection of Windows Event Logs, see the [Windows Event Logs](../../tutorials/windows-event-logs.md) documentation.

## Configurations

Adapter Type: `evtx`

- `client_options`: see [common adapter configuration](../usage.md).
- `file_path`: path to the `.evtx` file to ingest.
- `write_timeout_sec`: number of seconds before a write to LimaCharlie times out (default: 600).

### Configuration File Example

```yaml
evtx:
  file_path: "C:\\Evidence\\Security.evtx"
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "wel"
    sensor_seed_key: "ir-evidence-01"
    hostname: "compromised-host"
```

### CLI Deployment

[Adapter downloads](../deployment.md) are available on the deployment page.

```bash
/path/to/lc_adapter evtx \
  file_path=/path/to/Security.evtx \
  client_options.identity.installation_key=$INSTALLATION_KEY \
  client_options.identity.oid=$OID \
  client_options.platform=wel \
  client_options.sensor_seed_key=ir-evidence-01 \
  client_options.hostname=compromised-host
```

## API Doc

See the [unofficial documentation on EVTX](https://www.giac.org/paper/gcia/2999/evtx-windows-event-logging/115806).
