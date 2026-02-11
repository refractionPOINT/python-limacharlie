"""ARL (Authenticated Resource Locator) SDK for LimaCharlie v2."""


class ARL:
    """Resolve and fetch data from Authenticated Resource Locators."""

    def __init__(self, org):
        self._org = org

    @property
    def client(self):
        return self._org.client

    def get(self, arl_url):
        """Resolve an ARL and return the data.

        Args:
            arl_url: The ARL URL to resolve.

        Returns:
            dict or bytes: Resolved data.
        """
        return self.client.request("GET", f"arl/{self._org.oid}",
                                   query_params={"arl": arl_url})
