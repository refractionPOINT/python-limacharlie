"""Billing SDK for LimaCharlie v2."""

BILLING_URL = "https://billing.limacharlie.io/"


class Billing:
    def __init__(self, org):
        self._org = org

    @property
    def client(self):
        return self._org.client

    def get_status(self):
        return self.client.request("GET", f"orgs/{self._org.oid}/status", alt_root=BILLING_URL)

    def get_details(self):
        return self.client.request("GET", f"orgs/{self._org.oid}/details", alt_root=BILLING_URL)

    def get_invoice_url(self, year, month, fmt=None):
        year = str(int(year))
        month = str(int(month)).zfill(2)
        qp = {}
        if fmt:
            qp["format"] = fmt
        return self.client.request("GET", f"orgs/{self._org.oid}/invoice_url/{year}/{month}",
                                   alt_root=BILLING_URL, query_params=qp or None)

    def get_plans(self):
        return self.client.request("GET", "user/self/plans", alt_root=BILLING_URL)

    def get_sku_definitions(self):
        return self.client.request("GET", f"orgs/{self._org.oid}/sku-definitions", alt_root=BILLING_URL)
