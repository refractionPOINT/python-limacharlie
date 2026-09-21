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
        assert org.client.request.call_count == 2  # No GET-then-merge on update.
