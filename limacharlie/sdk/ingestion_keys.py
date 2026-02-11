"""Ingestion Keys SDK for LimaCharlie v2."""


class IngestionKeys:
    def __init__(self, org):
        self._org = org

    def list(self):
        return self._org.get_ingestion_keys()

    def create(self, name):
        return self._org.create_ingestion_key(name)

    def delete(self, name):
        return self._org.delete_ingestion_key(name)

    def configure_usp(self, name, parse_hint=None, format_re=None):
        return self._org.configure_usp_key(name, parse_hint=parse_hint, format_re=format_re)
