# python-limacharlie

Python SDK and CLI for LimaCharlie. `NEW_CLI.md` is the CLI design document.
`.claude/docs/sdk-docstring-conventions.md` is the docstring checklist for
`limacharlie/sdk/`.

Run the tests the way CI does: `pytest tests/unit/ tests/microbenchmarks/`.

## Adding, renaming, or moving a CLI command

Three hand-maintained maps describe the command surface. None of them updates
itself. Update all of them in the same change:

1. **`limacharlie/cli.py` — `_COMMAND_MODULE_MAP`.** Maps a top-level command
   name to its module so the CLI can lazy-load it. Enforced by
   `tests/unit/test_cli_command_map_lint.py`.
2. **`limacharlie/discovery.py` — `PROFILES`.** Groups commands by use-case;
   this is what `limacharlie help discover` prints. A verb in no profile is
   invisible to anyone — or any agent — discovering the CLI, and an entry
   naming a command that no longer exists prints advice that cannot be
   followed. Enforced by `tests/unit/test_discovery.py`.
3. **`doc/cli/`.** The user-facing command reference.

Reuse an existing profile name where one fits. `PROFILES` is meant to mirror
the profiles the LimaCharlie MCP server exposes (`NEW_CLI.md` §1.1), so the
names are a cross-repo contract, not a local choice.

When the lint reports a `PROFILES` entry that no longer resolves, find the
command's current spelling before touching the entry — most rotted entries were
renamed or moved, not removed. Drop an entry only when the command is genuinely
gone or has become a flag on another command.

## Adding a hive to sync, or anything else that needs a new permission

Customers back up and restore whole orgs with `limacharlie sync pull --all`,
often from a scheduled job using an API key per org that holds only the
permissions it needed when it was made. A hive added to `_HIVE_FLAG_MAP` in
`limacharlie/commands/sync.py` joins `--all` in the next release. From then
on, every `--all` pull with a key that lacks that hive's read permission fails
for the whole org until someone grants the permission. `--all-available` skips
the hive with a warning instead, but many jobs still use `--all`. Customers can
only find out which permission to grant from the changelog, so in the same
change:

1. **Add a "New permissions" entry to `CHANGELOG.md` under "Unreleased".** Name
   the hive, the flag, and every permission it takes: the read permission that
   `sync pull` needs, and the write permissions that `sync push` needs. Say
   plainly that `sync pull --all` fails with a key that lacks the read
   permission and that `--all-available` skips the hive. Example:

   ```markdown
   ### New permissions: `host_posture_rule` hive

   - `sync pull --all` and `--hive-host-posture-rule` now read the
     `host_posture_rule` hive, which needs `host_posture.get`. A key without it
     fails `sync pull --all`; `sync pull --all-available` skips the hive with
     a warning. Pushing rules needs `host_posture.set` and `sensor.task`.
   ```

2. **Take the permission names from the hive's definition in the Hive
   service, not from the hive name.** They often differ: `host_posture_rule`
   reads with `host_posture.get`, and `external_adapter` with
   `externaladapter.get.mtd`. Never guess a name. If you can't confirm it, say
   so in the PR and ask.
3. **Do the same for any new CLI command or SDK call that needs a permission
   no earlier release needed.** The same rule applies: one changelog line
   naming the permission.
4. **Add the hive to the Go SDK too** (`KnownHives` and `SyncAll()` in
   go-limacharlie). The Infrastructure extension and Git Sync use that list,
   and that repo has the same rule.
