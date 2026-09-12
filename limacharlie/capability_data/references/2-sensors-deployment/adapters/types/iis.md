# IIS Logs

Microsoft's Internet Information Services (IIS) web server is a web server commonly found on Microsoft Windows servers. This Adapter assists with sending IIS web logs to LimaCharlie via the Adapter binary.

Telemetry Platform (if applicable): `iis`

## Deployment Configurations

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: the type of data ingested through this adapter, like `text`, `json`, `gcp`, `carbon_black`, etc.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from, see below.

### Adapter-specific Options

IIS web logs often have a standardized schema, unless manually changed by administrators. The `iis` platform in LimaCharlie expects the following structure:

`#Fields: date time s-ip cs-method cs-uri-stem cs-uri-query s-port cs-username c-ip cs(User-Agent) cs(Referer) sc-status sc-substatus sc-win32-status time-taken`

#### Log Structure

If your IIS logs are a different structure from above, please let us know and we can assist in customizing the parser!

The structure of these fields is as follows:

| Field Name | Explanation |
| --- | --- |
| date | Date of log entry |
| time | Time of log entry |
| s-ip | The IP address of the web server |
| cs-method | The method of request from the client |
| cs-uri-stem | The URI requested by the client |
| cs-uri-query | The query added to the URI in the client request |
| s-port | The server port) |
| cs-username | The client username (if provided) |
| c-ip | The IP address of the client |
| cs-user-agent | The user-agent of the client |
| cs-referer | The referer that directed the client to the site |
| sc-status | The service status code |
| sc-substatus | The service substatus code (if applicable) |
| sc-win32-status | The Windows status code |
| time-taken | The time taken to render the request resource(s) |

## Configuration File

IIS logs are typically stored "on disk" of the web server, in files that roll daily. Thus, collecting IIS web logs would be done with a binary Adapter that can monitor specific IIS log folder(s) for new files. The Adapter type would be `file`, while the platform is `iis`.

The following configuration file can be used as a starter to monitor IIS web log directories. Replace any values with `< >` characters with values unique to your Organization and/or deployment. *Do not include the* `<` *or* `>` *characters in your config file!*

### Please customize according to your environment/LimaCharlie organization

```yaml
file:
  client_options:
    identity:
      installation_key: <installation key>
      oid: <organization id>
    platform: iis
    sensor_seed_key: <sensor_seed_key>
    // The following will map the timestamp of the event to the timestamp in the web log. Remove if you'd prefer to keep the event time as the time of ingestion.
    mapping:
      event_time_path: ts
  file_path: <C:\path\to\web\logs\u*.log>
  no_follow: false
```

A few notes about the IIS platform parser:

- The server IP address (identified in the logs as `s-ip` will be used as the hostname within LimaCharlie.
- The `date` and `time` fields are combined to a single field represented as `ts`. The above configuration uses this field as the event time, unless removed.
- The `sensor_seed_key` can be any value of your choosing, please make sure it's unique per web server.
- You can specify multiple configurations in one file if you wish to collect logs from multiple folders.
- The `no_follow: false` specification ensures that the Adapter monitors for new files and/or writes to existing files. You can exclude this option if you are going to ingest "dead" log files.
- All IIS events will be represented as `IIS_WEBLOG` in the Adapter telemetry.

If you have any questions about collecting IIS web logs, please reach out to the LimaCharlie team.

Once the config file is set, you can run the Adapter on Windows with the following command (assuming the file is named `config.yaml`):

`<adapter_name>.exe file config.yaml`

## Example Event

```json
{
    "c-ip": "192.168.1.11",
    "cs-method": "GET",
    "cs-referer)": "-",
    "cs-uri-query": "-",
    "cs-uri-stem": "/path/to/my/web/page",
    "cs-user-agent": "Mozilla/5.0+(Windows+NT+10.0;+Win64;+x64)+AppleWebKit/537.36+(KHTML,+like+Gecko)+Chrome/128.0.0.0+Safari/537.36",
    "cs-username": "-",
    "s-ip": "192.168.1.10",
    "s-port": "99",
    "sc-status": "401",
    "sc-substatus": "2",
    "sc-win32-status": "5",
    "time-taken": "143",
    "ts": "2024-09-05 12:36:14"
}
```
