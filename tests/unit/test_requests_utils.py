import shlex

import pytest

from limacharlie.request_utils import getCurlCommandString


class DummyRequestNoMethod:
    """
    Dummy request without get_method or header_items.
    Has a full_url attribute and optional data.
    """
    def __init__(self, full_url, data=None):
        self.full_url = full_url
        self.data = data


class DummyRequestWithMethods:
    """
    Dummy request that provides get_method, header_items, and get_full_url.
    Headers can be passed as a dict or list of tuples.
    """
    def __init__(self, method, headers, data, url):
        self._method = method
        self._headers = headers
        self.data = data
        self.full_url = url

    def get_method(self):
        return self._method

    def header_items(self):
        if isinstance(self._headers, dict):
            return list(self._headers.items())
        return self._headers

    def get_full_url(self):
        return self.full_url


class DummyRequestNoFullUrl:
    """
    Dummy request that does not have either get_full_url or full_url.
    This should raise an AttributeError when used.
    """
    def __init__(self, data=None):
        self.data = data


def test_default_get_method():
    """Test a basic GET request when get_method and header_items are missing."""
    dummy = DummyRequestNoMethod("http://example.com")
    result = getCurlCommandString(dummy)
    expected = "curl -X " + shlex.quote("GET") + " " + shlex.quote("http://example.com")
    assert result == expected


def test_post_with_headers():
    """Test a POST request with headers and no data."""
    headers = {"Content-Type": "application/json"}
    dummy = DummyRequestWithMethods("POST", headers, None, "http://example.com/api")
    result = getCurlCommandString(dummy)
    expected = (
        "curl -X " + shlex.quote("POST") +
        " -H " + shlex.quote("Content-Type: application/json") +
        " " + shlex.quote("http://example.com/api")
    )
    assert result == expected


def test_with_utf8_data():
    """Test a request with a valid UTF-8 data payload."""
    data = b'{"key": "value"}'
    dummy = DummyRequestWithMethods("PUT", {"Accept": "application/json"}, data, "http://example.com/update")
    result = getCurlCommandString(dummy)
    expected = (
        "curl -X " + shlex.quote("PUT") +
        " -H " + shlex.quote("Accept: application/json") +
        " -d " + shlex.quote('{"key": "value"}') +
        " " + shlex.quote("http://example.com/update")
    )
    assert result == expected


def test_with_non_utf8_data():
    """Test a request with data that cannot be decoded as UTF-8."""
    class NonUTF8Data:
        def decode(self, encoding):
            raise UnicodeDecodeError("utf-8", b"", 0, 1, "error")
        def __str__(self):
            return "NonUTF8Data"
    data = NonUTF8Data()
    dummy = DummyRequestWithMethods("PATCH", {"Authorization": "Bearer token"}, data, "http://example.com/patch")
    result = getCurlCommandString(dummy)
    expected = (
        "curl -X " + shlex.quote("PATCH") +
        " -H " + shlex.quote("Authorization: Bearer token") +
        " -d " + shlex.quote("NonUTF8Data") +
        " " + shlex.quote("http://example.com/patch")
    )
    assert result == expected


def test_multiple_headers():
    """Test a request with multiple headers provided as a list of tuples."""
    headers = [("Accept", "application/json"), ("User-Agent", "pytest")]
    dummy = DummyRequestWithMethods("GET", headers, None, "http://example.com/multi")
    result = getCurlCommandString( dummy)
    expected = (
        "curl -X " + shlex.quote("GET") +
        " -H " + shlex.quote("Accept: application/json") +
        " -H " + shlex.quote("User-Agent: pytest") +
        " " + shlex.quote("http://example.com/multi")
    )
    assert result == expected


def test_missing_url():
    """Test that a request missing both get_full_url and full_url raises an error."""
    dummy = DummyRequestNoFullUrl()
    with pytest.raises(AttributeError):
        getCurlCommandString(dummy)