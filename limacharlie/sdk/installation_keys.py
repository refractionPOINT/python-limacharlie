"""Installation Keys SDK for LimaCharlie v2."""


class InstallationKeys:
    def __init__(self, org):
        self._org = org

    def list(self):
        return self._org.get_installation_keys()

    def get(self, iid):
        return self._org.get_installation_key(iid)

    def create(self, description, tags=None, use_public_ca=False):
        return self._org.create_installation_key(description, tags=tags, use_public_ca=use_public_ca)

    def delete(self, iid):
        return self._org.delete_installation_key(iid)
