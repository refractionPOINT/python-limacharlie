import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization


def _make_org(oid, key):
    client = Client(oid=oid, api_key=key)
    return Organization(client)


def test_v2_sensor_list(oid, key):
    org = _make_org(oid, key)
    # list_sensors is a generator; consume it into a list.
    sensors = list(org.list_sensors())
    assert isinstance(sensors, list)


def test_v2_sensor_tags(oid, key):
    org = _make_org(oid, key)
    tags = org.get_all_tags()
    assert isinstance(tags, list)
