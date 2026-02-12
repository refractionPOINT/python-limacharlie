"""Spout (streaming pull) SDK for LimaCharlie v2."""

from __future__ import annotations

import json
import threading
import time
from queue import Queue, Empty
from typing import Any, TYPE_CHECKING

import requests

from ..errors import ValidationError, ApiError

if TYPE_CHECKING:
    from .organization import Organization

_CLOUD_KEEP_ALIVES = 60
_TIMEOUT_SEC = (_CLOUD_KEEP_ALIVES * 2) + 1
_STREAM_URL = "https://stream-tmp.limacharlie.io"
_VALID_DATA_TYPES = ("event", "detect", "audit", "deployment", "billing")


class Spout:
    """Pull-mode streaming listener for events, detections, or audit logs.

    Connects to stream.limacharlie.io via HTTP POST and receives a
    continuous stream of newline-delimited JSON records.

    Usage:
        spout = Spout(org, "event", tag="my-tag")
        try:
            while True:
                data = spout.get(timeout=5)
                if data is not None:
                    process(data)
        finally:
            spout.shutdown()
    """

    def __init__(self, org: Organization, data_type: str, is_parse: bool = True,
                 max_buffer: int = 1024, inv_id: str | None = None, tag: str | None = None,
                 cat: str | None = None, sid: str | None = None,
                 extra_params: dict[str, str] | None = None) -> None:
        """Connect to limacharlie.io to start receiving streaming data.

        Args:
            org: Organization SDK object (has oid, client with api_key/jwt).
            data_type: Type of data to stream: event, detect, audit, deployment, billing.
            is_parse: If True (default), parse each line as JSON.
            max_buffer: Maximum number of messages to buffer in queue.
            inv_id: Only receive events with this investigation ID.
            tag: Only receive events from sensors with this tag.
            cat: Only receive detections of this category.
            sid: Only receive events/detections from this sensor.
            extra_params: Additional parameters for the spout request.
        """
        if data_type not in _VALID_DATA_TYPES:
            raise ValidationError(f"Invalid data type: {data_type}. Must be one of {_VALID_DATA_TYPES}")

        self._org = org
        self._oid = org.oid
        self._data_type = data_type
        self._is_parse = is_parse
        self._max_buffer = max_buffer
        self._dropped = 0
        self._is_stop = False

        # Build spout parameters.
        self._spout_params: dict[str, str] = {"type": self._data_type}
        if hasattr(org, 'client') and org.client._api_key:
            self._spout_params["api_key"] = org.client._api_key
        elif hasattr(org, 'client') and org.client._jwt:
            self._spout_params["jwt"] = org.client._jwt
        if inv_id is not None:
            self._spout_params["inv_id"] = inv_id
        if tag is not None:
            self._spout_params["tag"] = tag
        if cat is not None:
            self._spout_params["cat"] = cat
        if sid is not None:
            self._spout_params["sid"] = sid
        if hasattr(org, 'client') and org.client._uid:
            self._spout_params["uid"] = org.client._uid
        if extra_params:
            self._spout_params.update(extra_params)

        self.queue: Queue[Any] = Queue(maxsize=self._max_buffer)
        self._threads: list[threading.Thread] = []

        # Connect to stream.
        self._conn = self._get_stream()
        if self._conn.status_code != 200:
            raise ApiError(f"Failed to open spout ({self._conn.status_code}): {self._conn.text}")

        t = threading.Thread(target=self._handle_connection, daemon=True)
        self._threads.append(t)
        t.start()

    def _get_stream(self) -> requests.Response:
        return requests.post(
            f"{_STREAM_URL}/{self._oid}",
            data=self._spout_params,
            stream=True,
            allow_redirects=False,
            timeout=_TIMEOUT_SEC,
        )

    def shutdown(self) -> None:
        """Stop receiving data and clean up."""
        if self._is_stop:
            return
        self._is_stop = True
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None
        for t in self._threads:
            t.join(timeout=2)

    def get(self, timeout: int = 1) -> Any | None:
        """Get next message from the queue.

        Args:
            timeout: Seconds to wait for a message.

        Returns:
            The next message, or None if timeout expired.
        """
        try:
            return self.queue.get(timeout=timeout)
        except Empty:
            return None

    @property
    def dropped(self) -> int:
        """Number of messages dropped because the queue was full."""
        return self._dropped

    def reset_dropped(self) -> None:
        """Reset the dropped message counter."""
        self._dropped = 0

    @property
    def is_running(self) -> bool:
        """Whether the spout is still running."""
        return not self._is_stop

    def _handle_connection(self) -> None:
        while not self._is_stop:
            try:
                for line in self._conn.iter_lines(chunk_size=1024 * 1024 * 10):
                    if self._is_stop:
                        break
                    try:
                        if self._is_parse:
                            parsed = json.loads(line.decode())
                            if "__trace" in parsed:
                                if parsed["__trace"] == "dropped":
                                    self._dropped += int(parsed.get("n", 0))
                                continue
                            self.queue.put_nowait(parsed)
                        else:
                            self.queue.put_nowait(line)
                    except Exception:
                        self._dropped += 1
            except Exception:
                if self._is_stop:
                    break

            # Reconnect if not stopped.
            if not self._is_stop:
                try:
                    self._conn = self._get_stream()
                except Exception:
                    if not self._is_stop:
                        time.sleep(5)
