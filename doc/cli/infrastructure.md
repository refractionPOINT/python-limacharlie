[Documentation](../README.md) > [CLI](README.md) > Infrastructure

# Infrastructure

Commands for infrastructure-as-code sync, outputs, artifacts, payloads, YARA, integrity rules, logging rules, and exfiltration watches.

## sync

Sync uses the `ext-infrastructure` extension to pull and push org configuration. D&R rules and FP rules are synced through their respective hives.

```bash
# Pull/push everything
limacharlie sync pull --config-file lc_conf.yaml --all
limacharlie sync push --config-file lc_conf.yaml --all --dry-run
limacharlie sync push --config-file lc_conf.yaml --all --force

# Sync specific resource types
limacharlie sync pull --config-file outputs.yaml --outputs
limacharlie sync push --config-file outputs.yaml --outputs

# Sync D&R rules and FP rules via hives
limacharlie sync pull --config-file dr.yaml --hive-dr-general --hive-fp
limacharlie sync push --config-file dr.yaml --hive-dr-general --hive-fp --dry-run
```

Available hive flags: `--hive-dr-general`, `--hive-dr-managed`, `--hive-dr-service`,
`--hive-fp`, `--hive-cloud-sensor`, `--hive-extension-config`, `--hive-yara`,
`--hive-lookup`, `--hive-secret`, `--hive-query`, `--hive-playbook`,
`--hive-ai-agent`, `--hive-external-adapter`.

## output

```bash
limacharlie output list
limacharlie output create --name my-output --module syslog --type event --dest 'host:514'
limacharlie output delete --name my-output
```

## artifact

```bash
limacharlie artifact list
limacharlie artifact upload --file /path/to/file --source my-source
limacharlie artifact download --id ARTIFACT_ID
```

## payload

```bash
limacharlie payload list
limacharlie payload upload --file /path/to/binary --name my-payload
limacharlie payload download --name my-payload
limacharlie payload delete --name my-payload
```

## yara

```bash
limacharlie yara rules-list
limacharlie yara rule-add --name my-rule --rule-file rule.yar
limacharlie yara scan --sid SENSOR_ID --source my-rule
limacharlie yara sources-list
```

## integrity

```bash
limacharlie integrity list                     # File integrity rules
```

## logging

```bash
limacharlie logging list                       # Logging rules
```

## exfil

```bash
limacharlie exfil list                         # Exfiltration watches
```

## See Also

- [Configuration Sync SDK](../sdk/configs.md) — Configs Python class for IaC
- [Other SDK Classes](../sdk/other-classes.md) — Artifacts, Payloads, Outputs classes
- [Hive & Data Stores](hive-data.md) — Hive records and shortcuts
