"""Workspace onboarding regressions: discovery and lossless provider writes."""
import json
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from limacharlie.cli import cli


def test_mailsec_hives_are_discoverable_without_credentials():
    result = CliRunner().invoke(cli, ["--output", "json", "hive", "list-types"])
    assert result.exit_code == 0, result.output
    assert {"mailsec_provider", "mailsec_policy", "dr-mail"} <= set(json.loads(result.output))


@pytest.mark.parametrize("envelope", [False, True])
def test_provider_create_then_update_sends_zero_without_merging(tmp_path, envelope):
    """Exercise Click's file parser and the real SDK serializer, capturing HTTP params."""
    org = MagicMock()
    org.oid = "test-oid"
    org.client.request.return_value = {"guid": "g1"}
    record = tmp_path / "gws.yaml"
    with patch("limacharlie.commands.hive.Client"), patch(
        "limacharlie.commands.hive.Organization", return_value=org
    ):
        for days in (14, 0):
            payload = {"provider": "gworkspace", "credentials": "hive://secret/gws-mail",
                       "ingest": {"mode": "push", "backfill_days": days}}
            record.write_text(yaml.safe_dump({"data": payload} if envelope else payload))
            result = CliRunner().invoke(cli, [
                "hive", "set", "--hive-name", "mailsec_provider", "--key", "gws-prod",
                "--input-file", str(record), "--enabled",
            ])
            assert result.exit_code == 0, result.output
            call = org.client.request.call_args
            assert call.args == ("POST", "hive/mailsec_provider/test-oid/gws-prod/data")
            assert json.loads(call.kwargs["params"]["data"]) == payload
        # The data is never read back and merged; --enabled only reads metadata.
        reads = [c.args[1] for c in org.client.request.call_args_list if c.args[0] == "GET"]
        assert reads == ["hive/mailsec_provider/test-oid/gws-prod/mtd"] * 2
        assert org.client.request.call_count == 4


def test_imap_provider_record_keeps_its_nested_mailbox_list(tmp_path):
    """An imap record carries per-mailbox credentials; none of it may be flattened or merged."""
    org = MagicMock()
    org.oid = "test-oid"
    org.client.request.return_value = {"guid": "g1"}
    payload = {
        "provider": "imap",
        "imap": {"mailboxes": [
            {"address": "alice@gmail.com", "host": "imap.gmail.com", "port": 993,
             "security": "tls", "credentials": "hive://secret/imap-alice"},
            {"address": "bob@mail.example.org", "host": "imap.example.org", "port": 143,
             "security": "starttls", "username": "bob", "credentials": "hive://secret/imap-bob"},
        ]},
        "ingest": {"mode": "auto", "backfill_days": 14},
    }
    record = tmp_path / "imap.yaml"
    record.write_text(yaml.safe_dump(payload))
    with patch("limacharlie.commands.hive.Client"), patch(
        "limacharlie.commands.hive.Organization", return_value=org
    ):
        result = CliRunner().invoke(cli, [
            "hive", "set", "--hive-name", "mailsec_provider", "--key", "imap",
            "--input-file", str(record), "--enabled",
        ])
    assert result.exit_code == 0, result.output
    call = org.client.request.call_args
    assert call.args == ("POST", "hive/mailsec_provider/test-oid/imap/data")
    assert json.loads(call.kwargs["params"]["data"]) == payload
