# Syslog

Syslog is both a protocol and common logging format that consolidate events to a central location for storage. On \*nix systems, Syslog often outputs to predefined locations, such as `/var/log`. The LimaCharlie Adapter can be configured as a Syslog endpoint to collect events either via TCP or UDP.

Syslog data can also be ingested via other data platforms, such as an S3 bucket.

Syslog events are observed in LimaCharlie as the `text` platform.

A more detailed guide to syslog collection can be found in the [Log Collection Guide](../../log-collection-guide.md).

## Adapter Deployment

Given its ubiquity, Syslog can be ingested via a myriad of methods in both text/log and streaming formats. For non-streaming methods, please refer to the corresponding Adapter type (such as [S3](s3.md), [GCP](google-cloud-pubsub.md), etc.)

### Syslog-specific Configurations

All Adapters share the [common client configuration options](../usage.md). A syslog Adapter has a few unique configuration options not found with other Adapter types. These include:

- `port`: port to listen for syslog from.
- `iface`: the interface name to listen for new connections/packets from, defaults to all.
- `is_udp`: if `true`, listen over UDP instead of TCP. Cannot be combined with SSL/TLS.
- `ssl_cert`: path to a file with the SSL cert to use to receive logs over TCP.
- `ssl_key`: path to a file with the SSL key to use to receive logs over TCP.
- `mutual_tls_cert`: path to a CA certificate file for mutual TLS client authentication.
- `write_timeout_sec`: number of seconds before a write to LimaCharlie times out (default: 600).

### Collecting Syslog via Docker

The following example walks through configuring a Docker container as a syslog Adapter.

```bash
docker run --rm -it -p 1514:1514 refractionpoint/lc-adapter:latest syslog port=1514 \
  client_options.identity.installation_key=e9a3bcdf-efa2-47ae-b6df-579a02f3a54d \
  client_options.identity.oid=8cbe27f4-bfa1-4afb-ba19-138cd51389cd \
  client_options.platform=text "client_options.mapping.parsing_grok=%{DATESTAMP:date} %{HOSTNAME:host} %{WORD:exe}\[%{INT:pid}\]: %{GREEDYDATA:msg}" \
  client_options.sensor_seed_key=testclient1 \
  client_options.mapping.rename_only=true \
  "client_options.mapping.mapping[0].src_field=host" \
  "client_options.mapping.mapping[0].dst_field=syslog_hostname"
```

Here's a breakdown of the above example:

- `docker run --rm`: run a container and don't keep the contents around when it's stopped.
- `-it`: make the container interactive so you can ctrl-c to stop it.
- `-p 1514:1514`: allow the container to listen on port `1514` on the local host and use the same port within the container.
- `refractionpoint/lc-adapter:latest`: this is the name of the public container provided by LimaCharlie.
- `syslog`: the method the Adapter should use to collect data locally. The `syslog` value will operate as a syslog endpoint on the TCP port specified.
- `port=1514`: the TCP port the Adapter should listen on. By default this is a normal TCP connection (not SSL), although SSL options exist.
- `client_options.identity.installation_key=....`: the Installation Key from LimaCharlie.
- `client_options.identity.`OID`=....`: the Organization ID from LimaCharlie the installation key above belongs to.
- `client_options.platform=text`: this indicates the type of data that will be received from this adapter. In this case it's syslog, so `text` lines.
- `client_options.mapping.parsing_grok=....`: this is the grok expression describing how to interpret the text lines and how to convert them to JSON.
- `client_options.sensor_seed_key=....`: this is the value that identifies this instance of the Adapter. Record it to re-use the Sensor generated for this Adapter later if you have to re-install the Adapter.
- `client_options.mapping.rename_only=true`: only rename the field in mapping below, so keep the other original fields.
- `client_options.mapping.mapping[0].src_field=....`: the source field of the first mapping record.
- `client_options.mapping.mapping[0].dst_field=....`: the destination field of the first mapping record.

To test it, assuming we're on the same Debian box as the container, pipe the syslog to the container:

```text
journalctl -f -q | netcat 127.0.0.1 1514
```

### Collecting Syslog via Binary Adapter

The LimaCharlie binary Adapter can be deployed as a syslog listener. This option allows you to configure multiple syslog outputs to a single listener, and ingest multiple types of events with a single Adapter.

#### Step 1: Create an installation key

We recommend utilizing a unique installation key for this deployment, specifically with a `syslog` Tag. This allows for a level of delineation within  rules and outputs via Tags.

#### Step 2: Create an Adapter config file

Syslog events are typically ingested as `text`, however often have specific structures to them. Utilizing a config file allows for easy management of a regex string to extract relevant fields from syslog output.

The following example config file can be a starting point. However, you might need to modify the regex to match your specific message.

```yaml
syslog:
  port: 1514
  iface: "0.0.0.0"
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_SYSLOG"
    hostname: "syslog-adapter"
    platform: "text"
    sensor_seed_key: "syslog-collector"
    mapping:
      parsing_grok:
        message: "^<%{INT:pri}>%{SYSLOGTIMESTAMP:timestamp}\\s+%{HOSTNAME:hostname}\\s+%{WORD:tag}(?:\\[%{INT:pid}\\])?:\\s+%{GREEDYDATA:message}"
      sensor_hostname_path: "hostname"
      event_type_path: "tag"
      event_time_path: "timestamp"
      event_time_timezone: "America/New_York"  # Required if logs use local time (SYSLOGTIMESTAMP has no timezone)
  # Optional syslog-specific configuration
  is_udp: false                               # TCP (default) vs UDP
  write_timeout_sec: 30                       # Write timeout
  ssl_cert: "/certs/syslog_server.pem"       # Optional SSL cert
  ssl_key: "/certs/syslog_server.key"        # Optional SSL key
  mutual_tls_cert: "/certs/client_ca.pem"    # Optional mTLS
```

#### Step 3: Configure syslog output to send messages to a local listener

This step will depend on the type of syslog daemon you are using (syslog, rsyslog, syslog-ng, etc.) Within the daemon configuration file, configure the desired facility(-ies) to direct to the local listener. In the following example, we configured `auth` and `authpriv` events to write to both `/var/log/audit.log` and `127.0.0.1:1514`.

```text
auth,authpriv.*   /var/log/auth.log
auth,authpriv.*   @@127.0.0.1:1514
```

After applying the appropriate configuration, restart the syslog daemon.

#### Step 4: Confirm that syslog messages are sent to the correct location

Utilizing a tool like `netcat`, you can listen on the appropriate port to confirm that messages are being sent. The following command will spawn a `netcat` listener on port 1514:

```text
nc -l -p 1514
```

#### Step 5: Run the LimaCharlie Adapter

Execute the binary Adapter with the syslog configuration file in order to start the LimaCharlie listener. If started correctly, you should see the following messages in `stdout`:

```text
DBG <date>: usp-client connecting
DBG <date>: usp-client connected
DBG <date>: listening for connections on :1514
```

Double-check the LimaCharlie Sensors list, and you should see the text adapter with the respective hostname sending `Syslog` events.
