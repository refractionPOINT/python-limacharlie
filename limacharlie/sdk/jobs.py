"""Jobs SDK for LimaCharlie v2."""

from __future__ import annotations

import time
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization


class Jobs:
    """Service/replicant job tracking."""

    def __init__(self, org: Organization) -> None:
        self._org = org

    @property
    def client(self) -> Any:
        """The underlying API client."""
        return self._org.client

    def list(self, start_time: int | None = None, end_time: int | None = None,
             limit: int | None = None, sid: str | None = None) -> list[dict[str, Any]]:
        """List jobs.

        Args:
            start_time: Filter start time (unix seconds).
            end_time: Filter end time (unix seconds).
            limit: Maximum number of jobs to return.
            sid: Filter by sensor ID.
        """
        return self._org.get_jobs(start_time=start_time, end_time=end_time,
                                  limit=limit, sid=sid)

    def get(self, job_id: str) -> dict[str, Any]:
        """Get a job by ID.

        Args:
            job_id: Job identifier.
        """
        return self.client.request("GET", f"job/{self._org.oid}/{job_id}")

    def delete(self, job_id: str) -> dict[str, Any]:
        """Delete a job.

        Args:
            job_id: Job identifier.
        """
        return self.client.request("DELETE", f"job/{self._org.oid}/{job_id}")

    def wait(self, job_id: str, timeout: int = 300, poll_interval: int = 5) -> dict[str, Any]:
        """Wait for a job to complete.

        Args:
            job_id: Job identifier.
            timeout: Max wait time in seconds.
            poll_interval: Seconds between polls.

        Returns:
            dict: Final job status.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = self.get(job_id)
            if job.get("is_done", False) or job.get("completed", False):
                return job
            time.sleep(min(poll_interval, deadline - time.time()))
        return self.get(job_id)
