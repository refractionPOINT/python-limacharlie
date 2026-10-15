import os
import sys

# Get the directory of the current conftest.py file
current_dir = os.path.dirname(os.path.abspath(__file__))

# Calculate the project root (adjust the number of ".." if needed)
project_root = os.path.abspath(os.path.join(current_dir, '../../'))

# Insert the project root at the beginning of sys.path
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import pytest  # noqa: E402

from limacharlie.client import Client  # noqa: E402
from limacharlie.errors import NotFoundError  # noqa: E402
from limacharlie.sdk.organization import Organization  # noqa: E402


def pytest_addoption( parser ):
    parser.addoption( "--oid", action = "store", required = True )
    parser.addoption( "--key", action = "store", required = True )


def pytest_generate_tests( metafunc ):
    option_value = metafunc.config.option.oid
    if "oid" in metafunc.fixturenames and option_value is not None:
        metafunc.parametrize( "oid", [ option_value ], ids = [ "oid" ] )
    option_value = metafunc.config.option.key
    if "key" in metafunc.fixturenames and option_value is not None:
        # Constant id: pytest would otherwise embed the key value in every test id (and the build log).
        metafunc.parametrize( "key", [ option_value ], ids = [ "key" ] )


# ---------------------------------------------------------------------------
# Key cleanup
#
# Tests that create API keys or installation keys register the key's unique
# name (or description) with one of the fixtures below BEFORE creating it.
# Teardown looks the keys up by that name in the org's key list and deletes
# them by the id the list returns. It therefore does not depend on the test
# having parsed an id out of the create response, and it runs whether the test
# passed, failed half way, or already deleted the key itself (nothing is found).
#
# A key that is already gone never fails a test: a not-found response is
# ignored, and a failed delete is checked against a fresh listing. A key that
# is still present after its delete failed is raised from teardown, which
# pytest reports as a separate ERROR next to the test's own result: a leaked
# key is never silent, and it never replaces the test's own failure.
# ---------------------------------------------------------------------------


def _key_entries(listing, id_field):
    """Yield (id, entry) for each key in a listing keyed by id or given as a list."""
    if isinstance(listing, dict):
        for kid, entry in listing.items():
            if isinstance(entry, dict):
                yield kid, entry
    elif isinstance(listing, list):
        for entry in listing:
            if isinstance(entry, dict) and entry.get(id_field):
                yield entry[id_field], entry


def _delete_keys(kind, ids, delete, list_ids):
    """Delete every id, attempting all of them, and raise if any key remains.

    A key that is already gone is not an error: a not-found response is
    ignored, and when a delete fails the org is listed again, so a key that was
    removed anyway (by the test itself, or a delete that succeeded but
    reported an error) does not fail the test. Only a key that is still
    present after its delete failed is reported.
    """
    errors = {}
    for kid in ids:
        try:
            delete(kid)
        except NotFoundError:
            pass
        except Exception as e:
            errors[kid] = e
    if not errors:
        return
    remaining = set(list_ids())
    left = [f"{kid}: {e!r}" for kid, e in errors.items() if kid in remaining]
    if left:
        raise RuntimeError(f"failed to delete {len(left)} test {kind}(s): {left}")


@pytest.fixture
def api_key_cleanup(oid, key):
    """Return a function that registers an API key name for deletion at teardown."""
    names = set()
    yield names.add
    if not names:
        return
    org = Organization(Client(oid=oid, api_key=key))

    def matching():
        return [
            h for h, entry in _key_entries(org.get_api_keys(), "key_hash")
            if (entry.get("name") or entry.get("key_name")) in names
        ]

    _delete_keys("API key", matching(), org.remove_api_key, matching)


@pytest.fixture
def installation_key_cleanup(oid, key):
    """Return a function that registers an installation key description for deletion at teardown."""
    descriptions = set()
    yield descriptions.add
    if not descriptions:
        return
    org = Organization(Client(oid=oid, api_key=key))

    def matching():
        return [
            iid for iid, entry in _key_entries(org.get_installation_keys(), "iid")
            if (entry.get("desc") or entry.get("description")) in descriptions
        ]

    _delete_keys("installation key", matching(), org.delete_installation_key, matching)
