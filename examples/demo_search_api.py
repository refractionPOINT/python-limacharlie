#!/usr/bin/env python3
"""
LimaCharlie Search API Demo

This example demonstrates how to use the LimaCharlie Search API to:
1. Validate a search query and get estimated pricing
2. Execute a search and retrieve results
3. Export results to CSV format
4. Compress the CSV output

Requirements:
    pip install limacharlie

Usage:
    python demo_search_api.py
"""

import limacharlie
from limacharlie.SearchAPI import flatten_dict
import csv
import gzip
import json
import sys
import time
from datetime import datetime, timedelta

def example_basic_search():
    """
    Basic example: Execute a simple search query using the SDK.

    NOTE: In the CLI, you can use user-friendly time formats like:
      limacharlie search-api execute -q "event_type = NEW_PROCESS" -s "now-1h" -e "now"

    Parameters:
        None

    Return:
        None
    """
    print("\n=== Example 1: Basic Search (SDK) ===")

    # Initialize the Manager using default credentials
    # You can also pass oid and secret_api_key explicitly
    man = limacharlie.Manager()

    # Define search parameters
    # Search for NEW_PROCESS events in the last hour
    end_time = int(time.time())
    start_time = end_time - 3600  # 1 hour ago

    query = "event_type = NEW_PROCESS"

    print(f"Query: {query}")
    print(f"Time range: {datetime.fromtimestamp(start_time)} to {datetime.fromtimestamp(end_time)}")
    print("\nCLI equivalent:")
    print(f'  limacharlie search-api execute -q "{query}" -s "now-1h" -e "now"')

    # Execute the search with automatic pagination
    # This will transparently iterate through all pages of results
    result_count = 0
    for result in man.executeSearch(query, start_time, end_time):
        result_count += 1
        # Print first few results
        if result_count <= 3:
            print(f"\nResult {result_count}:")
            print(json.dumps(result, indent=2)[:500] + "...")

    print(f"\nTotal results: {result_count}")


def example_validate_search():
    """
    Example: Validate a search query before executing it.

    This is useful to check syntax and get estimated pricing.

    Parameters:
        None

    Return:
        None
    """
    print("\n=== Example 2: Validate Search Query ===")

    man = limacharlie.Manager()

    # Define search parameters
    end_time = int(time.time())
    start_time = end_time - 86400  # 24 hours ago

    query = "event_type = NETWORK_CONNECTIONS AND routing.hostname contains 'web-server'"

    print(f"Validating query: {query}")

    # Validate the search
    validation = man.validateSearch(query, start_time, end_time)

    print("\nValidation result:")
    print(json.dumps(validation, indent=2))

    # Check for errors
    if validation.get('error'):
        print(f"\n❌ Query validation failed: {validation['error']}")
        return False

    # Print estimated price
    estimated_price = validation.get('estimatedPrice', {})
    if estimated_price:
        price = estimated_price.get('value', 0)
        currency = estimated_price.get('currency', 'USD')
        print(f"\n✓ Estimated price: {price:.4f} {currency}")

    return True


def example_search_to_csv():
    """
    Example: Export search results to CSV format.

    Parameters:
        None

    Return:
        None
    """
    print("\n=== Example 3: Export Results to CSV ===")

    man = limacharlie.Manager()

    # Search for detection events in the last 24 hours
    end_time = int(time.time())
    start_time = end_time - 86400

    query = "event_type = DETECTION"
    output_file = "search_results.csv"

    print(f"Query: {query}")
    print(f"Output file: {output_file}")

    # Open CSV file for writing
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        csv_writer = None
        result_count = 0

        # Execute search and write results to CSV
        for result in man.executeSearch(query, start_time, end_time, stream='detect'):
            result_count += 1

            # Flatten the result for CSV export
            # Extract key fields - customize based on your needs
            flat_result = flatten_result(result)

            # Initialize CSV writer with headers from first result
            if csv_writer is None:
                fieldnames = flat_result.keys()
                csv_writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                csv_writer.writeheader()

            # Write the result
            csv_writer.writerow(flat_result)

            # Print progress every 100 results
            if result_count % 100 == 0:
                print(f"Processed {result_count} results...")

    print(f"\n✓ Exported {result_count} results to {output_file}")


def example_search_to_compressed_csv():
    """
    Example: Export search results to compressed CSV (gzip).

    This is useful for large result sets to save disk space.

    Parameters:
        None

    Return:
        None
    """
    print("\n=== Example 4: Export Results to Compressed CSV ===")

    man = limacharlie.Manager()

    # Search for all events in the last hour
    end_time = int(time.time())
    start_time = end_time - 3600

    query = "event_type = *"  # All event types
    output_file = "search_results.csv.gz"

    print(f"Query: {query}")
    print(f"Output file: {output_file}")

    # Open compressed CSV file for writing
    with gzip.open(output_file, 'wt', newline='', encoding='utf-8') as csvfile:
        csv_writer = None
        result_count = 0

        # Execute search and write results to compressed CSV
        for result in man.executeSearch(query, start_time, end_time):
            result_count += 1

            # Flatten the result
            flat_result = flatten_result(result)

            # Initialize CSV writer with headers from first result
            if csv_writer is None:
                fieldnames = flat_result.keys()
                csv_writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                csv_writer.writeheader()

            # Write the result
            csv_writer.writerow(flat_result)

            # Print progress
            if result_count % 100 == 0:
                print(f"Processed {result_count} results...")

    print(f"\n✓ Exported {result_count} results to {output_file}")

    # Show file size comparison
    import os
    compressed_size = os.path.getsize(output_file)
    print(f"Compressed file size: {compressed_size:,} bytes ({compressed_size / 1024 / 1024:.2f} MB)")


def example_advanced_search():
    """
    Example: Advanced search with custom polling configuration.

    Parameters:
        None

    Return:
        None
    """
    print("\n=== Example 5: Advanced Search with Custom Settings ===")

    man = limacharlie.Manager()

    # Search for network connections in the last 6 hours
    end_time = int(time.time())
    start_time = end_time - (6 * 3600)

    query = """
    event_type = NETWORK_CONNECTIONS
    AND routing.hostname contains 'database'
    """

    print(f"Query: {query.strip()}")

    # Execute search with custom polling settings
    # - max_poll_attempts: Maximum polling attempts per page
    # - poll_interval: Seconds between poll attempts
    result_count = 0
    for result in man.executeSearch(
        query,
        start_time,
        end_time,
        stream='event',  # Specify the stream
        max_poll_attempts=500,  # Allow more attempts for longer queries
        poll_interval=3  # Wait 3 seconds between polls
    ):
        result_count += 1

    print(f"\nTotal results: {result_count}")


def flatten_result(result):
    """
    Flatten a nested result object for CSV export.

    This function extracts common fields from search results.
    Customize this based on your specific needs.

    Parameters:
        result (dict): The search result object to flatten.

    Return:
        dict: Flattened result with string values.
    """
    flat = {}

    # Check if this is an events result
    if isinstance(result, dict) and result.get('type') == 'events':
        # Handle events result type
        rows = result.get('rows', [])
        if rows:
            # For events results, we'll export the first row
            # In production, you might want to handle multiple rows differently
            row = rows[0] if isinstance(rows, list) else rows
            flat = flatten_dict(row)
    elif isinstance(result, dict):
        # Handle other result types (detections, etc.)
        flat = flatten_dict(result)
    else:
        flat = {'data': str(result)}

    return flat


def example_search_with_progress_tracking():
    """
    Example: Search with progress tracking callback.

    Demonstrates how to show progress while search is running.

    Parameters:
        None

    Return:
        None
    """
    print("\n=== Example 7: Search with Progress Tracking ===")

    man = limacharlie.Manager()

    end_time = int(time.time())
    start_time = end_time - 3600  # 1 hour ago

    query = "event_type = NEW_PROCESS"

    print(f"Query: {query}")
    print("Progress: ", end="", flush=True)

    # Progress counter
    poll_count = [0]

    def show_progress():
        poll_count[0] += 1
        if poll_count[0] % 5 == 0:  # Print every 5th poll
            print(".", end="", flush=True)

    # Execute search with progress callback
    result_count = 0
    for result in man.executeSearch(
        query,
        start_time,
        end_time,
        progress_callback=show_progress
    ):
        result_count += 1

    print(f"\n✓ Search completed! Polled {poll_count[0]} times, got {result_count} results")


def example_search_detections_to_csv():
    """
    Example: Export detection results to CSV with specific fields.

    Parameters:
        None

    Return:
        None
    """
    print("\n=== Example 6: Export Detections to CSV ===")

    man = limacharlie.Manager()

    # Search for detections in the last 7 days
    end_time = int(time.time())
    start_time = end_time - (7 * 86400)

    query = "event_type = DETECTION"
    output_file = "detections.csv"

    print(f"Query: {query}")
    print(f"Output file: {output_file}")

    # Define specific fields we want to export
    fieldnames = [
        'timestamp',
        'detect_id',
        'cat',
        'routing_hostname',
        'routing_sid',
        'routing_oid',
        'detect_rule_name',
        'detect_summary',
    ]

    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        csv_writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        csv_writer.writeheader()

        result_count = 0

        for result in man.executeSearch(query, start_time, end_time, stream='detect'):
            result_count += 1

            # Extract specific fields for detections
            row = {}

            # Handle both nested result structures
            if isinstance(result, dict):
                if result.get('type') == 'events':
                    # Unwrap events type
                    rows = result.get('rows', [])
                    if rows:
                        result = rows[0] if isinstance(rows, list) else rows

                # Extract common detection fields
                row['timestamp'] = result.get('routing', {}).get('event_time', '')
                row['detect_id'] = result.get('routing', {}).get('log_id', '')
                row['cat'] = result.get('detect', {}).get('cat', '')
                row['routing_hostname'] = result.get('routing', {}).get('hostname', '')
                row['routing_sid'] = result.get('routing', {}).get('sid', '')
                row['routing_oid'] = result.get('routing', {}).get('oid', '')
                row['detect_rule_name'] = result.get('detect', {}).get('name', '')

                # Summary might be nested
                summary = result.get('detect', {}).get('summary', '')
                if isinstance(summary, dict):
                    summary = json.dumps(summary)
                row['detect_summary'] = summary

            csv_writer.writerow(row)

            if result_count % 50 == 0:
                print(f"Processed {result_count} detections...")

    print(f"\n✓ Exported {result_count} detections to {output_file}")


def main():
    """
    Main function to run all examples.

    Parameters:
        None

    Return:
        None
    """
    print("=" * 60)
    print("LimaCharlie Search API Demo")
    print("=" * 60)

    try:
        # Run examples
        # Comment out examples you don't want to run

        # Example 1: Basic search
        # example_basic_search()

        # Example 2: Validate query
        example_validate_search()

        # Example 3: Export to CSV
        # example_search_to_csv()

        # Example 4: Export to compressed CSV
        # example_search_to_compressed_csv()

        # Example 5: Advanced search
        # example_advanced_search()

        # Example 6: Export detections to CSV
        # example_search_detections_to_csv()

        print("\n" + "=" * 60)
        print("Demo complete!")
        print("=" * 60)

    except limacharlie.utils.LcApiException as e:
        print(f"\n❌ API Error: {e}", file=sys.stderr)
        if hasattr(e, 'code'):
            print(f"Status code: {e.code}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
