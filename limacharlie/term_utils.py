import os
import sys

from pygments import highlight, lexers, formatters

from . import json_utils as json


def useColors():
    """
    Return true if we should use ANSI colors in the output.
    :return: True if ANSI colors should be used, False otherwise.
    """
    # Check if stdout is a tty (i.e., terminal)
    if not sys.stdout.isatty():
        return False

    # Optionally, disable colors if the NO_COLOR environment variable is set
    if "NO_COLOR" in os.environ:
        return False

    # Also, sometimes checking TERM helps to avoid "dumb" terminals
    term = os.environ.get("TERM", "")
    if term == "dumb":
        return False

    return True

def prettyFormatDict(data: dict, use_colors: bool = None, indent: int = 2) -> str:
    """
    Pretty format a dictionary to a string, optionally with ANSI colors.

    :param data: The dictionary to format.
    :param use_colors: Whether to use ANSI colors.
    :param ident: The number of spaces to use for indentation.
    :return: The formatted string.
    """
    formatted_json = json.dumps(data, sort_keys=True, indent=indent)

    use_colors = (use_colors if use_colors is not None else useColors())
    if use_colors:
        result = highlight(formatted_json, lexers.JsonLexer(), formatters.TerminalFormatter())
    else:
        result = formatted_json

    return result
