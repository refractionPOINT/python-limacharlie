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


def pytest_addoption( parser ):
    parser.addoption( "--oid", action = "store", required = True )
    parser.addoption( "--key", action = "store", required = True )


def pytest_generate_tests( metafunc ):
    option_value = metafunc.config.option.oid
    if "oid" in metafunc.fixturenames and option_value is not None:
        metafunc.parametrize( "oid", [ option_value ] )
    option_value = metafunc.config.option.key
    if "key" in metafunc.fixturenames and option_value is not None:
        metafunc.parametrize( "key", [ option_value ] )


# Replicant services required by integration tests.
_REQUIRED_REPLICANTS = ["integrity", "exfil", "logging", "yara"]


@pytest.fixture(scope="session", autouse=True)
def _ensure_required_services(request):
    """Subscribe the test org to required replicant services before tests run.

    Runs once per session.  Services that are already subscribed are left
    untouched, and only newly-added subscriptions are removed at teardown
    so the org ends in the same state it started in.
    """
    oid = request.config.getoption("--oid")
    key = request.config.getoption("--key")

    from limacharlie.client import Client
    from limacharlie.sdk.organization import Organization

    client = Client(oid=oid, api_key=key)
    org = Organization(client)

    # Discover which replicants are already subscribed.
    resources = client.request("GET", f"orgs/{oid}/resources")
    existing = set(resources.get("resources", {}).get("replicant", []))

    added = []
    for svc in _REQUIRED_REPLICANTS:
        if svc not in existing:
            org.subscribe_to_extension(f"replicant/{svc}")
            added.append(svc)

    yield

    # Teardown: remove only what we added.
    for svc in added:
        try:
            org.unsubscribe_from_extension(f"replicant/{svc}")
        except Exception:
            pass