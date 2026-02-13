"""Tests for limacharlie.sdk.sensor module."""

from unittest.mock import MagicMock
import pytest

from limacharlie.sdk.sensor import Sensor


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    return org


@pytest.fixture
def sensor(mock_org):
    return Sensor(mock_org, "aaaa-bbbb-cccc-dddd")


class TestSensorInit:
    def test_stores_sid(self, mock_org):
        s = Sensor(mock_org, "my-sid")
        assert s.sid == "my-sid"

    def test_sid_converted_to_str(self, mock_org):
        s = Sensor(mock_org, 12345)
        assert s.sid == "12345"

    def test_cached_info(self, mock_org):
        s = Sensor(mock_org, "sid", info={"hostname": "test"})
        assert s._info == {"hostname": "test"}


class TestSensorPlatformConstants:
    def test_platform_constants(self):
        assert Sensor.PLATFORM_WINDOWS == 0x10000000
        assert Sensor.PLATFORM_LINUX == 0x20000000
        assert Sensor.PLATFORM_MACOS == 0x30000000

    def test_arch_constants(self):
        assert Sensor.ARCH_X86 == 0x00000001
        assert Sensor.ARCH_X64 == 0x00000002
        assert Sensor.ARCH_ARM64 == 0x00000004


class TestSensorInfo:
    def test_get_info_fetches_on_first_call(self, sensor, mock_org):
        mock_org.client.request.return_value = {"info": {"hostname": "box1", "plat": 0x10000002}}
        result = sensor.get_info()
        mock_org.client.request.assert_called_once_with("GET", "aaaa-bbbb-cccc-dddd")
        assert result["hostname"] == "box1"

    def test_get_info_caches(self, sensor, mock_org):
        mock_org.client.request.return_value = {"info": {"hostname": "box1"}}
        sensor.get_info()
        sensor.get_info()
        # Should only call API once due to caching
        assert mock_org.client.request.call_count == 1

    def test_is_online(self, sensor, mock_org):
        mock_org.client.request.return_value = {"online": {"component_id": "abc123"}}
        assert sensor.is_online() is True

    def test_is_online_empty(self, sensor, mock_org):
        mock_org.client.request.return_value = {"online": {}}
        assert sensor.is_online() is False

    def test_is_online_error(self, sensor, mock_org):
        mock_org.client.request.return_value = {"online": {"error": "not found"}}
        assert sensor.is_online() is False


class TestSensorTags:
    def test_get_tags(self, sensor, mock_org):
        # V1 returns {"tags": {"<sid>": {"tag1": null, "tag2": null}}}
        mock_org.client.request.return_value = {
            "tags": {"aaaa-bbbb-cccc-dddd": {"web": None, "prod": None}}
        }
        result = sensor.get_tags()
        mock_org.client.request.assert_called_once_with("GET", "aaaa-bbbb-cccc-dddd/tags")
        assert sorted(result) == ["prod", "web"]

    def test_get_tags_list_format(self, sensor, mock_org):
        # Also handles a plain list format
        mock_org.client.request.return_value = {"tags": ["web", "prod"]}
        result = sensor.get_tags()
        assert sorted(result) == ["prod", "web"]

    def test_add_tag(self, sensor, mock_org):
        sensor.add_tag("new-tag")
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"
        assert "new-tag" in str(call_args)

    def test_remove_tag(self, sensor, mock_org):
        sensor.remove_tag("old-tag")
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "DELETE"


class TestSensorIsolation:
    def test_isolate(self, sensor, mock_org):
        sensor.isolate()
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"

    def test_rejoin(self, sensor, mock_org):
        sensor.rejoin()
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "DELETE"


class TestSensorTask:
    def test_task(self, sensor, mock_org):
        sensor.task("os_processes")
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"

    def test_delete(self, sensor, mock_org):
        sensor.delete()
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "DELETE"


class TestSensorEventRetention:
    def test_get_event_retention_uses_correct_params(self, sensor, mock_org):
        mock_org.client.request.return_value = {"retention": {}}
        sensor.get_event_retention(1000, 2000)
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "GET"
        assert "insight/event_count/" in call_args[0][1]
        qp = call_args[1]["query_params"]
        # v1 uses 'start'/'end', not 'startTime'/'endTime'
        assert qp["start"] == "1000"
        assert qp["end"] == "2000"
        assert "startTime" not in qp
        assert "endTime" not in qp

    def test_get_event_retention_detailed(self, sensor, mock_org):
        mock_org.client.request.return_value = {"retention": {}}
        sensor.get_event_retention(1000, 2000, is_detailed=True)
        call_args = mock_org.client.request.call_args
        qp = call_args[1]["query_params"]
        assert qp["is_detailed"] == "true"


class TestSensorTaskContract:
    def test_task_string_wraps_in_list(self, sensor, mock_org):
        mock_org.client.request.return_value = {}
        sensor.task("os_processes")
        mock_org.client.request.assert_called_once_with(
            "POST", "aaaa-bbbb-cccc-dddd",
            params={"tasks": ["os_processes"]},
        )

    def test_task_list_passed_directly(self, sensor, mock_org):
        mock_org.client.request.return_value = {}
        sensor.task(["os_processes", "os_services"])
        mock_org.client.request.assert_called_once_with(
            "POST", "aaaa-bbbb-cccc-dddd",
            params={"tasks": ["os_processes", "os_services"]},
        )

    def test_task_with_investigation_id(self, sensor, mock_org):
        mock_org.client.request.return_value = {}
        sensor.task("os_processes", inv_id="inv-123")
        mock_org.client.request.assert_called_once_with(
            "POST", "aaaa-bbbb-cccc-dddd",
            params={"tasks": ["os_processes"], "investigation_id": "inv-123"},
        )


class TestSensorAddTagContract:
    def test_add_tag_params(self, sensor, mock_org):
        mock_org.client.request.return_value = {}
        sensor.add_tag("new-tag")
        mock_org.client.request.assert_called_once_with(
            "POST", "aaaa-bbbb-cccc-dddd/tags",
            params={"tags": "new-tag"},
        )

    def test_add_tag_with_ttl(self, sensor, mock_org):
        mock_org.client.request.return_value = {}
        sensor.add_tag("temp-tag", ttl=3600)
        mock_org.client.request.assert_called_once_with(
            "POST", "aaaa-bbbb-cccc-dddd/tags",
            params={"tags": "temp-tag", "ttl": 3600},
        )


class TestSensorRemoveTagContract:
    def test_remove_single_tag(self, sensor, mock_org):
        mock_org.client.request.return_value = {}
        sensor.remove_tag("old-tag")
        mock_org.client.request.assert_called_once_with(
            "DELETE", "aaaa-bbbb-cccc-dddd/tags",
            params={"tag": "old-tag"},
        )

    def test_remove_tag_list(self, sensor, mock_org):
        mock_org.client.request.return_value = {}
        sensor.remove_tag(["t1", "t2"])
        mock_org.client.request.assert_called_once_with(
            "DELETE", "aaaa-bbbb-cccc-dddd/tags",
            params={"tags": "t1,t2"},
        )


class TestSensorIsolationContract:
    def test_isolate_path(self, sensor, mock_org):
        mock_org.client.request.return_value = {}
        sensor.isolate()
        mock_org.client.request.assert_called_once_with("POST", "aaaa-bbbb-cccc-dddd/isolation")

    def test_rejoin_path(self, sensor, mock_org):
        mock_org.client.request.return_value = {}
        sensor.rejoin()
        mock_org.client.request.assert_called_once_with("DELETE", "aaaa-bbbb-cccc-dddd/isolation")


class TestSensorSealContract:
    def test_seal(self, sensor, mock_org):
        mock_org.client.request.return_value = {}
        sensor.seal()
        mock_org.client.request.assert_called_once_with("POST", "aaaa-bbbb-cccc-dddd/seal")

    def test_unseal(self, sensor, mock_org):
        mock_org.client.request.return_value = {}
        sensor.unseal()
        mock_org.client.request.assert_called_once_with("DELETE", "aaaa-bbbb-cccc-dddd/seal")


class TestSensorDeleteContract:
    def test_delete_uses_sid_path(self, sensor, mock_org):
        mock_org.client.request.return_value = {}
        sensor.delete()
        mock_org.client.request.assert_called_once_with("DELETE", "aaaa-bbbb-cccc-dddd")


class TestSensorGetOverviewContract:
    def test_get_overview_params(self, sensor, mock_org):
        mock_org.client.request.return_value = {"overview": [1000, 1500, 2000]}
        result = sensor.get_overview(1000, 2000)
        mock_org.client.request.assert_called_once_with(
            "GET", "insight/test-oid/aaaa-bbbb-cccc-dddd/overview",
            query_params={"start": "1000", "end": "2000"},
        )
        assert result == [1000, 1500, 2000]


class TestSensorGetEventByAtomContract:
    def test_get_event_by_atom_path(self, sensor, mock_org):
        mock_org.client.request.return_value = {"event": {"type": "NEW_PROCESS"}}
        result = sensor.get_event_by_atom("atom-xyz")
        mock_org.client.request.assert_called_once_with(
            "GET", "insight/test-oid/aaaa-bbbb-cccc-dddd/atom-xyz",
        )
        assert result == {"event": {"type": "NEW_PROCESS"}}


class TestSensorGetChildrenEventsContract:
    def test_get_children_events_params(self, sensor, mock_org):
        mock_org.client.request.return_value = {"events": "compressed-data"}
        mock_org.client.unwrap.return_value = [{"type": "FILE_CREATE"}]
        result = sensor.get_children_events("atom-xyz")
        mock_org.client.request.assert_called_once_with(
            "GET", "insight/test-oid/aaaa-bbbb-cccc-dddd/atom-xyz/children",
            query_params={"is_compressed": "true"},
        )
        mock_org.client.unwrap.assert_called_once_with("compressed-data")
        assert result == [{"type": "FILE_CREATE"}]
