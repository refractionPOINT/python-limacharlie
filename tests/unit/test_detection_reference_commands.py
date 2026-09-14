"""Parse the published examples through real Click options without API calls.

Unlike appending --help (which skips required-argument validation), replacing
only the leaf callback exercises option names, required values, types and paths.
Handler behavior for D&R files and AI arguments is tested separately.
"""
import re
import shlex
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.help_topics import CHEATSHEETS

REFERENCE = Path(__file__).resolve().parents[2] / "doc/cli/detection-response.md"


def examples():
    text = REFERENCE.read_text().replace("\\\n", " ")
    return [line.strip() for block in re.findall(r"```bash\n(.*?)```", text, re.S)
            for line in block.splitlines() if line.strip().startswith("limacharlie ")] + [
                line.strip() for line in CHEATSHEETS["detection-engineering"].splitlines()
                if line.strip().startswith("limacharlie ")]


@pytest.mark.parametrize("example", examples())
def test_reference_command_parses(example, tmp_path, monkeypatch):
    for name in ("rule.yaml", "detect.yaml", "respond.yaml", "events.json", "fp.yaml", "dr.yaml"):
        (tmp_path / name).write_text("{}")
    monkeypatch.chdir(tmp_path)
    args = shlex.split(example)[1:]
    command = cli
    ctx = click.Context(cli)
    for word in args:
        if not isinstance(command, click.Group):
            break
        child = command.get_command(ctx, word)
        assert child is not None, f"Unknown command {word}: {example}"
        command = child
        ctx = click.Context(command, info_name=word, parent=ctx)
    assert not isinstance(command, click.Group), example
    called = []
    monkeypatch.setattr(command, "callback", lambda **kwargs: called.append(kwargs))
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert len(called) == 1, example
