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

    def test_derived_from_ref_rooted_schema(self):
        # Mirrors the real reflected shape: a {"schema": {...}} wrapper whose
        # root $refs into $defs/<Record>; type names are that record's
        # properties (minus the discriminator), NOT the bare $defs keys.
        from limacharlie.commands._adapter_types import _types_from_schema
        schema = {"schema": {
            "$ref": "#/$defs/CloudSensorRecord",
            "$defs": {
                "CloudSensorRecord": {
                    "properties": {
                        "s3": {}, "office365": {}, "threatlocker": {}, "sensor_type": {},
                    },
                },
                "ClientOptions": {}, "AckBufferOptions": {},  # helper structs
            },
        }}
        names = _types_from_schema(schema)
        assert set(names) == {"s3", "office365", "threatlocker"}
        # The discriminator and helper-struct $defs names must NOT leak in.
        assert "sensor_type" not in names
        assert "ClientOptions" not in names and "AckBufferOptions" not in names

    def test_derived_from_inline_properties_schema(self):
        # Fallback shape: no $ref, properties inline on the root.
        from limacharlie.commands._adapter_types import _types_from_schema
        schema = {"schema": {
            "properties": {"s3": {}, "syslog": {}, "sensor_type": {}, "client_options": {}},
        }}
        names = _types_from_schema(schema)
        assert "sensor_type" not in names and "client_options" not in names
        assert "s3" in names and "syslog" in names

    def test_per_hive_schema_selection(self):
        # cloud-adapter and external-adapter must enumerate their OWN hive.
        from limacharlie.commands import _adapter_types as at
        captured = {}

        class _FakeHive:
            def __init__(self, org, hive_name):
                captured["hive_name"] = hive_name
            def get_schema(self):
                return {"schema": {"$ref": "#/$defs/R", "$defs": {"R": {"properties": {"s3": {}}}}}}

        with patch.object(at, "Hive", _FakeHive):
            at.adapter_types(None, "external_adapter")
        assert captured["hive_name"] == "external_adapter"

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


# ---------------------------------------------------------------------------
# adapter schema --type  (per-type config schema)
# ---------------------------------------------------------------------------

class TestAdapterTypeSchema:
    _SCHEMA = {"schema": {
        "$ref": "#/$defs/CloudSensorRecord",
        "$defs": {
            "CloudSensorRecord": {"properties": {
                "sensor_type": {"type": "string"},
                "threatlocker": {"$ref": "#/$defs/ThreatLockerConfig"},
            }},
            "ThreatLockerConfig": {"properties": {
                "api_key": {"type": "string"}, "instance_letter": {"type": "string"},
            }, "required": ["api_key"]},
        },
    }}

    @patch("limacharlie.commands._adapter_types.Hive")
    def test_resolves_known_type(self, mock_hive_cls):
        from limacharlie.commands._adapter_types import adapter_type_schema
        mock_hive = MagicMock(); mock_hive.get_schema.return_value = self._SCHEMA
        mock_hive_cls.return_value = mock_hive
        root, node = adapter_type_schema(None, "cloud_sensor", "threatlocker")
        assert node is not None
        assert node.get("$ref", "").endswith("ThreatLockerConfig")
        # root retains $defs so the caller can resolve/flatten.
        assert "ThreatLockerConfig" in root["$defs"]

    @patch("limacharlie.commands._adapter_types.Hive")
    def test_unknown_type_returns_none(self, mock_hive_cls):
        from limacharlie.commands._adapter_types import adapter_type_schema
        mock_hive = MagicMock(); mock_hive.get_schema.return_value = self._SCHEMA
        mock_hive_cls.return_value = mock_hive
        _root, node = adapter_type_schema(None, "cloud_sensor", "bogus")
        assert node is None

    @patch("limacharlie.commands._adapter_types.Hive")
    def test_cli_table_render(self, mock_hive_cls):
        mock_hive = MagicMock(); mock_hive.get_schema.return_value = self._SCHEMA
        mock_hive_cls.return_value = mock_hive
        runner = CliRunner()
        with patch("limacharlie.client.Client"):
            result = runner.invoke(cli, [
                "--output", "table", "cloud-adapter", "schema", "--type", "threatlocker"])
        assert result.exit_code == 0, result.output
        # Flattened field listing resolves the type config's properties.
        assert "api_key" in result.output and "instance_letter" in result.output

    @patch("limacharlie.commands._adapter_types.Hive")
    def test_cli_unknown_type_errors_with_valid_list(self, mock_hive_cls):
        mock_hive = MagicMock(); mock_hive.get_schema.return_value = self._SCHEMA
        mock_hive_cls.return_value = mock_hive
        runner = CliRunner()
        with patch("limacharlie.client.Client"):
            result = runner.invoke(cli, ["cloud-adapter", "schema", "--type", "bogus"])
        assert result.exit_code != 0
        assert "Unknown adapter type 'bogus'" in result.output
        assert "threatlocker" in result.output  # lists the valid types


# ---------------------------------------------------------------------------
# adapter sensors --key  (find an adapter's sensor(s) by iid)
# ---------------------------------------------------------------------------

class TestAdapterSensors:
    _IID = "11111111-1111-1111-1111-111111111111"

    @patch("limacharlie.commands._adapter_types.Hive")
    def test_matches_by_iid_via_selector(self, mock_hive_cls):
        from limacharlie.commands._adapter_types import adapter_sensors
        rec = MagicMock()
        rec.data = {"sensor_type": "s3", "s3": {"client_options": {
            "identity": {"installation_key": self._IID}, "hostname": "ignored"}}}
        mock_hive_cls.return_value.get.return_value = rec
        org = MagicMock()
        # The server applies the selector; the mock returns the filtered set.
        org.list_sensors.return_value = [
            {"iid": self._IID, "sid": "S1", "hostname": "h1", "is_online": True, "alive": "t"},
        ]
        out = adapter_sensors(org, "cloud_sensor", "my-adapter")
        org.list_sensors.assert_called_once_with(selector=f'iid == "{self._IID}"')
        assert out["match_by"] == "iid" and out["match_value"] == self._IID
        assert out["selector"] == f'iid == "{self._IID}"'
        assert [s["sid"] for s in out["sensors"]] == ["S1"]

    @patch("limacharlie.commands._adapter_types.Hive")
    def test_empty_when_not_registered(self, mock_hive_cls):
        from limacharlie.commands._adapter_types import adapter_sensors
        rec = MagicMock()
        rec.data = {"sensor_type": "s3", "s3": {"client_options": {
            "identity": {"installation_key": self._IID}}}}
        mock_hive_cls.return_value.get.return_value = rec
        org = MagicMock(); org.list_sensors.return_value = []
        out = adapter_sensors(org, "cloud_sensor", "a")
        assert out["sensors"] == [] and "note" in out

    @patch("limacharlie.commands._adapter_types.Hive")
    def test_hostname_fallback_when_key_not_uuid(self, mock_hive_cls):
        from limacharlie.commands._adapter_types import adapter_sensors
        rec = MagicMock()
        rec.data = {"sensor_type": "webhook", "webhook": {"client_options": {
            "identity": {"installation_key": "AAAAbase64notuuid=="}, "hostname": "wh-1"}}}
        mock_hive_cls.return_value.get.return_value = rec
        org = MagicMock()
        org.list_sensors.return_value = [
            {"iid": "x", "sid": "S1", "hostname": "wh-1", "is_online": True, "alive": "t"},
        ]
        out = adapter_sensors(org, "cloud_sensor", "wh")
        org.list_sensors.assert_called_once_with(selector='hostname == "wh-1"')
        assert out["match_by"] == "hostname" and [s["sid"] for s in out["sensors"]] == ["S1"]

    @patch("limacharlie.commands._adapter_types.Hive")
    def test_no_resolvable_identity_does_not_query(self, mock_hive_cls):
        from limacharlie.commands._adapter_types import adapter_sensors
        rec = MagicMock()
        rec.data = {"sensor_type": "s3", "s3": {"client_options": {}}}
        mock_hive_cls.return_value.get.return_value = rec
        org = MagicMock()
        out = adapter_sensors(org, "cloud_sensor", "a")
        assert out["match_by"] is None and out["sensors"] == []
        org.list_sensors.assert_not_called()


# ---------------------------------------------------------------------------
# api-key create --store-secret  (atomic mint -> secret)
# ---------------------------------------------------------------------------

class TestApiKeyStoreSecret:
    @patch("limacharlie.sdk.hive.Hive")
    @patch("limacharlie.commands.api_key.Client")
    @patch("limacharlie.commands.api_key.Organization")
    def test_store_secret_writes_value_new(self, mock_org_cls, _client, mock_hive_cls):
        mock_org = MagicMock()
        mock_org.add_api_key.return_value = {"api_key": "minted-value", "key_name": "k", "success": True}
        mock_org_cls.return_value = mock_org
        mock_hive = MagicMock(); mock_hive_cls.return_value = mock_hive
        # No existing secret of this name -> get_metadata raises -> create (no etag).
        mock_hive.get_metadata.side_effect = Exception("not found")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "api-key", "create", "--name", "k", "--permissions", "org.get",
            "--store-secret", "k-secret", "--store-secret-tag", "clitest",
        ])
        assert result.exit_code == 0, result.output
        # The secret hive received the minted value verbatim.
        mock_hive_cls.assert_called_once()
        assert mock_hive_cls.call_args[0][1] == "secret"
        record = mock_hive.set.call_args[0][0]
        assert record.data == {"secret": "minted-value"}
        assert record.tags == ["clitest"]
        assert record.enabled is True
        assert record.etag is None  # creating a new secret, no conditional etag
        assert "new secret" in result.output

    @patch("limacharlie.sdk.hive.Hive")
    @patch("limacharlie.commands.api_key.Client")
    @patch("limacharlie.commands.api_key.Organization")
    def test_store_secret_updates_existing_with_etag(self, mock_org_cls, _client, mock_hive_cls):
        from limacharlie.sdk.hive import HiveRecord
        mock_org = MagicMock()
        mock_org.add_api_key.return_value = {"api_key": "minted-value", "key_name": "k"}
        mock_org_cls.return_value = mock_org
        mock_hive = MagicMock(); mock_hive_cls.return_value = mock_hive
        # An existing secret -> carry its etag so the write is a conditional update.
        mock_hive.get_metadata.return_value = HiveRecord(name="k-secret", etag="ETAG-1")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "api-key", "create", "--name", "k", "--permissions", "org.get",
            "--store-secret", "k-secret",
        ])
        assert result.exit_code == 0, result.output
        record = mock_hive.set.call_args[0][0]
        assert record.data == {"secret": "minted-value"}
        assert record.etag == "ETAG-1"
        assert "Updated existing" in result.output

    @patch("limacharlie.sdk.hive.Hive")
    @patch("limacharlie.commands.api_key.Client")
    @patch("limacharlie.commands.api_key.Organization")
    def test_no_store_secret_does_not_touch_hive(self, mock_org_cls, _client, mock_hive_cls):
        mock_org = MagicMock()
        mock_org.add_api_key.return_value = {"api_key": "v", "key_name": "k"}
        mock_org_cls.return_value = mock_org
        runner = CliRunner()
        result = runner.invoke(cli, ["api-key", "create", "--name", "k", "--permissions", "org.get"])
        assert result.exit_code == 0, result.output
        mock_hive_cls.assert_not_called()
