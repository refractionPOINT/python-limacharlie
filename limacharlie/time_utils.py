"""
Time parsing utilities for LimaCharlie SDK.

Supports multiple time formats:
- Relative times: "now", "now-10m", "now-1h", "now-7d"
- ISO dates: "2025-12-30", "2025-12-30 10:00:00"
- Unix timestamps: 1234567890 (seconds or milliseconds)
"""

import re
import time
from datetime import datetime, timedelta, timezone


def parse_time_input(time_str):
    """
    Parse a time string in various formats and return Unix timestamp (seconds).

    Supported formats:
    - "now" - Current time
    - "now-10m" - 10 minutes ago
    - "now-1h" - 1 hour ago
    - "now-7d" - 7 days ago
    - "now-2w" - 2 weeks ago
    - "2025-12-30" - ISO date (assumed UTC)
    - "2025-12-30 10:00:00" - ISO datetime (assumed UTC)
    - "2025-12-30T10:00:00" - ISO datetime with T separator
    - "2025-12-30T10:00:00Z" - ISO datetime with timezone
    - "2025-12-30T10:00:00+05:00" - ISO datetime with timezone offset
    - "1234567890" - Unix timestamp (seconds)
    - "1234567890000" - Unix timestamp (milliseconds, auto-detected)

    Parameters:
        time_str (str or int): Time string or timestamp to parse.

    Return:
        int: Unix timestamp in seconds.

    Raises:
        ValueError: If the time format is not recognized.
    """
    # Handle None or empty string
    if time_str is None or time_str == '':
        raise ValueError("Time string cannot be empty")

    # Convert to string if it's a number
    if isinstance(time_str, (int, float)):
        time_str = str(int(time_str))

    time_str = time_str.strip()

    # Handle "now"
    if time_str.lower() == "now":
        return int(time.time())

    # Handle relative times like "now-10m", "now-1h", "now-7d"
    relative_match = re.match(r'^now\s*-\s*(\d+)\s*([smhdwMy])$', time_str, re.IGNORECASE)
    if relative_match:
        amount = int(relative_match.group(1))
        # Keep original case for 'M' vs 'm' distinction (months vs minutes)
        unit = relative_match.group(2)

        # Calculate the timedelta
        # Note: 'm' (lowercase) = minutes, 'M' (uppercase) = months
        if unit.lower() == 's':
            delta = timedelta(seconds=amount)
        elif unit == 'm':  # Lowercase only = minutes
            delta = timedelta(minutes=amount)
        elif unit.lower() == 'h':
            delta = timedelta(hours=amount)
        elif unit.lower() == 'd':
            delta = timedelta(days=amount)
        elif unit.lower() == 'w':
            delta = timedelta(weeks=amount)
        elif unit == 'M':  # Uppercase only = months (approximate as 30 days)
            delta = timedelta(days=amount * 30)
        elif unit.lower() == 'y':  # Years (approximate as 365 days)
            delta = timedelta(days=amount * 365)
        else:
            raise ValueError(f"Unknown time unit: {unit}")

        # Calculate the timestamp
        target_time = datetime.now(timezone.utc) - delta
        return int(target_time.timestamp())

    # Try to parse as Unix timestamp (seconds or milliseconds)
    if time_str.isdigit():
        timestamp = int(time_str)

        # Auto-detect milliseconds vs seconds
        # Timestamps > 10^10 are likely milliseconds (after year 2286 in seconds)
        if timestamp > 10_000_000_000:
            # Milliseconds
            return timestamp // 1000
        else:
            # Seconds
            return timestamp

    # Try to parse as ISO date/datetime
    # Supported formats:
    # - "2025-12-30"
    # - "2025-12-30 10:00:00"
    # - "2025-12-30T10:00:00"
    # - "2025-12-30T10:00:00Z"
    # - "2025-12-30T10:00:00+05:00"
    # - "2025-12-30T10:00:00.123456Z"

    # List of formats to try
    formats = [
        "%Y-%m-%dT%H:%M:%S.%fZ",       # ISO with microseconds and Z
        "%Y-%m-%dT%H:%M:%S.%f%z",      # ISO with microseconds and timezone
        "%Y-%m-%dT%H:%M:%SZ",          # ISO with Z
        "%Y-%m-%dT%H:%M:%S%z",         # ISO with timezone offset
        "%Y-%m-%dT%H:%M:%S",           # ISO with T separator
        "%Y-%m-%d %H:%M:%S.%f",        # With microseconds
        "%Y-%m-%d %H:%M:%S",           # Date and time with space
        "%Y-%m-%d",                    # Date only
    ]

    for fmt in formats:
        try:
            # Parse the datetime
            dt = datetime.strptime(time_str, fmt)

            # If no timezone info, assume UTC
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)

            return int(dt.timestamp())
        except ValueError:
            continue

    # If nothing worked, raise an error
    raise ValueError(
        f"Unable to parse time: '{time_str}'. "
        f"Supported formats: 'now', 'now-10m', '2025-12-30', '2025-12-30 10:00:00', "
        f"'2025-12-30T10:00:00Z', Unix timestamp (seconds or milliseconds)"
    )


def parse_time_range(start_str, end_str):
    """
    Parse start and end time strings and return Unix timestamps.

    Parameters:
        start_str (str or int): Start time in any supported format.
        end_str (str or int): End time in any supported format.

    Return:
        tuple: (start_timestamp, end_timestamp) as integers (seconds).

    Raises:
        ValueError: If either time format is not recognized or if start > end.
    """
    start_ts = parse_time_input(start_str)
    end_ts = parse_time_input(end_str)

    # Validate that start is before end
    if start_ts > end_ts:
        raise ValueError(
            f"Start time ({start_ts}, {datetime.fromtimestamp(start_ts, tz=timezone.utc)}) "
            f"is after end time ({end_ts}, {datetime.fromtimestamp(end_ts, tz=timezone.utc)})"
        )

    return start_ts, end_ts


def format_timestamp(timestamp, use_iso=True):
    """
    Format a Unix timestamp as a human-readable string.

    Parameters:
        timestamp (int): Unix timestamp in seconds.
        use_iso (bool): If True, use ISO format; otherwise use local time format.

    Return:
        str: Formatted timestamp string.
    """
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)

    if use_iso:
        return dt.isoformat()
    else:
        return dt.strftime('%Y-%m-%d %H:%M:%S UTC')
