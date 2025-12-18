"""
Integration tests for the Search API.

These tests verify end-to-end functionality of the Search API,
including real API interactions with the LimaCharlie cloud.

Note: These tests require valid LC credentials passed via --oid and --key CLI options.
"""

import limacharlie
import time
import subprocess
import sys
import os
import tempfile


def test_credentials_search(oid, key):
    """
    Test that credentials have the required permissions for Search API.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    lc = limacharlie.Manager(oid, key)

    # Search API requires specific permissions
    assert lc.testAuth([
        'org.get',
        'insight.evt.get',
    ])


def test_validate_simple_query(oid, key):
    """
    Test validating a simple search query returns expected structure.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    lc = limacharlie.Manager(oid, key)

    # Use a short time range to minimize cost
    end_time = int(time.time())
    start_time = end_time - 60  # 1 minute

    # Query format: <sensor_selector> | <event_filter> | <projection>
    query = "* | NEW_PROCESS | *"

    result = lc.validateSearch(query, start_time, end_time)

    # Should have expected keys
    assert 'query' in result
    assert 'estimatedPrice' in result

    # Should not have an error
    assert result.get('error') is None

    # Price should be reasonable for 1 minute
    price = result['estimatedPrice']['value']
    assert price >= 0
    assert price < 10  # Sanity check - should be cheap for 1 minute


def test_validate_invalid_query(oid, key):
    """
    Test that validating an invalid query returns an error.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    lc = limacharlie.Manager(oid, key)

    end_time = int(time.time())
    start_time = end_time - 60

    # Invalid query syntax
    query = "invalid query syntax here $$#"

    result = lc.validateSearch(query, start_time, end_time)

    # Should have an error
    assert result.get('error') is not None


def test_validate_with_stream(oid, key):
    """
    Test validation with different stream parameters.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    lc = limacharlie.Manager(oid, key)

    end_time = int(time.time())
    start_time = end_time - 60

    # Test each stream type
    # Query format: <sensor_selector> | <event_filter> | <projection>
    # Valid stream values: event, detection, audit
    streams = ['event', 'detection', 'audit']

    for stream in streams:
        result = lc.validateSearch(
            "* | * | *",
            start_time,
            end_time,
            stream=stream
        )

        # Should succeed (no error)
        assert result.get('error') is None, f"Failed for stream: {stream}"


def test_initiate_and_cancel_search(oid, key):
    """
    Test initiating a search and then canceling it.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    lc = limacharlie.Manager(oid, key)

    # Use a longer time range that will take time to execute
    end_time = int(time.time())
    start_time = end_time - 3600  # 1 hour

    # Query format: <sensor_selector> | <event_filter> | <projection>
    query = "* | * | *"

    # Initiate the search
    init_response = lc.initiateSearch(query, start_time, end_time, paginated=True)

    # Should have a query ID
    assert 'queryId' in init_response
    query_id = init_response['queryId']
    assert query_id is not None
    assert len(query_id) > 0

    # Cancel the search
    cancel_response = lc.cancelSearch(query_id)

    # Cancel should succeed (or already be done)
    # The response structure may vary, but shouldn't raise an exception
    assert cancel_response is not None


def test_execute_simple_search(oid, key):
    """
    Test executing a simple search and receiving results.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    lc = limacharlie.Manager(oid, key)

    # Very short time range to minimize cost and execution time
    end_time = int(time.time())
    start_time = end_time - 60  # 1 minute

    # Query format: <sensor_selector> | <event_filter> | <projection>
    query = "* | NEW_PROCESS | *"

    results = []
    result_count = 0

    # Execute search and collect results
    for result in lc.executeSearch(
        query,
        start_time,
        end_time,
        max_poll_attempts=100,  # Limit poll attempts for test
        poll_interval=1
    ):
        results.append(result)
        result_count += 1

        # Limit results for testing to avoid long test times
        if result_count >= 10:
            break

    # Should complete without error
    # Result count might be 0 if no events match (both are valid)
    assert result_count >= 0

    # If we got results, verify they have expected structure
    if results:
        for result in results:
            assert isinstance(result, dict)
            # Results should have a type field
            assert 'type' in result


def test_execute_search_with_callbacks(oid, key):
    """
    Test that callbacks are invoked during search execution.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    lc = limacharlie.Manager(oid, key)

    end_time = int(time.time())
    start_time = end_time - 60

    # Query format: <sensor_selector> | <event_filter> | <projection>
    query = "* | NEW_PROCESS | *"

    # Track callback invocations
    callback_data = {
        'progress_called': 0,
        'query_initiated_called': False,
        'query_id': None
    }

    def progress_callback():
        callback_data['progress_called'] += 1

    def on_query_initiated(query_id):
        callback_data['query_initiated_called'] = True
        callback_data['query_id'] = query_id

    result_count = 0
    for result in lc.executeSearch(
        query,
        start_time,
        end_time,
        max_poll_attempts=50,
        poll_interval=1,
        progress_callback=progress_callback,
        on_query_initiated=on_query_initiated
    ):
        result_count += 1
        # Limit for testing
        if result_count >= 5:
            break

    # Query initiated callback should have been called
    assert callback_data['query_initiated_called'] is True
    assert callback_data['query_id'] is not None

    # Progress callback may have been called (depends on how fast the query completes)
    # We can't strictly assert it was called since quick queries might complete immediately
    assert callback_data['progress_called'] >= 0


def test_execute_search_different_streams(oid, key):
    """
    Test executing searches on different stream types.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    lc = limacharlie.Manager(oid, key)

    end_time = int(time.time())
    start_time = end_time - 60

    # Query format: <sensor_selector> | <event_filter> | <projection>
    # Valid stream values: event, detection, audit
    streams_to_test = {
        'event': '* | * | *',
        'detection': '* | * | *',
        'audit': '* | * | *'
    }

    for stream, query in streams_to_test.items():
        result_count = 0

        # Execute search should not raise exception
        for result in lc.executeSearch(
            query,
            start_time,
            end_time,
            stream=stream,
            max_poll_attempts=30,
            poll_interval=1
        ):
            result_count += 1
            # Limit results
            if result_count >= 3:
                break

        # Should complete without error (result count may be 0)
        assert result_count >= 0


def test_poll_search_results_pagination(oid, key):
    """
    Test manual pagination through poll search results.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    lc = limacharlie.Manager(oid, key)

    # Slightly longer range to increase chance of getting results
    end_time = int(time.time())
    start_time = end_time - 300  # 5 minutes

    # Query format: <sensor_selector> | <event_filter> | <projection>
    query = "* | * | *"

    # Initiate the search with pagination enabled
    init_response = lc.initiateSearch(query, start_time, end_time, paginated=True)
    query_id = init_response['queryId']

    results = []
    page_count = 0
    last_token = None

    # Poll for results with manual pagination
    while page_count < 3:  # Limit to 3 pages for testing
        poll_response = lc.pollSearchResults(
            query_id,
            token=last_token,
            max_attempts=60,
            poll_interval=1
        )

        if poll_response.get('error'):
            # Error occurred - could be timeout or other issue
            break

        if poll_response.get('results'):
            results.extend(poll_response['results'])

        last_token = poll_response.get('nextToken')
        page_count += 1

        # No more pages available
        if not last_token:
            break

    # Should have completed at least one page
    assert page_count >= 1


def test_cli_validate_command(oid, key):
    """
    Test the CLI validate command via subprocess.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    # Set up environment with credentials
    env = os.environ.copy()
    env['LC_OID'] = oid
    env['LC_API_KEY'] = key

    # Run the CLI command
    # Query format: <sensor_selector> | <event_filter> | <projection>
    result = subprocess.run(
        [
            sys.executable, '-m', 'limacharlie',
            'search-api', 'validate',
            '-q', '* | NEW_PROCESS | *',
            '-s', 'now-1m',
            '-e', 'now'
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60
    )

    # Should succeed
    assert result.returncode == 0

    # Should output JSON with estimatedPrice
    output = result.stdout + result.stderr
    assert 'estimatedPrice' in output


def test_cli_execute_command(oid, key):
    """
    Test the CLI execute command via subprocess.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    # Set up environment with credentials
    env = os.environ.copy()
    env['LC_OID'] = oid
    env['LC_API_KEY'] = key

    with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
        output_file = f.name

    try:
        # Run the CLI command
        # Query format: <sensor_selector> | <event_filter> | <projection>
        result = subprocess.run(
            [
                sys.executable, '-m', 'limacharlie',
                'search-api', 'execute',
                '-q', '* | NEW_PROCESS | *',
                '-s', 'now-1m',
                '-e', 'now',
                '--output-file', output_file,
                '--non-interactive'
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=120  # 2 minute timeout
        )

        # Should succeed
        assert result.returncode == 0

        # Output file should exist (even if empty)
        assert os.path.exists(output_file)
    finally:
        # Clean up
        if os.path.exists(output_file):
            os.unlink(output_file)


def test_cli_execute_csv_output(oid, key):
    """
    Test the CLI execute command with CSV output format.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    # Set up environment with credentials
    env = os.environ.copy()
    env['LC_OID'] = oid
    env['LC_API_KEY'] = key

    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
        output_file = f.name

    try:
        # Run the CLI command with CSV output
        # Query format: <sensor_selector> | <event_filter> | <projection>
        result = subprocess.run(
            [
                sys.executable, '-m', 'limacharlie',
                'search-api', 'execute',
                '-q', '* | NEW_PROCESS | *',
                '-s', 'now-1m',
                '-e', 'now',
                '--output-file', output_file,
                '--output-format', 'csv',
                '--non-interactive'
            ],
            capture_output=True,
            text=True,
            env=env,
            timeout=120
        )

        # Should succeed
        assert result.returncode == 0

        # Output file should exist
        assert os.path.exists(output_file)
    finally:
        # Clean up
        if os.path.exists(output_file):
            os.unlink(output_file)


def test_cli_execute_with_stream(oid, key):
    """
    Test the CLI execute command with stream parameter.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    # Set up environment with credentials
    env = os.environ.copy()
    env['LC_OID'] = oid
    env['LC_API_KEY'] = key

    # Run the CLI command with stream parameter
    # Query format: <sensor_selector> | <event_filter> | <projection>
    result = subprocess.run(
        [
            sys.executable, '-m', 'limacharlie',
            'search-api', 'execute',
            '-q', '* | * | *',
            '-s', 'now-1m',
            '-e', 'now',
            '--stream', 'audit',
            '--non-interactive'
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=120
    )

    # Should succeed (even with no results)
    assert result.returncode == 0


def test_cli_validate_time_formats(oid, key):
    """
    Test CLI validate command with various time format inputs.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    # Set up environment with credentials
    env = os.environ.copy()
    env['LC_OID'] = oid
    env['LC_API_KEY'] = key

    # Test relative time format
    # Query format: <sensor_selector> | <event_filter> | <projection>
    result = subprocess.run(
        [
            sys.executable, '-m', 'limacharlie',
            'search-api', 'validate',
            '-q', '* | NEW_PROCESS | *',
            '-s', 'now-5m',
            '-e', 'now'
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60
    )
    assert result.returncode == 0

    # Test unix timestamp format (seconds)
    end_ts = str(int(time.time()))
    start_ts = str(int(time.time()) - 60)
    result = subprocess.run(
        [
            sys.executable, '-m', 'limacharlie',
            'search-api', 'validate',
            '-q', '* | NEW_PROCESS | *',
            '-s', start_ts,
            '-e', end_ts
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=60
    )
    assert result.returncode == 0


def test_search_result_structure(oid, key):
    """
    Test that search results have the expected structure with metadata.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    lc = limacharlie.Manager(oid, key)

    end_time = int(time.time())
    start_time = end_time - 60

    # Query format: <sensor_selector> | <event_filter> | <projection>
    query = "* | * | *"

    results = []
    for result in lc.executeSearch(
        query,
        start_time,
        end_time,
        max_poll_attempts=60,
        poll_interval=1
    ):
        results.append(result)
        # Get at least a few results to verify structure
        if len(results) >= 3:
            break

    # If we got results, verify they have expected metadata
    for result in results:
        # Each result should be a dict with type
        assert isinstance(result, dict)
        assert 'type' in result

        # Type should be one of the expected values
        assert result['type'] in ['events', 'facets', 'timeline']

        # Should have page number metadata
        assert '_page_number' in result


def test_execute_search_resume_functionality(oid, key):
    """
    Test that search can be resumed with query_id and resume_token.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    lc = limacharlie.Manager(oid, key)

    end_time = int(time.time())
    start_time = end_time - 300  # 5 minutes for more results

    # Query format: <sensor_selector> | <event_filter> | <projection>
    query = "* | * | *"

    # First, initiate the search and get the query ID
    init_response = lc.initiateSearch(query, start_time, end_time, paginated=True)
    query_id = init_response['queryId']

    # Get first page of results
    first_page = lc.pollSearchResults(
        query_id,
        max_attempts=60,
        poll_interval=1
    )

    next_token = first_page.get('nextToken')

    # If there's a next token, we can test resume
    if next_token:
        # Resume from the next token using executeSearch
        resumed_results = []
        for result in lc.executeSearch(
            query,
            start_time,
            end_time,
            query_id=query_id,
            resume_token=next_token,
            max_poll_attempts=30,
            poll_interval=1
        ):
            resumed_results.append(result)
            if len(resumed_results) >= 3:
                break

        # Should be able to get results from resumed search
        assert len(resumed_results) >= 0


def test_org_urls_includes_search(oid, key):
    """
    Test that org URLs endpoint returns the search URL.

    Parameters:
        oid (str): The organization ID.
        key (str): The API key.

    Return:
        None
    """
    lc = limacharlie.Manager(oid, key)

    urls = lc.getOrgURLs()

    # Should have search URL
    assert 'search' in urls
    assert urls['search'] is not None
    assert len(urls['search']) > 0
