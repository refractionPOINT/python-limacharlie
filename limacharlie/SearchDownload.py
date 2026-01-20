"""CLI module for managing search download jobs.

This module provides commands for creating and managing long-running
background jobs that download complete search results to cloud storage.

Available commands:
    start    - Start a new download job
    status   - Get the status of a download job
    list     - List download jobs for the organization
    cancel   - Cancel a running download job
    wait     - Wait for a download job to complete
"""

from limacharlie import Manager
from limacharlie.time_utils import parse_time_input, format_timestamp
from limacharlie.utils import LcApiException
import sys
import json
import time
import signal


def format_duration(seconds):
    """
    Format a duration in seconds to a human-readable string.

    Parameters:
        seconds (float): Duration in seconds.

    Returns:
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


def format_bytes(num_bytes):
    """
    Format bytes to a human-readable string.

    Parameters:
        num_bytes (int): Number of bytes.

    Returns:
        str: Formatted string (e.g., "1.5 GB", "256 MB").
    """
    if num_bytes >= 1024**3:
        return "%.2f GB" % (num_bytes / (1024**3))
    elif num_bytes >= 1024**2:
        return "%.2f MB" % (num_bytes / (1024**2))
    elif num_bytes >= 1024:
        return "%.2f KB" % (num_bytes / 1024)
    else:
        return "%d bytes" % num_bytes


def print_job_status(status, verbose=False):
    """
    Print job status in a human-readable format.

    Parameters:
        status (dict): Job status dictionary.
        verbose (bool): If True, print detailed progress information.

    Returns:
        None
    """
    job_id = status.get('jobId', 'unknown')
    job_status = status.get('status', 'unknown')
    created_at = status.get('createdAt', '')

    # Status indicator
    status_icons = {
        'queued': '⏳',
        'running': '🔄',
        'merging': '📦',
        'completed': '✅',
        'failed': '❌',
        'cancelled': '🚫'
    }
    icon = status_icons.get(job_status, '❓')

    print(f"{icon} Job: {job_id}")
    print(f"   Status: {job_status}")
    print(f"   Created: {created_at}")

    if status.get('startedAt'):
        print(f"   Started: {status['startedAt']}")

    if status.get('completedAt'):
        print(f"   Completed: {status['completedAt']}")

    # Progress information
    progress = status.get('progress', {})
    if progress and (verbose or job_status in ['running', 'merging']):
        events = progress.get('eventsProcessed', 0)
        pages = progress.get('pagesProcessed', 0)
        bytes_processed = progress.get('bytesProcessed', 0)
        runtime = progress.get('runtimeSeconds', 0)

        print(f"   Progress:")
        print(f"     - Events processed: {events:,}")
        print(f"     - Pages processed: {pages}")
        print(f"     - Data processed: {format_bytes(bytes_processed)}")
        if runtime > 0:
            print(f"     - Runtime: {format_duration(runtime)}")

        # Rate metrics
        events_per_sec = progress.get('eventsPerSecond', 0)
        if events_per_sec > 0:
            print(f"     - Rate: {events_per_sec:.1f} events/sec")

        # Date range progress
        date_percent = progress.get('dateRangePercent', 0)
        if date_percent > 0:
            print(f"     - Date range: {date_percent:.1f}%")

    # Error message
    if status.get('error'):
        print(f"   Error: {status['error']}")

    # Result URL
    if status.get('resultUrl'):
        print(f"   Result URL: {status['resultUrl']}")
        if status.get('resultExpiry'):
            print(f"   URL Expires: {status['resultExpiry']}")

    # Metadata
    metadata = status.get('metadata', {})
    if metadata and verbose:
        print(f"   Metadata:")
        for key, value in metadata.items():
            print(f"     - {key}: {value}")


def main(sourceArgs=None):
    """
    Command line interface for LimaCharlie Search Download API.

    Parameters:
        sourceArgs (list): Optional list of CLI arguments to parse.

    Returns:
        None
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog='limacharlie search-download',
        description='Manage long-running search download jobs'
    )

    # Create subparsers for different commands
    subparsers = parser.add_subparsers(dest='command', help='search-download commands')
    subparsers.required = True

    # Start command - initiate a new download job
    start_parser = subparsers.add_parser(
        'start',
        help='Start a new search download job'
    )
    start_parser.add_argument(
        '-q', '--query',
        type=str,
        required=True,
        dest='query',
        help='The search query to execute.'
    )
    start_parser.add_argument(
        '-s', '--start',
        type=str,
        required=True,
        dest='start',
        help='Start time - supports: "now-10m", "now-1h", "2025-12-30 10:00:00", Unix timestamp.'
    )
    start_parser.add_argument(
        '-e', '--end',
        type=str,
        required=True,
        dest='end',
        help='End time - supports: "now", "now-1h", "2025-12-30 10:00:00", Unix timestamp.'
    )
    start_parser.add_argument(
        '--stream',
        type=str,
        default=None,
        dest='stream',
        help='Optional stream name (e.g., "event", "detect", "audit").'
    )
    start_parser.add_argument(
        '--compression',
        type=str,
        choices=['zip', 'none'],
        default='zip',
        dest='compression',
        help='Compression type for the result file (default: zip).'
    )
    start_parser.add_argument(
        '--token-hours',
        type=float,
        default=8.0,
        dest='token_hours',
        help='Token validity in hours for the download job (default: 8). Jobs can run up to 6 hours.'
    )
    start_parser.add_argument(
        '--metadata',
        type=str,
        default=None,
        dest='metadata',
        help='Optional JSON metadata to attach to the job (e.g., \'{"purpose": "forensics"}\').'
    )
    start_parser.add_argument(
        '--wait',
        action='store_true',
        default=False,
        dest='wait',
        help='Wait for the job to complete instead of returning immediately.'
    )
    start_parser.add_argument(
        '--json',
        action='store_true',
        default=False,
        dest='json_output',
        help='Output raw JSON instead of formatted text.'
    )

    # Status command - get job status
    status_parser = subparsers.add_parser(
        'status',
        help='Get the status of a download job'
    )
    status_parser.add_argument(
        'job_id',
        type=str,
        help='The job ID to check.'
    )
    status_parser.add_argument(
        '--json',
        action='store_true',
        default=False,
        dest='json_output',
        help='Output raw JSON instead of formatted text.'
    )
    status_parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        default=False,
        dest='verbose',
        help='Show detailed progress information.'
    )

    # List command - list download jobs
    list_parser = subparsers.add_parser(
        'list',
        help='List download jobs for the organization'
    )
    list_parser.add_argument(
        '--limit',
        type=int,
        default=20,
        dest='limit',
        help='Maximum number of jobs to return (default: 20, max: 1000).'
    )
    list_parser.add_argument(
        '--offset',
        type=int,
        default=0,
        dest='offset',
        help='Number of jobs to skip for pagination (default: 0).'
    )
    list_parser.add_argument(
        '--json',
        action='store_true',
        default=False,
        dest='json_output',
        help='Output raw JSON instead of formatted text.'
    )
    list_parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        default=False,
        dest='verbose',
        help='Show detailed progress information for each job.'
    )

    # Cancel command - cancel a running job
    cancel_parser = subparsers.add_parser(
        'cancel',
        help='Cancel a running download job'
    )
    cancel_parser.add_argument(
        'job_id',
        type=str,
        help='The job ID to cancel.'
    )

    # Wait command - wait for job completion
    wait_parser = subparsers.add_parser(
        'wait',
        help='Wait for a download job to complete'
    )
    wait_parser.add_argument(
        'job_id',
        type=str,
        help='The job ID to wait for.'
    )
    wait_parser.add_argument(
        '--poll-interval',
        type=int,
        default=10,
        dest='poll_interval',
        help='Seconds between status checks (default: 10).'
    )
    wait_parser.add_argument(
        '--timeout',
        type=int,
        default=None,
        dest='timeout',
        help='Maximum seconds to wait before timing out (default: no timeout).'
    )
    wait_parser.add_argument(
        '--json',
        action='store_true',
        default=False,
        dest='json_output',
        help='Output raw JSON instead of formatted text.'
    )
    wait_parser.add_argument(
        '-q', '--quiet',
        action='store_true',
        default=False,
        dest='quiet',
        help='Suppress progress output, only print final result.'
    )

    # URL command - get download URL for a completed job
    url_parser = subparsers.add_parser(
        'url',
        help='Get the download URL for a completed job'
    )
    url_parser.add_argument(
        'job_id',
        type=str,
        help='The job ID to get the URL for.'
    )

    args = parser.parse_args(sourceArgs)

    # Create manager instance
    manager = Manager()

    # Execute the requested command
    if args.command == 'start':
        # Parse time inputs
        try:
            start_ts = parse_time_input(args.start)
            end_ts = parse_time_input(args.end)
        except ValueError as e:
            print(f"Error parsing time: {e}", file=sys.stderr)
            sys.exit(1)

        # Parse metadata if provided
        metadata = None
        if args.metadata:
            try:
                metadata = json.loads(args.metadata)
                if not isinstance(metadata, dict):
                    raise ValueError("Metadata must be a JSON object")
            except json.JSONDecodeError as e:
                print(f"Error parsing metadata JSON: {e}", file=sys.stderr)
                sys.exit(1)

        # Generate long-lived token for the job
        expiry_seconds = int(time.time() + args.token_hours * 3600)
        try:
            manager.getJWT(expiry_seconds=expiry_seconds)
        except LcApiException as e:
            print(f"Error generating token: {e}", file=sys.stderr)
            sys.exit(1)

        # Print job info
        if not args.json_output:
            print("Starting search download job...", file=sys.stderr)
            print(f"Query: {args.query}", file=sys.stderr)
            print(f"Time range: {format_timestamp(start_ts)} to {format_timestamp(end_ts)}", file=sys.stderr)
            print(f"Token valid for: {args.token_hours} hours", file=sys.stderr)
            print("", file=sys.stderr)

        try:
            result = manager.initiateSearchDownload(
                query=args.query,
                start_time=start_ts,
                end_time=end_ts,
                compression=args.compression,
                stream=args.stream,
                metadata=metadata
            )
        except LcApiException as e:
            print(f"Error starting download job: {e}", file=sys.stderr)
            sys.exit(1)

        job_id = result.get('jobId', 'unknown')

        if args.json_output:
            print(json.dumps(result, indent=2))
        else:
            print(f"Download job started: {job_id}")

            # Print estimated stats if available
            estimated = result.get('estimatedStats', {})
            if estimated:
                events = estimated.get('eventsMatched', 0)
                price = estimated.get('estimatedPrice', {})
                if events:
                    print(f"Estimated events: {events:,}")
                if price:
                    print(f"Estimated price: {price.get('price', 0):.4f} {price.get('currency', 'USD')}")

            if result.get('tokenExpiry'):
                print(f"Token expires: {result['tokenExpiry']}")

        # Wait for completion if requested
        if args.wait:
            if not args.json_output:
                print("\nWaiting for job to complete...", file=sys.stderr)

            def progress_cb(status):
                if not args.json_output:
                    progress = status.get('progress', {})
                    events = progress.get('eventsProcessed', 0)
                    job_status = status.get('status', '')
                    runtime = progress.get('runtimeSeconds', 0)
                    print(f"\r  Status: {job_status} | Events: {events:,} | Runtime: {format_duration(runtime)}   ",
                          end='', file=sys.stderr, flush=True)

            try:
                final_status = manager.waitForSearchDownload(
                    job_id,
                    poll_interval=10,
                    progress_callback=progress_cb
                )
                if not args.json_output:
                    print("\n", file=sys.stderr)
                    print_job_status(final_status, verbose=True)
                else:
                    print(json.dumps(final_status, indent=2))
            except LcApiException as e:
                print(f"\nError: {e}", file=sys.stderr)
                sys.exit(1)

    elif args.command == 'status':
        try:
            status = manager.getSearchDownloadStatus(args.job_id)
        except LcApiException as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        if args.json_output:
            print(json.dumps(status, indent=2))
        else:
            print_job_status(status, verbose=args.verbose)

    elif args.command == 'list':
        try:
            jobs = manager.listSearchDownloads(limit=args.limit, offset=args.offset)
        except LcApiException as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        if args.json_output:
            print(json.dumps({'jobs': jobs}, indent=2))
        else:
            if not jobs:
                print("No download jobs found.")
            else:
                print(f"Found {len(jobs)} download job(s):\n")
                for job in jobs:
                    print_job_status(job, verbose=args.verbose)
                    print()

    elif args.command == 'cancel':
        try:
            manager.cancelSearchDownload(args.job_id)
            print(f"Job {args.job_id} cancelled successfully.")
        except LcApiException as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == 'wait':
        interrupted = [False]

        def signal_handler(signum, frame):
            interrupted[0] = True
            print("\nInterrupted. The job is still running in the background.", file=sys.stderr)
            print(f"Check status with: limacharlie search-download status {args.job_id}", file=sys.stderr)
            sys.exit(130)

        signal.signal(signal.SIGINT, signal_handler)

        def progress_cb(status):
            if not args.quiet and not args.json_output:
                progress = status.get('progress', {})
                events = progress.get('eventsProcessed', 0)
                job_status = status.get('status', '')
                runtime = progress.get('runtimeSeconds', 0)
                date_pct = progress.get('dateRangePercent', 0)
                print(f"\r  Status: {job_status} | Events: {events:,} | Progress: {date_pct:.1f}% | Runtime: {format_duration(runtime)}   ",
                      end='', file=sys.stderr, flush=True)

        if not args.quiet and not args.json_output:
            print(f"Waiting for job {args.job_id} to complete...", file=sys.stderr)

        try:
            final_status = manager.waitForSearchDownload(
                args.job_id,
                poll_interval=args.poll_interval,
                timeout=args.timeout,
                progress_callback=progress_cb
            )

            if not args.quiet and not args.json_output:
                print("\n", file=sys.stderr)

            if args.json_output:
                print(json.dumps(final_status, indent=2))
            else:
                print_job_status(final_status, verbose=True)

        except LcApiException as e:
            if not args.quiet:
                print(f"\nError: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == 'url':
        try:
            status = manager.getSearchDownloadStatus(args.job_id)
        except LcApiException as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        if status.get('status') != 'completed':
            print(f"Job is not completed (status: {status.get('status')})", file=sys.stderr)
            if status.get('status') in ['queued', 'running', 'merging']:
                print(f"Wait for completion with: limacharlie search-download wait {args.job_id}", file=sys.stderr)
            sys.exit(1)

        url = status.get('resultUrl')
        if not url:
            print("No result URL available (results may have expired)", file=sys.stderr)
            sys.exit(1)

        print(url)

    else:
        parser.print_help()
        sys.exit(1)
