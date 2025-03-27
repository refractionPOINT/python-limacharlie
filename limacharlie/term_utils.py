import os
import sys
import re
import json

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

     TODO:
         - Limit total number of facets printed.
         - Limit total number of values printed for each facet.
     """
     console = Console() if has_rich else ConsoleFallback()

     console.print("[bold cyan]Facets[/bold cyan]\n")

     if not facets:
         console.print("[bold red]No facets available.[/bold red]")
         return

     for facet, values in facets.items():
         console.print(f"* {facet}:")
         for key, count in values.items():
             console.print(f"  - {key}: {count}")

     console.print("")


def printHistogram(hist_data, col_width=25):
     """
     Prints a histogram where timestamps are displayed on the left and bars are represented by # symbols.
     """
     console = Console() if has_rich else ConsoleFallback()
     console.print("[bold cyan]Histogram[/bold cyan]\n")

     if not hist_data:
         print("No histogram data available.")
         return

    # Sort the keys for consistent ordering.
     keys = sorted(hist_data.keys())
     max_count = max(hist_data.values())

     # Build and print each row from max_count down to 1.
     for level in range(max_count, 0, -1):
         row_str = ""
         for key in keys:
             if hist_data[key] >= level:
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
