"""A code-scan push that is told to come back later (429) comes back later.

These drive the REAL client (only ``urlopen`` and the sleep are replaced), so
the ``Retry-After`` header travels the same way it does against the API: out
of the HTTP error, through ``Client.request`` into ``RateLimitError``, and into
the push's backoff.
"""

import io
import json
import os
from http.client import HTTPMessage
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

import pytest

from limacharlie.client import Client, parse_retry_after
from limacharlie.errors import ApiError, RateLimitError
from limacharlie.sdk import cloudsec as cloudsec_mod
from limacharlie.sdk.cloudsec import CloudSec, _ingest_busy_delay


OID = "11111111-2222-3333-4444-555555555555"
BUSY_BODY = json.dumps({
    "error": "code_ingest: ingest_busy: this organization already has 2 pushes running "
             "and more waiting on this replica; retry this push after its earlier pushes finish",
    "error_code": "ingest_busy",
    "retry": True,
}).encode()


@pytest.fixture(autouse=True)
def _isolate_caches(monkeypatch, tmp_path):
    from limacharlie.config import _reset_config_cache
    from limacharlie.jwt_cache import _reset_cache_disabled
    from limacharlie.paths import _reset_path_cache

    config_dir = str(tmp_path / "lc_config")
    os.makedirs(config_dir, exist_ok=True)
    monkeypatch.setenv("LC_CONFIG_DIR", config_dir)
    for var in ("LC_CREDS_FILE", "LC_LEGACY_CONFIG", "LC_EPHEMERAL_CREDS", "LC_NO_JWT_CACHE"):
        monkeypatch.delenv(var, raising=False)
    _reset_path_cache()
    _reset_config_cache()
    _reset_cache_disabled()
    yield
    _reset_path_cache()
    _reset_config_cache()
    _reset_cache_disabled()


def _http_429(retry_after=None, body=BUSY_BODY):
    headers = HTTPMessage()
    headers["Content-Type"] = "application/json"
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return HTTPError("https://api.limacharlie.io/v1/x", 429, "Too Many Requests", headers, io.BytesIO(body))


def _http_400():
    return HTTPError("https://api.limacharlie.io/v1/x", 400, "Bad Request", HTTPMessage(),
                     io.BytesIO(b'{"error": "code_ingest: repo_not_in_policy_scope: no"}'))


def _ok(payload):
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode()
    resp.getheaders.return_value = []
    return resp


def _cloudsec(is_retry_quota_errors=False):
    client = Client(oid=OID, jwt="jwt", is_retry_quota_errors=is_retry_quota_errors)
    org = MagicMock()
    org.oid = OID
    org.client = client
    return CloudSec(org)


def _bodies(mock_urlopen):
    return [call.args[0].data for call in mock_urlopen.call_args_list]


class TestRetryAfterReachesTheError:
    @patch("limacharlie.client.urlopen")
    def test_429_carries_its_retry_after(self, mock_urlopen):
        mock_urlopen.side_effect = [_http_429("30")]
        client = Client(oid=OID, jwt="jwt")
        with pytest.raises(RateLimitError) as e:
            client.request("POST", "x")
        assert e.value.retry_after == 30

    @patch("limacharlie.client.urlopen")
    def test_429_without_retry_after_is_none_not_zero(self, mock_urlopen):
        mock_urlopen.side_effect = [_http_429(None)]
        client = Client(oid=OID, jwt="jwt")
        with pytest.raises(RateLimitError) as e:
            client.request("POST", "x")
        assert e.value.retry_after is None

    @patch("limacharlie.client.time")
    @patch("limacharlie.client.urlopen")
    def test_per_call_override_beats_the_client_retry_flag(self, mock_urlopen, mock_time):
        """A caller running its own backoff gets the 429 at once even on a --retry client."""
        mock_urlopen.side_effect = [_http_429("30"), _ok({"ok": True})]
        client = Client(oid=OID, jwt="jwt", is_retry_quota_errors=True)
        with pytest.raises(RateLimitError):
            client.request("POST", "x", retry_quota_errors=False)
        assert mock_urlopen.call_count == 1
        mock_time.sleep.assert_not_called()

    def test_parse_retry_after_forms(self):
        assert parse_retry_after("30") == 30
        assert parse_retry_after(" 7 ") == 7
        # An HTTP-date 90 seconds after "now".
        assert parse_retry_after("Wed, 21 Oct 2015 07:29:30 GMT", now=1445412480.0) == 90
        assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT", now=1445412580.0) == 0
        for garbage in (None, "", "-5", "soon", "1.5e3", "\u00b2", "\u0663\u0660"):
            assert parse_retry_after(garbage) is None
        # Past Python's integer-string limit: clamped, not a ValueError out of request().
        assert parse_retry_after("9" * 5000) == 999_999_999


class TestIngestRetriesBusy:
    @patch.object(cloudsec_mod.time, "sleep")
    @patch("limacharlie.client.urlopen")
    def test_busy_then_accepted(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = [_http_429("30"), _http_429("30"), _ok({"result": {"findings": 3}})]
        out = _cloudsec().ingest_code_results("acme/api", "report", b"\x1f\x8bdoc", commit="c0ffee")
        assert out == {"result": {"findings": 3}}
        assert mock_urlopen.call_count == 3
        # The same push each time.
        bodies = _bodies(mock_urlopen)
        assert bodies[0] == bodies[1] == bodies[2]
        assert json.loads(bodies[0])["repo"] == "acme/api"
        # Each wait honours Retry-After as a floor, with at most 50% jitter on top.
        waits = [c.args[0] for c in mock_sleep.call_args_list]
        assert len(waits) == 2
        for w in waits:
            assert 30.0 <= w <= 45.0

    @patch.object(cloudsec_mod.time, "sleep")
    @patch("limacharlie.client.urlopen")
    def test_gives_up_after_busy_retries(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = [_http_429("1") for _ in range(10)]
        with pytest.raises(RateLimitError) as e:
            _cloudsec().ingest_code_results("acme/api", "sarif", {"runs": []}, busy_retries=3)
        assert mock_urlopen.call_count == 4
        assert mock_sleep.call_count == 3
        assert e.value.retry_after == 1
        # The hint names what happened, not a --retry flag that does not apply here.
        assert "--retry" not in str(e.value)
        assert "refused 4 times" in str(e.value)

    @patch.object(cloudsec_mod.time, "sleep")
    @patch("limacharlie.client.urlopen")
    def test_zero_retries_raises_at_once(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = [_http_429("30"), _ok({"result": {}})]
        with pytest.raises(RateLimitError):
            _cloudsec().ingest_code_results("acme/api", "sarif", {"runs": []}, busy_retries=0)
        assert mock_urlopen.call_count == 1
        mock_sleep.assert_not_called()

    @patch.object(cloudsec_mod.time, "sleep")
    @patch("limacharlie.client.urlopen")
    def test_total_wait_is_bounded(self, mock_urlopen, mock_sleep):
        """A server that keeps asking for the maximum cannot hold a CI job past the budget."""
        mock_urlopen.side_effect = [_http_429("3600") for _ in range(50)]
        with pytest.raises(RateLimitError):
            _cloudsec().ingest_code_results("acme/api", "sarif", {"runs": []}, busy_retries=40)
        waits = [c.args[0] for c in mock_sleep.call_args_list]
        assert waits, "it never retried"
        assert sum(waits) <= cloudsec_mod._INGEST_BUSY_BUDGET_S
        # Each Retry-After was clamped, not obeyed for an hour.
        assert max(waits) <= cloudsec_mod._INGEST_RETRY_AFTER_MAX_S * (1 + cloudsec_mod._INGEST_JITTER)
        assert mock_urlopen.call_count < 41

    @patch.object(cloudsec_mod.time, "sleep")
    @patch("limacharlie.client.time")
    @patch("limacharlie.client.urlopen")
    def test_a_retry_client_does_not_stack_its_own_429_loop(self, mock_urlopen, mock_client_time, mock_sleep):
        """With the CLI's --retry on, the push still makes exactly one request per attempt."""
        mock_urlopen.side_effect = [_http_429("30"), _ok({"result": {}})]
        _cloudsec(is_retry_quota_errors=True).ingest_code_results("acme/api", "sarif", {"runs": []})
        assert mock_urlopen.call_count == 2
        mock_client_time.sleep.assert_not_called()
        assert mock_sleep.call_count == 1

    @patch.object(cloudsec_mod.time, "sleep")
    @patch("limacharlie.client.urlopen")
    def test_a_deterministic_refusal_is_not_retried(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = [_http_400(), _ok({"result": {}})]
        with pytest.raises(ApiError):
            _cloudsec().ingest_code_results("acme/api", "sarif", {"runs": []})
        assert mock_urlopen.call_count == 1
        mock_sleep.assert_not_called()


class TestBackoffShape:
    class _Rand:
        def __init__(self, pick):
            self.pick = pick

        def uniform(self, lo, hi):
            return lo if self.pick == "lo" else hi

    def test_without_retry_after_it_backs_off_exponentially_to_the_cap(self):
        lo = self._Rand("lo")
        assert [_ingest_busy_delay(n, None, lo) for n in range(6)] == [5.0, 10.0, 20.0, 40.0, 60.0, 60.0]

    def test_retry_after_is_a_floor_and_is_clamped(self):
        lo = self._Rand("lo")
        assert _ingest_busy_delay(0, 30, lo) == 30.0
        # A longer backoff than the server asked for is kept.
        assert _ingest_busy_delay(4, 30, lo) == 60.0
        assert _ingest_busy_delay(0, 3600, lo) == cloudsec_mod._INGEST_RETRY_AFTER_MAX_S

    def test_jitter_is_on_top_and_bounded(self):
        assert _ingest_busy_delay(0, 30, self._Rand("hi")) == 45.0
        # Real randomness spreads a fan-out: 50 draws are not all the same wait.
        draws = {_ingest_busy_delay(0, 30) for _ in range(50)}
        assert len(draws) > 1
        assert all(30.0 <= d <= 45.0 for d in draws)
