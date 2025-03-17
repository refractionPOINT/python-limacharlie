import json
import gzip
import requests
from urllib.parse import quote

from . import __version__

class WebhookSender(object):
    def __init__(self, manager, hook_name, secret_value):
        self._manager = manager
        urls = self._manager.getOrgURLs()
        if 'hooks' not in urls:
            raise ValueError("Hook URL not found in org URLs")

        hook_url = urls['hooks']
        self.url = f"https://{hook_url}/{self._manager._oid}/{quote(hook_name)}/{quote(secret_value)}"
        self.client = requests.Session()
        self.client.timeout = 30  # 30 seconds timeout

    def send(self, data):
        try:
            b = gzip.compress(json.dumps(data).encode())
            headers = {
                "Content-Type": "application/json",
                "Content-Encoding": "gzip",
                "User-Agent": "lc-sdk-webhook/%s" % (__version__)
            }
            response = self.client.post(self.url, data=b, headers=headers)
        except Exception as e:
            raise Exception(f"Error sending data: {e}")

        if response.status_code != 200:
            raise Exception(f"HTTP status code {response.status_code}: {response.text}")

        return None

    def close(self):
        self.client.close()
