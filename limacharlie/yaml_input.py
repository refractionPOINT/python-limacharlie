"""YAML loading for investigation hive records.

PyYAML implements YAML 1.1, where the bare words ``on``, ``off``, ``yes`` and
``no`` are booleans. The investigation hives (``investigation_policy``,
``investigation_pack`` and ``investigation_plan``) are read as YAML 1.2 or JSON by the services, where those
words are text, and a field such as ``ai_may_decide: {"*": off}`` must stay the
string ``"off"``: read the 1.1 way it is sent as ``false`` and the Hive refuses it.

:func:`load_yaml` is ``yaml.safe_load`` with the YAML 1.2 boolean rule (only
``true`` and ``false`` are booleans). It is used ONLY for those two hives, through
:func:`load_record_yaml`; every other file the CLI reads keeps ``yaml.safe_load``
and its YAML 1.1 meaning, because customers' existing files depend on it.
"""

from __future__ import annotations

import re
from typing import Any

import yaml

_BOOL_TAG = "tag:yaml.org,2002:bool"
_BOOL_RE = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")


class _Yaml12BoolLoader(yaml.SafeLoader):
    """SafeLoader whose only implicit booleans are ``true`` and ``false``."""

    yaml_implicit_resolvers = {
        first: [(tag, regexp) for tag, regexp in resolvers if tag != _BOOL_TAG]
        for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }


_Yaml12BoolLoader.add_implicit_resolver(_BOOL_TAG, _BOOL_RE, list("tTfF"))


#: The hives whose records are read with the YAML 1.2 boolean rule.
INVESTIGATION_HIVES = frozenset({"investigation_policy", "investigation_pack", "investigation_plan"})


def load_record_yaml(content: str, hive_name: str | None) -> Any:
    """Parse YAML (or JSON) that becomes a record of ``hive_name``.

    Args:
        content: The document text.
        hive_name: The hive the data is written to, or None when it is not a hive record.

    Returns:
        Any: :func:`load_yaml` for an investigation hive, ``yaml.safe_load`` for every other hive.

    Raises:
        yaml.YAMLError: If the text is not valid YAML.
    """
    if hive_name in INVESTIGATION_HIVES:
        return load_yaml(content)
    return yaml.safe_load(content)


def load_yaml(content: str) -> Any:
    """Parse YAML (or JSON) text with the YAML 1.2 boolean rule.

    Args:
        content: The document text.

    Returns:
        Any: The parsed value, as ``yaml.safe_load`` returns it, except that
            ``on``, ``off``, ``yes`` and ``no`` (and ``y``/``n``) stay strings.

    Raises:
        yaml.YAMLError: If the text is not valid YAML.
    """
    return yaml.load(content, Loader=_Yaml12BoolLoader)  # noqa: S506 - a SafeLoader subclass
