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

- A body that decodes to more than the decoded-size limit (default
  :data:`DEFAULT_MAX_DECODED_BYTES`, 1 GiB). The limit is enforced while
  decoding, so a stream with an extreme compression ratio is stopped after
  at most the limit plus one step of output, never inflated in full. Bodies
  that arrive uncompressed are not limited, exactly as before.

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
import os
import shutil
import warnings
import zlib
from typing import IO, Any, Callable, Iterable, NamedTuple

from .errors import ResponseDecodeError

# Read and decode in steps of this many bytes.
_DECODE_CHUNK = 256 * 1024

# Compressed bytes fed to the zstandard package's decoder per step, at most.
_ZSTANDARD_INPUT_CHUNK = 64 * 1024

# Upper bound on the decoded bytes one compressed zstd byte can produce. The
# densest zstd input is an RLE block: a 3-byte header plus 1 byte that
# expands to a full 128 KiB block, 32,768x; 65,536 leaves headroom. The
# zstandard package's decompressobj has no output limit, so its input is fed
# in pieces small enough that one piece cannot overshoot the decoded-size
# limit by more than about 1 MiB.
_ZSTD_MAX_EXPANSION = 1 << 16
_ZSTANDARD_MIN_INPUT = 16

#: Default limit on a compressed response's decoded size, in bytes (1 GiB).
#: The largest responses that pass through this decoder are search result
#: pages, which decode to at most a few hundred megabytes; everything else
#: (listings, CSV exports, single records) is smaller or paged, and bulk
#: downloads use signed URLs that are never decoded here. 1 GiB leaves a wide
#: margin above all of them while stopping a stream with an extreme
#: compression ratio, a few kilobytes on the wire, from exhausting memory.
DEFAULT_MAX_DECODED_BYTES = 1024 ** 3

#: Environment variable that overrides :data:`DEFAULT_MAX_DECODED_BYTES`.
ENV_MAX_DECODED_BYTES = "LC_MAX_DECODED_RESPONSE_BYTES"

_TRUNCATED = "Compressed file ended before the end-of-stream marker was reached"


def max_decoded_bytes_from_env() -> int | None:
    """Return the decoded-size limit from ``LC_MAX_DECODED_RESPONSE_BYTES``.

    Unset or empty gives :data:`DEFAULT_MAX_DECODED_BYTES`. An integer number
    of bytes sets the limit; 0 or a negative number removes it (``None``).
    Any other value warns and keeps the default, so a typo never removes
    the protection or stops the CLI from starting.
    """
    raw = os.environ.get(ENV_MAX_DECODED_BYTES, "").strip()
    if not raw:
        return DEFAULT_MAX_DECODED_BYTES
    try:
        value = int(raw)
    except ValueError:
        warnings.warn(
            f"{ENV_MAX_DECODED_BYTES}={raw!r} is not an integer number of bytes; "
            f"using the default limit of {DEFAULT_MAX_DECODED_BYTES} bytes.",
            stacklevel=2,
        )
        return DEFAULT_MAX_DECODED_BYTES
    return value if value > 0 else None


class _DecodedTooLarge(Exception):
    """Raised inside the decoder chain when the decoded-size limit is exceeded."""


class _LimitedReader:
    """Read-only file wrapper that fails once more than *limit* bytes are read."""

    def __init__(self, fp: IO[bytes], limit: int) -> None:
        self._fp = fp
        self._limit = limit
        self.total = 0

    def read(self, size: int = -1) -> bytes:
        data = self._fp.read(size)
        self.total += len(data)
        if self.total > self._limit:
            raise _DecodedTooLarge()
        return data


def _gzip_reader(fp: IO[bytes], limit: int | None) -> IO[bytes]:
    # GzipFile handles multi-member streams and trailing zero padding, verifies
    # each member's CRC-32 and length, and raises EOFError on a truncated one.
    # read(n) returns at most n bytes, so the limit is enforced by the caller.
    return gzip.GzipFile(fileobj=fp, mode="rb")


_DECODERS: dict[str, Callable[[IO[bytes], int | None], IO[bytes]]] = {
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

    def _stdlib_zstd_reader(fp: IO[bytes], limit: int | None) -> IO[bytes]:
        # ZstdFile reads across frames, skips skippable frames and raises
        # EOFError on a truncated frame. read(n) returns at most n bytes, so
        # the limit is enforced by the caller.
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

            ``decompressobj`` returns all the output of the input it is given,
            so with a *limit* the input is fed in pieces of at most
            (limit - decoded so far) / _ZSTD_MAX_EXPANSION bytes: one piece
            cannot inflate past the limit by more than about 1 MiB.
            """

            def __init__(self, fp: IO[bytes], limit: int | None) -> None:
                self._fp = fp
                self._limit = limit
                self._produced = 0
                self._input = b""
                self._pos = 0
                self._dctx = _zstandard.ZstdDecompressor()
                self._obj = self._dctx.decompressobj()
                self._in_frame = False
                self._pending = bytearray()
                self._done = False

            def _piece_size(self) -> int:
                if self._limit is None:
                    return _ZSTANDARD_INPUT_CHUNK
                room = (self._limit - self._produced) // _ZSTD_MAX_EXPANSION
                return max(_ZSTANDARD_MIN_INPUT, min(_ZSTANDARD_INPUT_CHUNK, room))

            def _feed(self, data: bytes) -> None:
                while data:
                    self._in_frame = True
                    out = self._obj.decompress(data)
                    self._produced += len(out)
                    if self._limit is not None and self._produced > self._limit:
                        raise _DecodedTooLarge()
                    self._pending += out
                    if not self._obj.eof:
                        return
                    data = self._obj.unused_data
                    self._obj = self._dctx.decompressobj()
                    self._in_frame = False

            def read(self, size: int = -1) -> bytes:
                while not self._done and (size < 0 or len(self._pending) < size):
                    if self._pos >= len(self._input):
                        self._input = self._fp.read(_ZSTANDARD_INPUT_CHUNK)
                        self._pos = 0
                    if not self._input:
                        if self._in_frame:
                            raise EOFError(_TRUNCATED)
                        self._done = True
                        break
                    end = self._pos + self._piece_size()
                    piece = self._input[self._pos:end] if self._pos or end < len(self._input) else self._input
                    self._pos = end
                    self._feed(piece)
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


def read_body(fp: Any, codings: list[str],
              max_decoded: int | None = DEFAULT_MAX_DECODED_BYTES) -> DecodedBody:
    """Read the whole body from *fp* and remove *codings* from it.

    Args:
        fp: The response, or anything with ``read()``; an
            ``http.client.HTTPResponse`` or a ``urllib.error.HTTPError``.
        codings: The response's content codings in the order they were
            applied, as :func:`content_codings` returns them.
        max_decoded: Most bytes any decoding step may produce, or None for
            no limit. Applies only when there is a coding to remove.

    Returns:
        The decoded body, with the wire size when a coding was removed.

    Raises:
        ResponseDecodeError: A coding is not supported, the stream is
            truncated or corrupt, or it decodes to more than *max_decoded*.
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
        reader = _DECODERS[coding](reader, max_decoded)
        if max_decoded is not None:
            # Every layer is limited, so an inner layer of stacked codings
            # cannot inflate unchecked either.
            reader = _LimitedReader(reader, max_decoded)  # type: ignore[assignment]
    out = io.BytesIO()
    try:
        shutil.copyfileobj(reader, out, _DECODE_CHUNK)
    except _DecodedTooLarge:
        raise ResponseDecodeError(
            f"The {label} response body decodes to more than {max_decoded} bytes "
            f"(stopped after {counter.count} compressed bytes), the limit set by "
            f"{ENV_MAX_DECODED_BYTES} (default {DEFAULT_MAX_DECODED_BYTES}).",
            encoding=label,
            suggestion=(
                f"If the response is legitimate, raise the limit with "
                f"{ENV_MAX_DECODED_BYTES}=<bytes> (0 removes it) or "
                f"Client(max_decoded_response_bytes=...)."
            ),
        ) from None
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
