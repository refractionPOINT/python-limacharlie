"""Extensions SDK for LimaCharlie v2."""


class Extensions:
    """Extension subscription and request management."""

    def __init__(self, org):
        self._org = org

    def list_subscribed(self):
        return self._org.get_subscriptions()

    def subscribe(self, name):
        return self._org.subscribe_to_extension(name)

    def unsubscribe(self, name):
        return self._org.unsubscribe_from_extension(name)

    def request(self, extension_name, action, data=None):
        """Call an extension.

        Args:
            extension_name: Extension name.
            action: Action to invoke.
            data: Request data dict.

        Returns:
            dict: Extension response.
        """
        params = {"action": action}
        if data:
            params.update(data)
        return self._org.service_request(extension_name, params)
