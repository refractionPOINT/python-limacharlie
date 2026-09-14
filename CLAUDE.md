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
