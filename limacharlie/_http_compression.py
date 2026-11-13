"""Compressed HTTP response bodies for the API client.

The API client (:class:`limacharlie.client.Client`) asks the server for a
compressed response body and decodes it here, so every caller sees the same
bytes, text and parsed JSON it would see for an uncompressed response. Large
JSON responses such as search result pages are several times smaller on the
wire compressed.

Contract:

- :data:`ACCEPT_ENCODING` is the ``Accept-Encoding`` request header value:
  ``"zstd, gzip"`` when a Zstandard decoder is importable, else ``"gzip"``.
  The Zstandard decoder is the standard library's ``compression.zstd``
  (Python 3.14+) or, before that, the optional ``zstandard`` package when it
  is already installed. gzip uses the standard library and is always
  available. No package is required beyond the standard library.
- :func:`read_body` reads a whole response body and removes every content
  coding the response's ``Content-Encoding`` names, last-applied first
  (RFC 9110, section 8.4). Coding names are case-insensitive; ``x-gzip`` is
  gzip; ``identity`` is a no-op. With no coding left to remove the body is
  returned exactly as ``fp.read()`` returns it. An empty body is empty
  whatever coding it is labelled with.
- Decoding follows the response's ``Content-Encoding`` alone, never what was
  requested: a response that arrives compressed is decoded even when the
  client did not ask for compression.

Errors (:class:`limacharlie.errors.ResponseDecodeError`):

- A coding this module cannot decode (``br``, ``deflate``, ``compress``, or
  ``zstd`` with no decoder available). The client never asks for one of
  those, so receiving one means something between the client and the server
  re-encoded the response. It is reported by name rather than guessed at.
- A truncated or corrupt stream: a missing end-of-stream marker, a bad
  checksum, or trailing bytes that are not another compressed member or
  frame. A partially decoded body is never returned. This includes a
  connection that closes early: urllib's sized reads return a short body
  silently in that case, so a cut inside a member or frame is caught by the
  stream's own end marker, and a cut exactly between members or frames by
  the response's unmet ``Content-Length``.

Transport errors raised while reading (a timeout, a reset connection, a
chunked body cut mid-chunk) are not decode errors and pass through unchanged,
exactly as they do for an uncompressed read.

Performance: the body is decoded while it streams in, in
:data:`_DECODE_CHUNK` steps, into a single growing buffer whose bytes are
returned without a final copy. The compressed body is never held in full.
Peak memory is the decoded body plus the decoder's state and one chunk, which
is about what an uncompressed read of the same body holds.
"""

from __future__ import annotations

import gzip
import io
import shutil
import zlib
from typing import IO, Any, Callable, Iterable, NamedTuple

from .errors import ResponseDecodeError

# Read and decode in steps of this many bytes.
_DECODE_CHUNK = 256 * 1024

# Compressed bytes fed to the zstandard package's decoder per step. Its
# decompressobj has no output limit, so this bounds the decoded bytes one
# step can produce for any realistic ratio.
_ZSTANDARD_INPUT_CHUNK = 64 * 1024

_TRUNCATED = "Compressed file ended before the end-of-stream marker was reached"


def _gzip_reader(fp: IO[bytes]) -> IO[bytes]:
    # GzipFile handles multi-member streams and trailing zero padding, verifies
    # each member's CRC-32 and length, and raises EOFError on a truncated one.
    return gzip.GzipFile(fileobj=fp, mode="rb")


_DECODERS: dict[str, Callable[[IO[bytes]], IO[bytes]]] = {
    "gzip": _gzip_reader,
    "x-gzip": _gzip_reader,
}

_DECODE_ERRORS: tuple[type[BaseException], ...] = (EOFError, gzip.BadGzipFile, zlib.error)

#: Which Zstandard decoder is in use: "compression.zstd", "zstandard" or None.
ZSTD_BACKEND: str | None = None

try:  # Python 3.14+
    from compression import zstd as _stdlib_zstd
except ImportError:
    _stdlib_zstd = None  # type: ignore[assignment]

if _stdlib_zstd is not None:

    def _stdlib_zstd_reader(fp: IO[bytes]) -> IO[bytes]:
        # ZstdFile reads across frames, skips skippable frames and raises
        # EOFError on a truncated frame.
        return _stdlib_zstd.ZstdFile(fp, mode="rb")

    _DECODERS["zstd"] = _stdlib_zstd_reader
    _DECODE_ERRORS = _DECODE_ERRORS + (_stdlib_zstd.ZstdError,)
    ZSTD_BACKEND = "compression.zstd"
else:
    try:
        import zstandard as _zstandard
    except ImportError:
        _zstandard = None  # type: ignore[assignment]
    # decompressobj().eof is what detects a truncated frame; versions without
    # it are not used.
    if _zstandard is not None and hasattr(_zstandard.ZstdDecompressor().decompressobj(), "eof"):

        class _ZstandardReader:
            """Read-only file that decodes a zstd stream with the zstandard package.

            This is a frame loop written here, not a library reader: the
            package's own ``stream_reader`` returns a truncated frame's prefix
            as if it were the whole body, with no error, and the standard
            library decoder needs Python 3.14. The loop feeds input to one
            ``decompressobj`` per frame (which also consumes skippable
            frames), starts the next frame from the previous one's
            ``unused_data``, and raises EOFError when the input ends inside a
            frame. Corrupt input and trailing garbage raise
            ``zstandard.ZstdError`` from the decoder itself.
            """

            def __init__(self, fp: IO[bytes]) -> None:
                self._fp = fp
                self._dctx = _zstandard.ZstdDecompressor()
                self._obj = self._dctx.decompressobj()
                self._in_frame = False
                self._pending = bytearray()
                self._done = False

            def _feed(self, data: bytes) -> None:
                while data:
                    self._in_frame = True
                    self._pending += self._obj.decompress(data)
                    if not self._obj.eof:
                        return
                    data = self._obj.unused_data
                    self._obj = self._dctx.decompressobj()
                    self._in_frame = False

            def read(self, size: int = -1) -> bytes:
                while not self._done and (size < 0 or len(self._pending) < size):
                    data = self._fp.read(_ZSTANDARD_INPUT_CHUNK)
                    if not data:
                        if self._in_frame:
                            raise EOFError(_TRUNCATED)
                        self._done = True
                        break
                    self._feed(data)
                if size < 0 or size >= len(self._pending):
                    out = bytes(self._pending)
                    self._pending.clear()
                else:
                    out = bytes(self._pending[:size])
                    del self._pending[:size]
                return out

        _DECODERS["zstd"] = _ZstandardReader  # type: ignore[assignment]
        _DECODE_ERRORS = _DECODE_ERRORS + (_zstandard.ZstdError,)
        ZSTD_BACKEND = "zstandard"

#: The ``Accept-Encoding`` value the client sends: the codings this module can
#: decode, preferred first. ``x-gzip`` is accepted on responses but not asked for.
ACCEPT_ENCODING = "zstd, gzip" if "zstd" in _DECODERS else "gzip"


class DecodedBody(NamedTuple):
    """A response body after content decoding."""

    body: bytes
    """The decoded body."""
    wire_bytes: int | None
    """Bytes read from the connection when a coding was removed, else None."""
    encoding: str
    """The codings removed, as the response named them (lowercase), or ''."""


class _CountingReader:
    """Read-only file wrapper that counts the bytes read through it.

    ``is_empty()`` reads ahead one chunk to tell an empty body from a
    non-empty one; that chunk is returned by the next ``read``.
    """

    def __init__(self, fp: IO[bytes]) -> None:
        self._fp = fp
        self._head = b""
        self.count = 0

    def is_empty(self) -> bool:
        self._head = self._fp.read(_DECODE_CHUNK)
        self.count += len(self._head)
        return not self._head

    def read(self, size: int = -1) -> bytes:
        if self._head:
            if size < 0 or size >= len(self._head):
                head, self._head = self._head, b""
                if size < 0:
                    rest = self._fp.read()
                    self.count += len(rest)
                    return head + rest
                return head
            head, self._head = self._head[:size], self._head[size:]
            return head
        data = self._fp.read(size)
        self.count += len(data)
        return data


def content_codings(header_items: Iterable[tuple[str, str]]) -> list[str]:
    """Return the content codings named by every ``Content-Encoding`` header.

    Header names match case-insensitively and several header lines combine in
    order, as RFC 9110 allows. Codings are lowercased; ``identity`` and empty
    list elements are dropped, so an uncompressed response gives ``[]``.
    """
    codings: list[str] = []
    for name, value in header_items:
        if not isinstance(name, str) or name.lower() != "content-encoding":
            continue
        for part in str(value).split(","):
            coding = part.strip().lower()
            if coding and coding != "identity":
                codings.append(coding)
    return codings


def read_body(fp: Any, codings: list[str]) -> DecodedBody:
    """Read the whole body from *fp* and remove *codings* from it.

    Args:
        fp: The response, or anything with ``read()``; an
            ``http.client.HTTPResponse`` or a ``urllib.error.HTTPError``.
        codings: The response's content codings in the order they were
            applied, as :func:`content_codings` returns them.

    Returns:
        The decoded body, with the wire size when a coding was removed.

    Raises:
        ResponseDecodeError: A coding is not supported, or the stream is
            truncated or corrupt.
    """
    if not codings:
        return DecodedBody(fp.read(), None, "")

    label = ", ".join(codings)
    for coding in codings:
        if coding not in _DECODERS:
            raise ResponseDecodeError(
                f"The server sent a response with Content-Encoding {label!r}; "
                f"this client decodes only {', '.join(sorted(_DECODERS))}.",
                encoding=label,
            )

    counter = _CountingReader(fp)
    if counter.is_empty():
        return DecodedBody(b"", 0, label)
    reader: IO[bytes] = counter  # type: ignore[assignment]
    for coding in reversed(codings):
        reader = _DECODERS[coding](reader)
    out = io.BytesIO()
    try:
        shutil.copyfileobj(reader, out, _DECODE_CHUNK)
    except _DECODE_ERRORS as exc:
        raise ResponseDecodeError(
            f"Failed to decode the {label} response body after "
            f"{counter.count} compressed bytes: {exc}",
            encoding=label,
        ) from exc
    # A connection that closes early exactly at a gzip member or zstd frame
    # boundary looks like a clean end to the decoder. http.client still holds
    # the Content-Length shortfall; an uncompressed read raises IncompleteRead.
    remaining = getattr(fp, "length", None)
    if isinstance(remaining, int) and remaining > 0:
        raise ResponseDecodeError(
            f"The {label} response body ended {remaining} bytes short of its "
            f"Content-Length after {counter.count} compressed bytes.",
            encoding=label,
        )
    return DecodedBody(out.getvalue(), counter.count, label)
