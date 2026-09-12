# Log Collection Guide

This guide covers how to collect system logs into LimaCharlie using USP adapters. While the examples focus on common Linux log paths, the same adapter configurations work on any supported platform (FreeBSD, macOS, etc.) — just adjust the file paths for your OS.

## Collection Methods

### File Adapter (Recommended for Log Files)

The file adapter monitors log files for changes and streams new entries to LimaCharlie. It supports glob patterns for monitoring multiple files and handles log rotation automatically.

#### Key Features

- Glob pattern support (/var/log/*.log)
- Automatic log rotation handling (with inode-based detection)
- Polling mode for reliable collection on BSD, network filesystems, and across log rotations
- Backfill support for historical data
- Multi-line JSON parsing
- Grok pattern parsing for structured log extraction

#### Basic Configuration

```yaml
file:
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "text"  # or "json" for structured logs
    sensor_seed_key: "linux-logs"
  file_path: "/path/to/logfile"
  backfill: false  # Set true to read existing content
  no_follow: false # Set true to stop after reading existing content
```

### Syslog Adapter

The syslog adapter runs as a syslog server, accepting logs via TCP or UDP. This is useful for centralizing logs from multiple systems or integrating with existing syslog infrastructure.

#### Key Features

- TCP and UDP support
- TLS encryption support
- Mutual TLS authentication
- RFC 3164/5424 syslog format support

#### Basic Configuration

```yaml
syslog:
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "text"
    sensor_seed_key: "syslog-server"
  port: 514
  iface: "0.0.0.0"
  is_udp: false  # Use TCP by default
```

## Log Parsing Options

LimaCharlie supports two methods for parsing unstructured log data:

- **parsing_grok**: Uses Grok patterns (recommended) - pre-built patterns for common log formats, easier to read and maintain
- **parsing_re**: Uses regular expressions - for custom formats or when Grok patterns don't meet specific needs

Grok patterns are built on regular expressions but provide named patterns for common elements like timestamps, IP addresses, and log formats. Use Grok when possible for better maintainability.

## Common Log Sources

### System Logs (/var/log/messages, /var/log/syslog)

Traditional system logs contain kernel messages, service logs, and general system events.

**File Adapter Approach:**

```yaml
file:
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "text"
    sensor_seed_key: "system-logs"
    mapping:
      parsing_grok:
        message: "%{SYSLOGTIMESTAMP:date} %{HOSTNAME:host} %{DATA:service}(?:\\[%{POSINT:pid}\\])?: %{GREEDYDATA:message}"
      sensor_hostname_path: "host"
      event_type_path: "service"
  file_path: "/var/log/messages"  # or /var/log/syslog
```

### Kernel Logs (/var/log/kern.log)

Kernel-specific messages including hardware events, driver messages, and security events.

```yaml
file:
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "text"
    sensor_seed_key: "kernel-logs"
    mapping:
      parsing_grok:
        message: "%{SYSLOGTIMESTAMP:date} %{HOSTNAME:host} kernel: %{GREEDYDATA:message}"
      sensor_hostname_path: "host"
      event_type_path: "kernel"
  file_path: "/var/log/kern.log"
```

### Apache Logs (/var/log/httpd/*, /var/log/apache2/*)

```yaml
file:
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "text"
    sensor_seed_key: "apache-logs"
    mapping:
      parsing_grok:
        message: "%{COMMONAPACHELOG}"
      event_type_path: "verb"
  file_path: "/var/log/apache2/access.log"  # or /var/log/httpd/access_log
```

### Nginx Logs (/var/log/nginx/*)

```yaml
file:
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "text"
    sensor_seed_key: "nginx-logs"
    mapping:
      parsing_grok:
        message: "%{NGINXACCESS}"
      event_type_path: "verb"
  file_path: "/var/log/nginx/access.log"
```

### Audit Logs (/var/log/audit/audit.log)

Linux audit logs are critical for CIS Controls compliance and security monitoring.

```yaml
file:
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "text"
    sensor_seed_key: "audit-logs"
    mapping:
      parsing_grok:
        message: "type=%{DATA:audit_type} msg=audit\\(%{NUMBER:timestamp}:%{NUMBER:serial}\\): %{GREEDYDATA:audit_data}"
      event_type_path: "audit_type"
      event_time_path: "timestamp"
  file_path: "/var/log/audit/audit.log"
```

## Journalctl

Modern logging solution that can output in JSON format for structured parsing.

### Method 1: Pipe to Stdin Adapter

```bash
# Stream journalctl JSON output into the stdin adapter
journalctl -f -q --output=json | /path/to/lc_adapter stdin \
  client_options.identity.installation_key=$INSTALLATION_KEY \
  client_options.identity.oid=$OID \
  client_options.platform=json \
  client_options.sensor_seed_key=journalctl-logs \
  client_options.hostname=my-server
```

## Method 2: Output to File and Monitor

```bash
# Create a systemd service to write journal to file
sudo tee /etc/systemd/system/journal-export.service << EOF
[Unit]
Description=Export systemd journal to file
After=systemd-journald.service

[Service]
ExecStart=/usr/bin/journalctl -f -q --output=json
StandardOutput=append:/var/log/journal-export.json
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable journal-export.service
sudo systemctl start journal-export.service
```

Then monitor the file:

```yaml
file:
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "json"  # JSON format for structured data
    sensor_seed_key: "journalctl-logs"
    mapping:
      sensor_hostname_path: "_HOSTNAME"
      event_type_path: "_SYSTEMD_UNIT"
      event_time_path: "__REALTIME_TIMESTAMP"
  file_path: "/var/log/journal-export.json"
```

## Multi-File Collection

For collecting multiple log types simultaneously:

```yaml
# /var/log/messages
file:
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "text"
    sensor_seed_key: "system-logs"
  file_path: "/var/log/messages"

---

# Kernel logs
file:
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "text"
    sensor_seed_key: "kernel-logs"
  file_path: "/var/log/kern.log"

---

# Audit logs
file:
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "text"
    sensor_seed_key: "audit-logs"
  file_path: "/var/log/audit/audit.log"

---

# Web server logs (glob pattern for multiple files)
file:
  client_options:
    identity:
      oid: "your-organization-id"
      installation_key: "your-installation-key"
    platform: "text"
    sensor_seed_key: "web-logs"
  file_path: "/var/log/nginx/*.log"
```

## Best Practices

- **Use JSON format when possible** - Modern logs often support JSON output, which provides better structure and parsing.
- **Configure appropriate Grok patterns** - Grok provides pre-built patterns for common log formats and is easier to maintain than regex. Use `parsing_grok` over `parsing_re` when possible.
- **Set sensor_seed_key appropriately** - Use descriptive names that identify the log source for easier management.
- **Monitor file permissions** - Ensure the adapter has read access to log files.
- **Use backfill carefully** - Only enable for initial historical data collection to avoid duplicates.
- **Enable polling when needed** - Set `poll: true` if the adapter stops collecting after log rotation, or when running on FreeBSD/BSD systems or network filesystems. See the [File Adapter documentation](adapters/types/file.md#polling-mode) for details.
- **Implement proper field mapping** - Extract hostname, timestamps, and event types for better searchability.
- **Pattern testing** - Test Grok patterns against sample log lines before deployment. Common patterns include %{COMMONAPACHELOG}, %{SYSLOGTIMESTAMP}, and %{NGINXACCESS}.

## Troubleshooting

Common issues:

- **File permission errors**: Check that the adapter process has read access to log files
- **Parse failures**: Validate Grok patterns against actual log formats
- **Missing logs**: Verify file paths and glob patterns
- **Adapter stops collecting after log rotation**: Set `poll: true` in your file adapter configuration. This switches from filesystem event notifications to polling, which reliably detects new data after log rotation tools (e.g. `newsyslog`, `logrotate`) replace the file. This is especially common on FreeBSD and other BSD systems
- **Connection issues**: Check network connectivity and authentication credentials
