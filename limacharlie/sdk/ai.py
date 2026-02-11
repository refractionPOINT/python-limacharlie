"""AI generation SDK for LimaCharlie v2."""

import json


class AI:
    """AI-powered generation of rules, queries, selectors, and playbooks."""

    def __init__(self, org):
        self._org = org

    @property
    def client(self):
        return self._org.client

    def generate_dr_rule(self, description):
        return self.client.request("POST", f"ai/{self._org.oid}/dr",
                                   raw_body=json.dumps({"description": description}).encode(),
                                   content_type="application/json")

    def generate_detection(self, description):
        return self.client.request("POST", f"ai/{self._org.oid}/detection",
                                   raw_body=json.dumps({"description": description}).encode(),
                                   content_type="application/json")

    def generate_response(self, description):
        return self.client.request("POST", f"ai/{self._org.oid}/response",
                                   raw_body=json.dumps({"description": description}).encode(),
                                   content_type="application/json")

    def generate_lcql(self, description):
        return self.client.request("POST", f"ai/{self._org.oid}/lcql",
                                   raw_body=json.dumps({"description": description}).encode(),
                                   content_type="application/json")

    def generate_sensor_selector(self, description):
        return self.client.request("POST", f"ai/{self._org.oid}/sensor_selector",
                                   raw_body=json.dumps({"description": description}).encode(),
                                   content_type="application/json")

    def generate_playbook(self, description):
        return self.client.request("POST", f"ai/{self._org.oid}/playbook/python",
                                   raw_body=json.dumps({"description": description}).encode(),
                                   content_type="application/json")

    def summarize_detection(self, detection_data):
        return self.client.request("POST", f"ai/{self._org.oid}/det_summary",
                                   raw_body=json.dumps(detection_data).encode(),
                                   content_type="application/json")
