[Documentation](../README.md) > [CLI](README.md) > Deception

# Deception

Deception (`ext-deception`) plants unique decoys on endpoints through the sensor and alerts when one is read or used. It also makes drops: tokens with no sensor behind them (a link, a QR code, a host name, a document) that you put wherever an intruder would look.

Everything that decides what alerts is one record: the `ext-deception` record of the `extension_config` hive (policies, templates, reader allowlists, declared drops). The extension keeps no learned state that changes what alerts.

Subscribe first: `limacharlie extension subscribe --name ext-deception`.

| Command | What it does |
|---|---|
| `deception config get` / `set` / `enable` | The configuration record. |
| `deception kinds` | Decoy kinds with their spec schemas, the template library, benign readers. |
| `deception plan` | What `deploy` would do (read-only). |
| `deception deploy` | Apply the configuration: rules, other extensions' entries, decoys. |
| `deception rollout-status` | How far the rollout to the sensors is (cheap to poll). |
| `deception list` | Decoys (never their secret values). |
| `deception list-hosts` | Targeted sensors and sensors with decoys, with their status. |
| `deception verify` / `rotate` / `remove` | Act on decoys by policy, sensor, template or instance id. |
| `deception coverage` | What is covered, unavailable, blind or broken. |
| `deception test-fire` | Prove each alert path (or one drop) with synthetic hits. |
| `deception list-test-runs` / `list-test-paths` | Test-fire runs, and every alert path with its latest result. |
| `deception list-hits` | Recorded hits, or hit groups. |
| `deception list-readers` | Who reads the decoys, with the allowlist entry that would approve them. |
| `deception restore-rules` | Put shipped detection rules back as shipped, enabled. |
| `deception drops ...` | `create`, `list`, `get`, `update`, `rotate`, `delete`, `draft-document`. |
| `deception uninstall` / `uninstall-status` | Remove everything before unsubscribing; read where it stands. |

In a terminal (`--output table`, the default there), a list prints its rows as a table and the rest of the answer (page token, totals, summary) as YAML, and any other answer prints as YAML, so no value is cut. Every other `--output` format prints the answer whole.

Every command maps to one extension request (`extension request --name ext-deception --action <action>` does the same with raw JSON). The extension validates every request and the configuration; the CLI only checks the shape of its own flags.

## Permissions

- `ext.request` for every request.
- `ext.conf.get` and `ext.conf.set` for the configuration record. `config set` reads the stored metadata first, which takes `ext.conf.get` (or `ext.conf.get.mtd`).

No permission is new: these are the ones `extension request` and `extension config-get` / `config-set` already need.

## Quick start

```bash
limacharlie deception kinds --output yaml          # the template library and kind schemas
limacharlie deception config set --input-file deception.yaml
limacharlie deception plan
limacharlie deception deploy
limacharlie deception rollout-status
limacharlie deception coverage
limacharlie deception test-fire
limacharlie deception list-readers                 # while a policy observes
```

## config

```bash
limacharlie deception config get --output yaml > ext-deception.yaml
limacharlie deception config set --input-file deception.yaml
limacharlie deception config set --input-file ext-deception.yaml   # compare-and-set
limacharlie deception config enable
```

`config set` takes either the configuration itself (`schema_version`, `policies`, `templates`, ...) or a record as `config get` prints it (`data` holding the configuration, with `usr_mtd` and `sys_mtd.etag`).

- **Etag.** The etag in the input, or `--etag`, makes the write a compare-and-set: it is refused if someone saved the record since it was read, or deleted it. `--no-etag` ignores the etag in the input.
- **Enabled state.** Without `usr_mtd` or a flag, an existing record keeps its metadata, and a record that does not exist yet is created **enabled** (a disabled record gives the extension an empty configuration). Creation is conditional, so a record created meanwhile is not replaced. A `usr_mtd` block replaces the stored metadata, as with `hive set`. `--enabled` / `--disabled` set the state and win over `usr_mtd`; on an existing record they keep its other metadata, and the write is conditional on the metadata they were read with.
- `config enable` enables a record saved disabled (for example a new record written by `extension config-set`).

The record also works with `limacharlie extension config-get` / `config-set`, the generic `hive` commands and `limacharlie sync` (`--hive-extension-config`).

## plan, deploy and rollout

```bash
limacharlie deception plan --policy linux-servers
limacharlie deception plan --draft-policy policy.yaml --draft-templates templates.yaml
limacharlie deception deploy
limacharlie deception deploy --apply-pack deception-alert --apply-pack deception-respond
limacharlie deception rollout-status
limacharlie deception restore-rules --rule deception-respond
```

`--draft-policy` plans an unsaved policy record instead, with `--draft-templates` (a list of template records the save would add). `deploy` never overwrites a shipped detection rule you edited: `--apply-pack` (repeatable) or `--apply-all-pack` replace them with the current shipped version. The rollout continues after `deploy` returns. `restore-rules` exits 1 unless every rule was restored and reads back enabled.

## Decoys and hosts

```bash
limacharlie deception list --policy linux-servers
limacharlie deception list --state failed --exclude-skipped --summary
limacharlie deception list-hosts --sort problems --summary
limacharlie deception verify --sid 11111111-2222-3333-4444-555555555555
limacharlie deception rotate --template kubeconfig-backup
limacharlie deception remove --instance-id <id> --confirm
```

`verify`, `rotate` and `remove` take `--instance-id` (repeatable), `--sid`, `--policy` and `--template`, combined when several are given. One call handles a bounded batch: `more: true` means run it again. `remove` needs `--confirm`.

Lists are filtered and paged on the server. `--page-size` is at most 500 (default 100); pass a page's `next_page_token` as `--page-token` to get the next one.

## Coverage, test-fire and hits

```bash
limacharlie deception coverage
limacharlie deception test-fire --policy linux-servers
limacharlie deception test-fire --drop-id <drop id>
limacharlie deception list-test-runs --state pending
limacharlie deception list-test-paths --state failed
limacharlie deception list-hits --layer read --mode observe --page-size 50
limacharlie deception list-hits --group --event-type deception_hit --event-type deception_drop_hit
limacharlie deception list-readers --days 7 --platform linux
```

`list-hits` takes `--since` and `--until` in Unix seconds. `--event-type` and `--auto-response-outcome` are repeatable. `--hit-id` reads one hit and ignores the other filters.

## Drops

```bash
limacharlie deception drops create --form url --label "finance wiki: payroll page" --memo "pasted in the payroll space"
limacharlie deception drops create --form document --format docx --label "HR share" --title "Salary review 2027" --save salary-review.docx
limacharlie deception drops create --form qr --label "server room door" --save door.svg
limacharlie deception drops list --last-hit never
limacharlie deception drops get --name finance-wiki-payroll
limacharlie deception drops update --drop-id <id> --state disabled
limacharlie deception drops rotate --drop-id <id>
limacharlie deception drops delete --drop-id <id> --confirm
limacharlie deception drops draft-document --format docx
```

`create`, `get` and `rotate` print what to paste (the only answers that carry a secret value). `--save PATH` also writes the document (checked against its `sha256`) or the QR code as SVG to a file; the answer is printed either way, and `drops create --save` refuses a url or hostname drop before making it.

A document's content comes from `--title`, `--line` (repeatable, one paragraph each), `--link-text`, `--author`, `--file-name`, or `--document-file` (YAML or JSON with those fields; the flags override it). A field left out is generated.

`update` and `rotate` are compare-and-set on the drop's version: pass `--version` as read, or leave it out to use the current one. On `update`, `--observe-until ""` clears it, `--redirect-url ""` removes the redirect and `--reset-document` makes the whole document generated again. Drops declared in the configuration's `drops` list are changed there: `update` and `delete` refuse them.

## Uninstall

```bash
limacharlie deception uninstall --confirm
limacharlie deception uninstall-status
limacharlie deception uninstall --force --confirm
limacharlie deception uninstall --cancel
```

Run it **before** unsubscribing, and again until `uninstall-status` reports `safe_to_unsubscribe`. `--force` finishes although decoys remain on offline sensors; `--cancel` abandons it.
