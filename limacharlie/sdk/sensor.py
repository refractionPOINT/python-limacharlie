"""Sensor SDK class for LimaCharlie v2."""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Generator
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .organization import Organization
    from ..client import Client


class Sensor:
    """Represents a single LimaCharlie sensor.

    Provides methods for tasking, tagging, network isolation, and event queries.
    """

    PLATFORM_WINDOWS = 0x10000000
    PLATFORM_LINUX = 0x20000000
    PLATFORM_MACOS = 0x30000000
    PLATFORM_IOS = 0x40000000
    PLATFORM_ANDROID = 0x50000000
    PLATFORM_CHROMEOS = 0x60000000

    ARCH_X86 = 0x00000001
    ARCH_X64 = 0x00000002
    ARCH_ARM = 0x00000003
    ARCH_ARM64 = 0x00000004
    ARCH_ALPINE64 = 0x00000005
    ARCH_CHROME = 0x00000006

    def __init__(self, org: Organization, sid: str, info: dict[str, Any] | None = None) -> None:
        self._org = org
        self.sid = str(sid)
        self._info = info

    @property
    def client(self) -> Client:
        """The underlying API client."""
        return self._org.client

    def get_info(self) -> dict[str, Any]:
        """Get full sensor details."""
        if self._info is None:
            data = self.client.request("GET", self.sid)
            self._info = data.get("info", data)
        return self._info

    def is_online(self) -> bool:
        """Check if the sensor is currently online."""
        data = self.client.request("GET", self.sid)
        online = data.get("online", {})
        return len(online) > 0 and "error" not in online

    def wait_online(self, timeout: int) -> bool:
        """Wait for sensor to come online.

        Args:
            timeout: Seconds to wait.

        Returns:
            bool: True if online before timeout.
        """
        deadline = time.time() + timeout
        while not self.is_online():
            if time.time() >= deadline:
                return False
            time.sleep(min(60, deadline - time.time()))
        return True

    # --- Platform helpers ---

    def _get_platform(self) -> int:
        info = self.get_info()
        plat = info.get("plat", 0)
        if isinstance(plat, str):
            plat = int(plat, 16) if plat.startswith("0x") else int(plat)
        return plat & 0xF0000000

    def _get_architecture(self) -> int:
        info = self.get_info()
        arch = info.get("arch", 0)
        if isinstance(arch, str):
            arch = int(arch, 16) if arch.startswith("0x") else int(arch)
        return arch & 0x0000000F

    @property
    def is_windows(self) -> bool:
        """True if this sensor is running on Windows."""
        return self._get_platform() == self.PLATFORM_WINDOWS

    @property
    def is_linux(self) -> bool:
        """True if this sensor is running on Linux."""
        return self._get_platform() == self.PLATFORM_LINUX

    @property
    def is_macos(self) -> bool:
        """True if this sensor is running on macOS."""
        return self._get_platform() == self.PLATFORM_MACOS

    @property
    def is_chrome(self) -> bool:
        """True if this sensor is a Chrome OS sensor."""
        return self._get_architecture() == self.ARCH_CHROME

    @property
    def hostname(self) -> str:
        """The hostname reported by this sensor."""
        return self.get_info().get("hostname", "")

    # --- Tasking ---

    def task(self, tasks: str | list[str], inv_id: str | None = None) -> dict[str, Any]:
        """Send task(s) to the sensor (fire-and-forget).

        Args:
            tasks: Task command string or list of commands.
            inv_id: Optional investigation ID.

        Returns:
            dict: API response.
        """
        if isinstance(tasks, str):
            tasks = [tasks]
        params = {"tasks": tasks}
        if inv_id:
            params["investigation_id"] = inv_id
        return self.client.request("POST", self.sid, params=params)

    # --- Tags ---

    def get_tags(self) -> list[str]:
        """Get tags applied to this sensor.

        Returns:
            list: Tag strings.
        """
        resp = self.client.request("GET", f"{self.sid}/tags")
        tags_data = resp.get("tags", {})
        if isinstance(tags_data, dict):
            # V1 format: {"tags": {"<sid>": {"tag1": ..., "tag2": ...}}}
            sid_tags = tags_data.get(self.sid, {})
            if isinstance(sid_tags, dict):
                return list(sid_tags.keys())
            return list(sid_tags) if sid_tags else []
        return list(tags_data) if tags_data else []

    def add_tag(self, tag: str | list[str], ttl: int | None = None) -> dict[str, Any]:
        """Add a tag to this sensor.

        Args:
            tag: Tag string or list of tags.
            ttl: Optional TTL in seconds.

        Returns:
            dict: API response.
        """
        params = {"tags": tag}
        if ttl is not None:
            params["ttl"] = int(ttl)
        return self.client.request("POST", f"{self.sid}/tags", params=params)

    def remove_tag(self, tag: str | list[str]) -> dict[str, Any]:
        """Remove a tag from this sensor.

        Args:
            tag: Tag string or list of tags.

        Returns:
            dict: API response.
        """
        if isinstance(tag, str):
            params = {"tag": tag}
        else:
            params = {"tags": ",".join(tag)}
        return self.client.request("DELETE", f"{self.sid}/tags", params=params)

    # --- Network isolation ---

    def is_isolated(self) -> bool:
        """Check if sensor is isolated from the network."""
        # Network isolation is ephemeral, always refresh
        self._info = None
        info = self.get_info()
        return info.get("should_isolate", False)

    def isolate(self) -> dict[str, Any]:
        """Isolate sensor from the network.

        Returns:
            dict: API response.
        """
        return self.client.request("POST", f"{self.sid}/isolation")

    def rejoin(self) -> dict[str, Any]:
        """Rejoin sensor to the network.

        Returns:
            dict: API response.
        """
        return self.client.request("DELETE", f"{self.sid}/isolation")

    # --- Seal ---

    def is_sealed(self) -> bool:
        """Check if sensor is sealed."""
        # Seal is ephemeral, always refresh
        self._info = None
        info = self.get_info()
        return info.get("should_seal", False)

    def seal(self) -> dict[str, Any]:
        """Seal the sensor, preventing uninstallation."""
        return self.client.request("POST", f"{self.sid}/seal")

    def unseal(self) -> dict[str, Any]:
        """Unseal the sensor, allowing uninstallation."""
        return self.client.request("DELETE", f"{self.sid}/seal")

    # --- Lifecycle ---

    def delete(self) -> dict[str, Any]:
        """Delete this sensor.

        Returns:
            dict: API response.
        """
        return self.client.request("DELETE", self.sid)

    # --- Events ---

    def get_events(self, start: int, end: int, limit: int | None = None, event_type: str | None = None, is_forward: bool = True) -> Generator[dict[str, Any], None, None]:
        """Get historical events for this sensor.

        Args:
            start: Start time (unix seconds).
            end: End time (unix seconds).
            limit: Max events.
            event_type: Filter by event type.
            is_forward: Chronological order (default True).

        Yields:
            dict: Event records.
        """
        cursor = "-"
        n_returned = 0
        while cursor:
            qp = {
                "start": str(int(start)),
                "end": str(int(end)),
                "is_compressed": "true",
                "is_forward": "true" if is_forward else "false",
                "cursor": cursor,
            }
            if limit is not None:
                qp["limit"] = str(limit)
            if event_type:
                qp["event_type"] = event_type

            resp = self.client.request("GET", f"insight/{self._org.oid}/{self.sid}", query_params=qp)
            cursor = resp.get("next_cursor")
            for evt in self.client.unwrap(resp.get("events", "")):
                yield evt
                n_returned += 1
                if limit is not None and n_returned >= limit:
                    return
            if limit is not None and n_returned >= limit:
                return

    def get_overview(self, start: int, end: int) -> list[Any]:
        """Get event overview (timeline) for this sensor.

        Args:
            start: Start time (unix seconds).
            end: End time (unix seconds).

        Returns:
            list: Overview timestamps.
        """
        data = self.client.request("GET", f"insight/{self._org.oid}/{self.sid}/overview",
                                   query_params={"start": str(start), "end": str(end)})
        return data.get("overview", data)

    def get_event_by_atom(self, atom: str) -> dict[str, Any]:
        """Get an event by its atom.

        Args:
            atom: Event atom identifier.

        Returns:
            dict: Event data.
        """
        return self.client.request("GET", f"insight/{self._org.oid}/{self.sid}/{atom}")

    def get_children_events(self, atom: str) -> list[dict[str, Any]]:
        """Get child events of an atom.

        Args:
            atom: Parent event atom.

        Returns:
            list: Child events.
        """
        data = self.client.request("GET", f"insight/{self._org.oid}/{self.sid}/{atom}/children",
                                   query_params={"is_compressed": "true"})
        return self.client.unwrap(data.get("events", ""))

    def get_event_retention(self, start: int, end: int, is_detailed: bool = False) -> dict[str, Any]:
        """Get event retention statistics.

        Args:
            start: Start time (unix seconds).
            end: End time (unix seconds).
            is_detailed: Include detailed breakdown.

        Returns:
            dict: Retention statistics.
        """
        qp = {"start": str(start), "end": str(end)}
        if is_detailed:
            qp["is_detailed"] = "true"
        return self.client.request("GET", f"insight/event_count/{self._org.oid}/{self.sid}",
                                   query_params=qp)
