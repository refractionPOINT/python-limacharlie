[Documentation](../README.md) > [CLI](README.md) > Host Posture

# Host Posture

Host Posture (`ext-host-posture`) checks Windows, macOS and Linux sensors for misconfigurations. The checks are rules in the organization's `host_posture_rule` hive, one record per rule. The extension ships no rules: install LimaCharlie's default pack, then edit, disable or add your own. Every rule is equally trusted, whoever wrote it.

Subscribe first: `limacharlie extension subscribe --name ext-host-posture`.

| Command | What it does |
|---|---|
| `host-posture install-defaults` | Write the default pack into the rule hive. |
| `host-posture rules ...` | The rule hive: `list`, `get`, `set`, `delete`, `enable`, `disable`, `tag`. |
| `host-posture scan --sid SID` | Check one online sensor now. |
| `host-posture sweep [--tag TAG]` | Sweep sensors now, including offline ones when they return. |
| `host-posture results ...` | Per-host results: `summary`, `hosts`, `host`, `rules`, `rule-hosts`, `standards`. |
| `host-posture status` | Extension health: build, pack version, rule counts. |

## Permissions

- `host_posture.get` reads rules and results. `host_posture.set` writes rules.
- Saving a rule (`rules set`), and `rules enable` and `rules disable`, also need `sensor.task`, because a rule runs on your sensors.
- `rules delete` needs only `host_posture.set`.

## install-defaults

```bash
limacharlie host-posture install-defaults
limacharlie host-posture install-defaults --dry-run
limacharlie host-posture install-defaults --update
limacharlie host-posture install-defaults --id lc.windows.network.smb1-server --disabled
```

The command reads the pack from the extension and writes each rule into your hive with **your** permissions. The extension decides what each rule needs (`pack_status`); the CLI computes nothing itself. Nothing is overwritten silently:

| State | Meaning | What the command does |
|---|---|---|
| `new` | No record for it. | Creates it, enabled (`--disabled` creates it disabled). Creation is conditional, so a record that appears in the meantime is not replaced. |
| `current` | Your record is the pack's rule, unedited, at the same version. | Nothing. |
| `update_available` | Unedited, and the pack has a newer version. | Replaces it with `--update`. The write is conditional on the etag that was read. Enabled state, expiry, other tags, `ui_actions` and your own comment are kept. |
| `edited` | Your record differs from what the pack installed, or has no digest tag. Checked first. | Skips it unless `--force`. |
| `org_newer` | Your record is unedited but its version is higher than the pack's. | Skips it unless `--force`. |

If a write finds the record changed meanwhile (a new rule that appeared, an update that lost the etag race), nothing is retried: the rule is skipped and `pack_status` is read again, so the entry reports `state_now`.

`--force` implies `--update`. `--id` (repeatable) installs only those rules. `--dry-run` writes nothing.

Records the command writes carry the tag `lc:default-pack`, a tag `lc:pack-sha256:<digest>` with the digest exactly as the extension returned it with the pack, and a comment naming the pack version. The extension compares that digest with the record as it is now to tell an edited rule from an unedited one. A record without the tag counts as edited.

The output has `pack_version`, `created`, `updated`, `skipped` (each with a `reason`) and `failed`. The command exits 1 when a write failed.

## rules

```bash
limacharlie host-posture rules list
limacharlie host-posture rules get --key lc.linux.kernel.ptrace-scope
limacharlie host-posture rules set --key acme.linux.fs.protected-symlinks --input-file rule.yaml --enabled
limacharlie host-posture rules disable --key lc.linux.kernel.ptrace-scope
limacharlie host-posture rules delete --key acme.linux.fs.protected-symlinks --confirm
```

A record (`data`):

```yaml
data:
  rule:                        # one lc-posture/v1 rule document
    apiVersion: lc-posture/v1
    kind: Signature
    id: acme.linux.fs.protected-symlinks   # must equal the record key
    version: 1
    # ... probes, violation, evidence, remediation, tests
  scope:                       # optional
    sensor_tags: [prod]        # run only on sensors with one of these tags
    exclude_sensor_tags: [kiosk]   # skip sensors with any of these (wins)
```

The server validates the whole rule, including its tests, and refuses it with the field path of every problem; the CLI does not validate. Pass `--enabled` when creating a record, as with other hives, so that the rule runs. See the [rule format](https://docs.limacharlie.io/7-administration/config-hive/host-posture-rule/) and [how to write rules](https://docs.limacharlie.io/5-integrations/extensions/limacharlie/host-posture-writing-rules/).

The rule hive also syncs with `limacharlie sync` (`--hive-host-posture-rule`, and `--all`) and works with the generic `limacharlie hive` commands (`--hive-name host_posture_rule`).

## scan and sweep

```bash
limacharlie host-posture scan --sid 11111111-2222-3333-4444-555555555555
limacharlie host-posture sweep
limacharlie host-posture sweep --tag prod --tag web
```

`scan` needs an online sensor and returns `job_id`, `sid`, `platform` and `tasks_issued`. `sweep` uses reliable tasking, so it also reaches sensors that are offline now, and returns `job_id` and `sensors_tasked`. With `--tag`, only sensors carrying at least one of the tags are swept.

## results

```bash
limacharlie host-posture results summary
limacharlie host-posture results hosts --severity high --platform windows --limit 50
limacharlie host-posture results host --sid 11111111-2222-3333-4444-555555555555
limacharlie host-posture results rules --severity critical
limacharlie host-posture results rule-hosts --rule-id lc.windows.network.smb1-server --status fail
limacharlie host-posture results standards --framework cis
```

Filtering and paging happen on the server. `--limit` is at most 200 (default 50); pass a page's `next_cursor` as `--cursor` to get the next. Statuses are `pass`, `fail`, `error`, `not_applicable` and `unsupported`; severities are `critical`, `high`, `medium`, `low` and `info`.

`results summary` reports `cloud_security` as `published`, `not_subscribed` or `error`: organizations also subscribed to Cloud Security additionally get one rolled-up finding per failing rule there.
