[Documentation](../README.md) > [CLI](README.md) > Hive & Data Stores

# Hive & Data Stores

Hives are key-value stores for LimaCharlie configuration data. Several hive types have dedicated shortcut commands for simpler syntax.

## hive

```bash
# Generic hive access
limacharlie hive list --hive-name dr-general
limacharlie hive get --hive-name dr-general --key my-rule
limacharlie hive set --hive-name secret --key my-key --input-file data.json
limacharlie hive delete --hive-name secret --key my-key --confirm
```

The flag is `--hive-name`; `--category` does not exist and never has.

### Security product configuration

`limacharlie hive list-types` includes the product configuration hives:

| Hive | Purpose |
|---|---|
| `cloudsec_provider` | Cloud, identity, SaaS, and source-control connections |
| `cloudsec_policy` | Cloud posture and Code Security policies |
| `cloudsec_query` | Saved Cloud Security graph queries |
| `cloudsec_code_rule` | Enabled Code Security rules, including editable defaults and custom rules |
| `mailsec_provider` | Microsoft 365 and Google Workspace mail connections |
| `mailsec_policy` | Email Security policies |
| `dr-mail` | Email detection and verdict rules |
| `app_control_policy` | Application Control policies |
| `app_control_rule` | Application Control allow and deny rules |

Store provider credentials in `secret` records and reference them with `hive://secret/<key>`. Most hives default new records to disabled; `cloudsec_policy`, `acl` and the app-control hives default them to enabled. Pass `--enabled` or `--disabled` to be explicit. See the [Cloud Security](cloud-security.md) and [Email Security](email-security.md) onboarding guides before creating connections.

### Metadata on `hive set`

A record's metadata (`usr_mtd`: `enabled`, `tags`, `comment`, `expiry`) is replaced as a
whole whenever any is sent, and a metadata block without `enabled` is stored as disabled.
`hive set` therefore treats `--enabled`, `--disabled`, `--tag-add`, `--tag-rm`, `--comment` and `--expiry` as metadata:

| You pass | What is sent |
|----------|--------------|
| data only | No metadata. An existing record keeps its metadata; a new one gets the hive's default. |
| data with a `usr_mtd` block in the input | The block, with any flags applied on top. It is authoritative: a block without `enabled` (even `{}`) means disabled. A null `usr_mtd:` counts as absent. |
| data with metadata flags and no `usr_mtd` block | The record's current metadata is read and merged: the enabled state and every field you did not set are kept. If the record does not exist, it is created with the flags as given; without `--enabled` that means disabled, and a warning on stderr says to pass `--enabled`. Any other error reading the record aborts the command. |
| no data, metadata flags | A metadata-only update, merged the same way. |

The shortcut commands below, and `dr set`, merge the same way for `--tag`, `--comment`
and `--enabled/--disabled`, except that their `--tag` replaces the tag list rather than
adding to it.

### Expiry

A record can expire. `usr_mtd.expiry` is a Unix epoch in **milliseconds** (`0` = never),
which is how the hive stores and compares it.

```bash
# --expiry takes SECONDS, like every other timestamp flag in this CLI, and converts.
limacharlie hive set --hive-name secret --key my-key --expiry 1789459200

# A value written into the record is sent EXACTLY as given, so it must be milliseconds —
# which is what makes `hive get ... | hive set ...` round-trip.
limacharlie hive get --hive-name secret --key my-key | \
  limacharlie hive set --hive-name secret --key my-key
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
limacharlie note list --brief          # descriptions only, without the note bodies
```

### sop

```bash
limacharlie sop list
limacharlie sop list --brief           # descriptions only, without the procedure bodies
limacharlie sop get --key ransomware-response
```

### ai-skill

```bash
limacharlie ai-skill list
limacharlie ai-skill list --brief      # name/description/when_to_use, without SKILL.md bodies or bundled files
limacharlie ai-skill get --key triage
```

`list` returns whole records, so for these three hives it includes every
document body. `--brief` reduces each record's `data` to the fields that say
what it is, leaving metadata intact — list to find what you want, then `get`
the ones you need.

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

### app-control

Application Control policies and rules. Both hives are per-organization and use
the `app_control.get` and `app_control.set` permissions. Each subcommand group
supports `list`, `get`, `set`, `delete`, `enable`, `disable` and `tag`, like the
other hive shortcuts.

```bash
limacharlie app-control policy list
limacharlie app-control policy get --key workstations
limacharlie app-control policy set --key workstations --input-file policy.yaml --enabled
limacharlie app-control policy delete --key workstations --confirm

limacharlie app-control rule list
limacharlie app-control rule get --key block-tool-x
limacharlie app-control rule set --key block-tool-x --input-file rule.yaml --enabled
limacharlie app-control rule delete --key block-tool-x --confirm
```

A policy record (`app_control_policy`, one record per policy):

```yaml
data:
  priority: 100              # integer
  platforms: [windows]       # windows, macos
  tags: [workstations]
  mode: permissive           # off | permissive | permissive_sync | enforcing
  stance: allowlist          # allowlist | blocklist
  trust_os_vendor: true
```

A rule record (`app_control_rule`); the record key is the rule ID, at most 64 bytes:

```yaml
data:
  action: deny               # allow | deny
  kind: sha256               # path | signer | signing_id | signer_root | sha256
  value: e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
  policies: [workstations]   # names of the policy records the rule applies to
```

The server validates every record; the CLI does not, so an invalid value is
rejected with the reason. A sensor gets the first enabled policy (lowest `priority`, then
record name) whose platforms and tags match it, together with every enabled
rule that names that policy or names none. Deleting a policy does not disarm
sensors that already have it; set `mode: off` instead.

Unlike most hives, a new record on these two hives is enabled when it is sent
with no metadata. Passing `--tag` or `--comment` without `--enabled` keeps an
existing record's enabled state, but creates a record that does not exist yet
disabled (a warning says so), so pass `--enabled` with them when creating. The same hives are reachable with the generic
`limacharlie hive` commands (`--hive-name app_control_policy`) and sync with
`limacharlie sync` (`--hive-app-control-policy`, `--hive-app-control-rule`).

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
