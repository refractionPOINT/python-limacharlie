"""Shell completion script generation for LimaCharlie CLI.

Outputs shell-specific completion scripts that can be sourced or
eval'd to enable tab-completion for all commands, options, and arguments.
"""

from __future__ import annotations

import click
from click.shell_completion import get_completion_class

from ..discovery import register_explain


_EXPLAIN_COMPLETION = """\
Generate shell completion scripts for the LimaCharlie CLI.

Supported shells: bash, zsh, fish.

Setup instructions:

  Bash (add to ~/.bashrc):
    eval "$(limacharlie completion bash)"

  Zsh (add to ~/.zshrc):
    eval "$(limacharlie completion zsh)"

  Fish (add to ~/.config/fish/completions/limacharlie.fish):
    limacharlie completion fish > ~/.config/fish/completions/limacharlie.fish

After sourcing, press <TAB> to complete commands, subcommands, and options.
"""

register_explain("completion", _EXPLAIN_COMPLETION)


@click.command("completion")
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def cmd(shell: str) -> None:
    """Generate shell completion script.

    Output a completion script for SHELL (bash, zsh, or fish).
    Eval the output in your shell profile to enable tab-completion.

    Examples:

    \b
        eval "$(limacharlie completion bash)"
        eval "$(limacharlie completion zsh)"
        limacharlie completion fish > ~/.config/fish/completions/limacharlie.fish
    """
    # Import the root CLI group to generate completions for.
    from ..cli import cli as root_cli

    cls = get_completion_class(shell)
    if cls is None:
        raise click.ClickException(f"Unsupported shell: {shell}")

    comp = cls(
        cli=root_cli,
        ctx_args={},
        prog_name="limacharlie",
        complete_var="_LIMACHARLIE_COMPLETE",
    )
    click.echo(comp.source())
