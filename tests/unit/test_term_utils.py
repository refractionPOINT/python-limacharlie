import os
import sys
import json
import pytest

from limacharlie.term_utils import useColors, prettyFormatDict

# -------------------------------
# Tests for the useColors function
# -------------------------------

def test_useColors_no_tty(monkeypatch):
    """Test that useColors returns False when sys.stdout is not a tty."""
    class DummyStdout:
        def isatty(self):
            return False

    monkeypatch.setattr(sys, 'stdout', DummyStdout())
    # Ensure NO_COLOR is not set and TERM is a regular terminal.
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    assert useColors() is False

def test_useColors_no_color_env(monkeypatch):
    """Test that useColors returns False when NO_COLOR is set, even if stdout is a tty."""
    class DummyStdout:
        def isatty(self):
            return True

    monkeypatch.setattr(sys, 'stdout', DummyStdout())
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "xterm")
    assert useColors() is False

def test_useColors_term_dumb(monkeypatch):
    """Test that useColors returns False when TERM is 'dumb'."""
    class DummyStdout:
        def isatty(self):
            return True

    monkeypatch.setattr(sys, 'stdout', DummyStdout())
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    assert useColors() is False

def test_useColors_true(monkeypatch):
    """Test that useColors returns True when conditions are met."""
    class DummyStdout:
        def isatty(self):
            return True

    monkeypatch.setattr(sys, 'stdout', DummyStdout())
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    assert useColors() is True

# -------------------------------
# Tests for the prettyFormatDict function
# -------------------------------

def test_prettyFormatDict_no_colors():
    """
    When use_colors is explicitly False, prettyFormatDict should return the JSON string
    exactly as produced by json.dumps with sorted keys and proper indenting.
    """
    data = {"b": 1, "a": 2}
    result = prettyFormatDict(data, use_colors=False, indent=2)
    expected = json.dumps(data, indent=2, sort_keys=True)
    assert result == expected

def test_prettyFormatDict_with_colors():
    """
    When use_colors is True, prettyFormatDict should return a string that includes ANSI escape sequences.
    We check for common ANSI escape codes (e.g., "\x1b[") in the result.
    """
    data = {"b": 1, "a": 2}
    result = prettyFormatDict(data, use_colors=True, indent=2)
    assert "\x1b[" in result

def test_prettyFormatDict_default_use_colors(monkeypatch):
    """
    When use_colors is None, prettyFormatDict should fall back to useColors().
    Here we simulate an environment that forces useColors() to return True.
    """
    class DummyStdout:
        def isatty(self):
            return True

    monkeypatch.setattr(sys, 'stdout', DummyStdout())
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")

    data = {"b": 1, "a": 2}
    result = prettyFormatDict(data, use_colors=None, indent=2)
    # Since useColors() would be True in this controlled env, ANSI codes should be present.
    assert "\x1b[" in result

def test_prettyFormatDict_empty_dict():
    """
    Test prettyFormatDict with an empty dictionary.
    """
    data = {}
    result = prettyFormatDict(data, use_colors=False, indent=2)
    expected = json.dumps(data, indent=2, sort_keys=True)
    assert result == expected