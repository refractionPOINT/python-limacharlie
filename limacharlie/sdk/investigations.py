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
