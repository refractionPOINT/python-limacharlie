"""False Positive Rules SDK for LimaCharlie v2."""


class FPRules:
    """False positive rule management."""

    def __init__(self, org):
        self._org = org

    def list(self):
        return self._org.get_fps()

    def get(self, name):
        fps = self.list()
        if isinstance(fps, dict):
            return fps.get(name)
        return None

    def create(self, name, rule, is_replace=False, ttl=None):
        return self._org.add_fp(name, rule, is_replace=is_replace, ttl=ttl)

    def delete(self, name):
        return self._org.delete_fp(name)
