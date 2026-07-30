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


def test_v2_sensor_list_online_only(oid, key):
    # is_online_only must (a) never WIDEN the result and (b) actually FILTER:
    # every sensor it returns must currently be online. (a) is a race-free
    # invariant. (b) is the meaningful check - a subset assertion alone would
    # also pass if the server silently ignored the parameter and returned the
    # full list, so we confirm the returned sensors are genuinely online.
    #
    # The exact query-parameter wiring is pinned deterministically by the unit
    # tests. Online state is inherently volatile, so (b) reads the online set
    # (a single bulk get_online_sensors call, scoped to just the returned SIDs)
    # immediately after the listing to keep the race window minimal.
    org = _make_org(oid, key)
    all_sensors = list(org.list_sensors())
    online_only = list(org.list_sensors(is_online_only=True))

    # (a) never widens, and every returned sensor is a real org sensor.
    assert len(online_only) <= len(all_sensors)
    all_sids = {s.get("sid") for s in all_sensors}
    online_only_sids = [s.get("sid") for s in online_only if s.get("sid")]
    for sid in online_only_sids:
        assert sid in all_sids

    # (b) every sensor is_online_only returned is actually online right now.
    if online_only_sids:
        actually_online = set(org.get_online_sensors(sids=online_only_sids))
        for sid in online_only_sids:
            assert sid in actually_online, (
                f"is_online_only returned {sid}, but it is not currently online"
            )


def test_v2_sensor_tags(oid, key):
    org = _make_org(oid, key)
    tags = org.get_all_tags()
    assert isinstance(tags, list)
