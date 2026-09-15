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
def test_the_flag_overrides_an_input_file_expiry_and_is_still_converted(mock_hive_cls, _org, _client):
    """The branch a metadata-only invocation does not reach.

    The flag and the file can both carry an expiry, and the flag wins. The two values here are
    deliberately NOT a factor of 1000 apart: with round numbers this test would pass whether the
    flag won or the file did, which is the trap that makes an override test look fine and prove
    nothing. Zero is not a separate case — 0*1000 is 0 — so it is asserted here rather than in a
    test of its own that could not fail.
    """
    hive = _hive_with_record()
    mock_hive_cls.return_value = hive
    payload = '{"data": {"a": 1}, "usr_mtd": {"expiry": 5555555555555}}'

    result = CliRunner().invoke(
        cli, ["hive", "set", "--hive-name", "secret", "--key", "k", "--expiry", "1789459200"], input=payload
    )

    assert result.exit_code == 0, result.output
    assert hive.set.call_args[0][0].expiry == 1789459200000

    hive.set.reset_mock()
    result = CliRunner().invoke(cli, ["hive", "set", "--hive-name", "secret", "--key", "k", "--expiry", "0"])
    assert result.exit_code == 0, result.output
    assert hive.set.call_args[0][0].expiry == 0


@patch("limacharlie.commands.hive.Client")
@patch("limacharlie.commands.hive.Organization")
@patch("limacharlie.commands.hive.Hive")
def test_a_negative_expiry_is_refused_rather_than_amplified(mock_hive_cls, _org, _client):
    """Guarding only the upper direction left the lower one worse than before: -1 became -1000,
    and the API answered with the same opaque INVALID_EXPIRY_TIME this flag existed to stop
    producing."""
    hive = _hive_with_record()
    mock_hive_cls.return_value = hive

    result = CliRunner().invoke(cli, ["hive", "set", "--hive-name", "secret", "--key", "k", "--expiry", "-1"])

    assert result.exit_code != 0
    assert "negative" in result.output
    hive.set.assert_not_called()


@patch("limacharlie.commands.hive.Client")
@patch("limacharlie.commands.hive.Organization")
@patch("limacharlie.commands.hive.Hive")
def test_the_conversion_is_reported_rather_than_silent(mock_hive_cls, _org, _client):
    """`hive get` renders the stored value, so without this line a user types 1789459200, reads
    back 1789459200000, and has nothing anywhere to explain the difference."""
    hive = _hive_with_record()
    mock_hive_cls.return_value = hive

    result = CliRunner().invoke(cli, ["hive", "set", "--hive-name", "secret", "--key", "k", "--expiry", "1789459200"])

    assert result.exit_code == 0, result.output
    assert "1789459200000" in result.output and "milliseconds" in result.output


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
