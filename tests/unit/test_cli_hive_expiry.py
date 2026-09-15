"""The hive --expiry flag speaks seconds; the hive API stores milliseconds.

Before this conversion no value satisfied both ends: anything ``validate_epoch_seconds``
accepted was rejected by the API as already expired (``INVALID_EXPIRY_TIME``), and anything the
API accepted was refused by the CLI as looking like milliseconds. The flag was unusable.
"""

from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie.sdk.hive import HiveRecord


def _hive_with_record():
    hive = MagicMock()
    hive.get_metadata.return_value = HiveRecord("k")
    hive.set.return_value = {"guid": "g1"}
    return hive


@patch("limacharlie.commands.hive.Client")
@patch("limacharlie.commands.hive.Organization")
@patch("limacharlie.commands.hive.Hive")
def test_expiry_flag_is_sent_to_the_api_in_milliseconds(mock_hive_cls, _org, _client):
    hive = _hive_with_record()
    mock_hive_cls.return_value = hive

    result = CliRunner().invoke(cli, ["hive", "set", "--hive-name", "secret", "--key", "k", "--expiry", "1789459200"])

    assert result.exit_code == 0, result.output
    assert hive.set.call_args[0][0].expiry == 1789459200000


@patch("limacharlie.commands.hive.Client")
@patch("limacharlie.commands.hive.Organization")
@patch("limacharlie.commands.hive.Hive")
def test_zero_still_means_never_rather_than_the_epoch(mock_hive_cls, _org, _client):
    hive = _hive_with_record()
    mock_hive_cls.return_value = hive

    result = CliRunner().invoke(cli, ["hive", "set", "--hive-name", "secret", "--key", "k", "--expiry", "0"])

    assert result.exit_code == 0, result.output
    assert hive.set.call_args[0][0].expiry == 0


@patch("limacharlie.commands.hive.Client")
@patch("limacharlie.commands.hive.Organization")
@patch("limacharlie.commands.hive.Hive")
def test_a_millisecond_value_is_still_refused(mock_hive_cls, _org, _client):
    """The guard stays. Accepting milliseconds too would make the flag's unit unknowable —
    1789459200000 would mean 2026, and 1789459200 would also mean 2026, so a user could never
    tell which one they had typed."""
    hive = _hive_with_record()
    mock_hive_cls.return_value = hive

    result = CliRunner().invoke(cli, ["hive", "set", "--hive-name", "secret", "--key", "k", "--expiry", "1789459200000"])

    assert result.exit_code != 0
    assert "milliseconds" in result.output
    hive.set.assert_not_called()


@patch("limacharlie.commands.hive.Client")
@patch("limacharlie.commands.hive.Organization")
@patch("limacharlie.commands.hive.Hive")
def test_an_input_file_expiry_is_passed_through_untouched(mock_hive_cls, _org, _client):
    """A record read back from the API carries MILLISECONDS, so converting this path too would
    multiply it again and push the expiry ~55,000 years out. ``hive get | hive set`` has to
    round-trip."""
    hive = _hive_with_record()
    mock_hive_cls.return_value = hive
    payload = '{"data": {"a": 1}, "usr_mtd": {"expiry": 1789459200000}}'

    result = CliRunner().invoke(cli, ["hive", "set", "--hive-name", "secret", "--key", "k"], input=payload)

    assert result.exit_code == 0, result.output
    assert hive.set.call_args[0][0].expiry == 1789459200000
