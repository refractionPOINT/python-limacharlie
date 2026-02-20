from limacharlie import Manager
from limacharlie.time_utils import parse_time_input, format_timestamp
import sys
import json
import time
import csv
import os
import signal


# Global state for signal handling
class SearchState:
    def __init__(self):
        self.manager = None
        self.query_id = None
        self.interrupted = False

    def cancel_search(self):
        '''Cancel the current search if one is running.'''
        if self.query_id and self.manager:
            try:
                print( "\n\nCanceling search query...", file = sys.stderr )
                self.manager.cancelSearch( self.query_id )
                print( "Search query canceled.", file = sys.stderr )
            except Exception as e:
                print( "Error canceling search: %s" % ( e, ), file = sys.stderr )

_search_state = SearchState()

def _signal_handler(signum, frame):
    '''Handle SIGINT (Ctrl+C) by canceling the running search.'''
    _search_state.interrupted = True
    _search_state.cancel_search()
    sys.exit( 130 )  # 128 + SIGINT (2)

def flatten_dict(d, parent_key='', sep='/'):
    """
    Recursively flatten a nested dictionary for CSV export.

    Parameters:
        d (dict): Dictionary to flatten.
        parent_key (str): Parent key for nested keys.
        sep (str): Separator for nested keys.

    Return:
        dict: Flattened dictionary with string values.
    """
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k

        if isinstance(v, dict):
            # Recursively flatten nested dicts
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        elif isinstance(v, list):
            # Convert lists to JSON strings
            items.append((new_key, json.dumps(v)))
        else:
            # Convert all values to strings for CSV compatibility
            items.append((new_key, str(v) if v is not None else ''))

    return dict(items)


def format_duration(seconds):
    """
    Format a duration in seconds to a human-readable string.

    Parameters:
        seconds (float): Duration in seconds.

    Return:
        str: Formatted duration string (e.g., "1h 23m", "45s").
    """
    if seconds < 60:
        return "%ds" % int(seconds)
    elif seconds < 3600:
        return "%dm %ds" % (int(seconds / 60), int(seconds % 60))
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return "%dh %dm" % (hours, minutes)


def format_time_range(seconds):
    """
    Format a time range in seconds to a compact string.

    Parameters:
        seconds (int): Time range in seconds.

    Return:
        str: Formatted time range string (e.g., "7d", "24h", "30m").
    """
    if seconds < 60:
        return "%ds" % int(seconds)
    elif seconds < 3600:
        return "%dm" % int(seconds / 60)
    elif seconds < 86400:
        return "%dh" % int(seconds / 3600)
    else:
        return "%dd" % int(seconds / 86400)


def print_statistics(total_time, poll_count, page_count, event_row_count, facet_count, timeline_count, include_facets, include_timeline):
    """
    Print execution statistics to stderr.

    Parameters:
        total_time (float): Total execution time in seconds.
        poll_count (int): Number of poll attempts.
        page_count (int): Number of pages retrieved.
        event_row_count (int): Number of event rows.
        facet_count (int): Number of facets.
        timeline_count (int): Number of timeline entries.
        include_facets (bool): Whether facets were included.
        include_timeline (bool): Whether timeline was included.

    Return:
        None
    """
    print("Search completed!", file=sys.stderr)
    print("Statistics:", file=sys.stderr)
    print("  - Total execution time: %.2f seconds" % (total_time,), file=sys.stderr)
    print("  - Poll attempts: %d" % (poll_count,), file=sys.stderr)
    print("  - Pages: %d" % (page_count,), file=sys.stderr)
    print("  - Event rows: %d" % (event_row_count,), file=sys.stderr)
    if include_facets and facet_count > 0:
        print("  - Facets: %d" % (facet_count,), file=sys.stderr)
    if include_timeline and timeline_count > 0:
        print("  - Timeline entries: %d" % (timeline_count,), file=sys.stderr)


def print_billing_stats(billing_stats):
    """
    Print billing statistics to stderr.

    Parameters:
        billing_stats (dict): Billing statistics from search results.

    Return:
        None
    """
    if not billing_stats:
        return

    print("Billing:", file=sys.stderr)

    if 'bytesScanned' in billing_stats:
        bytes_scanned = billing_stats['bytesScanned']
        # Convert to human-readable format
        if bytes_scanned >= 1024**3:
            print("  - Bytes scanned: %.2f GB" % (bytes_scanned / (1024**3),), file=sys.stderr)
        elif bytes_scanned >= 1024**2:
            print("  - Bytes scanned: %.2f MB" % (bytes_scanned / (1024**2),), file=sys.stderr)
        else:
            print("  - Bytes scanned: %d bytes" % (bytes_scanned,), file=sys.stderr)

    if 'eventsScanned' in billing_stats:
        print("  - Events scanned: %d" % (billing_stats['eventsScanned'],), file=sys.stderr)

    if 'eventsMatched' in billing_stats:
        print("  - Events matched: %d" % (billing_stats['eventsMatched'],), file=sys.stderr)

    if 'eventsProcessed' in billing_stats:
        print("  - Events processed: %d" % (billing_stats['eventsProcessed'],), file=sys.stderr)

    if 'estimatedPrice' in billing_stats:
        price = billing_stats['estimatedPrice']
        if isinstance(price, dict):
            value = price.get('value', 0)
            currency = price.get('currency', 'USD')
            print("  - Estimated price: %.4f %s" % (value, currency), file=sys.stderr)
        else:
            print("  - Estimated price: %.4f USD" % (price,), file=sys.stderr)


def main( sourceArgs = None ):
    """
    Command line interface for the LimaCharlie Search API.

    Parameters:
        sourceArgs (list): optional list of CLI arguments to parse.

    Return:
        None
    """
    import argparse

    parser = argparse.ArgumentParser( prog = 'limacharlie search-api' )

    # Create subparsers for different commands
    subparsers = parser.add_subparsers( dest = 'command', help = 'search-api commands' )
    subparsers.required = True

    # Validate command
    validate_parser = subparsers.add_parser( 'validate', help = 'validate a search query and get estimated pricing' )
    validate_parser.add_argument( '-q', '--query',
                                  type = str,
                                  required = True,
                                  dest = 'query',
                                  help = 'the search query to validate.' )
    validate_parser.add_argument( '-s', '--start',
                                  type = str,
                                  required = True,
                                  dest = 'start',
                                  help = 'start time - supports: "now-10m", "now-1h", "2025-12-30 10:00:00", Unix timestamp (seconds/ms).' )
    validate_parser.add_argument( '-e', '--end',
                                  type = str,
                                  required = True,
                                  dest = 'end',
                                  help = 'end time - supports: "now", "now-1h", "2025-12-30 10:00:00", Unix timestamp (seconds/ms).' )
    validate_parser.add_argument( '--stream',
                                  type = str,
                                  required = False,
                                  dest = 'stream',
                                  default = None,
                                  help = 'optional stream name (e.g., "event", "detect", "audit").' )

    # Execute command
    execute_parser = subparsers.add_parser( 'execute', help = 'execute a search query with automatic pagination' )
    execute_parser.add_argument( '-q', '--query',
                                 type = str,
                                 required = True,
                                 dest = 'query',
                                 help = 'the search query to execute.' )
    execute_parser.add_argument( '-s', '--start',
                                 type = str,
                                 required = True,
                                 dest = 'start',
                                 help = 'start time - supports: "now-10m", "now-1h", "2025-12-30 10:00:00", Unix timestamp (seconds/ms).' )
    execute_parser.add_argument( '-e', '--end',
                                 type = str,
                                 required = True,
                                 dest = 'end',
                                 help = 'end time - supports: "now", "now-1h", "2025-12-30 10:00:00", Unix timestamp (seconds/ms).' )
    execute_parser.add_argument( '--stream',
                                 type = str,
                                 required = False,
                                 dest = 'stream',
                                 default = None,
                                 help = 'optional stream name (e.g., "event", "detect", "audit").' )
    execute_parser.add_argument( '--max-poll-attempts',
                                 type = int,
                                 required = False,
                                 dest = 'max_poll_attempts',
                                 default = 300,
                                 help = 'maximum number of polling attempts per page (default: 300).' )
    execute_parser.add_argument( '--poll-interval',
                                 type = int,
                                 required = False,
                                 dest = 'poll_interval',
                                 default = 2,
                                 help = 'seconds to wait between poll attempts (default: 2).' )
    execute_parser.add_argument( '--pretty',
                                 action = 'store_true',
                                 default = False,
                                 required = False,
                                 dest = 'pretty',
                                 help = 'output pretty-printed JSON (default: compact JSON, one result per line).' )
    execute_parser.add_argument( '--output-file',
                                 type = str,
                                 required = False,
                                 dest = 'output_file',
                                 default = None,
                                 help = 'optional file path to write results to (default: stdout).' )
    execute_parser.add_argument( '--output-format',
                                 type = str,
                                 required = False,
                                 dest = 'output_format',
                                 choices = ['jsonl', 'csv'],
                                 default = None,
                                 help = 'output format: jsonl or csv (default: auto-detect from file extension, or jsonl for stdout).' )
    execute_parser.add_argument( '--non-interactive',
                                 action = 'store_true',
                                 default = False,
                                 required = False,
                                 dest = 'non_interactive',
                                 help = 'disable progress indicators (useful for scripts and automation).' )
    execute_parser.add_argument( '--include-facets',
                                 action = 'store_true',
                                 default = False,
                                 required = False,
                                 dest = 'include_facets',
                                 help = 'include facets results (type: facets) in output (default: only events).' )
    execute_parser.add_argument( '--include-timeline',
                                 action = 'store_true',
                                 default = False,
                                 required = False,
                                 dest = 'include_timeline',
                                 help = 'include timeline results (type: timeline) in output (default: only events).' )

    args = parser.parse_args( sourceArgs )

    # Create manager instance
    manager = Manager()

    # Execute the requested command
    if args.command == 'validate':
        # Parse time inputs
        try:
            start_ts = parse_time_input( args.start )
            end_ts = parse_time_input( args.end )

            # Print parsed time range for user confirmation
            print( "Time range: %s to %s" % ( format_timestamp( start_ts ), format_timestamp( end_ts ) ), file = sys.stderr )

        except ValueError as e:
            print( "Error parsing time: %s" % ( e, ), file = sys.stderr )
            sys.exit( 1 )

        # Validate the search query
        result = manager.validateSearch(
            args.query,
            start_ts,
            end_ts,
            stream = args.stream
        )

        # Print validation results
        print( json.dumps( result, indent = 2 ) )

        # Check for validation error
        if result.get( 'error', None ):
            print( "Validation failed: %s" % ( result['error'], ), file = sys.stderr )
            sys.exit( 1 )

        # Print estimated price if available
        estimated_price = result.get( 'estimatedPrice', {} )
        if estimated_price:
            price_value = estimated_price.get( 'value', 0 )
            currency = estimated_price.get( 'currency', 'USD' )
            print( "Estimated price: %.4f %s" % ( price_value, currency ), file = sys.stderr )

    elif args.command == 'execute':
        # Parse time inputs
        try:
            start_ts = parse_time_input( args.start )
            end_ts = parse_time_input( args.end )
        except ValueError as e:
            print( "Error parsing time: %s" % ( e, ), file = sys.stderr )
            sys.exit( 1 )

        # Determine output format
        output_format = args.output_format
        if output_format is None and args.output_file:
            # Auto-detect from file extension
            _, ext = os.path.splitext( args.output_file )
            if ext.lower() == '.csv':
                output_format = 'csv'
            else:
                output_format = 'jsonl'
        elif output_format is None:
            # Default to jsonl for stdout
            output_format = 'jsonl'

        # Open output file if specified
        output_file = None
        csv_writer = None
        csv_rows_buffer = []  # Buffer for CSV rows (to collect all field names first)
        if args.output_file:
            if output_format == 'csv':
                output_file = open( args.output_file, 'w', newline='', encoding='utf-8' )
            else:
                output_file = open( args.output_file, 'w' )

        try:
            # Set up signal handler for Ctrl+C
            _search_state.manager = manager
            signal.signal( signal.SIGINT, _signal_handler )

            # Print query info to stderr so results go to stdout
            if not args.non_interactive:
                print( "Executing search query...", file = sys.stderr )
                print( "Query: %s" % ( args.query, ), file = sys.stderr )
                print( "Time range: %s (%s) to %s (%s)" % (
                    format_timestamp( start_ts ),
                    args.start,
                    format_timestamp( end_ts ),
                    args.end
                ), file = sys.stderr )
                if args.stream:
                    print( "Stream: %s" % ( args.stream, ), file = sys.stderr )
                print( "", file = sys.stderr )

            # Track execution time
            exec_start_time = time.time()

            # Callback for when query is initiated
            def on_query_initiated(query_id):
                _search_state.query_id = query_id

            # Progress tracking
            poll_count = [0]  # Use list to allow modification in nested function
            time_range_seconds = end_ts - start_ts

            # Progress callback with progress bar
            def progress_callback():
                if _search_state.interrupted:
                    return
                poll_count[0] += 1
                if not args.non_interactive:
                    elapsed = time.time() - exec_start_time

                    elapsed_str = format_duration(elapsed)
                    range_str = format_time_range(time_range_seconds)

                    # Progress bar showing elapsed time processing the time range
                    # Since we don't know actual progress, just show activity
                    bar_width = 20
                    # Animate the bar based on poll count
                    pos = poll_count[0] % (bar_width + 1)
                    if pos < bar_width:
                        bar = ' ' * pos + '>' + '=' * (bar_width - pos - 1)
                    else:
                        bar = '=' * bar_width

                    print( "\r[%s] Elapsed: %s | Range: %s | Polls: %d" % ( bar, elapsed_str, range_str, poll_count[0] ), end = '', file = sys.stderr, flush = True )

            # Execute the search with automatic pagination
            page_count = 0
            last_page_number = 0
            event_row_count = 0
            facet_count = 0
            timeline_count = 0
            billing_stats = {}  # Track latest billing stats

            # Section labels for separators
            section_labels = {
                'timeline': 'TIMELINE',
                'facets': 'FACETS',
                'events': 'EVENTS'
            }

            for result in manager.executeSearch(
                args.query,
                start_ts,
                end_ts,
                stream = args.stream,
                max_poll_attempts = args.max_poll_attempts,
                poll_interval = args.poll_interval,
                progress_callback = progress_callback,
                on_query_initiated = on_query_initiated
            ):
                # Check for interruption
                if _search_state.interrupted:
                    break

                # Track page count using metadata
                current_page = result.get( '_page_number', 1 )
                if current_page > last_page_number:
                    page_count = current_page
                    last_page_number = current_page

                # Check if this is first of type in page (for section separator)
                is_first_of_type = result.get( '_first_of_type_in_page', False )
                result_type = result.get( 'type', None )

                # Update billing stats (keep latest from each page)
                page_billing_stats = result.get( '_billing_stats', {} )
                if page_billing_stats:
                    billing_stats = page_billing_stats

                # Extract the appropriate data based on type (for counting)
                if result_type == 'events':
                    rows = result.get( 'rows', [] )
                elif result_type == 'facets':
                    rows = result.get( 'facets', [] )
                elif result_type == 'timeline':
                    rows = result.get( 'timeseries', [] )
                else:
                    rows = []

                # Count by type (always count, even if not outputting)
                for row in rows:
                    if result_type == 'events':
                        event_row_count += 1
                    elif result_type == 'facets':
                        facet_count += 1
                    elif result_type == 'timeline':
                        timeline_count += 1

                # Determine if we should output this result type
                # When writing to file: only write events (machine-parsable data)
                # When writing to stdout: write facets/timeline/events based on flags
                should_output_for_file = ( result_type == 'events' )
                should_output_for_stdout = False
                if result_type == 'events':
                    should_output_for_stdout = True
                elif result_type == 'facets' and args.include_facets:
                    should_output_for_stdout = True
                elif result_type == 'timeline' and args.include_timeline:
                    should_output_for_stdout = True

                # Decide if we should output based on destination
                should_output = should_output_for_file if output_file else should_output_for_stdout

                if should_output:
                    # Print section separator (only to stdout, not to files)
                    if is_first_of_type and output_format != 'csv' and not output_file:
                        section_label = section_labels.get( result_type, result_type.upper() )
                        separator_line = '\r\n--- %s ---' % ( section_label, )  # \r\n to clear progress bar
                        print( separator_line, flush = True )

                    # Output each row
                    for row in rows:
                        if output_format == 'csv':
                            # Flatten the row for CSV
                            flat_row = flatten_dict( row )

                            # Buffer CSV rows to collect all field names first
                            if output_file:
                                csv_rows_buffer.append( flat_row )
                            else:
                                # For stdout, we can't buffer - use dynamic field handling
                                if csv_writer is None:
                                    fieldnames = flat_row.keys()
                                    csv_writer = csv.DictWriter( sys.stdout, fieldnames = fieldnames, extrasaction = 'ignore' )
                                    csv_writer.writeheader()
                                csv_writer.writerow( flat_row )
                        else:
                            # Output each row as JSON (JSONL format)
                            if args.pretty:
                                row_json = json.dumps( row, indent = 2 )
                            else:
                                row_json = json.dumps( row )

                            if output_file:
                                output_file.write( row_json + '\n' )
                                output_file.flush()
                            else:
                                print( row_json, flush = True )

            # Write buffered CSV rows if any
            if output_format == 'csv' and output_file and len( csv_rows_buffer ) > 0:
                # Collect all unique field names from all rows
                all_fieldnames = set()
                for row in csv_rows_buffer:
                    all_fieldnames.update( row.keys() )

                # Sort field names for consistent column ordering
                all_fieldnames = sorted( all_fieldnames )

                # Write CSV with all field names
                csv_writer = csv.DictWriter( output_file, fieldnames = all_fieldnames, extrasaction = 'ignore' )
                csv_writer.writeheader()
                for row in csv_rows_buffer:
                    csv_writer.writerow( row )

            # Calculate execution time
            exec_end_time = time.time()
            total_time = exec_end_time - exec_start_time

            # Print summary to stderr
            if not args.non_interactive:
                print( "\r" + " " * 80 + "\r", end = '', file = sys.stderr )  # Clear progress bar
                print_statistics(total_time, poll_count[0], page_count, event_row_count, facet_count, timeline_count, args.include_facets, args.include_timeline)
                print_billing_stats(billing_stats)

        finally:
            # Clear global state
            _search_state.query_id = None
            _search_state.manager = None

            # Close output file if it was opened
            if output_file:
                output_file.close()
                if not args.non_interactive:
                    print( "Results written to: %s" % ( args.output_file, ), file = sys.stderr )

    else:
        parser.print_help()
        sys.exit( 1 )
