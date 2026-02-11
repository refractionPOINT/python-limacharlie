"""Shared fixtures for LimaCharlie CLI v2 integration tests."""

import os
import sys
import uuid
import pytest

# Ensure project root is on the path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../../"))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from limacharlie.client import Client
from limacharlie.sdk.organization import Organization


TEST_PREFIX = "test-cli-v2-"


def unique_name(base=""):
    """Generate a unique test name with prefix."""
    return f"{TEST_PREFIX}{base}{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="session")
def oid(request):
    """Get the organization ID from pytest options."""
    return request.config.getoption("--oid")


@pytest.fixture(scope="session")
def api_key(request):
    """Get the API key from pytest options."""
    return request.config.getoption("--key")


@pytest.fixture(scope="session")
def client(oid, api_key):
    """Create an authenticated Client instance."""
    return Client(oid=oid, api_key=api_key)


@pytest.fixture(scope="session")
def org(client):
    """Create an Organization instance."""
    return Organization(client)
