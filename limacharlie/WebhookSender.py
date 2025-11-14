import json
import gzip
import requests
from urllib.parse import quote

from . import __version__
from .user_agent_utils import build_user_agent

def _build_webhook_user_agent():
    """
    Build a comprehensive User-Agent string for webhook requests.

    Inspired by the Scalyr Agent implementation (Apache 2.0 licensed):
    https://github.com/scalyr/scalyr-agent-2/blob/97c7405d4a8a7c2d376826779831e6be2753e2ce/scalyr_agent/scalyr_client.py#L881

    The User-Agent includes:
    - Library version
    - Python version
    - Operating system
    - SSL/TLS version

    Returns:
        str: Formatted User-Agent string.

    Example User-Agent strings:
        - Linux: "lc-sdk-webhook/4.10.3;python-3.11.2;debian-12;openssl-3.0.0"
        - macOS: "lc-sdk-webhook/4.10.3;python-3.11.2;macos-14.0;openssl-3.0.0"
        - Windows: "lc-sdk-webhook/4.10.3;python-3.11.2;windows-10;openssl-3.0.0"
    """
    return build_user_agent('lc-sdk-webhook', __version__)

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
                "User-Agent": _build_webhook_user_agent()
            }
            response = self.client.post(self.url, data=b, headers=headers)
        except Exception as e:
            raise Exception(f"Error sending data: {e}")

        if response.status_code != 200:
            raise Exception(f"HTTP status code {response.status_code}: {response.text}")

        return None

    def close(self):
        self.client.close()
