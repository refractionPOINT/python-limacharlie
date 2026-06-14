[Documentation](../README.md) > [CLI](README.md) > Hive & Data Stores

# Hive & Data Stores

Hives are key-value stores for LimaCharlie configuration data. Several hive types have dedicated shortcut commands for simpler syntax.

## hive

```bash
# Generic hive access
limacharlie hive list --category dr-general
limacharlie hive get --category dr-general --key my-rule
limacharlie hive set --category secret --key my-key --input-file data.json
limacharlie hive delete --category secret --key my-key --confirm
```

## Shortcut Commands

These commands provide simpler syntax for specific hive categories. They support the same operations as the generic `hive` command.

### secret

```bash
limacharlie secret list
limacharlie secret get --key my-secret
limacharlie secret set --key my-secret --input-file secret.json
limacharlie secret delete --key my-secret --confirm
```

### lookup

```bash
limacharlie lookup list
limacharlie lookup set --key ioc-list --input-file iocs.json
```

### playbook

```bash
limacharlie playbook list
```

### note

```bash
limacharlie note list
```

### sop

```bash
limacharlie sop list
```

### adapter (external-adapter)

```bash
limacharlie external-adapter list
```

### cloud-sensor (cloud-adapter)

```bash
limacharlie cloud-adapter list
```

### app

User-authored, AI-generated mini web apps (a self-contained HTML document
rendered in a sandboxed iframe by the web UI).

```bash
limacharlie app list
limacharlie app get --key my-app
limacharlie app set --key my-app --input-file app.yaml
limacharlie app delete --key my-app --confirm
```

## extension

```bash
limacharlie extension list                    # Subscribed extensions
limacharlie extension list-available          # All available extensions
limacharlie extension subscribe --name lookup/my-resource
limacharlie extension unsubscribe --name lookup/my-resource
limacharlie extension request --name my-ext --action do-thing --data '{}'
limacharlie extension schema --name my-ext
limacharlie extension config-list --name my-ext
```

## See Also

- [Hive SDK](../sdk/hive.md) — Hive and HiveRecord Python classes
- [Other SDK Classes](../sdk/other-classes.md) — Extensions class
- [Infrastructure](infrastructure.md) — Sync hive data with infrastructure-as-code
