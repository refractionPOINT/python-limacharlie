"""Tests for misc SDK modules: fp_rules, outputs, insight, extensions,
installation_keys, ingestion_keys, users, groups, api_keys, billing,
artifacts, payloads, replay, integrity, exfil, logging_rules, ai,
investigations, usp, jobs, yara, arl.
"""

import json
from unittest.mock import MagicMock
import pytest

# Fixtures
@pytest.fixture
def mock_org():
    org = MagicMock()
    org.oid = "test-oid"
    org.client = MagicMock()
    return org


# --- FP Rules ---
class TestFPRules:
    def test_list(self, mock_org):
        from limacharlie.sdk.fp_rules import FPRules
        fp = FPRules(mock_org)
        mock_org.get_fps.return_value = {"fp1": {"data": {}}}
        result = fp.list()
        mock_org.get_fps.assert_called_once()
        assert "fp1" in result

    def test_create(self, mock_org):
        from limacharlie.sdk.fp_rules import FPRules
        fp = FPRules(mock_org)
        fp.create("fp1", {"op": "is"})
        mock_org.add_fp.assert_called_once()

    def test_delete(self, mock_org):
        from limacharlie.sdk.fp_rules import FPRules
        fp = FPRules(mock_org)
        fp.delete("fp1")
        mock_org.delete_fp.assert_called_once_with("fp1")


# --- Outputs ---
class TestOutputs:
    def test_list(self, mock_org):
        from limacharlie.sdk.outputs import Outputs
        o = Outputs(mock_org)
        mock_org.get_outputs.return_value = {"out1": {"module": "syslog"}}
        result = o.list()
        mock_org.get_outputs.assert_called_once()
        assert "out1" in result

    def test_create(self, mock_org):
        from limacharlie.sdk.outputs import Outputs
        o = Outputs(mock_org)
        o.create("out1", "syslog", "event", dest_host="1.2.3.4:443")
        mock_org.add_output.assert_called_once()

    def test_delete(self, mock_org):
        from limacharlie.sdk.outputs import Outputs
        o = Outputs(mock_org)
        o.delete("out1")
        mock_org.delete_output.assert_called_once_with("out1")


# --- Insight ---
class TestInsight:
    def test_search_ioc(self, mock_org):
        from limacharlie.sdk.insight import Insight
        ins = Insight(mock_org)
        mock_org.client.request.return_value = {"results": []}
        ins.search_ioc("domain", "evil.com")
        mock_org.client.request.assert_called_once()
        call_args = mock_org.client.request.call_args
        assert "insight/test-oid/objects/domain" in call_args[0][1]

    def test_batch_search(self, mock_org):
        from limacharlie.sdk.insight import Insight
        ins = Insight(mock_org)
        mock_org.client.request.return_value = {"results": []}
        ins.batch_search({"domain": ["evil.com", "bad.io"]})
        mock_org.client.request.assert_called_once()


# --- Extensions ---
class TestExtensions:
    def test_list_subscribed(self, mock_org):
        from limacharlie.sdk.extensions import Extensions
        ext = Extensions(mock_org)
        mock_org.client.request.return_value = {"ext1": True}
        result = ext.list_subscribed()
        mock_org.client.request.assert_called_once()
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "GET"
        assert "subscriptions" in call_args[0][1]

    def test_subscribe(self, mock_org):
        from limacharlie.sdk.extensions import Extensions
        ext = Extensions(mock_org)
        ext.subscribe("ext1")
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"
        assert "ext1" in call_args[0][1]

    def test_unsubscribe(self, mock_org):
        from limacharlie.sdk.extensions import Extensions
        ext = Extensions(mock_org)
        ext.unsubscribe("ext1")
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "DELETE"
        assert "ext1" in call_args[0][1]

    def test_request(self, mock_org):
        from limacharlie.sdk.extensions import Extensions
        ext = Extensions(mock_org)
        mock_org.client._jwt = "test-jwt"
        mock_org.client.request.return_value = {"result": "ok"}
        result = ext.request("ext-test", "do_thing", {"key": "val"})
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"
        assert "extension/request/ext-test" in call_args[0][1]
        params = call_args[1]["params"]
        assert "gzdata" in params
        assert params["action"] == "do_thing"


# --- Installation Keys ---
class TestInstallationKeys:
    def test_list(self, mock_org):
        from limacharlie.sdk.installation_keys import InstallationKeys
        ik = InstallationKeys(mock_org)
        mock_org.get_installation_keys.return_value = {"keys": []}
        result = ik.list()
        mock_org.get_installation_keys.assert_called_once()

    def test_create(self, mock_org):
        from limacharlie.sdk.installation_keys import InstallationKeys
        ik = InstallationKeys(mock_org)
        ik.create(description="test key", tags=["server"])
        mock_org.create_installation_key.assert_called_once_with("test key", tags=["server"], use_public_ca=False)

    def test_delete(self, mock_org):
        from limacharlie.sdk.installation_keys import InstallationKeys
        ik = InstallationKeys(mock_org)
        ik.delete("iid-123")
        mock_org.delete_installation_key.assert_called_once_with("iid-123")


# --- Ingestion Keys ---
class TestIngestionKeys:
    def test_list(self, mock_org):
        from limacharlie.sdk.ingestion_keys import IngestionKeys
        ingk = IngestionKeys(mock_org)
        mock_org.get_ingestion_keys.return_value = {"keys": []}
        ingk.list()
        mock_org.get_ingestion_keys.assert_called_once()

    def test_create(self, mock_org):
        from limacharlie.sdk.ingestion_keys import IngestionKeys
        ingk = IngestionKeys(mock_org)
        ingk.create("my-key")
        mock_org.create_ingestion_key.assert_called_once_with("my-key")


# --- Users ---
class TestUsers:
    def test_list(self, mock_org):
        from limacharlie.sdk.users import Users
        u = Users(mock_org)
        mock_org.get_users.return_value = {"users": []}
        u.list()
        mock_org.get_users.assert_called_once()

    def test_invite(self, mock_org):
        from limacharlie.sdk.users import Users
        u = Users(mock_org)
        u.invite("user@example.com")
        mock_org.add_user.assert_called_once_with("user@example.com")


# --- Groups ---
class TestGroups:
    def test_list(self, mock_org):
        from limacharlie.sdk.groups import Groups
        g = Groups(mock_org)
        mock_org.get_groups.return_value = {"groups": []}
        g.list()
        mock_org.get_groups.assert_called_once()


# --- API Keys ---
class TestApiKeys:
    def test_list(self, mock_org):
        from limacharlie.sdk.api_keys import ApiKeys
        ak = ApiKeys(mock_org)
        mock_org.get_api_keys.return_value = {"keys": []}
        ak.list()
        mock_org.get_api_keys.assert_called_once()

    def test_create(self, mock_org):
        from limacharlie.sdk.api_keys import ApiKeys
        ak = ApiKeys(mock_org)
        ak.create("my-key", ["sensor.list", "sensor.task"])
        mock_org.add_api_key.assert_called_once_with("my-key", ["sensor.list", "sensor.task"], ip_range=None)


# --- Billing ---
class TestBilling:
    def test_get_status(self, mock_org):
        from limacharlie.sdk.billing import Billing, BILLING_URL
        b = Billing(mock_org)
        b.get_status()
        call_args = mock_org.client.request.call_args
        assert call_args[1]["alt_root"] == BILLING_URL

    def test_get_invoice_url(self, mock_org):
        from limacharlie.sdk.billing import Billing
        b = Billing(mock_org)
        b.get_invoice_url(2024, 1)
        call_args = mock_org.client.request.call_args
        assert "2024" in call_args[0][1]
        assert "01" in call_args[0][1]

    def test_get_plans(self, mock_org):
        from limacharlie.sdk.billing import Billing, BILLING_URL
        b = Billing(mock_org)
        b.get_plans()
        call_args = mock_org.client.request.call_args
        assert "user/self/plans" in call_args[0][1]


# --- Artifacts ---
class TestArtifacts:
    def test_list(self, mock_org):
        from limacharlie.sdk.artifacts import Artifacts
        a = Artifacts(mock_org)
        mock_org.client.request.return_value = {"artifacts": []}
        a.list()
        mock_org.client.request.assert_called_once()


# --- Payloads ---
class TestPayloads:
    def test_list(self, mock_org):
        from limacharlie.sdk.payloads import Payloads
        p = Payloads(mock_org)
        mock_org.client.request.return_value = {"payloads": []}
        p.list()
        mock_org.client.request.assert_called_once()

    def test_delete(self, mock_org):
        from limacharlie.sdk.payloads import Payloads
        p = Payloads(mock_org)
        p.delete("payload-name")
        mock_org.client.request.assert_called_once()


# --- Replay ---
class TestReplay:
    def test_run_with_rule_name(self, mock_org):
        from limacharlie.sdk.replay import Replay
        r = Replay(mock_org)
        mock_org.service_request.return_value = {"job_id": "j1"}
        r.run(rule_name="my-rule", start=1704067200, end=1704153600)
        mock_org.service_request.assert_called_once()
        call_args = mock_org.service_request.call_args
        assert call_args[0][0] == "replay"
        params = call_args[0][1]
        assert params["rule_name"] == "my-rule"
        assert params["start"] == "1704067200"

    def test_run_with_detect_respond(self, mock_org):
        from limacharlie.sdk.replay import Replay
        r = Replay(mock_org)
        mock_org.service_request.return_value = {"job_id": "j1"}
        r.run(detect={"op": "is"}, respond=[{"action": "report"}], start=1000, end=2000)
        mock_org.service_request.assert_called_once()


# --- Integrity ---
class TestIntegrity:
    def test_list(self, mock_org):
        from limacharlie.sdk.integrity import Integrity
        i = Integrity(mock_org)
        mock_org.service_request.return_value = {"rules": {}}
        i.list()
        mock_org.service_request.assert_called_once()

    def test_create(self, mock_org):
        from limacharlie.sdk.integrity import Integrity
        i = Integrity(mock_org)
        i.create("test-rule", ["*.exe"])
        mock_org.service_request.assert_called_once()


# --- Exfil ---
class TestExfil:
    def test_list(self, mock_org):
        from limacharlie.sdk.exfil import Exfil
        e = Exfil(mock_org)
        mock_org.service_request.return_value = {"watch": {}, "list": {}}
        e.list()
        mock_org.service_request.assert_called_once()


# --- Logging Rules ---
class TestLoggingRules:
    def test_list(self, mock_org):
        from limacharlie.sdk.logging_rules import LoggingRules
        lr = LoggingRules(mock_org)
        mock_org.service_request.return_value = {"rules": {}}
        lr.list()
        mock_org.service_request.assert_called_once()


# --- AI ---
class TestAI:
    def test_generate_dr_rule(self, mock_org):
        from limacharlie.sdk.ai import AI
        ai = AI(mock_org)
        mock_org.client.request.return_value = {"rule": {"detect": {}}}
        ai.generate_dr_rule("detect mimikatz usage")
        mock_org.client.request.assert_called_once()


# --- Investigations ---
class TestInvestigations:
    def test_list(self, mock_org):
        from limacharlie.sdk.investigations import Investigations
        inv = Investigations(mock_org)
        mock_org.client.request.return_value = {"investigations": []}
        inv.list()
        mock_org.client.request.assert_called_once()

    def test_create(self, mock_org):
        from limacharlie.sdk.investigations import Investigations
        inv = Investigations(mock_org)
        inv.create({"title": "test"})
        mock_org.client.request.assert_called_once()

    def test_delete(self, mock_org):
        from limacharlie.sdk.investigations import Investigations
        inv = Investigations(mock_org)
        inv.delete("inv-123")
        mock_org.client.request.assert_called_once()


# --- USP ---
class TestUSP:
    def test_validate(self, mock_org):
        from limacharlie.sdk.usp import USP
        u = USP(mock_org)
        u.validate("text", mapping={"key": "val"})
        call_args = mock_org.client.request.call_args
        assert call_args[0][0] == "POST"
        body = json.loads(call_args[1]["raw_body"])
        assert body["platform"] == "text"
        assert body["mapping"] == {"key": "val"}


# --- Jobs ---
class TestJobs:
    def test_list(self, mock_org):
        from limacharlie.sdk.jobs import Jobs
        j = Jobs(mock_org)
        mock_org.get_jobs.return_value = {"jobs": []}
        j.list()
        mock_org.get_jobs.assert_called_once()

    def test_get(self, mock_org):
        from limacharlie.sdk.jobs import Jobs
        j = Jobs(mock_org)
        mock_org.client.request.return_value = {"job_id": "j1", "is_done": True}
        j.get("j1")
        mock_org.client.request.assert_called_once()

    def test_delete(self, mock_org):
        from limacharlie.sdk.jobs import Jobs
        j = Jobs(mock_org)
        j.delete("j1")
        mock_org.client.request.assert_called_once()


# --- YARA ---
class TestYara:
    def test_scan(self, mock_org):
        from limacharlie.sdk.yara import Yara
        y = Yara(mock_org)
        y.scan("sid-123", "rule content")
        mock_org.service_request.assert_called_once()

    def test_list_rules(self, mock_org):
        from limacharlie.sdk.yara import Yara
        y = Yara(mock_org)
        y.list_rules()
        mock_org.service_request.assert_called_once()


# --- ARL ---
class TestARL:
    def test_get(self, mock_org):
        from limacharlie.sdk.arl import ARL
        a = ARL(mock_org)
        mock_org.client.request.return_value = {"data": "resolved"}
        a.get("arl://my-resource")
        mock_org.client.request.assert_called_once_with(
            "GET", "arl/test-oid", query_params={"arl": "arl://my-resource"}
        )
