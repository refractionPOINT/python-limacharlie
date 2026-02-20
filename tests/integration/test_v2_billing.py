import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization
from limacharlie.sdk.billing import Billing


def _make_org(oid, key):
    client = Client(oid=oid, api_key=key)
    return Organization(client)


def test_v2_billing_status(oid, key):
    org = _make_org(oid, key)
    billing = Billing(org)
    status = billing.get_status()
    assert isinstance(status, dict)
