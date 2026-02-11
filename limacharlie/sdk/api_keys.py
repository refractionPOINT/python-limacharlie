"""API Keys SDK for LimaCharlie v2."""


class ApiKeys:
    def __init__(self, org):
        self._org = org

    def list(self):
        return self._org.get_api_keys()

    def create(self, name, permissions, ip_range=None):
        return self._org.add_api_key(name, permissions, ip_range=ip_range)

    def delete(self, key_hash):
        return self._org.remove_api_key(key_hash)
