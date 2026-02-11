"""Jobs SDK for LimaCharlie v2."""

import time


class Jobs:
    """Service/replicant job tracking."""

    def __init__(self, org):
        self._org = org

    @property
    def client(self):
        return self._org.client

    def list(self, start_time=None, end_time=None, limit=None, sid=None):
        return self._org.get_jobs(start_time=start_time, end_time=end_time,
                                  limit=limit, sid=sid)

    def get(self, job_id):
        return self.client.request("GET", f"job/{self._org.oid}/{job_id}")

    def delete(self, job_id):
        return self.client.request("DELETE", f"job/{self._org.oid}/{job_id}")

    def wait(self, job_id, timeout=300, poll_interval=5):
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
