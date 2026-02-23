"""Verify zstandard is NOT importable (used after pip uninstall)."""

try:
    import zstandard

    raise AssertionError("zstandard should not be importable")
except ImportError:
    print("zstandard correctly unavailable")
