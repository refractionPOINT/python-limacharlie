"""Tests for finishing an OAuth login by pasting the redirect URL.

When the CLI runs on a remote box (for example over SSH), the provider sends
the user's browser to http://localhost:<port>/callback on *their* machine, so
the CLI's local callback server never sees it. The user pastes that URL into
the terminal instead. The local server must keep working at the same time for
people who forward the port or log in on the same machine.
"""

import os
import socket
import sys
import threading
import urllib.request
from unittest import mock

import pytest

import limacharlie.oauth_firebase_simple as fb
from limacharlie.oauth_firebase_simple import FirebaseAuthError, SimpleFirebaseAuth
from limacharlie.oauth_server import OAuthCallbackServer

REDIRECT = "http://localhost:8085/callback"
QUERY = "state=abc123&code=4%2F0Aean-xyz&scope=email+openid"


@pytest.fixture
def stdin_pipe(monkeypatch):
    """Replace stdin with a pipe the test can write lines into."""
    r, w = os.pipe()
    reader = os.fdopen(r, "r")
    writer = os.fdopen(w, "w")
    monkeypatch.setattr(sys, "stdin", reader)
    yield writer
    for f in (reader, writer):
        try:
            f.close()
        except OSError:
            pass


class FakeServer:
    """Stands in for OAuthCallbackServer without binding a port."""

    def __init__(self, timeout=5, result=None):
        self.timeout = timeout
        self.port = 8085
        self._result = result

    def poll_callback(self, timeout):
        result, self._result = self._result, None
        return result


def _auth_with(server):
    auth = SimpleFirebaseAuth()
    auth.callback_server = server
    return auth


@pytest.mark.parametrize("pasted", [
    f"{REDIRECT}?{QUERY}",
    f"  {REDIRECT}?{QUERY}  ",
    f"'{REDIRECT}?{QUERY}'",
    f"/callback?{QUERY}",
    f"?{QUERY}",
    QUERY,
])
def test_parse_pasted_redirect_accepts_url_path_or_query(pasted):
    assert fb._parse_pasted_redirect(pasted) == f"/callback?{QUERY}"


def test_parse_pasted_redirect_keeps_provider_error():
    path = fb._parse_pasted_redirect(f"{REDIRECT}?error=access_denied&state=abc")
    assert path == "/callback?error=access_denied&state=abc"
    with pytest.raises(FirebaseAuthError, match="access_denied"):
        SimpleFirebaseAuth()._extract_query_string(path)


@pytest.mark.parametrize("pasted", [
    "",
    "   ",
    "hello",
    REDIRECT,
    f"{REDIRECT}?code=4%2F0Aean-xyz",  # state cut off
    "https://accounts.google.com/o/oauth2/auth?client_id=x&state=y",
])
def test_parse_pasted_redirect_rejects_non_redirects(pasted):
    assert fb._parse_pasted_redirect(pasted) is None


def test_pasted_url_completes_wait(stdin_pipe):
    stdin_pipe.write(f"{REDIRECT}?{QUERY}\n")
    stdin_pipe.flush()

    path = _auth_with(FakeServer())._wait_for_redirect(True, REDIRECT)

    assert path == f"/callback?{QUERY}"


def test_bad_paste_reprompts_then_accepts(stdin_pipe, capsys):
    stdin_pipe.write("not a url\n\n")
    stdin_pipe.write(f"{REDIRECT}?{QUERY}\n")
    stdin_pipe.flush()

    path = _auth_with(FakeServer())._wait_for_redirect(True, REDIRECT)

    assert path == f"/callback?{QUERY}"
    out = capsys.readouterr().out
    # One hint for the bad line, none for the blank one.
    assert out.count("does not look like the sign-in redirect URL") == 1
    assert REDIRECT in out


def test_server_callback_still_wins_when_paste_enabled(stdin_pipe):
    server = FakeServer(result=(True, f"/callback?{QUERY}", None))

    path = _auth_with(server)._wait_for_redirect(True, REDIRECT)

    assert path == f"/callback?{QUERY}"


def test_stdin_eof_falls_back_to_server(stdin_pipe):
    stdin_pipe.close()

    class LateServer(FakeServer):
        calls = 0

        def poll_callback(self, timeout):
            self.calls += 1
            if self.calls < 3:
                return None
            return (True, f"/callback?{QUERY}", None)

    path = _auth_with(LateServer())._wait_for_redirect(True, REDIRECT)

    assert path == f"/callback?{QUERY}"


def test_server_error_is_raised(stdin_pipe):
    server = FakeServer(result=(False, None, "Authentication timeout"))

    with pytest.raises(FirebaseAuthError, match="Authentication timeout"):
        _auth_with(server)._wait_for_redirect(True, REDIRECT)


def test_wait_times_out_without_input(stdin_pipe):
    with pytest.raises(FirebaseAuthError, match="timeout"):
        _auth_with(FakeServer(timeout=0.3))._wait_for_redirect(True, REDIRECT)


def _signin_response():
    resp = mock.Mock()
    resp.json.return_value = {
        "idToken": "id-token",
        "refreshToken": "refresh-token",
        "expiresIn": "3600",
        "localId": "firebase-uid",
        "email": "user@example.com",
    }
    resp.raise_for_status.return_value = None
    return resp


def test_no_browser_login_completes_from_pasted_url(stdin_pipe, capsys):
    """Full flow: --no-browser prints the URL, user pastes the redirect, tokens come back."""
    stdin_pipe.write(f"{REDIRECT}?{QUERY}\n")
    stdin_pipe.flush()

    class StubServer(FakeServer):
        def start(self):
            return self.port

        def stop(self):
            pass

    with mock.patch.object(fb, "OAuthCallbackServer", StubServer), \
         mock.patch.object(SimpleFirebaseAuth, "_create_auth_uri",
                           return_value=("session-1", "https://accounts.google.com/auth?x=1")), \
         mock.patch.object(fb.webbrowser, "open") as browser_open, \
         mock.patch.object(fb.requests, "post", return_value=_signin_response()) as post:
        tokens = SimpleFirebaseAuth().start_auth_flow("google.com", no_browser=True)

    browser_open.assert_not_called()
    assert tokens["id_token"] == "id-token"
    assert tokens["uid"] == "firebase-uid"
    payload = post.call_args.kwargs["json"]
    assert payload["postBody"] == QUERY
    assert payload["requestUri"] == REDIRECT
    assert payload["sessionId"] == "session-1"
    out = capsys.readouterr().out
    assert "https://accounts.google.com/auth?x=1" in out
    assert "paste it here" in out


def test_failed_exchange_after_paste_hints_at_truncation(stdin_pipe):
    stdin_pipe.write(f"{REDIRECT}?{QUERY}\n")
    stdin_pipe.flush()

    class StubServer(FakeServer):
        def start(self):
            return self.port

        def stop(self):
            pass

    rejected = mock.Mock()
    rejected.raise_for_status.side_effect = fb.requests.exceptions.HTTPError("400 Client Error")
    with mock.patch.object(fb, "OAuthCallbackServer", StubServer), \
         mock.patch.object(SimpleFirebaseAuth, "_create_auth_uri",
                           return_value=("session-1", "https://accounts.google.com/auth?x=1")), \
         mock.patch.object(fb.requests, "post", return_value=rejected):
        with pytest.raises(FirebaseAuthError, match="may have been cut short"):
            SimpleFirebaseAuth().start_auth_flow("google.com", no_browser=True)


def test_ssh_without_display_does_not_open_browser(stdin_pipe, monkeypatch):
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.1 5000 10.0.0.2 22")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    stdin_pipe.write(f"{REDIRECT}?{QUERY}\n")
    stdin_pipe.flush()

    class StubServer(FakeServer):
        def start(self):
            return self.port

        def stop(self):
            pass

    with mock.patch.object(fb, "OAuthCallbackServer", StubServer), \
         mock.patch.object(SimpleFirebaseAuth, "_create_auth_uri",
                           return_value=("session-1", "https://accounts.google.com/auth?x=1")), \
         mock.patch.object(fb.webbrowser, "open") as browser_open, \
         mock.patch.object(fb.requests, "post", return_value=_signin_response()):
        SimpleFirebaseAuth().start_auth_flow("google.com", no_browser=False)

    browser_open.assert_not_called()


def test_ssh_with_forwarded_display_still_opens_browser(stdin_pipe, monkeypatch):
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.1 5000 10.0.0.2 22")
    monkeypatch.setenv("DISPLAY", "localhost:10.0")

    class StubServer(FakeServer):
        def start(self):
            return self.port

        def stop(self):
            pass

    server = StubServer(result=(True, f"/callback?{QUERY}", None))
    with mock.patch.object(fb, "OAuthCallbackServer", return_value=server), \
         mock.patch.object(SimpleFirebaseAuth, "_create_auth_uri",
                           return_value=("session-1", "https://accounts.google.com/auth?x=1")), \
         mock.patch.object(fb.webbrowser, "open", return_value=True) as browser_open, \
         mock.patch.object(fb.requests, "post", return_value=_signin_response()):
        SimpleFirebaseAuth().start_auth_flow("google.com", no_browser=False)

    browser_open.assert_called_once()


def test_real_callback_server_works_while_waiting_for_paste(stdin_pipe):
    """A browser hitting the local server (or a forwarded port) still completes the login."""
    class EphemeralPortServer(OAuthCallbackServer):
        # The real server only uses 8085-8089; don't depend on those being free.
        def find_free_port(self):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("localhost", 0))
                return s.getsockname()[1]

    server = EphemeralPortServer(timeout=10)
    port = server.start()
    try:
        auth = _auth_with(server)
        url = f"http://localhost:{port}/callback?{QUERY}"
        t = threading.Thread(target=lambda: urllib.request.urlopen(url, timeout=5).read())
        t.start()
        path = auth._wait_for_redirect(True, f"http://localhost:{port}/callback")
        t.join(timeout=5)
    finally:
        server.stop()

    assert path == f"/callback?{QUERY}"
