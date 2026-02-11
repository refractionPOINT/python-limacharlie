"""Sensor SDK class for LimaCharlie v2."""

import json
import time
import uuid


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

    def __init__(self, org, sid, info=None):
        self._org = org
        self.sid = str(sid)
        self._info = info

    @property
    def client(self):
        return self._org.client

    def get_info(self):
        """Get full sensor details."""
        if self._info is None:
            self._info = self.client.request("GET", self.sid)
        return self._info

    def is_online(self):
        """Check if the sensor is currently online."""
        info = self.client.request("GET", self.sid)
        return info.get("is_online", info.get("alive", False))

    def wait_online(self, timeout):
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

    def _get_platform(self):
        info = self.get_info()
        plat = info.get("plat", 0)
        if isinstance(plat, str):
            plat = int(plat, 16) if plat.startswith("0x") else int(plat)
        return plat & 0xF0000000

    def _get_architecture(self):
        info = self.get_info()
        arch = info.get("arch", 0)
        if isinstance(arch, str):
            arch = int(arch, 16) if arch.startswith("0x") else int(arch)
        return arch & 0x0000000F

    @property
    def is_windows(self):
        return self._get_platform() == self.PLATFORM_WINDOWS

    @property
    def is_linux(self):
        return self._get_platform() == self.PLATFORM_LINUX

    @property
    def is_macos(self):
        return self._get_platform() == self.PLATFORM_MACOS

    @property
    def is_chrome(self):
        return self._get_architecture() == self.ARCH_CHROME

    @property
    def hostname(self):
        return self.get_info().get("hostname", "")

    # --- Tasking ---

    def task(self, tasks, inv_id=None):
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

    def get_tags(self):
        """Get tags applied to this sensor.

        Returns:
            list: Tag strings.
        """
        resp = self.client.request("GET", f"{self.sid}/tags")
        return resp.get("tags", [])

    def add_tag(self, tag, ttl=None):
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

    def remove_tag(self, tag):
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

    def is_isolated(self):
        """Check if sensor is isolated from the network."""
        info = self.client.request("GET", self.sid)
        return info.get("is_isolated", False)

    def isolate(self):
        """Isolate sensor from the network.

        Returns:
            dict: API response.
        """
        return self.client.request("POST", f"{self.sid}/isolation")

    def rejoin(self):
        """Rejoin sensor to the network.

        Returns:
            dict: API response.
        """
        return self.client.request("DELETE", f"{self.sid}/isolation")

    # --- Seal ---

    def is_sealed(self):
        """Check if sensor is sealed."""
        info = self.client.request("GET", self.sid)
        return info.get("is_sealed", False)

    def seal(self):
        return self.client.request("POST", f"{self.sid}/seal")

    def unseal(self):
        return self.client.request("DELETE", f"{self.sid}/seal")

    # --- Lifecycle ---

    def delete(self):
        """Delete this sensor.

        Returns:
            dict: API response.
        """
        return self.client.request("DELETE", self.sid)

    # --- Events ---

    def get_events(self, start, end, limit=None, event_type=None, is_forward=False):
        """Get historical events for this sensor.

        Args:
            start: Start time (unix seconds).
            end: End time (unix seconds).
            limit: Max events.
            event_type: Filter by event type.
            is_forward: Chronological order.

        Yields:
            dict: Event records.
        """
        cursor = "-"
        while cursor:
            qp = {
                "start": str(start),
                "end": str(end),
                "is_compressed": "true",
                "cursor": cursor,
            }
            if limit:
                qp["limit"] = str(limit)
            if event_type:
                qp["event_type"] = event_type
            if is_forward:
                qp["is_forward"] = "true"

            resp = self.client.request("GET", f"insight/{self._org.oid}/{self.sid}", query_params=qp)
            for evt in resp.get("events", []):
                yield evt

            cursor = resp.get("cursor")
            if cursor == "-" or not cursor:
                break

    def get_overview(self, start, end):
        """Get event overview (timeline) for this sensor.

        Args:
            start: Start time (unix seconds).
            end: End time (unix seconds).

        Returns:
            list: Overview data.
        """
        return self.client.request("GET", f"insight/{self._org.oid}/{self.sid}/overview",
                                   query_params={"start": str(start), "end": str(end)})

    def get_event_by_atom(self, atom):
        """Get an event by its atom.

        Args:
            atom: Event atom identifier.

        Returns:
            dict: Event data.
        """
        return self.client.request("GET", f"insight/{self._org.oid}/{self.sid}/{atom}")

    def get_children_events(self, atom):
        """Get child events of an atom.

        Args:
            atom: Parent event atom.

        Returns:
            dict: Child events.
        """
        return self.client.request("GET", f"insight/{self._org.oid}/{self.sid}/{atom}/children")

    def get_event_retention(self, start, end, is_detailed=False):
        """Get event retention statistics.

        Args:
            start: Start time (unix seconds).
            end: End time (unix seconds).
            is_detailed: Include detailed breakdown.

        Returns:
            dict: Retention statistics.
        """
        qp = {"startTime": str(start), "endTime": str(end)}
        if is_detailed:
            qp["is_detailed"] = "true"
        return self.client.request("GET", f"insight/event_count/{self._org.oid}/{self.sid}",
                                   query_params=qp)
