"""Firehose (streaming push) SDK for LimaCharlie v2."""

import json
import os
import socket
import ssl
import tempfile
import threading
import traceback
from queue import Queue, Empty
from urllib.request import urlopen

from ..errors import ValidationError, ApiError

_VALID_DATA_TYPES = ("event", "detect", "audit")


class Firehose:
    """Push-mode streaming listener for events, detections, or audit logs.

    Creates a TLS server that limacharlie.io connects to and pushes data.
    Optionally auto-registers the output in limacharlie.io.

    Usage:
        fh = Firehose(org, "0.0.0.0:4444", "event", name="my-firehose")
        try:
            while True:
                data = fh.get(timeout=5)
                if data is not None:
                    process(data)
        finally:
            fh.shutdown()
    """

    def __init__(self, org, listen_on, data_type, public_dest=None, name=None,
                 ssl_cert=None, ssl_key=None, is_parse=True, max_buffer=1024,
                 inv_id=None, tag=None, cat=None, sid=None,
                 is_delete_on_failure=False, on_dropped=None):
        """Create a firehose listener.

        Args:
            org: Organization SDK object.
            listen_on: Interface:port to listen on (e.g., "0.0.0.0:443").
            data_type: Type of data: event, detect, audit.
            public_dest: Public IP:port for LC to connect to (auto-detected if None).
            name: Name to register as an Output (if None, assumes output exists).
            ssl_cert: Path to PEM SSL certificate file.
            ssl_key: Path to PEM SSL key file.
            is_parse: If True, parse data as JSON.
            max_buffer: Max messages to buffer in queue.
            inv_id: Only receive events with this investigation ID.
            tag: Only receive events from sensors with this tag.
            cat: Only receive detections of this category.
            sid: Only receive events/detections from this sensor.
            is_delete_on_failure: Delete the output in LC on failure.
            on_dropped: Callback for dropped messages.
        """
        if data_type not in _VALID_DATA_TYPES:
            raise ValidationError(f"Invalid data type: {data_type}. Must be one of {_VALID_DATA_TYPES}")

        self._org = org
        self._keep_running = True
        self._data_type = data_type
        self._name = name
        self._output_name = None
        self._is_parse = is_parse
        self._max_buffer = max_buffer
        self._dropped = 0
        self._on_dropped = on_dropped
        self._is_delete_on_failure = is_delete_on_failure

        # Parse listen address.
        parts = listen_on.split(":")
        if len(parts) > 1:
            self._listen_host = parts[0] or "0.0.0.0"
            self._listen_port = int(parts[1])
        else:
            self._listen_host = parts[0] or "0.0.0.0"
            self._listen_port = 443

        self._public_dest = public_dest if public_dest else None

        # Validate SSL paths.
        self._ssl_cert = ssl_cert
        self._ssl_key = ssl_key
        if self._ssl_cert and not os.path.isfile(self._ssl_cert):
            raise ValidationError(f"No cert file at path: {self._ssl_cert}")
        if self._ssl_key and not os.path.isfile(self._ssl_key):
            raise ValidationError(f"No key file at path: {self._ssl_key}")

        self.queue = Queue(maxsize=self._max_buffer)

        # Generate self-signed certs if none provided.
        if self._ssl_cert is None or self._ssl_key is None:
            _, tmp_key = tempfile.mkstemp()
            _, tmp_cert = tempfile.mkstemp()
            ret = os.system(
                f'openssl req -x509 -days 36500 -newkey rsa:4096 '
                f'-keyout {tmp_key} -out {tmp_cert} -nodes -sha256 '
                f'-subj "/C=US/ST=CA/L=Mountain View/O=refractionPOINT/CN=limacharlie_firehose" '
                f'> /dev/null 2>&1'
            )
            if ret != 0:
                raise ApiError("Failed to generate self-signed certificate.")
            use_key = tmp_key
            use_cert = tmp_cert
        else:
            use_key = self._ssl_key
            use_cert = self._ssl_cert

        # Start TLS server.
        self._ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._ssl_ctx.load_cert_chain(certfile=use_cert, keyfile=use_key)
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self._listen_host, self._listen_port))
        self._server_sock.listen(5)
        self._server_sock.settimeout(2)

        self._server_thread = threading.Thread(target=self._server_loop, daemon=True)
        self._server_thread.start()

        # Register output if name is specified.
        if self._name is not None:
            self._output_name = f"tmp_live_{self._name}"
            from .outputs import Outputs
            outputs_sdk = Outputs(org)
            existing = outputs_sdk.list()
            if self._output_name not in existing:
                effective_dest = self._public_dest
                if effective_dest is None:
                    effective_dest = f"{self._get_public_ip()}:{self._listen_port}"
                is_strict = "true" if (self._ssl_cert and self._ssl_key) else "false"
                output_config = {
                    "dest_host": effective_dest,
                    "is_tls": "true",
                    "is_strict_tls": is_strict,
                    "is_no_header": "true",
                }
                if inv_id is not None:
                    output_config["inv_id"] = inv_id
                if tag is not None:
                    output_config["tag"] = tag
                if cat is not None:
                    output_config["cat"] = cat
                if sid is not None:
                    output_config["sid"] = sid
                if self._is_delete_on_failure:
                    output_config["is_delete_on_failure"] = "true"
                outputs_sdk.create(self._output_name, "syslog", self._data_type, **output_config)

    def shutdown(self):
        """Stop receiving data and unregister the output if created."""
        if not self._keep_running:
            return
        self._keep_running = False
        try:
            if self._name is not None and self._output_name is not None:
                from .outputs import Outputs
                try:
                    Outputs(self._org).delete(self._output_name)
                except Exception:
                    pass
        finally:
            try:
                self._server_sock.close()
            except Exception:
                pass

    def get(self, timeout=1):
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
    def dropped(self):
        """Number of messages dropped because the queue was full."""
        return self._dropped

    def reset_dropped(self):
        """Reset the dropped message counter."""
        self._dropped = 0

    @property
    def is_running(self):
        """Whether the firehose is still running."""
        return self._keep_running

    def _get_public_ip(self):
        return json.load(urlopen("http://jsonip.com"))["ip"]

    def _server_loop(self):
        while self._keep_running:
            try:
                conn, addr = self._server_sock.accept()
                t = threading.Thread(target=self._handle_client, args=(conn, addr), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except Exception:
                if self._keep_running:
                    continue
                break

    def _handle_client(self, sock, address):
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock = self._ssl_ctx.wrap_socket(
                sock, server_side=True,
                do_handshake_on_connect=True,
                suppress_ragged_eofs=True,
            )
        except Exception:
            return

        cur_data = []
        while self._keep_running:
            try:
                data = sock.recv(512 * 1024)
                if not data:
                    break

                chunks = data.split(b"\n")
                if len(chunks) == 1:
                    cur_data.append(chunks[0])
                    continue

                for chunk in chunks:
                    cur_data.append(chunk)
                    buf = b"".join(cur_data)
                    cur_data = []
                    if not buf:
                        continue
                    try:
                        if self._is_parse:
                            self.queue.put_nowait(json.loads(buf))
                        else:
                            self.queue.put_nowait(buf)
                    except Exception:
                        self._dropped += 1
                        if self._on_dropped is not None:
                            try:
                                if self._is_parse:
                                    self._on_dropped(json.loads(buf))
                                else:
                                    self._on_dropped(buf)
                            except Exception:
                                pass
            except Exception:
                break

        try:
            sock.close()
        except Exception:
            pass
