"""Microbenchmarks for decoding compressed API response bodies.

Measures ``limacharlie._http_compression.read_body`` on a synthetic
search-result page (about 8 MB of event rows), read from memory so only the
decode is timed: identity (a plain read, the floor), gzip, and zstd with
whichever decoder this Python has.

Run with timing:

    pytest tests/microbenchmarks/test_response_compression_microbenchmark.py --benchmark-enable --benchmark-only

In the default suite (``--benchmark-disable``) each benchmark runs once as a
correctness check: the decoded body must equal the original page.

Last measured (6.7 MB page; 1.31 MB gzip, 1.29 MB zstd; Linux x86-64, median
of the pytest-benchmark rounds, min in brackets):

    Python 3.11 (zstd via the zstandard package)
      gzip   14.1 ms  [13.0 ms]   ~480 MB/s decoded
      zstd    5.6 ms  [ 5.2 ms]   ~1.2 GB/s decoded
    Python 3.14 (zstd via compression.zstd)
      gzip   16.1 ms  [13.1 ms]
      zstd    5.0 ms  [ 4.5 ms]

The identity case is a zero-copy ``BytesIO.read()`` (about 0.3 us), so it
checks the pass-through path rather than giving a cost floor.
"""

import gzip
import io
import json
import random

import pytest

from limacharlie import _http_compression as hc


def _page(rows: int = 16_000) -> bytes:
    rnd = random.Random(11)
    paths = [f"C:\\Program Files\\Vendor{i}\\bin\\tool{i % 13}.exe" for i in range(80)]
    out = []
    for i in range(rows):
        p = rnd.choice(paths)
        out.append({
            "data": {
                "event": {"FILE_PATH": p, "COMMAND_LINE": f'"{p}" --mode {i % 5}',
                          "HASH": "%064x" % rnd.getrandbits(256), "PROCESS_ID": rnd.randrange(65000)},
                "routing": {"hostname": f"host-{rnd.randrange(200):04d}", "event_type": "NEW_PROCESS",
                            "event_time": 1_700_000_000_000 + i, "event_id": "%032x" % rnd.getrandbits(128)},
            },
            "ts": 1_700_000_000_000 + i,
        })
    return json.dumps({"completed": True, "results": [{"type": "events", "rows": out}]}).encode()


PAGE = _page()


def _zstd_compress(data: bytes) -> bytes | None:
    try:
        from compression import zstd
        return zstd.compress(data)
    except ImportError:
        pass
    try:
        import zstandard
        return zstandard.ZstdCompressor().compress(data)
    except ImportError:
        return None


@pytest.mark.parametrize("coding", ["identity", "gzip", "zstd"])
def test_read_body(benchmark, coding):
    if coding == "identity":
        wire, codings = PAGE, []
    elif coding == "gzip":
        wire, codings = gzip.compress(PAGE), ["gzip"]
    else:
        if hc.ZSTD_BACKEND is None:
            pytest.skip("no zstd decoder on this Python")
        wire, codings = _zstd_compress(PAGE), ["zstd"]
    result = benchmark(lambda: hc.read_body(io.BytesIO(wire), codings))
    assert result.body == PAGE
