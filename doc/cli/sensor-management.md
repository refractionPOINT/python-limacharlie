[Documentation](../README.md) > [CLI](README.md) > Sensor Management

# Sensor Management

Commands for sensor lifecycle, tagging, network isolation, tasking, downloads, and installation keys.

## sensor

```bash
limacharlie sensor list
limacharlie sensor list --online --selector 'plat == windows'
limacharlie sensor list --selector '"prod" in tags' --limit 50
limacharlie sensor list --tag production --limit 50
limacharlie sensor list --hostname web-server
limacharlie sensor get --sid SENSOR_ID
limacharlie sensor wait-online --sid SENSOR_ID --timeout 120
limacharlie sensor delete --sid SENSOR_ID --confirm
limacharlie sensor export                # Full fleet manifest
limacharlie sensor upgrade               # Trigger version update
limacharlie sensor set-version --version 4.29.0
limacharlie sensor dump --sid SENSOR_ID --confirm  # Memory dump
limacharlie sensor sweep --sid SENSOR_ID --config '{"os_processes": true}'
```

## tag

```bash
limacharlie tag list --sid SENSOR_ID
limacharlie tag add --sid SENSOR_ID --tag suspicious --ttl 600
limacharlie tag remove --sid SENSOR_ID --tag suspicious
limacharlie tag find --tag production    # Find all sensors with a tag
limacharlie tag mass-add --selector '`linux` in tags' --tag patch-pending
limacharlie tag mass-remove --selector '`linux` in tags' --tag patch-pending
```

## endpoint-policy

```bash
limacharlie endpoint-policy status --sid SENSOR_ID
limacharlie endpoint-policy isolate --sid SENSOR_ID
limacharlie endpoint-policy rejoin --sid SENSOR_ID
limacharlie endpoint-policy seal --sid SENSOR_ID
limacharlie endpoint-policy unseal --sid SENSOR_ID
```

## task

```bash
limacharlie task send --sid SENSOR_ID --command os_processes
limacharlie task request --sid SENSOR_ID --command os_processes  # Wait for response
limacharlie task reliable-send --sid SENSOR_ID --command os_processes
limacharlie task reliable-list --sid SENSOR_ID
```

## download

```bash
# List all available download targets
limacharlie download list

# Download sensor (EDR agent) installers
limacharlie download sensor --list                                  # Show available targets
limacharlie download sensor --platform linux --arch 64              # Linux x64
limacharlie download sensor --platform windows --arch msi64 -o sensor.msi  # Windows MSI
limacharlie download sensor --platform mac --arch arm64             # macOS Apple Silicon
limacharlie download sensor --platform linux --arch deb64           # Debian package
limacharlie download sensor --platform chrome                       # Chrome extension

# Download adapter (USP) binaries
limacharlie download adapter --list                                 # Show available targets
limacharlie download adapter --platform linux --arch 64             # Linux x64
limacharlie download adapter --platform mac --arch arm64            # macOS Apple Silicon
limacharlie download adapter --platform windows --arch 64           # Windows x64

# Pipe to stdout (for remote deployment scripts)
limacharlie download sensor --platform linux --arch 64 -o - | ssh host 'cat > /tmp/lc_sensor && chmod +x /tmp/lc_sensor'
```

## installation-key

```bash
limacharlie installation-key list
limacharlie installation-key create --description "Production fleet"
limacharlie installation-key delete --iid KEY_ID
```

## See Also

- [Sensor SDK class](../sdk/sensors.md) — Python API for sensor operations
- [Detection & Response](detection-response.md) — D&R rules and false positives
- [Data & Query](data-query.md) — Search historical events and detections
