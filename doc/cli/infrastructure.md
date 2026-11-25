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

`--all` is strict: if the key cannot read one of the hives, the pull fails (for
example `host_posture_rule` without `host_posture.get`). For scheduled backups
use `sync pull --all-available`, which selects the same set but skips hives the
key has no permission for, so a new hive or permission added by a release does
not break the job:

```bash
limacharlie sync pull --config-file lc_conf.yaml --all-available
```

Each skipped hive prints `Warning: skipped hive <hive>: this key lacks
<permission>; grant it to include this hive in the sync.` on stderr (also with
`--quiet`) and the command exits 0. `--all` and `--all-available` cannot be
combined; explicit `--hive-*` flags are redundant with `--all-available`. A
hive named only by an explicit `--hive-*` flag stays strict. `--all-available`
is pull-only and needs a backend that supports skipping; an older backend fails
on the first unreadable hive, as `--all` does.

Available hive flags: `--hive-cloudsec-policy`, `--hive-cloudsec-provider`,
`--hive-cloudsec-query`, `--hive-cloudsec-code-rule`, `--hive-mailsec-provider`, `--hive-dr-mail`, `--hive-mailsec-policy`, `--hive-app-control-policy`, `--hive-app-control-rule`, `--hive-host-posture-rule`, `--hive-acl`, `--hive-dr-general`, `--hive-dr-managed`, `--hive-dr-service`,
`--hive-fp`, `--hive-cloud-sensor`, `--hive-extension-config`, `--hive-yara`,
`--hive-lookup`, `--hive-secret`, `--hive-query`, `--hive-playbook`,
`--hive-ai-agent`, `--hive-external-adapter`.

### Permissions each hive needs

Listing a hive's records checks its metadata permission (`.get.mtd`); reading
each record's data checks the `.get` permission. A key with the first but not
the second sees the records with `data: null`. `sync push` needs the set
permission (and the `.set.mtd` one where shown); removing a record, which only
`--force` does, needs the delete permission. A key made before a hive was added
to `--all` lacks these permissions, which is what `--all-available` is for.

| Hive | Flag | `sync pull` needs | `sync push` needs |
|---|---|---|---|
| `acl` | `--hive-acl` | `acl.get` | `acl.set` |
| `ai_agent` | `--hive-ai-agent` | `ai_agent.get.mtd`, `ai_agent.get` | `ai_agent.set` (+ `ai_agent.set.mtd`), `ai_agent.del` |
| `ai_memory` | `--hive-ai-memory` | `ai_memory.get.mtd`, `ai_memory.get` | `ai_memory.set` (+ `ai_memory.set.mtd`), `ai_memory.del` |
| `ai_skill` | `--hive-ai-skill` | `ai_skill.get.mtd`, `ai_skill.get` | `ai_skill.set` (+ `ai_skill.set.mtd`), `ai_skill.del` |
| `app_control_policy` | `--hive-app-control-policy` | `app_control.get` | `app_control.set` |
| `app_control_rule` | `--hive-app-control-rule` | `app_control.get` | `app_control.set` |
| `cloud_sensor` | `--hive-cloud-sensor` | `cloudsensor.get.mtd`, `cloudsensor.get` | `cloudsensor.set` (+ `cloudsensor.set.mtd`), `cloudsensor.del` |
| `cloudsec_code_rule` | `--hive-cloudsec-code-rule` | `cloudsec.get` | `cloudsec.set` |
| `cloudsec_policy` | `--hive-cloudsec-policy` | `cloudsec.get` | `cloudsec.set` |
| `cloudsec_provider` | `--hive-cloudsec-provider` | `cloudsec_provider.get.mtd`, `cloudsec_provider.get` | `cloudsec_provider.set` (+ `cloudsec_provider.set.mtd`), `cloudsec_provider.del` |
| `cloudsec_query` | `--hive-cloudsec-query` | `cloudsec.get` | `cloudsec.set` |
| `dr-general` | `--hive-dr-general` | `dr.list` | `dr.set`, `dr.del` |
| `dr-mail` | `--hive-dr-mail` | `mailsec.get` | `mailsec.set` |
| `dr-managed` | `--hive-dr-managed` | `dr.list.managed` | `dr.set.managed`, `dr.del.managed` |
| `dr-service` | `--hive-dr-service` | metadata: `dr.list`, `dr.list.managed`, `dr.list.replicant`, `dr.list.service`; data: `dr.list.replicant`, `dr.list.service` | `dr.set.replicant`, `dr.set.service`, `dr.del.replicant`, `dr.del.service` |
| `external_adapter` | `--hive-external-adapter` | `externaladapter.get.mtd`, `externaladapter.get` | `externaladapter.set` (+ `externaladapter.set.mtd`), `externaladapter.del` |
| `extension_config` | `--hive-extension-config` | `ext.conf.get.mtd`, `ext.conf.get` | `ext.conf.set` (+ `ext.conf.set.mtd`), `ext.conf.del` |
| `fp` | `--hive-fp` | `fp.ctrl` | `fp.ctrl` |
| `host_posture_rule` | `--hive-host-posture-rule` | `host_posture.get` | `host_posture.set` and `sensor.task` (delete: `host_posture.set`) |
| `investigation_plan` | `--investigation-plan` | `investigation_plan.get.mtd`, `investigation_plan.get` | `investigation_plan.set` (+ `investigation_plan.set.mtd`), `investigation_plan.del` |
| `investigation_policy` | `--investigation-policy` | `investigation_policy.get.mtd`, `investigation_policy.get` | `investigation_policy.set` (+ `investigation_policy.set.mtd`), `investigation_policy.del` |
| `lookup` | `--hive-lookup` | `lookup.get.mtd`, `lookup.get` | `lookup.set` (+ `lookup.set.mtd`), `lookup.del` |
| `mailsec_policy` | `--hive-mailsec-policy` | `mailsec.get` | `mailsec.set` |
| `mailsec_provider` | `--hive-mailsec-provider` | `mailsec_provider.get.mtd`, `mailsec_provider.get` | `mailsec_provider.set` (+ `mailsec_provider.set.mtd`), `mailsec_provider.del` |
| `playbook` | `--hive-playbook` | `playbook.get.mtd`, `playbook.get` | `playbook.set` (+ `playbook.set.mtd`), `playbook.del` |
| `query` | `--hive-query` | `query.get.mtd`, `query.get` | `query.set` (+ `query.set.mtd`), `query.del` |
| `secret` | `--hive-secret` | `secret.get.mtd`, `secret.get` | `secret.set` (+ `secret.set.mtd`), `secret.del` |
| `yara` | `--hive-yara` | `yara.get.mtd`, `yara.get` | `yara.set` (+ `yara.set.mtd`), `yara.del` |

The `investigation_*` hives exist only where the Investigation Engine is
enabled. The other sections `--all` syncs (outputs, integrity, exfil,
artifact, resources, extensions, org values, installation keys) use their usual
permissions, which this table does not cover.

### ACL scopes

Use `--hive-acl` to sync scope membership; `--all` includes it too:

```bash
limacharlie sync pull --config-file acl.yaml --hive-acl --hive-secret
limacharlie sync push --config-file acl.yaml --hive-acl --hive-secret --dry-run
```

Scope records are stored under `hives.acl`. Sync preserves `acl:` tags in other
records' `usr_mtd.tags`; it does not add classification tags automatically.
The syncing identity needs `acl.get` to fetch membership and `acl.set` to write
membership or add/remove `acl:` tags, in addition to the usual resource permissions.
It also needs the relevant scope membership to read restricted record contents;
`acl.set` does not itself grant that read access. Do not push redacted content
containing `acl_restricted: true` as a replacement for the original record.
Permission failures are reported by push and produce a nonzero exit status.
User members must use their stable UID, not an email address; API-key members
use the key name.

Existing Owner/Administrator assignments may need to be reapplied, or the new
permissions granted explicitly, before an existing automation identity can sync ACLs.

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

### Mail Security rules as code

Mail rules and policy are ordinary Hive records. Pull and push the same configuration used by the Mail Rules UI:

```bash
limacharlie sync pull --config-file mailsec.yaml --hive-dr-mail --hive-mailsec-policy
limacharlie sync push --config-file mailsec.yaml --hive-dr-mail --hive-mailsec-policy --dry-run
limacharlie sync push --config-file mailsec.yaml --hive-dr-mail --hive-mailsec-policy
```

These hives and `mailsec_provider` (`--hive-mailsec-provider`) are included by `--all`.
Vendor-managed `dr-mail` rules tagged `limacharlie` are reconciled daily by the
Email Security extension: edits pushed by sync revert to shipped content.
Disable unwanted rules with `usr_mtd.enabled: false` instead of editing them;
the extension preserves that choice. Customer-authored rules remain editable.
Rule keys have no reserved prefix; each `dr-mail` record contains one rule, with its on/off state in `usr_mtd.enabled`.

### Application Control as code

Application Control policies and rules are ordinary Hive records, each in its own hive (`app_control_policy` and `app_control_rule`):

```bash
limacharlie sync pull --config-file app-control.yaml --hive-app-control-policy --hive-app-control-rule
limacharlie sync push --config-file app-control.yaml --hive-app-control-policy --hive-app-control-rule --dry-run
limacharlie sync push --config-file app-control.yaml --hive-app-control-policy --hive-app-control-rule
```

Both hives are also included by `--all`. Records are stored under `hives.app_control_policy` and `hives.app_control_rule`; a rule's key is its rule ID and its `policies` field names the policy records it applies to. Push the policies together with the rules that reference them. The syncing identity needs `app_control.get` to pull and `app_control.set` to push.

### Cloud Security and Code Security configuration

```bash
limacharlie sync pull --config-file cloud-security.yaml --hive-cloudsec-provider \
  --hive-cloudsec-policy --hive-cloudsec-query --hive-cloudsec-code-rule
limacharlie sync push --config-file cloud-security.yaml --hive-cloudsec-provider \
  --hive-cloudsec-policy --hive-cloudsec-query --hive-cloudsec-code-rule --dry-run
```

All four hives are included by `--all`. Records retain their `data` and
`usr_mtd` metadata. Credentials such as `hive://secret/github-key` remain
references through pull and push; including the provider hive does not export
secret values. Sync the `secret` hive separately only when you intend to manage
its contents. Policy, query and code-rule reads need `cloudsec.get`, writes
`cloudsec.set`; response policy writes additionally need `cloudsec.respond`.
Provider records require `cloudsec_provider.get` / `cloudsec_provider.set` and
corresponding metadata permissions (plus `.del` for deletions).
See [Configuring Code Security](cloud-security.md#configuring-code-security).

### Investigation configuration sync

`sync pull` and `sync push` accept `--investigation-policy` and
`--investigation-plan`; `--all` includes both. Native records live at
`hives.investigation_policy.<record>` and `hives.investigation_plan.<record>`
with `data` and `usr_mtd` fields. Keep unknown data fields and user metadata
when editing exports. Apply reads native versions for CAS; Git is not a source
of unconditional ETags. Force deletion respects selected hives and tags.
