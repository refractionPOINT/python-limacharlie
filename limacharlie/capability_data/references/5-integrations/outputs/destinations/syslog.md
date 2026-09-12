# Syslog

## Syslog (TCP)

Output events and detections to a syslog target.

- `dest_host`: the IP or DNS and port to connect to, format `www.myorg.com:514`.
- `is_tls`: if `true` will output over TCP/TLS.
- `is_strict_tls`: if `true` will enforce validation of TLS certs.
- `is_no_header`: if `true` will not emit a Syslog header before every message. This effectively turns it into a TCP output.
- `structured_data`: arbitrary field to include in syslog "Structured Data" headers. Sometimes useful for cloud SIEMs integration.

Example:

```text
dest_host: storage.corp.com
is_tls: "true"
is_strict_tls: "true"
is_no_header: "false"
```

## Related articles

- [Syslog](../../../2-sensors-deployment/adapters/types/syslog.md)

## What's Next

- [Tines](tines.md)
