"""AI Memory SDK for LimaCharlie v2.

Wraps the ``ai_memory`` hive, which stores per-agent memory entries.
Each Hive record is keyed by an agent identifier and holds a
``memories`` map of filesystem-style names to memory contents.

The hive's PreIngest hook applies a partial-merge on every Set: keys
present in the incoming ``memories`` map replace (or, when the value
is JSON null, drop) the matching key in the stored record, while keys
absent from the incoming map are preserved untouched. This SDK bakes
that semantic in:

  * :meth:`AiMemory.set` sends a single named memory and trusts the
    hook to merge it in — the rest of the record is never touched and
    never has to round-trip through the client.
  * :meth:`AiMemory.delete` sends ``{"memories": {name: None}}`` so
    the hook drops just that one entry.
  * :meth:`AiMemory.delete_record` removes the entire agent record
    (no merge semantics involved).

Reference (server-side merge hook): legion_config_hive
``hives/def_ai_memory.go`` — ``MergeAiMemory``.
"""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING
from urllib.parse import quote as urlescape

if TYPE_CHECKING:
    from ..client import Client
    from .organization import Organization

from .hive import Hive, HiveRecord


# Hive name used by the ai_memory definition in legion_config_hive.
HIVE_NAME = "ai_memory"

# Top-level field in the record's data dict that holds the memories map.
# Mirrors aiMemoryFieldKey in def_ai_memory.go.
MEMORIES_FIELD = "memories"


class AiMemory:
    """Client for the ``ai_memory`` hive in a LimaCharlie organization.

    Usage::

        am = AiMemory(org)
        am.set("my-agent", "notes/today", "wrote the cli wrapper")
        content = am.get("my-agent", "notes/today")
        am.delete("my-agent", "notes/today")     # drop one memory
        am.delete_record("my-agent")             # drop the whole agent
    """

    def __init__(self, org: Organization, partition_key: str | None = None) -> None:
        """Initialize the AI memory client.

        Args:
            org: Organization instance.
            partition_key: Optional partition key (defaults to org OID).
        """
        self._org = org
        self._hive = Hive(org, HIVE_NAME, partition_key=partition_key)

    @property
    def hive(self) -> Hive:
        """The underlying :class:`Hive` instance for advanced callers."""
        return self._hive

    @property
    def client(self) -> Client:
        """The underlying API client."""
        return self._org.client

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def list_records(self) -> dict[str, HiveRecord]:
        """List every agent record in the ``ai_memory`` hive.

        Returns:
            Mapping of record name (agent identifier) → :class:`HiveRecord`.
        """
        return self._hive.list()

    def get_record(self, agent: str) -> HiveRecord:
        """Fetch the full memory record for an agent.

        Args:
            agent: Agent identifier (the hive record key).

        Returns:
            :class:`HiveRecord` with the full ``memories`` map in
            ``record.data["memories"]``.
        """
        return self._hive.get(agent)

    def list_memories(self, agent: str) -> dict[str, str]:
        """Return the agent's memories as a flat name → content map.

        Args:
            agent: Agent identifier.

        Returns:
            Dict of memory name to memory content. Empty dict when the
            record exists but has no memories (or no ``memories`` field).
        """
        record = self._hive.get(agent)
        return _extract_memories(record)

    def get(self, agent: str, memory_name: str) -> str | None:
        """Fetch a single memory entry's content.

        Args:
            agent: Agent identifier (the hive record key).
            memory_name: Name of the memory entry within the record.

        Returns:
            The memory's content string, or ``None`` when the entry
            does not exist on the record.
        """
        memories = self.list_memories(agent)
        return memories.get(memory_name)

    # ------------------------------------------------------------------
    # Write (partial merge)
    # ------------------------------------------------------------------

    def set(self, agent: str, memory_name: str, content: str) -> dict[str, Any]:
        """Create or replace a single memory entry.

        Sends ``{"memories": {memory_name: content}}`` only — every other
        memory on the record is preserved by the hive's PreIngest merge
        hook. No prior fetch is required and no etag round-trip is
        needed for concurrent updates of disjoint memory names.

        Args:
            agent: Agent identifier (the hive record key).
            memory_name: Name of the memory entry to write.
            content: Memory content (string).

        Returns:
            dict: API response.
        """
        return self._partial_set(agent, {memory_name: content})

    def set_many(self, agent: str, memories: dict[str, str | None]) -> dict[str, Any]:
        """Set or drop multiple memory entries in one request.

        Args:
            agent: Agent identifier.
            memories: Map of memory name to content. A value of ``None``
                drops that memory entry on the server (per the merge hook).

        Returns:
            dict: API response.
        """
        return self._partial_set(agent, memories)

    def delete(self, agent: str, memory_name: str) -> dict[str, Any]:
        """Delete a single memory entry from the agent record.

        Sends ``{"memories": {memory_name: None}}`` so the merge hook
        drops just that key — the rest of the record is preserved.

        Args:
            agent: Agent identifier.
            memory_name: Memory entry name to drop.

        Returns:
            dict: API response.
        """
        return self._partial_set(agent, {memory_name: None})

    def delete_record(self, agent: str) -> dict[str, Any]:
        """Delete the entire memory record for an agent.

        Use :meth:`delete` to drop a single memory entry; this method
        removes the whole hive record.

        Args:
            agent: Agent identifier.

        Returns:
            dict: API response.
        """
        return self._hive.delete(agent)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _partial_set(self, agent: str, memories: dict[str, str | None]) -> dict[str, Any]:
        """POST a partial ``memories`` payload to the hive endpoint.

        Goes around :meth:`Hive.set` so we can send ``null`` values
        (Python ``None``) — :class:`HiveRecord` would strip them on the
        way through ``json.dumps``-of-the-dataclass round-trip if we
        relied on it. The merge hook on the server treats null values as
        deletions for the matching memory name.
        """
        payload = {MEMORIES_FIELD: memories}
        return self.client.request(
            "POST",
            f"hive/{HIVE_NAME}/{self._hive._partition_key}/{urlescape(agent, safe='')}/data",
            params={"data": json.dumps(payload)},
        )


def _extract_memories(record: HiveRecord) -> dict[str, str]:
    """Return the ``memories`` map from a record, normalized to a dict."""
    if record.data is None:
        return {}
    raw = record.data.get(MEMORIES_FIELD)
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, str)}
