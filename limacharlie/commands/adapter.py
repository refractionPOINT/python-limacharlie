"""External adapter commands for LimaCharlie CLI v2."""

from __future__ import annotations

from ._hive_shortcut import make_hive_group
group = make_hive_group("ext-adapter", "external_adapter", "external adapter")
