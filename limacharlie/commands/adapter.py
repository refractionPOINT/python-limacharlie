"""Adapter commands for LimaCharlie CLI v2."""
from ._hive_shortcut import make_hive_group
group = make_hive_group("adapter", "external_adapter", "adapter")
