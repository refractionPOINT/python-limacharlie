"""CS-14 additive response contract through the actual SDK transport wrapper."""
from unittest.mock import MagicMock

from limacharlie.sdk.cloudsec import CloudSec


def test_runtime_resolution_preserves_evidence_and_unknown_across_chunks():
    org = MagicMock()
    org.oid = "b85fd2bd-ae21-4c1f-8a42-b90b51aeddeb"
    row = {
        "sid": "sensor", "urn": "asset", "level": "derived",
        "source": "sensor_cloud_resolver",
        "observed_at": "2026-09-22T00:00:00Z",
        "stale_at": "2026-09-22T00:15:00Z",
        "node": {"cluster_urn": "cluster", "node_uid": "node"},
    }
    org.client.request.side_effect = [
        {"resolved": [row], "unresolved": ["unknown"], "resolver_ready": True},
        {"resolved": [], "unresolved": ["cache-failed"], "resolver_ready": False},
    ]
    result = CloudSec(org).resolve_sensors([f"sensor-{i}" for i in range(101)])
    assert org.client.request.call_count == 2
    assert result == {
        "resolved": [row], "unresolved": ["unknown", "cache-failed"],
        "resolver_ready": False,
    }
    assert not {"exposed", "reaches_crownjewel", "lc_risk"}.intersection(row)
    for call in org.client.request.call_args_list:
        assert call.args[1] == f"cloudsec/{org.oid}/resolve/sensors"
