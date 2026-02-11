"""Groups SDK for LimaCharlie v2."""


class Groups:
    def __init__(self, org):
        self._org = org

    def list(self):
        return self._org.get_groups()

    def get(self, group_id):
        return self._org.get_group(group_id)

    def create(self, name):
        return self._org.create_group(name)

    def delete(self, group_id):
        return self._org.delete_group(group_id)

    def add_member(self, group_id, email):
        return self._org.add_group_member(group_id, email)

    def remove_member(self, group_id, email):
        return self._org.remove_group_member(group_id, email)

    def add_owner(self, group_id, email):
        return self._org.add_group_owner(group_id, email)

    def remove_owner(self, group_id, email):
        return self._org.remove_group_owner(group_id, email)

    def set_permissions(self, group_id, permissions):
        return self._org.set_group_permissions(group_id, permissions)

    def get_logs(self, group_id):
        return self._org.get_group_logs(group_id)

    def add_org(self, group_id, oid):
        return self._org.add_group_org(group_id, oid)

    def remove_org(self, group_id, oid):
        return self._org.remove_group_org(group_id, oid)
