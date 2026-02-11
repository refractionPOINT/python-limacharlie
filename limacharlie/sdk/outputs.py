"""Outputs SDK for LimaCharlie v2."""


class Outputs:
    """Output integration management."""

    def __init__(self, org):
        self._org = org

    def list(self):
        return self._org.get_outputs()

    def create(self, name, module, data_type, **kwargs):
        return self._org.add_output(name, module, data_type, **kwargs)

    def delete(self, name):
        return self._org.delete_output(name)
