"""Tests for limacharlie.sdk.jobs module."""

from unittest.mock import MagicMock, patch
import pytest

from limacharlie.sdk.jobs import Jobs


@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    return org


@pytest.fixture
def jobs(mock_org):
    return Jobs(mock_org)


class TestJobsList:
    def test_list_delegates_to_org(self, jobs, mock_org):
        mock_org.get_jobs.return_value = [{"job_id": "j1"}]
        result = jobs.list()
        mock_org.get_jobs.assert_called_once_with(start_time=None, end_time=None,
                                                  limit=None, sid=None)
        assert result == [{"job_id": "j1"}]

    def test_list_with_params(self, jobs, mock_org):
        mock_org.get_jobs.return_value = []
        jobs.list(start_time=1000, end_time=2000, limit=10, sid="abc-sid")
        mock_org.get_jobs.assert_called_once_with(start_time=1000, end_time=2000,
                                                  limit=10, sid="abc-sid")


class TestJobsGet:
    def test_get(self, jobs, mock_org):
        mock_org.client.request.return_value = {"job_id": "j1", "status": "running"}
        result = jobs.get("j1")
        mock_org.client.request.assert_called_once_with("GET", "job/test-oid/j1")
        assert result == {"job_id": "j1", "status": "running"}


class TestJobsDelete:
    def test_delete(self, jobs, mock_org):
        mock_org.client.request.return_value = {}
        jobs.delete("j1")
        mock_org.client.request.assert_called_once_with("DELETE", "job/test-oid/j1")


class TestJobsWait:
    def test_wait_returns_immediately_when_done(self, jobs, mock_org):
        mock_org.client.request.return_value = {"job_id": "j1", "is_done": True}
        with patch("limacharlie.sdk.jobs.time") as mock_time:
            mock_time.time.return_value = 1000.0
            result = jobs.wait("j1")
        assert result["is_done"] is True
        mock_org.client.request.assert_called_once_with("GET", "job/test-oid/j1")

    def test_wait_returns_on_completed_flag(self, jobs, mock_org):
        mock_org.client.request.return_value = {"job_id": "j1", "completed": True}
        with patch("limacharlie.sdk.jobs.time") as mock_time:
            mock_time.time.return_value = 1000.0
            result = jobs.wait("j1")
        assert result["completed"] is True

    def test_wait_polls_until_done(self, jobs, mock_org):
        mock_org.client.request.side_effect = [
            {"job_id": "j1", "is_done": False},
            {"job_id": "j1", "is_done": False},
            {"job_id": "j1", "is_done": True},
        ]
        with patch("limacharlie.sdk.jobs.time") as mock_time:
            # deadline = time()+300 = 1300
            # while check -> get1 -> sleep calc -> while check -> get2 -> sleep calc -> while check -> get3 -> done
            mock_time.time.side_effect = [1000.0, 1000.0, 1000.0, 1005.0, 1005.0, 1010.0]
            mock_time.sleep = MagicMock()
            result = jobs.wait("j1", timeout=300, poll_interval=5)
        assert result["is_done"] is True
        assert mock_org.client.request.call_count == 3
        assert mock_time.sleep.call_count == 2

    def test_wait_returns_last_status_on_timeout(self, jobs, mock_org):
        mock_org.client.request.return_value = {"job_id": "j1", "is_done": False}
        with patch("limacharlie.sdk.jobs.time") as mock_time:
            # deadline = time()+300 = 1300
            # while check (pass) -> get1 (not done) -> sleep calc -> while check (fail) -> final get
            mock_time.time.side_effect = [1000.0, 1000.0, 1000.0, 1301.0]
            mock_time.sleep = MagicMock()
            result = jobs.wait("j1", timeout=300)
        assert result["is_done"] is False
