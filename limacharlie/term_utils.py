import os
import sys
import re
import json
import math
import shutil


try:
    from pygments import highlight, lexers, formatters
    has_pygments = True
except ImportError:
    has_pygments = False
    highlight, lexers, formatters = None, None, None

try:
    from rich.console import Console
    has_rich = True
except ImportError:
    # If rich is not available, we will use the basic print function.
    has_rich = False
    Console = None

# If there are more than this number of facets fields, we will only print this number.
MAX_FACET_FIELD_COUNT = 20

# If there are more than this number of values for a facet, we will only print this number.
MAX_FACET_VALUE_COUNT = 10

# All the histogram bars will be scaled to fit in this number of rows.
MAX_HISTOGRAM_BAR_HEIGHT = 10


class ConsoleFallback:
    def print(self, message: str) -> None:
        """
        Fallback to the basic print function if rich is not available.

        It strips any text formatting from the message before printing it.
        """
        message = re.sub(r'\[.*?\]', '', message)
        print(message)


def printFacets(facets: dict) -> None:
    """
    Prints facets in a formatted manner, for example:

    * routing.event_type:
      - NEW_PROCESS: 3
    * event.COMMAND_LINE:
      - taskhostw.exe: 2
      - taskhostw.exe is evil: 1
    """
    console = Console() if has_rich else ConsoleFallback()

    console.print("[bold cyan]Facets[/bold cyan]\n")

    if not facets:
        console.print("[bold red]No facets available.[/bold red]")
        return

    i, j = 0, 0
    for facet, values in facets.items():
        i += 1

        if i >= MAX_FACET_FIELD_COUNT:
            console.print(f"* ... (truncated, only displaying first {MAX_FACET_FIELD_COUNT}) entries ...")
            break

        console.print(f"* {facet}:")

        j = 0
        for key, count in values.items():
            j += 1
            if j > MAX_FACET_VALUE_COUNT:
                console.print(f"  - ... (truncated, only displaying first {MAX_FACET_VALUE_COUNT}) entries ...")
                break

            console.print(f"  - {key}: {count}")

    console.print("")


def printHistogram(hist_data, col_width=25):
    """
    Prints a histogram where timestamps are displayed on the left and bars are represented by # symbols.
    """
    console = Console() if has_rich else ConsoleFallback()
    console.print("[bold cyan]Histogram[/bold cyan]\n")

    if not hist_data:
        console.print("[bold red]No histogram data available.[/bold red]")
        return

    # Sort the keys for consistent ordering.
    keys = sorted(hist_data.keys())
    max_count = max(hist_data.values())

    # Determine if scaling is needed.
    if max_count > MAX_HISTOGRAM_BAR_HEIGHT:
        # Scale counts to MAX_BAR_HEIGHT so that the largest bar reaches MAX_BAR_HEIGHT rows.
        scaled_data = { key: math.ceil(value * MAX_HISTOGRAM_BAR_HEIGHT/ max_count) for key, value in hist_data.items() }
        effective_max = MAX_HISTOGRAM_BAR_HEIGHT
    else:
        scaled_data = hist_data
        effective_max = max_count

    # Build and print each row from effective_max down to 1.
    for level in range(effective_max, 0, -1):
        row_str = ""
        for key in keys:
            if scaled_data[key] >= level:
                row_str += " " + "█".center(col_width) + " "
            else:
                row_str += " " + " ".center(col_width) + " "
        console.print(row_str)

    # Print a separator line.
    separator = ""
    for _ in keys:
        separator += " " + ("-" * col_width).center(col_width) + " "
    console.print(separator)

    # Print the labels centered under each column.
    label_str = ""
    for key in keys:
        # If the key is longer than col_width, truncate it.
        label = key if len(key) <= col_width else key[:col_width]
        label = f"{label} ({hist_data[key]})"
        label_str += " " + label.center(col_width) + " "
    console.print(label_str)

def printHistogram(hist_data, col_width=25):
    """
    Prints a histogram where timestamps are displayed on the left and bars are represented by block symbols.

    Limits the histogram to entries that fit within the current console width.
    Each histogram column is given a width of col_width plus some spacing.
    If there are more entries than can fit on one line, only the first ones are shown.

    Bars are scaled so that if the maximum count exceeds MAX_HISTOGRAM_BAR_HEIGHT,
    all bars are proportionally scaled to have a maximum height of MAX_HISTOGRAM_BAR_HEIGHT.
    """
    console = Console() if has_rich else ConsoleFallback()
    console.print("[bold cyan]Histogram[/bold cyan]\n")

    if not hist_data:
        console.print("[bold red]No histogram data available.[/bold red]")
        return

    # Sort keys for consistent ordering.
    keys = sorted(hist_data.keys())

    # Determine the console width.
    try:
        console_width = console.size.width
    except AttributeError:
        console_width = shutil.get_terminal_size((80, 24)).columns

    # Each column takes up col_width + 2 characters (1 space before and after)
    max_entries_allowed = console_width // (col_width + 2)
    total_entries = len(keys)
    truncated = False
    if total_entries > max_entries_allowed:
        keys = keys[:max_entries_allowed]
        truncated = True

    # Calculate the maximum count among the selected keys.
    max_count = max(hist_data[key] for key in keys)

    # Scale counts if needed.
    if max_count > MAX_HISTOGRAM_BAR_HEIGHT:
        scaled_data = {key: math.ceil(hist_data[key] * MAX_HISTOGRAM_BAR_HEIGHT / max_count) for key in keys}
        effective_max = MAX_HISTOGRAM_BAR_HEIGHT
    else:
        scaled_data = {key: hist_data[key] for key in keys}
        effective_max = max_count

    # Build and print each row from effective_max down to 1.
    for level in range(effective_max, 0, -1):
        row_str = ""
        for key in keys:
            if scaled_data[key] >= level:
                row_str += " " + "█".center(col_width) + " "
            else:
                row_str += " " + " ".center(col_width) + " "
        console.print(row_str)

    # Print a separator line.
    separator = ""
    for _ in keys:
        separator += " " + ("-" * col_width).center(col_width) + " "
    console.print(separator)

    # Print the labels centered under each column.
    label_str = ""
    for key in keys:
        # Truncate label if longer than col_width.
        label = key if len(key) <= col_width else key[:col_width]
        label = f"{label} ({hist_data[key]})"
        label_str += " " + label.center(col_width) + " "
    console.print(label_str)

    # If some entries were truncated, show a summary message.
    if truncated:
        console.print(f"\nShowing first {len(keys)} histogram entries out of {total_entries} total entries.")


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
    if has_pygments and use_colors:
        result = highlight(formatted_json, lexers.JsonLexer(), formatters.TerminalFormatter())
    else:
        result = formatted_json

    return result
