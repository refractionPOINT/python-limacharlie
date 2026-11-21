"""YAML loading for files and stdin that become API or hive record data.

PyYAML implements YAML 1.1, where the bare words ``on``, ``off``, ``yes`` and
``no`` are booleans. The services that receive this data read it as YAML 1.2
(or as JSON), where they are text, and a field such as
``ai_may_decide: {"*": off}`` must stay the string ``"off"``: read the 1.1 way
it is sent as ``false`` and the Hive refuses it. :func:`load_yaml` is
``yaml.safe_load`` with the YAML 1.2 boolean rule: only ``true`` and ``false``
(in any of ``true``/``True``/``TRUE`` spellings) are booleans. Everything else
reads as ``yaml.safe_load`` reads it.
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
