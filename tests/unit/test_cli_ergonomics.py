"""Tests for CLI discoverability/ergonomics improvements.

Covers the global projection flags (--fields/--sort-by/--reverse), the
api-key list --name filter, hive validate verdict, hive set metadata
flags, secret set --value / tag subcommand, dr set --detect/--respond,
adapter list-types, and hive schema flat rendering.
"""

import json
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from limacharlie.cli import cli
from limacharlie import output as output_mod
from limacharlie.sdk.hive import HiveRecord


def _extract_json(text):
    """Return the JSON document embedded in mixed stdout/stderr output.

    This CliRunner version merges stderr into output, so a stderr status
    line may precede the JSON body; slice from the first '{' or '['.
    """
    for i, ch in enumerate(text):
        if ch in "{[":
            return text[i:]
    return text


# ---------------------------------------------------------------------------
# Global projection state (module-level setters mirror set_filter_expr)
# ---------------------------------------------------------------------------

class TestProjectionState:
    def teardown_method(self):
        output_mod.set_fields(None)
        output_mod.set_sort_by(None)
        output_mod.set_reverse(False)

    def test_fields_module_level_fallback(self):
        output_mod.set_fields(["a", "c"])
        out = output_mod.format_output([{"a": 1, "b": 2, "c": 3}], "json")
        assert json.loads(out) == [{"a": 1, "c": 3}]

    def test_sort_by_and_reverse(self):
        output_mod.set_sort_by("a")
        output_mod.set_reverse(True)
        data = [{"a": 1}, {"a": 3}, {"a": 2}]
        out = output_mod.format_output(data, "json")
        assert [r["a"] for r in json.loads(out)] == [3, 2, 1]

    def test_explicit_arg_overrides_module_level(self):
        output_mod.set_fields(["a"])
        # Explicitly passing fields should win over module-level state.
        out = output_mod.format_output([{"a": 1, "b": 2}], "json", fields=["b"])
        assert json.loads(out) == [{"b": 2}]


class TestGlobalProjectionFlags:
    @patch("limacharlie.commands.dr.Client")
    @patch("limacharlie.commands.dr.Organization")
    @patch("limacharlie.commands.dr.Hive")
    def test_fields_flag_projects_output(self, mock_hive_cls, _org, _client):
        rec = MagicMock()
        rec.to_dict.return_value = {"data": {"x": 1}, "usr_mtd": {}, "sys_mtd": {}}
        mock_hive = MagicMock()
        mock_hive.list.return_value = {"r1": rec}
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        # The list output is a dict keyed by record name; --fields on a dict
        # narrows the keys.  Use --fields to keep only "r1".
        result = runner.invoke(cli, ["--output", "json", "--fields", "r1", "dr", "list"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert set(parsed.keys()) == {"r1"}
        # Reset module-level state so later tests are unaffected.
        output_mod.set_fields(None)


# ---------------------------------------------------------------------------
# api-key list --name
# ---------------------------------------------------------------------------

class TestApiKeyListName:
    @patch("limacharlie.commands.api_key.Client")
    @patch("limacharlie.commands.api_key.Organization")
    def test_name_filter_keeps_keyed_shape(self, mock_org_cls, _client):
        mock_org = MagicMock()
        mock_org.get_api_keys.return_value = {
            "hashA": {"name": "ci-key", "perms": ["dr.list"]},
            "hashB": {"name": "readonly", "perms": ["org.get"]},
        }
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "api-key", "list", "--name", "ci-key"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        # Still keyed by key-hash (object), narrowed to the match.
        assert parsed == {"hashA": {"name": "ci-key", "perms": ["dr.list"]}}

    @patch("limacharlie.commands.api_key.Client")
    @patch("limacharlie.commands.api_key.Organization")
    def test_no_match_returns_empty_object(self, mock_org_cls, _client):
        mock_org = MagicMock()
        mock_org.get_api_keys.return_value = {"hashA": {"name": "ci-key"}}
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "api-key", "list", "--name", "nope"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == {}

    @patch("limacharlie.commands.api_key.Client")
    @patch("limacharlie.commands.api_key.Organization")
    def test_without_name_unchanged(self, mock_org_cls, _client):
        raw = {"hashA": {"name": "ci-key"}, "hashB": {"name": "readonly"}}
        mock_org = MagicMock()
        mock_org.get_api_keys.return_value = raw
        mock_org_cls.return_value = mock_org

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "api-key", "list"])
        assert result.exit_code == 0, result.output
        assert json.loads(result.output) == raw


# ---------------------------------------------------------------------------
# hive validate verdict
# ---------------------------------------------------------------------------

class TestHiveValidateVerdict:
    @patch("limacharlie.commands.hive.Client")
    @patch("limacharlie.commands.hive.Organization")
    @patch("limacharlie.commands.hive.Hive")
    def test_empty_response_emits_valid_true(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.validate.return_value = {}  # API said nothing -> success
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--output", "json", "hive", "validate", "--hive-name", "lookup", "--key", "k"],
            input='{"data": {"x": 1}}\n',
        )
        assert result.exit_code == 0, result.output
        # Human confirmation goes to stderr (mixed into output here); the
        # machine-stable JSON verdict is the {"valid": true} object.
        assert "is valid." in result.output
        assert json.loads(_extract_json(result.output)) == {"valid": True}

    @patch("limacharlie.commands.hive.Client")
    @patch("limacharlie.commands.hive.Organization")
    @patch("limacharlie.commands.hive.Hive")
    def test_nonempty_response_preserved(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.validate.return_value = {"detail": "ok", "extra": 1}
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--output", "json", "hive", "validate", "--hive-name", "lookup", "--key", "k"],
            input='{"data": {"x": 1}}\n',
        )
        assert result.exit_code == 0, result.output
        assert json.loads(_extract_json(result.output)) == {"detail": "ok", "extra": 1}


# ---------------------------------------------------------------------------
# hive set metadata flags
# ---------------------------------------------------------------------------

class TestHiveSetMetadataFlags:
    @staticmethod
    def _existing(name="k"):
        return HiveRecord(name=name, data=None, enabled=True,
                          tags=["keep", "draft"], expiry=10, comment="old")

    @patch("limacharlie.commands.hive.Client")
    @patch("limacharlie.commands.hive.Organization")
    @patch("limacharlie.commands.hive.Hive")
    def test_metadata_only_additive_tags(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.get_metadata.return_value = self._existing()
        mock_hive.set.return_value = {"etag": "new"}
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        result = runner.invoke(cli, [
            "hive", "set", "--hive-name", "lookup", "--key", "k",
            "--tag-add", "prod", "--tag-rm", "draft", "--comment", "new note",
        ])
        assert result.exit_code == 0, result.output
        # Metadata-only path fetches current metadata, no data load.
        mock_hive.get_metadata.assert_called_once_with("k")
        record = mock_hive.set.call_args[0][0]
        # 'keep' preserved, 'draft' removed, 'prod' added.
        assert set(record.tags) == {"keep", "prod"}
        assert record.comment == "new note"

    @patch("limacharlie.commands.hive.Client")
    @patch("limacharlie.commands.hive.Organization")
    @patch("limacharlie.commands.hive.Hive")
    def test_no_data_no_flags_errors(self, mock_hive_cls, _org, _client):
        mock_hive_cls.return_value = MagicMock()
        runner = CliRunner()
        # No stdin, no input-file, no metadata flags -> usage error exit 4.
        result = runner.invoke(cli, ["hive", "set", "--hive-name", "lookup", "--key", "k"])
        assert result.exit_code == 4

    @patch("limacharlie.commands.hive.Client")
    @patch("limacharlie.commands.hive.Organization")
    @patch("limacharlie.commands.hive.Hive")
    def test_data_with_metadata_overrides(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.set.return_value = {"etag": "new"}
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        result = runner.invoke(cli, [
            "hive", "set", "--hive-name", "lookup", "--key", "k",
            "--tag-add", "prod", "--comment", "c",
        ], input='{"data": {"x": 1}}\n')
        assert result.exit_code == 0, result.output
        # Data was supplied, so no get_metadata fetch.
        mock_hive.get_metadata.assert_not_called()
        record = mock_hive.set.call_args[0][0]
        assert record.tags == ["prod"]
        assert record.comment == "c"
        assert record.data == {"x": 1}


# ---------------------------------------------------------------------------
# secret set --value and tag subcommand
# ---------------------------------------------------------------------------

class TestSecretValueAndTag:
    @patch("limacharlie.commands._hive_shortcut.Client")
    @patch("limacharlie.commands._hive_shortcut.Organization")
    @patch("limacharlie.commands._hive_shortcut.Hive")
    def test_set_value_wraps_secret(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.set.return_value = {"etag": "new"}
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        result = runner.invoke(cli, [
            "secret", "set", "--key", "my-secret", "--value", "s3cr3t",
            "--tag", "prod", "--comment", "note",
        ])
        assert result.exit_code == 0, result.output
        record = mock_hive.set.call_args[0][0]
        assert record.data == {"secret": "s3cr3t"}
        assert record.tags == ["prod"]
        assert record.comment == "note"

    def test_value_not_offered_for_structured_hive(self):
        # A hive without a single scalar value field (no value_key) must NOT
        # expose --value — the secret-style {data: {secret: ...}} wrapper would
        # be wrong for its data shape. Click rejects the unknown option.
        runner = CliRunner()
        result = runner.invoke(cli, ["lookup", "set", "--key", "k", "--value", "x"])
        assert result.exit_code != 0
        assert "no such option" in result.output.lower() or "No such option" in result.output

    @patch("limacharlie.commands._hive_shortcut.Client")
    @patch("limacharlie.commands._hive_shortcut.Organization")
    @patch("limacharlie.commands._hive_shortcut.Hive")
    def test_tag_works_for_structured_hive(self, mock_hive_cls, _org, _client, tmp_path):
        # --tag/--comment are generic metadata and remain available on every
        # hive shortcut, even those without --value.
        mock_hive = MagicMock()
        mock_hive.set.return_value = {"etag": "new"}
        mock_hive_cls.return_value = mock_hive
        f = tmp_path / "l.yaml"
        f.write_text("data:\n  a: 1\n")
        runner = CliRunner()
        result = runner.invoke(cli, [
            "lookup", "set", "--key", "k", "--input-file", str(f), "--tag", "prod",
        ])
        assert result.exit_code == 0, result.output
        record = mock_hive.set.call_args[0][0]
        assert record.tags == ["prod"]

    @patch("limacharlie.commands._hive_shortcut.Client")
    @patch("limacharlie.commands._hive_shortcut.Organization")
    @patch("limacharlie.commands._hive_shortcut.Hive")
    def test_tag_add_merges(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.get_metadata.return_value = HiveRecord(name="my-secret", tags=["a"])
        mock_hive.set.return_value = {"etag": "new"}
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        result = runner.invoke(cli, ["secret", "tag", "add", "--key", "my-secret", "-t", "b"])
        assert result.exit_code == 0, result.output
        record = mock_hive.set.call_args[0][0]
        assert set(record.tags) == {"a", "b"}

    @patch("limacharlie.commands._hive_shortcut.Client")
    @patch("limacharlie.commands._hive_shortcut.Organization")
    @patch("limacharlie.commands._hive_shortcut.Hive")
    def test_tag_rm_keeps_others(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.get_metadata.return_value = HiveRecord(name="my-secret", tags=["a", "b"])
        mock_hive.set.return_value = {"etag": "new"}
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        result = runner.invoke(cli, ["secret", "tag", "rm", "--key", "my-secret", "-t", "a"])
        assert result.exit_code == 0, result.output
        record = mock_hive.set.call_args[0][0]
        assert record.tags == ["b"]


# ---------------------------------------------------------------------------
# dr set --detect/--respond/--tag
# ---------------------------------------------------------------------------

class TestDrSetComponents:
    @patch("limacharlie.commands.dr.Client")
    @patch("limacharlie.commands.dr.Organization")
    @patch("limacharlie.commands.dr.Hive")
    def test_detect_respond_assembles_rule(self, mock_hive_cls, _org, _client, tmp_path):
        detect = tmp_path / "d.yaml"
        respond = tmp_path / "r.yaml"
        detect.write_text("op: is\npath: event/X\nvalue: y\n")
        respond.write_text("- action: report\n  name: n\n")

        mock_hive = MagicMock()
        mock_hive.set.return_value = {"etag": "new"}
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        result = runner.invoke(cli, [
            "dr", "set", "--key", "r", "--detect", str(detect),
            "--respond", str(respond), "--tag", "prod", "--enabled",
        ])
        assert result.exit_code == 0, result.output
        record = mock_hive.set.call_args[0][0]
        assert record.data == {
            "detect": {"op": "is", "path": "event/X", "value": "y"},
            "respond": [{"action": "report", "name": "n"}],
        }
        assert record.tags == ["prod"]
        assert record.enabled is True

    @patch("limacharlie.commands.dr.Client")
    @patch("limacharlie.commands.dr.Organization")
    @patch("limacharlie.commands.dr.Hive")
    def test_detect_with_input_file_errors(self, mock_hive_cls, _org, _client, tmp_path):
        detect = tmp_path / "d.yaml"
        respond = tmp_path / "r.yaml"
        infile = tmp_path / "in.yaml"
        for p in (detect, respond, infile):
            p.write_text("op: is\n")
        mock_hive_cls.return_value = MagicMock()

        runner = CliRunner()
        result = runner.invoke(cli, [
            "dr", "set", "--key", "r", "--detect", str(detect),
            "--respond", str(respond), "--input-file", str(infile),
        ])
        assert result.exit_code != 0
        assert "mutually exclusive" in result.output


# ---------------------------------------------------------------------------
# adapter list-types
# ---------------------------------------------------------------------------

class TestAdapterListTypes:
    def test_fallback_includes_threatlocker(self):
        from limacharlie.commands._adapter_types import adapter_types
        # Passing an org whose schema fetch raises forces the fallback path.
        rows = adapter_types(None)
        types = {r["type"] for r in rows}
        assert "threatlocker" in types
        assert "webhook" in types

    def test_derived_from_schema(self):
        from limacharlie.commands._adapter_types import _types_from_schema
        schema = {"schema": {
            "$defs": {"S3Config": {}, "SyslogConfig": {}},
            "properties": {"s3": {}, "syslog": {}, "sensor_type": {}, "client_options": {}},
        }}
        names = _types_from_schema(schema)
        # Non-type shared fields are excluded.
        assert "sensor_type" not in names
        assert "client_options" not in names
        assert "s3" in names and "syslog" in names

    @patch("limacharlie.commands._adapter_types.Hive")
    @patch("limacharlie.commands._adapter_types.Client", create=True)
    def test_cli_list_types(self, _client, mock_hive_cls):
        # When the schema fetch fails, the command still returns the curated list.
        mock_hive = MagicMock()
        mock_hive.get_schema.side_effect = Exception("no schema")
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        with patch("limacharlie.client.Client"):
            result = runner.invoke(cli, ["--output", "json", "cloud-adapter", "list-types"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        assert any(r["type"] == "threatlocker" for r in parsed)


# ---------------------------------------------------------------------------
# hive schema flat rendering
# ---------------------------------------------------------------------------

class TestHiveSchemaFlat:
    _SCHEMA = {"schema": {
        "$ref": "#/$defs/Rec",
        "$defs": {
            "Rec": {
                "type": "object",
                "required": ["prompt"],
                "properties": {
                    "prompt": {"type": "string"},
                    "model": {"type": "string", "enum": ["a", "b"]},
                    "nested": {"$ref": "#/$defs/Sub"},
                },
            },
            "Sub": {"type": "object", "properties": {"x": {"type": "integer"}}},
        },
    }}

    @patch("limacharlie.commands.hive.Client")
    @patch("limacharlie.commands.hive.Organization")
    @patch("limacharlie.commands.hive.Hive")
    def test_default_table_is_flat(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.get_schema.return_value = self._SCHEMA
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        # Force table (the default human view) explicitly.
        result = runner.invoke(cli, ["--output", "table", "hive", "schema", "--hive-name", "ai_agent"])
        assert result.exit_code == 0, result.output
        assert "prompt" in result.output
        assert "nested.x" in result.output  # $ref resolved + flattened

    @patch("limacharlie.commands.hive.Client")
    @patch("limacharlie.commands.hive.Organization")
    @patch("limacharlie.commands.hive.Hive")
    def test_json_keeps_raw(self, mock_hive_cls, _org, _client):
        mock_hive = MagicMock()
        mock_hive.get_schema.return_value = self._SCHEMA
        mock_hive_cls.return_value = mock_hive

        runner = CliRunner()
        result = runner.invoke(cli, ["--output", "json", "hive", "schema", "--hive-name", "ai_agent"])
        assert result.exit_code == 0, result.output
        parsed = json.loads(result.output)
        # Raw JSON Schema preserved, nothing lost.
        assert parsed == self._SCHEMA
