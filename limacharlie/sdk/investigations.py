"""Investigations SDK for LimaCharlie v2."""

import json


class Investigations:
    """Investigation management."""

    def __init__(self, org):
        self._org = org

    @property
    def client(self):
        return self._org.client

    def list(self):
        return self.client.request("GET", f"insight/{self._org.oid}/investigations")

    def get(self, investigation_id):
        return self.client.request("GET", f"insight/{self._org.oid}/investigations/{investigation_id}")

    def create(self, data):
        return self.client.request("POST", f"insight/{self._org.oid}/investigations",
                                   raw_body=json.dumps(data).encode(),
                                   content_type="application/json")

    def update(self, investigation_id, data):
        return self.client.request("POST", f"insight/{self._org.oid}/investigations/{investigation_id}",
                                   raw_body=json.dumps(data).encode(),
                                   content_type="application/json")

    def delete(self, investigation_id):
        return self.client.request("DELETE", f"insight/{self._org.oid}/investigations/{investigation_id}")

    def expand(self, investigation_id, sid=None, events=None):
        """Expand an investigation timeline.

        Args:
            investigation_id: Investigation ID.
            sid: Optional sensor ID.
            events: Optional list of events to add.

        Returns:
            dict: API response.
        """
        data = {}
        if sid is not None:
            data["sid"] = sid
        if events is not None:
            data["events"] = events
        return self.client.request("POST", f"insight/{self._org.oid}/investigations/{investigation_id}/expand",
                                   raw_body=json.dumps(data).encode(),
                                   content_type="application/json")
