# Mac Unified Logging

## Overview

This Adapter allows you to collect events from MacOS Unified Logging.

## Deployment Configurations

All adapters support the same `client_options`, which you should always specify if using the binary adapter or creating a webhook adapter. If you use any of the Adapter helpers in the web app, you will not need to specify these values.

- `client_options.identity.oid`: the LimaCharlie Organization ID (OID) this adapter is used with.
- `client_options.identity.installation_key`: the LimaCharlie Installation Key this adapter should use to identify with LimaCharlie.
- `client_options.platform`: the type of data ingested through this adapter, like `text`, `json`, `gcp`, `carbon_black`, etc.
- `client_options.sensor_seed_key`: an arbitrary name for this adapter which Sensor IDs (SID) are generated from, see below.

**Optional Arguments:**

- `predicate`: an [NSPredicate](https://developer.apple.com/documentation/foundation/nspredicate) filter string to limit which log entries are collected. Example: `predicate='subsystem=="com.apple.TimeMachine"'`
- `write_timeout_sec`: number of seconds before a write to LimaCharlie times out (default: 600).

## CLI Deployment

[Adapter downloads](../deployment.md) are available on the deployment page.

```bash
chmod +x /path/to/lc_adapter

/path/to/lc_adapter mac_unified_logging client_options.identity.installation_key=$INSTALLATION_KEY \
client_options.identity.oid=$OID \
client_options.platform=json \
client_options.sensor_seed_key=$SENSOR_NAME \
client_options.hostname=$SENSOR_NAME
```

### Configuration File Example

```yaml
mac_unified_logging:
  client_options:
    identity:
      oid: "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      installation_key: "YOUR_LC_INSTALLATION_KEY_MACOSUL"
    hostname: "user-macbook-pro"
    platform: "mac_unified_logging"
    sensor_seed_key: "macos-unified-logging-sensor"
  # Optional configuration
  write_timeout_sec: 600                           # Default: 600 seconds
  predicate: 'processImagePath endswith "/usr/sbin/sshd" OR subsystem == "com.apple.security"'
```

## Service Creation

If you want this adapter to run as a service, you can run the following script to add a plist file to the endpoint **with your variables replaced**. Please note that this example also has an example predicate, so if you do not wish to use a predicate, remove that line.

```bash
sudo -i

curl https://downloads.limacharlie.io/adapter/mac/64 -o /usr/local/bin/lc_adapter
chmod +x /usr/local/bin/lc_adapter

tee -a /Library/LaunchDaemons/io.limacharlie.adapter.macunifiedlogging.plist <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>io.limacharlie.adapter.macunifiedlogging</string>
    <key>UserName</key>
 <string>root</string>
    <key>RunAtLoad</key>
    <true/>
    <key>WorkingDirectory</key>
    <string>/usr/local/bin</string>
    <key>KeepAlive</key>
    <true/>
    <key>EnvironmentVariables</key>
    <dict>
      <key>PATH</key>
      <string>/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin</string>
    </dict>
    <key>Program</key>
    <string>/usr/local/bin/lc_adapter</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/lc_adapter</string>
        <string>mac_unified_logging</string>
        <string>client_options.identity.installation_key=$INSTALLATION_KEY</string>
        <string>client_options.identity.oid=$OID</string>
        <string>client_options.hostname=$SENSOR_NAME</string>
        <string>client_options.platform=json</string>
        <string>client_options.sensor_seed_key=$SENSOR_NAME</string>
        <string>predicate=eventMessage CONTAINS[c] "corp.sap.privileges"</string>
    </array>
  </dict>
</plist>
EOF

launchctl load -w /Library/LaunchDaemons/io.limacharlie.adapter.macunifiedlogging.plist
```
