"""Tests for limacharlie.sdk.artifacts module."""

from unittest.mock import MagicMock
import json
import pytest

from limacharlie.sdk.artifacts import Artifacts


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    return org


@pytest.fixture
def artifacts(mock_org):
    return Artifacts(mock_org)


class TestArtifactsList:
    def test_list_default_time_range(self, artifacts, mock_org):
        mock_org.client.request.return_value = {"artifacts": []}
        artifacts.list()
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("GET", "insight/test-oid/artifacts")
        qp = call_args[1]["query_params"]
        assert "start" in qp
        assert "end" in qp
        # start/end should be string representations of ints
        assert int(qp["start"]) > 0
        assert int(qp["end"]) > 0
        assert int(qp["end"]) > int(qp["start"])

    def test_list_default_range_is_24h(self, artifacts, mock_org):
        mock_org.client.request.return_value = {"artifacts": []}
        artifacts.list()
        qp = mock_org.client.request.call_args[1]["query_params"]
        diff = int(qp["end"]) - int(qp["start"])
        assert diff == 86400

    def test_list_with_sid(self, artifacts, mock_org):
        mock_org.client.request.return_value = {"artifacts": []}
        artifacts.list(sid="sensor-123")
        qp = mock_org.client.request.call_args[1]["query_params"]
        assert qp["sid"] == "sensor-123"

    def test_list_with_explicit_times(self, artifacts, mock_org):
        mock_org.client.request.return_value = {"artifacts": []}
        artifacts.list(start=1000, end=2000)
        qp = mock_org.client.request.call_args[1]["query_params"]
        assert qp["start"] == "1000"
        assert qp["end"] == "2000"

    def test_list_with_cursor_omits_times(self, artifacts, mock_org):
        mock_org.client.request.return_value = {"artifacts": []}
        artifacts.list(cursor="abc123")
        qp = mock_org.client.request.call_args[1]["query_params"]
        assert qp["cursor"] == "abc123"
        assert "start" not in qp
        assert "end" not in qp


class TestArtifactsGetUrl:
    def test_get_url(self, artifacts, mock_org):
        mock_org.client.request.return_value = {"export": "https://signed-url"}
        result = artifacts.get_url("art-id-1")
        mock_org.client.request.assert_called_once_with(
            "POST", "insight/test-oid/artifacts/originals/art-id-1",
        )
        assert result["export"] == "https://signed-url"


class TestArtifactsRules:
    def test_get_rules(self, artifacts, mock_org):
        mock_org.client.request.return_value = {"rules": []}
        artifacts.get_rules()
        mock_org.client.request.assert_called_once_with(
            "GET", "insight/test-oid/artifacts/rules",
        )

    def test_set_rule(self, artifacts, mock_org):
        mock_org.client.request.return_value = {}
        artifacts.set_rule(
            rule_name="collect-logs",
            platforms=["windows"],
            patterns=["C:\\logs\\*.log"],
            is_delete_after=True,
            retention_days=14,
        )
        call_args = mock_org.client.request.call_args
        assert call_args[0] == ("POST", "insight/test-oid/artifacts/rules")
        body = json.loads(call_args[1]["raw_body"])
        assert body["name"] == "collect-logs"
        assert body["platforms"] == ["windows"]
        assert body["patterns"] == ["C:\\logs\\*.log"]
        assert body["is_delete_after"] is True
        assert body["days_retention"] == 14
        assert call_args[1]["content_type"] == "application/json"

    def test_set_rule_with_tags(self, artifacts, mock_org):
        mock_org.client.request.return_value = {}
        artifacts.set_rule(
            rule_name="tagged-rule",
            platforms=["linux"],
            patterns=["/var/log/*.log"],
            tags=["server", "prod"],
        )
        body = json.loads(mock_org.client.request.call_args[1]["raw_body"])
        assert body["tags"] == ["server", "prod"]

    def test_set_rule_without_tags_omits_key(self, artifacts, mock_org):
        mock_org.client.request.return_value = {}
        artifacts.set_rule(
            rule_name="no-tags",
            platforms=["macos"],
            patterns=["/tmp/*.log"],
        )
        body = json.loads(mock_org.client.request.call_args[1]["raw_body"])
        assert "tags" not in body

    def test_delete_rule(self, artifacts, mock_org):
        mock_org.client.request.return_value = {}
        artifacts.delete_rule("collect-logs")
        mock_org.client.request.assert_called_once_with(
            "DELETE", "insight/test-oid/artifacts/rules",
            params={"name": "collect-logs"},
        )


class TestArtifactsUploadRetention:
    """The ingestion API keeps an upload for 365 days when no retention
    header is sent, so the client must always send one."""

    TOKEN = "11111111-2222-3333-4444-555555555555"

    @pytest.fixture
    def sent_headers(self, monkeypatch):
        captured = []

        def fake_urlopen(request):
            captured.append({k.lower(): v for k, v in request.header_items()})
            resp = MagicMock()
            resp.read.return_value = b'{"payload_id": "p"}'
            return resp

        monkeypatch.setattr("limacharlie.sdk.artifacts.urlopen", fake_urlopen)
        return captured

    @pytest.fixture
    def small_file(self, tmp_path):
        p = tmp_path / "a.txt"
        p.write_bytes(b"data")
        return str(p)

    def _artifacts(self, mock_org):
        mock_org.get_urls.return_value = {"logs": "ingest.example"}
        return Artifacts(mock_org, access_token=self.TOKEN)

    def test_default_retention_sent_when_omitted(self, mock_org, sent_headers, small_file):
        self._artifacts(mock_org).upload(small_file)
        assert sent_headers[0]["lc-retention-days"] == "30"

    def test_default_retention_sent_when_none(self, mock_org, sent_headers, small_file):
        self._artifacts(mock_org).upload(small_file, retention_days=None)
        assert sent_headers[0]["lc-retention-days"] == "30"

    def test_explicit_retention_sent(self, mock_org, sent_headers, small_file):
        self._artifacts(mock_org).upload(small_file, retention_days=2)
        assert sent_headers[0]["lc-retention-days"] == "2"

    def test_default_retention_on_every_multipart_chunk(self, mock_org, sent_headers, tmp_path, monkeypatch):
        monkeypatch.setattr("limacharlie.sdk.artifacts.MAX_UPLOAD_PART_SIZE", 4)
        p = tmp_path / "big.bin"
        p.write_bytes(b"0123456789")
        self._artifacts(mock_org).upload(str(p))
        assert len(sent_headers) == 3
        assert all(h["lc-retention-days"] == "30" for h in sent_headers)

    def test_cli_upload_without_flag_sends_default(self, sent_headers, small_file, monkeypatch):
        from click.testing import CliRunner
        from unittest.mock import patch
        from limacharlie.cli import cli

        monkeypatch.setenv("LC_LOGS_TOKEN", self.TOKEN)
        with patch("limacharlie.commands.artifact.Client"), \
             patch("limacharlie.commands.artifact.Organization") as org_cls:
            org = org_cls.return_value
            org.oid = "test-oid"
            org.get_urls.return_value = {"logs": "ingest.example"}
            result = CliRunner().invoke(cli, ["artifact", "upload", "--file", small_file])

        assert result.exit_code == 0, result.output
        assert sent_headers[0]["lc-retention-days"] == "30"
