import sys
import shlex

_IS_PYTHON_2 = False
if sys.version_info[ 0 ] < 3:
    _IS_PYTHON_2 = True


if _IS_PYTHON_2:
    from urllib2 import Request as URLRequest
else:
    from urllib.request import Request as URLRequest


def getCurlCommandString(request: URLRequest):
    """
    Budl cURL command string for a specific request to aid with debugging.

    Args:
        request: The request object to build the cURL command from.
    """
    parts = ["curl"]

    # Determine HTTP method (default to GET if not available)
    method = request.get_method() if hasattr(request, "get_method") else "GET"
    parts.extend(["-X", shlex.quote(method)])

    # Extract and add headers from the request.
    # request.header_items() returns a list of (header, value) pairs.
    if hasattr(request, "header_items"):
        for header, value in request.header_items():
            parts.extend(["-H", shlex.quote(f"{header}: {value}")])

    # If there's a data payload, add it.
    if request.data:
        try:
            data_str = request.data.decode("utf-8")
        except Exception:
            data_str = str(request.data)
        parts.extend(["-d", shlex.quote(data_str)])

    # Append the URL. Use get_full_url() if available.
    url = request.get_full_url() if hasattr(request, "get_full_url") else request.full_url
    parts.append(shlex.quote(url))

    # Join the parts into a single string command.
    return " ".join(parts)
