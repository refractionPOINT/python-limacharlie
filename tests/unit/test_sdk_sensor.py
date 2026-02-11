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
        mock_org.client.request.return_value = {"hostname": "box1", "plat": 0x10000002}
        result = sensor.get_info()
        mock_org.client.request.assert_called_once_with("GET", "aaaa-bbbb-cccc-dddd")
        assert result["hostname"] == "box1"

    def test_is_online(self, sensor, mock_org):
        mock_org.client.request.return_value = {"is_online": True}
        assert sensor.is_online() is True

    def test_is_online_fallback_alive(self, sensor, mock_org):
        mock_org.client.request.return_value = {"alive": True}
        assert sensor.is_online() is True


class TestSensorTags:
    def test_get_tags(self, sensor, mock_org):
        mock_org.client.request.return_value = {"tags": ["web", "prod"]}
        result = sensor.get_tags()
        mock_org.client.request.assert_called_once_with("GET", "aaaa-bbbb-cccc-dddd/tags")
        assert result == ["web", "prod"]

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
