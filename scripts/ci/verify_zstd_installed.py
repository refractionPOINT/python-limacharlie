"""Verify zstandard is installed and importable."""

import zstandard

print(f"zstandard {zstandard.__version__} OK")
