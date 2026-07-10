import os
import sys

import pytest

# Get the directory of the current conftest.py file
current_dir = os.path.dirname(os.path.abspath(__file__))

# Calculate the project root (adjust the number of ".." if needed)
project_root = os.path.abspath(os.path.join(current_dir, '../../'))

# Insert the project root at the beginning of sys.path
if project_root not in sys.path:
    sys.path.insert(0, project_root)


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Unit tests must never reach the network.

    Local dev machines carry live credentials in ~/.limacharlie.d, so an
    unmocked CLI/SDK invocation that slips past argument validation would
    otherwise perform a REAL API call (including writes) against a live
    org. Tests that need HTTP behavior patch ``limacharlie.client.urlopen``
    themselves (unittest.mock.patch overrides this guard for their scope).
    """
    def _blocked(*_a, **_k):
        raise AssertionError(
            "unit test attempted a real network call (limacharlie.client.urlopen)"
        )
    monkeypatch.setattr("limacharlie.client.urlopen", _blocked)