"""Users SDK for LimaCharlie v2."""


class Users:
    def __init__(self, org):
        self._org = org

    def list(self):
        return self._org.get_users()

    def invite(self, email):
        return self._org.add_user(email)

    def remove(self, email):
        return self._org.remove_user(email)

    def list_permissions(self):
        return self._org.get_user_permissions()

    def add_permission(self, email, permission):
        return self._org.add_user_permission(email, permission)

    def remove_permission(self, email, permission):
        return self._org.remove_user_permission(email, permission)

    def set_role(self, email, role):
        return self._org.set_user_role(email, role)
