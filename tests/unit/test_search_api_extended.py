"""
Extended unit tests for the Search API functionality.

Additional test coverage for:
- Different result types (events, facets, timeline, aggregations)
- Complex pagination scenarios
- Stream-specific behavior
- Error recovery
- Edge cases and boundary conditions
- Performance scenarios
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import json
import time
from io import StringIO


class TestSearchAPIValidation:
    """Test validation-specific scenarios."""

    def test_validate_search_with_error_response(self):
        """Test validation with error in response."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock validation error
        error_response = {
            'query': 'invalid syntax here',
            'error': 'Syntax error: unexpected token at position 8',
            'startTime': 1234567890,
            'endTime': 1234567900
        }
        manager._apiCall = Mock(return_value=error_response)

        result = manager.validateSearch('invalid syntax here', 1234567890, 1234567900)

        assert result['error'] == 'Syntax error: unexpected token at position 8'

    def test_validate_search_with_high_price(self):
        """Test validation returning high estimated price."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        high_price_response = {
            'query': 'event_type = *',
            'startTime': 1234567890,
            'endTime': 1734567890,  # Large range
            'estimatedPrice': {
                'value': 125.50,
                'currency': 'USD'
            }
        }
        manager._apiCall = Mock(return_value=high_price_response)

        result = manager.validateSearch('event_type = *', 1234567890, 1734567890)

        assert result['estimatedPrice']['value'] == 125.50

    def test_validate_search_different_streams(self):
        """Test validation with different stream parameters."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')
        manager._apiCall = Mock(return_value={'query': 'test', 'estimatedPrice': {'value': 0.01, 'currency': 'USD'}})

        # Test each stream type
        for stream in ['event', 'detect', 'audit']:
            manager.validateSearch('test query', 1000, 2000, stream=stream)

            call_args = manager._apiCall.call_args
            raw_body = call_args[1]['rawBody']
            request_data = json.loads(raw_body.decode())

            assert request_data['stream'] == stream

    def test_validate_search_zero_price(self):
        """Test validation with zero estimated price."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        zero_price_response = {
            'query': 'event_type = NEW_PROCESS',
            'startTime': 1234567890,
            'endTime': 1234567891,  # Very small range
            'estimatedPrice': {
                'value': 0.0,
                'currency': 'USD'
            }
        }
        manager._apiCall = Mock(return_value=zero_price_response)

        result = manager.validateSearch('event_type = NEW_PROCESS', 1234567890, 1234567891)

        assert result['estimatedPrice']['value'] == 0.0


class TestSearchAPIInitiate:
    """Test search initiation scenarios."""

    def test_initiate_search_different_streams(self):
        """Test initiating searches with different streams."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')
        manager._apiCall = Mock(return_value={'queryId': 'query-123'})

        for stream in ['event', 'detect', 'audit', None]:
            manager.initiateSearch('test', 1000, 2000, stream=stream)

            call_args = manager._apiCall.call_args
            raw_body = call_args[1]['rawBody']
            request_data = json.loads(raw_body.decode())

            if stream is None:
                assert 'stream' not in request_data
            else:
                assert request_data['stream'] == stream

    def test_initiate_search_api_error(self):
        """Test initiate search with API error."""
        from limacharlie import Manager
        from limacharlie.utils import LcApiException

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock API error
        manager._apiCall = Mock(side_effect=LcApiException('API Error: Rate limit exceeded', code=429))

        with pytest.raises(LcApiException) as exc_info:
            manager.initiateSearch('test', 1000, 2000)

        assert 'Rate limit exceeded' in str(exc_info.value)
        assert exc_info.value.code == 429


class TestSearchAPIPollResults:
    """Test polling result scenarios."""

    def test_poll_results_empty_results(self):
        """Test polling with empty results."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        empty_response = {
            'completed': True,
            'results': [],
            'nextToken': None
        }
        manager._apiCall = Mock(return_value=empty_response)

        result = manager.pollSearchResults('query-123')

        assert result['completed'] == True
        assert result['results'] == []
        assert result.get('nextToken') is None

    def test_poll_results_various_next_poll_times(self):
        """Test polling with various nextPollInMs values."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Test with different poll times
        poll_times = [100, 500, 1000, 5000]

        for poll_ms in poll_times:
            responses = [
                {'completed': False, 'nextPollInMs': poll_ms},
                {'completed': True, 'results': []}
            ]
            manager._apiCall = Mock(side_effect=responses)

            with patch('time.sleep') as mock_sleep:
                result = manager.pollSearchResults('query-123', poll_interval=1)

                # Verify sleep was called with appropriate time
                mock_sleep.assert_called()
                sleep_duration = mock_sleep.call_args[0][0]
                # Should use the larger of poll_ms/1000 or poll_interval
                expected = max(poll_ms / 1000.0, 1)
                assert sleep_duration == expected

    def test_poll_results_with_empty_token(self):
        """Test polling with empty string token (treated as None)."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')
        manager._apiCall = Mock(return_value={'completed': True, 'results': []})

        # Empty string token should be treated same as None
        result = manager.pollSearchResults('query-123', token='')

        call_args = manager._apiCall.call_args
        query_params = call_args[1]['queryParams']

        # Empty token should not be included in query params
        assert 'token' not in query_params or query_params['token'] == ''

    def test_poll_results_gradual_completion(self):
        """Test polling that gradually completes."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Simulate gradual completion
        responses = [
            {'completed': False, 'nextPollInMs': 100},
            {'completed': False, 'nextPollInMs': 200},
            {'completed': False, 'nextPollInMs': 300},
            {'completed': False, 'nextPollInMs': 400},
            {'completed': True, 'results': [{'data': 'final'}]}
        ]
        manager._apiCall = Mock(side_effect=responses)

        with patch('time.sleep'):
            result = manager.pollSearchResults('query-123', max_attempts=10)

        assert result['completed'] == True
        assert len(result['results']) == 1
        assert manager._apiCall.call_count == 5


class TestSearchAPIExecute:
    """Test complete search execution scenarios."""

    def test_execute_search_with_different_result_types(self):
        """Test executeSearch with various result types."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock initiateSearch
        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})

        # Test different result structures
        # Note: nextToken is in the LAST result object
        result_types = [
            # Events
            [{'type': 'events', 'rows': [{'event_id': '1'}], 'nextToken': None}],
            # Facets
            [{'type': 'facets', 'facets': [{'name': 'hostname', 'count': 10}], 'nextToken': None}],
            # Timeline
            [{'type': 'timeline', 'timeseries': [{'timestamp': 1234567890, 'value': 5}], 'nextToken': None}],
            # Mixed
            [
                {'type': 'events', 'rows': [{'event_id': '1'}], 'nextToken': None},
                {'type': 'facets', 'facets': [{'name': 'user', 'count': 3}], 'nextToken': None}
            ]
        ]

        for result_structure in result_types:
            manager.pollSearchResults = Mock(return_value={
                'completed': True,
                'results': result_structure
            })

            results = list(manager.executeSearch('test', 1000, 2000))

            assert len(results) == len(result_structure)

    def test_execute_search_large_result_set(self):
        """Test executeSearch with many pages."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})

        # Simulate 10 pages of results
        # Note: nextToken is in the LAST result object of each page
        page_count = 10
        poll_responses = []

        for i in range(page_count):
            is_last = (i == page_count - 1)
            results_list = []

            # Create 100 items per page
            for j in range(100):
                result_obj = {'page': i, 'item': j}
                # Put nextToken in the LAST result object
                if j == 99:  # Last item in this page
                    result_obj['nextToken'] = None if is_last else f'token-page-{i+1}'
                else:
                    result_obj['nextToken'] = None
                results_list.append(result_obj)

            poll_responses.append({
                'completed': True,
                'results': results_list
            })

        manager.pollSearchResults = Mock(side_effect=poll_responses)

        results = list(manager.executeSearch('test', 1000, 2000))

        # Should have 10 pages * 100 items = 1000 results
        assert len(results) == 1000
        # Verify pollSearchResults was called 10 times
        assert manager.pollSearchResults.call_count == 10

    def test_execute_search_with_stream_parameter(self):
        """Test executeSearch passes stream parameter correctly."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})
        manager.pollSearchResults = Mock(return_value={
            'completed': True,
            'results': []
        })

        # Test with different streams
        for stream in ['event', 'detect', 'audit']:
            list(manager.executeSearch('test', 1000, 2000, stream=stream))

            # Verify initiateSearch was called with correct stream
            call_kwargs = manager.initiateSearch.call_args[1]
            assert call_kwargs['stream'] == stream

    def test_execute_search_early_termination(self):
        """Test executeSearch when generator is not fully consumed."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})

        # Set up multiple pages
        # Note: nextToken is in the LAST result object of each page
        page1_results = []
        for i in range(100):
            result_obj = {'id': i}
            if i == 99:  # Last result
                result_obj['nextToken'] = 'token-2'
            else:
                result_obj['nextToken'] = None
            page1_results.append(result_obj)

        page2_results = []
        for i in range(100, 200):
            result_obj = {'id': i}
            if i == 199:  # Last result
                result_obj['nextToken'] = 'token-3'
            else:
                result_obj['nextToken'] = None
            page2_results.append(result_obj)

        page3_results = []
        for i in range(200, 300):
            result_obj = {'id': i}
            if i == 299:  # Last result
                result_obj['nextToken'] = None
            else:
                result_obj['nextToken'] = None
            page3_results.append(result_obj)

        poll_responses = [
            {'completed': True, 'results': page1_results},
            {'completed': True, 'results': page2_results},
            {'completed': True, 'results': page3_results}
        ]
        manager.pollSearchResults = Mock(side_effect=poll_responses)

        # Only consume first 50 results
        results = []
        for i, result in enumerate(manager.executeSearch('test', 1000, 2000)):
            results.append(result)
            if i >= 49:  # Stop after 50 results
                break

        assert len(results) == 50
        # Should only have called pollSearchResults once (first page)
        assert manager.pollSearchResults.call_count == 1

    def test_execute_search_custom_polling_config(self):
        """Test executeSearch with custom polling configuration."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})
        manager.pollSearchResults = Mock(return_value={
            'completed': True,
            'results': []
        })

        # Execute with custom settings
        list(manager.executeSearch(
            'test',
            1000,
            2000,
            max_poll_attempts=500,
            poll_interval=5
        ))

        # Verify custom settings were passed to pollSearchResults
        call_kwargs = manager.pollSearchResults.call_args[1]
        assert call_kwargs['max_attempts'] == 500
        assert call_kwargs['poll_interval'] == 5


class TestSearchAPICLIExtended:
    """Extended CLI command tests."""

    def test_cli_validate_with_time_formats(self, capsys):
        """Test validate command with various time formats."""
        from limacharlie.SearchAPI import main

        time_formats = [
            ('now-1h', 'now'),
            ('2025-12-30', '2025-12-31'),
            ('1234567890', '1234567900'),
        ]

        for start, end in time_formats:
            with patch('limacharlie.SearchAPI.Manager') as mock_manager_class:
                mock_manager = MagicMock()
                mock_manager_class.return_value = mock_manager

                mock_manager.validateSearch.return_value = {
                    'query': 'test',
                    'estimatedPrice': {'value': 0.01, 'currency': 'USD'}
                }

                # Run with this time format
                main(['validate', '-q', 'test', '-s', start, '-e', end])

                # Verify validateSearch was called with parsed timestamps
                mock_manager.validateSearch.assert_called_once()
                call_args = mock_manager.validateSearch.call_args[0]

                # Both should be integers (timestamps)
                assert isinstance(call_args[1], int)
                assert isinstance(call_args[2], int)

    def test_cli_execute_with_stream_option(self, capsys):
        """Test execute command with stream option."""
        from limacharlie.SearchAPI import main

        with patch('limacharlie.SearchAPI.Manager') as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            mock_manager.executeSearch.return_value = iter([])

            for stream in ['event', 'detect', 'audit']:
                main(['execute', '-q', 'test', '-s', '1000', '-e', '2000', '--stream', stream])

                call_kwargs = mock_manager.executeSearch.call_args[1]
                assert call_kwargs['stream'] == stream

    def test_cli_execute_with_custom_poll_settings(self, capsys):
        """Test execute command with custom polling settings."""
        from limacharlie.SearchAPI import main

        with patch('limacharlie.SearchAPI.Manager') as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            mock_manager.executeSearch.return_value = iter([])

            main([
                'execute',
                '-q', 'test',
                '-s', '1000',
                '-e', '2000',
                '--max-poll-attempts', '500',
                '--poll-interval', '5'
            ])

            call_kwargs = mock_manager.executeSearch.call_args[1]
            assert call_kwargs['max_poll_attempts'] == 500
            assert call_kwargs['poll_interval'] == 5

    def test_cli_execute_pretty_output(self, capsys):
        """Test execute command with pretty output."""
        from limacharlie.SearchAPI import main

        with patch('limacharlie.SearchAPI.Manager') as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            # Mock executeSearch with properly structured results
            mock_manager.executeSearch.return_value = iter([
                {
                    'type': 'events',
                    'rows': [{'event_id': '1', 'data': 'test'}],
                    'nextToken': None,
                    '_page_number': 1,
                    '_first_of_type_in_page': True,
                    '_billing_stats': {}
                }
            ])

            main(['execute', '-q', 'test', '-s', '1000', '-e', '2000', '--pretty'])

            captured = capsys.readouterr()

            # Pretty output should have indentation
            assert '  "event_id"' in captured.out or '    "event_id"' in captured.out

    def test_cli_validate_with_error(self, capsys):
        """Test validate command handling validation errors."""
        from limacharlie.SearchAPI import main

        with patch('limacharlie.SearchAPI.Manager') as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            mock_manager.validateSearch.return_value = {
                'query': 'invalid',
                'error': 'Syntax error in query'
            }

            with pytest.raises(SystemExit) as exc_info:
                main(['validate', '-q', 'invalid', '-s', '1000', '-e', '2000'])

            assert exc_info.value.code == 1

            captured = capsys.readouterr()
            assert 'Syntax error in query' in captured.err

    def test_cli_execute_with_api_exception(self, capsys):
        """Test execute command handling API exceptions."""
        from limacharlie.SearchAPI import main
        from limacharlie.utils import LcApiException

        with patch('limacharlie.SearchAPI.Manager') as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            mock_manager.executeSearch.side_effect = LcApiException('API Error')

            with pytest.raises(LcApiException):
                main(['execute', '-q', 'test', '-s', '1000', '-e', '2000'])

    def test_cli_validate_invalid_time_format(self, capsys):
        """Test validate command with invalid time format."""
        from limacharlie.SearchAPI import main

        with patch('limacharlie.SearchAPI.Manager') as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            with pytest.raises(SystemExit) as exc_info:
                main(['validate', '-q', 'test', '-s', 'invalid-time', '-e', 'now'])

            assert exc_info.value.code == 1

            captured = capsys.readouterr()
            assert 'Error parsing time' in captured.err

    def test_cli_execute_no_results(self, capsys):
        """Test execute command with no results."""
        from limacharlie.SearchAPI import main

        with patch('limacharlie.SearchAPI.Manager') as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            # Return empty iterator
            mock_manager.executeSearch.return_value = iter([])

            main(['execute', '-q', 'test', '-s', '1000', '-e', '2000'])

            captured = capsys.readouterr()
            # Check for event row count (should be 0)
            assert 'Event rows: 0' in captured.err


class TestSearchAPIIntegration:
    """Integration-style tests combining multiple components."""

    def test_full_workflow_validate_then_execute(self):
        """Test full workflow: validate, then execute."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Step 1: Validate
        manager._apiCall = Mock(return_value={
            'query': 'event_type = NEW_PROCESS',
            'estimatedPrice': {'value': 0.01, 'currency': 'USD'}
        })

        validation = manager.validateSearch('event_type = NEW_PROCESS', 1000, 2000)
        assert validation['estimatedPrice']['value'] == 0.01

        # Step 2: Execute
        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})
        manager.pollSearchResults = Mock(return_value={
            'completed': True,
            'results': [{'event_id': '1', 'nextToken': None}]
        })

        results = list(manager.executeSearch('event_type = NEW_PROCESS', 1000, 2000))
        assert len(results) == 1

    def test_pagination_with_mixed_result_sizes(self):
        """Test pagination with varying result sizes per page."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})

        # Different sized pages
        # Note: nextToken is in the LAST result object of each page
        def create_page(count, next_token):
            results = []
            for i in range(count):
                result_obj = {'id': i}
                if i == count - 1:  # Last result
                    result_obj['nextToken'] = next_token
                else:
                    result_obj['nextToken'] = None
                results.append(result_obj)
            return {'completed': True, 'results': results}

        poll_responses = [
            create_page(100, 'token-2'),
            create_page(50, 'token-3'),
            create_page(200, 'token-4'),
            create_page(10, None)
        ]
        manager.pollSearchResults = Mock(side_effect=poll_responses)

        results = list(manager.executeSearch('test', 1000, 2000))

        # Total: 100 + 50 + 200 + 10 = 360 results
        assert len(results) == 360
        assert manager.pollSearchResults.call_count == 4


class TestPaginationPersistence:
    """Test pagination persistence features."""

    def test_execute_search_with_resume_token(self):
        """
        Test executing search with resume_token to skip already-processed pages.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid"
        manager._getSearchUrl = Mock(return_value='https://search.test/v1')

        # Mock poll response with results
        poll_response = {
            'completed': True,
            'results': [
                {
                    'type': 'events',
                    'rows': [{'event': 'data'}],
                    'nextToken': None
                }
            ]
        }
        manager.pollSearchResults = Mock(return_value=poll_response)

        # Execute with resume_token (should skip initiation)
        results = list(manager.executeSearch(
            "event_type = NEW_PROCESS",
            1234567890,
            1234567900,
            query_id="existing-query-id",
            resume_token="resume-token-123"
        ))

        # Verify pollSearchResults was called with the resume token
        assert manager.pollSearchResults.call_count == 1
        call_args = manager.pollSearchResults.call_args
        assert call_args[1]['token'] == "resume-token-123"

        # Verify results were yielded
        assert len(results) == 1
        assert results[0]['type'] == 'events'

    def test_on_page_completed_callback(self):
        """
        Test that on_page_completed callback is called with correct arguments.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid"
        manager._getSearchUrl = Mock(return_value='https://search.test/v1')
        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})

        # Mock two pages of results
        page1_response = {
            'completed': True,
            'results': [
                {
                    'type': 'events',
                    'rows': [{'event': '1'}],
                    'nextToken': 'token-page-2'
                }
            ]
        }
        page2_response = {
            'completed': True,
            'results': [
                {
                    'type': 'events',
                    'rows': [{'event': '2'}],
                    'nextToken': None  # Last page
                }
            ]
        }
        manager.pollSearchResults = Mock(side_effect=[page1_response, page2_response])

        # Track callback invocations
        callback_calls = []
        def on_page_completed(page_number, next_token):
            callback_calls.append((page_number, next_token))

        # Execute search
        results = list(manager.executeSearch(
            "test query",
            1234567890,
            1234567900,
            on_page_completed=on_page_completed
        ))

        # Verify callback was called twice (once per page)
        assert len(callback_calls) == 2
        assert callback_calls[0] == (1, 'token-page-2')  # First page with token
        assert callback_calls[1] == (2, None)  # Last page without token

    def test_on_query_initiated_callback(self):
        """
        Test that on_query_initiated callback receives the query_id.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid"
        manager._getSearchUrl = Mock(return_value='https://search.test/v1')
        manager.initiateSearch = Mock(return_value={'queryId': 'new-query-id-456'})
        manager.pollSearchResults = Mock(return_value={
            'completed': True,
            'results': [{'type': 'events', 'rows': [], 'nextToken': None}]
        })

        # Track query_id
        received_query_id = [None]
        def on_query_initiated(query_id):
            received_query_id[0] = query_id

        # Execute search
        list(manager.executeSearch(
            "test query",
            1234567890,
            1234567900,
            on_query_initiated=on_query_initiated
        ))

        # Verify callback received the query_id
        assert received_query_id[0] == 'new-query-id-456'

    def test_resume_with_query_id_skips_initiation(self):
        """
        Test that providing query_id skips search initiation.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid"
        manager._getSearchUrl = Mock(return_value='https://search.test/v1')
        manager.initiateSearch = Mock()  # Should not be called
        manager.pollSearchResults = Mock(return_value={
            'completed': True,
            'results': [{'type': 'events', 'rows': [], 'nextToken': None}]
        })

        # Execute with existing query_id
        list(manager.executeSearch(
            "test query",
            1234567890,
            1234567900,
            query_id="existing-id"
        ))

        # Verify initiateSearch was NOT called
        manager.initiateSearch.assert_not_called()


class TestCancelSearch:
    """Test cancelSearch functionality."""

    def test_cancel_search_basic(self):
        """
        Test basic cancelSearch operation.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._getSearchUrl = Mock(return_value='https://search.test/v1')
        manager._apiCall = Mock(return_value={'cancelled': True})

        # Cancel a search
        result = manager.cancelSearch('query-id-123')

        # Verify DELETE request was made
        manager._apiCall.assert_called_once()
        call_args = manager._apiCall.call_args
        assert call_args[0][0] == 'search/query-id-123'
        assert call_args[0][1] == 'DELETE'
        assert call_args[1]['altRoot'] == 'https://search.test/v1'

        # Verify response
        assert result == {'cancelled': True}


class TestNextTokenExtraction:
    """Test nextToken extraction from last result object."""

    def test_next_token_from_last_result(self):
        """
        Test that nextToken is extracted from the last result object.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid"
        manager._getSearchUrl = Mock(return_value='https://search.test/v1')
        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})

        # Mock response with multiple results and nextToken in LAST result
        page1_response = {
            'completed': True,
            'results': [
                {'type': 'events', 'rows': [{'e': '1'}], 'nextToken': None},  # First result
                {'type': 'events', 'rows': [{'e': '2'}], 'nextToken': None},  # Middle result
                {'type': 'events', 'rows': [{'e': '3'}], 'nextToken': 'next-page-token'}  # LAST result
            ]
        }
        page2_response = {
            'completed': True,
            'results': [
                {'type': 'events', 'rows': [{'e': '4'}], 'nextToken': None}
            ]
        }

        manager.pollSearchResults = Mock(side_effect=[page1_response, page2_response])

        # Execute search
        list(manager.executeSearch("test", 123, 456))

        # Verify second poll was called with token from LAST result
        assert manager.pollSearchResults.call_count == 2
        second_call = manager.pollSearchResults.call_args_list[1]
        assert second_call[1]['token'] == 'next-page-token'

    def test_no_token_when_empty_results(self):
        """
        Test pagination stops when results array is empty.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid"
        manager._getSearchUrl = Mock(return_value='https://search.test/v1')
        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})
        manager.pollSearchResults = Mock(return_value={
            'completed': True,
            'results': []  # Empty results
        })

        # Execute search
        results = list(manager.executeSearch("test", 123, 456))

        # Verify only one poll (no pagination)
        assert manager.pollSearchResults.call_count == 1
        assert len(results) == 0


class TestBillingStats:
    """Test billing stats extraction and metadata."""

    def test_billing_stats_in_result_metadata(self):
        """
        Test that billing stats are included in result metadata.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid"
        manager._getSearchUrl = Mock(return_value='https://search.test/v1')
        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})

        # Mock response with stats
        poll_response = {
            'completed': True,
            'stats': {
                'bytesScanned': 1024000,
                'eventsScanned': 5000,
                'eventsMatched': 100,
                'eventsProcessed': 100,
                'estimatedPrice': {'value': 0.0025, 'currency': 'USD'}
            },
            'results': [
                {'type': 'events', 'rows': [{'e': '1'}], 'nextToken': None}
            ]
        }
        manager.pollSearchResults = Mock(return_value=poll_response)

        # Execute search
        results = list(manager.executeSearch("test", 123, 456))

        # Verify stats are in metadata
        assert len(results) == 1
        assert '_billing_stats' in results[0]
        stats = results[0]['_billing_stats']
        assert stats['bytesScanned'] == 1024000
        assert stats['eventsScanned'] == 5000
        assert stats['estimatedPrice']['value'] == 0.0025


class TestCSVFlatteningWithDynamicFields:
    """Test CSV output with dynamic fields."""

    def test_flatten_dict_with_slash_separator(self):
        """
        Test that flatten_dict uses / separator for nested keys.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import flatten_dict

        nested_dict = {
            'data': {
                'event': {
                    'COMMAND_LINE': 'cmd.exe',
                    'USER_NAME': 'admin'
                },
                'routing': {
                    'parent': 'sensor-123'
                }
            },
            'simple_field': 'value'
        }

        flattened = flatten_dict(nested_dict)

        # Verify slash separator
        assert 'data/event/COMMAND_LINE' in flattened
        assert 'data/event/USER_NAME' in flattened
        assert 'data/routing/parent' in flattened
        assert 'simple_field' in flattened

        # Verify values
        assert flattened['data/event/COMMAND_LINE'] == 'cmd.exe'
        assert flattened['data/event/USER_NAME'] == 'admin'
        assert flattened['data/routing/parent'] == 'sensor-123'
        assert flattened['simple_field'] == 'value'

    def test_flatten_dict_with_lists(self):
        """
        Test that lists are converted to JSON strings.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import flatten_dict

        dict_with_list = {
            'tags': ['tag1', 'tag2', 'tag3'],
            'nested': {
                'array': [1, 2, 3]
            }
        }

        flattened = flatten_dict(dict_with_list)

        # Verify lists are JSON strings
        assert flattened['tags'] == '["tag1", "tag2", "tag3"]'
        assert flattened['nested/array'] == '[1, 2, 3]'

    def test_flatten_dict_empty_dict(self):
        """
        Test that empty dict returns empty dict.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import flatten_dict

        flattened = flatten_dict({})
        assert flattened == {}

    def test_flatten_dict_with_none_values(self):
        """
        Test that None values are converted to empty strings.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import flatten_dict

        dict_with_none = {
            'field1': None,
            'nested': {
                'field2': None,
                'field3': 'value'
            }
        }

        flattened = flatten_dict(dict_with_none)

        # None values should become empty strings
        assert flattened['field1'] == ''
        assert flattened['nested/field2'] == ''
        assert flattened['nested/field3'] == 'value'

    def test_flatten_dict_with_empty_lists(self):
        """
        Test that empty lists are converted to JSON strings.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import flatten_dict

        dict_with_empty_list = {
            'empty': [],
            'nested': {
                'also_empty': []
            }
        }

        flattened = flatten_dict(dict_with_empty_list)

        assert flattened['empty'] == '[]'
        assert flattened['nested/also_empty'] == '[]'

    def test_flatten_dict_deeply_nested(self):
        """
        Test deeply nested structures.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import flatten_dict

        deep_dict = {
            'level1': {
                'level2': {
                    'level3': {
                        'level4': {
                            'level5': 'deep_value'
                        }
                    }
                }
            }
        }

        flattened = flatten_dict(deep_dict)

        assert flattened['level1/level2/level3/level4/level5'] == 'deep_value'

    def test_flatten_dict_custom_separator(self):
        """
        Test using custom separator.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import flatten_dict

        nested_dict = {
            'parent': {
                'child': 'value'
            }
        }

        flattened = flatten_dict(nested_dict, sep='.')
        assert flattened['parent.child'] == 'value'

        flattened_underscore = flatten_dict(nested_dict, sep='_')
        assert flattened_underscore['parent_child'] == 'value'

    def test_flatten_dict_with_numbers(self):
        """
        Test that numeric values are converted to strings.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import flatten_dict

        dict_with_numbers = {
            'int_val': 42,
            'float_val': 3.14,
            'nested': {
                'zero': 0,
                'negative': -100
            }
        }

        flattened = flatten_dict(dict_with_numbers)

        assert flattened['int_val'] == '42'
        assert flattened['float_val'] == '3.14'
        assert flattened['nested/zero'] == '0'
        assert flattened['nested/negative'] == '-100'

    def test_flatten_dict_with_booleans(self):
        """
        Test that boolean values are converted to strings.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import flatten_dict

        dict_with_bools = {
            'is_active': True,
            'is_deleted': False,
            'nested': {
                'enabled': True
            }
        }

        flattened = flatten_dict(dict_with_bools)

        assert flattened['is_active'] == 'True'
        assert flattened['is_deleted'] == 'False'
        assert flattened['nested/enabled'] == 'True'

    def test_flatten_dict_with_special_characters(self):
        """
        Test that special characters in keys are preserved.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import flatten_dict

        dict_with_special = {
            'field-with-dash': 'value1',
            'field_with_underscore': 'value2',
            'nested': {
                'field.with.dots': 'value3'
            }
        }

        flattened = flatten_dict(dict_with_special)

        assert flattened['field-with-dash'] == 'value1'
        assert flattened['field_with_underscore'] == 'value2'
        assert flattened['nested/field.with.dots'] == 'value3'


class TestResultTypeOrdering:
    """Test that results are ordered by type (timeline, facets, events)."""

    def test_results_sorted_by_type(self):
        """
        Test that results within a page are sorted: timeline → facets → events.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid"
        manager._getSearchUrl = Mock(return_value='https://search.test/v1')
        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})

        # Mock response with mixed order
        poll_response = {
            'completed': True,
            'results': [
                {'type': 'events', 'rows': [{'e': '1'}], 'nextToken': None},
                {'type': 'facets', 'facets': [{'f': '1'}], 'nextToken': None},
                {'type': 'timeline', 'timeseries': [{'t': '1'}], 'nextToken': None},
                {'type': 'events', 'rows': [{'e': '2'}], 'nextToken': None}
            ]
        }
        manager.pollSearchResults = Mock(return_value=poll_response)

        # Execute search
        results = list(manager.executeSearch("test", 123, 456))

        # Verify order: timeline, facets, events, events
        assert len(results) == 4
        assert results[0]['type'] == 'timeline'
        assert results[1]['type'] == 'facets'
        assert results[2]['type'] == 'events'
        assert results[3]['type'] == 'events'

    def test_first_of_type_in_page_flag(self):
        """
        Test that _first_of_type_in_page is set correctly for section separators.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid"
        manager._getSearchUrl = Mock(return_value='https://search.test/v1')
        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})

        # Mock response with multiple results of same type
        # Note: Results will be sorted as timeline → facets → events
        poll_response = {
            'completed': True,
            'results': [
                {'type': 'events', 'rows': [{'e': '1'}], 'nextToken': None},
                {'type': 'events', 'rows': [{'e': '2'}], 'nextToken': None},
                {'type': 'facets', 'facets': [{'f': '1'}], 'nextToken': None}
            ]
        }
        manager.pollSearchResults = Mock(return_value=poll_response)

        # Execute search
        results = list(manager.executeSearch("test", 123, 456))

        # After sorting: facets first, then events
        # First facets result should be marked as first
        assert results[0]['type'] == 'facets'
        assert results[0]['_first_of_type_in_page'] == True
        # First events result should be marked as first
        assert results[1]['type'] == 'events'
        assert results[1]['_first_of_type_in_page'] == True
        # Second events result should NOT be marked as first
        assert results[2]['type'] == 'events'
        assert results[2]['_first_of_type_in_page'] == False


class TestSearchAPIUtilityFunctions:
    """Test utility functions from SearchAPI module."""

    def test_format_duration_seconds(self):
        """
        Test format_duration with seconds only.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import format_duration

        assert format_duration(0) == "0s"
        assert format_duration(1) == "1s"
        assert format_duration(30) == "30s"
        assert format_duration(59) == "59s"
        assert format_duration(59.9) == "59s"

    def test_format_duration_minutes(self):
        """
        Test format_duration with minutes and seconds.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import format_duration

        assert format_duration(60) == "1m 0s"
        assert format_duration(90) == "1m 30s"
        assert format_duration(125) == "2m 5s"
        assert format_duration(3599) == "59m 59s"

    def test_format_duration_hours(self):
        """
        Test format_duration with hours and minutes.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import format_duration

        assert format_duration(3600) == "1h 0m"
        assert format_duration(3660) == "1h 1m"
        assert format_duration(5400) == "1h 30m"
        assert format_duration(7200) == "2h 0m"
        assert format_duration(86399) == "23h 59m"

    def test_format_time_range_seconds(self):
        """
        Test format_time_range with seconds.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import format_time_range

        assert format_time_range(0) == "0s"
        assert format_time_range(1) == "1s"
        assert format_time_range(30) == "30s"
        assert format_time_range(59) == "59s"

    def test_format_time_range_minutes(self):
        """
        Test format_time_range with minutes.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import format_time_range

        assert format_time_range(60) == "1m"
        assert format_time_range(120) == "2m"
        assert format_time_range(1800) == "30m"
        assert format_time_range(3599) == "59m"

    def test_format_time_range_hours(self):
        """
        Test format_time_range with hours.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import format_time_range

        assert format_time_range(3600) == "1h"
        assert format_time_range(7200) == "2h"
        assert format_time_range(43200) == "12h"
        assert format_time_range(86399) == "23h"

    def test_format_time_range_days(self):
        """
        Test format_time_range with days.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import format_time_range

        assert format_time_range(86400) == "1d"
        assert format_time_range(172800) == "2d"
        assert format_time_range(604800) == "7d"
        assert format_time_range(2592000) == "30d"

    def test_print_statistics_basic(self, capsys):
        """
        Test print_statistics with basic values.

        Parameters:
            capsys: pytest fixture for capturing output.

        Return:
            None
        """
        from limacharlie.SearchAPI import print_statistics

        print_statistics(
            total_time=12.5,
            poll_count=10,
            page_count=2,
            event_row_count=100,
            facet_count=0,
            timeline_count=0,
            include_facets=False,
            include_timeline=False
        )

        captured = capsys.readouterr()
        assert "Search completed!" in captured.err
        assert "Statistics:" in captured.err
        assert "Total execution time: 12.50 seconds" in captured.err
        assert "Poll attempts: 10" in captured.err
        assert "Pages: 2" in captured.err
        assert "Event rows: 100" in captured.err
        # Facets and timeline should not be mentioned when count is 0
        assert "Facets:" not in captured.err
        assert "Timeline entries:" not in captured.err

    def test_print_statistics_with_facets_and_timeline(self, capsys):
        """
        Test print_statistics with facets and timeline.

        Parameters:
            capsys: pytest fixture for capturing output.

        Return:
            None
        """
        from limacharlie.SearchAPI import print_statistics

        print_statistics(
            total_time=25.0,
            poll_count=20,
            page_count=5,
            event_row_count=500,
            facet_count=10,
            timeline_count=50,
            include_facets=True,
            include_timeline=True
        )

        captured = capsys.readouterr()
        assert "Event rows: 500" in captured.err
        assert "Facets: 10" in captured.err
        assert "Timeline entries: 50" in captured.err

    def test_print_statistics_with_zero_counts(self, capsys):
        """
        Test print_statistics with zero counts.

        Parameters:
            capsys: pytest fixture for capturing output.

        Return:
            None
        """
        from limacharlie.SearchAPI import print_statistics

        print_statistics(
            total_time=0.5,
            poll_count=1,
            page_count=0,
            event_row_count=0,
            facet_count=0,
            timeline_count=0,
            include_facets=True,
            include_timeline=True
        )

        captured = capsys.readouterr()
        assert "Event rows: 0" in captured.err
        # Zero counts should not be displayed even if included
        assert "Facets: 0" not in captured.err
        assert "Timeline entries: 0" not in captured.err

    def test_print_billing_stats_empty(self, capsys):
        """
        Test print_billing_stats with empty dict.

        Parameters:
            capsys: pytest fixture for capturing output.

        Return:
            None
        """
        from limacharlie.SearchAPI import print_billing_stats

        print_billing_stats({})

        captured = capsys.readouterr()
        # Should not print anything for empty stats
        assert captured.err == ""

    def test_print_billing_stats_none(self, capsys):
        """
        Test print_billing_stats with None.

        Parameters:
            capsys: pytest fixture for capturing output.

        Return:
            None
        """
        from limacharlie.SearchAPI import print_billing_stats

        print_billing_stats(None)

        captured = capsys.readouterr()
        # Should not print anything for None
        assert captured.err == ""

    def test_print_billing_stats_bytes_small(self, capsys):
        """
        Test print_billing_stats with small byte count.

        Parameters:
            capsys: pytest fixture for capturing output.

        Return:
            None
        """
        from limacharlie.SearchAPI import print_billing_stats

        stats = {'bytesScanned': 1024}
        print_billing_stats(stats)

        captured = capsys.readouterr()
        assert "Billing:" in captured.err
        assert "Bytes scanned: 1024 bytes" in captured.err

    def test_print_billing_stats_bytes_mb(self, capsys):
        """
        Test print_billing_stats with megabytes.

        Parameters:
            capsys: pytest fixture for capturing output.

        Return:
            None
        """
        from limacharlie.SearchAPI import print_billing_stats

        stats = {'bytesScanned': 5242880}  # 5 MB
        print_billing_stats(stats)

        captured = capsys.readouterr()
        assert "Bytes scanned: 5.00 MB" in captured.err

    def test_print_billing_stats_bytes_gb(self, capsys):
        """
        Test print_billing_stats with gigabytes.

        Parameters:
            capsys: pytest fixture for capturing output.

        Return:
            None
        """
        from limacharlie.SearchAPI import print_billing_stats

        stats = {'bytesScanned': 3221225472}  # 3 GB
        print_billing_stats(stats)

        captured = capsys.readouterr()
        assert "Bytes scanned: 3.00 GB" in captured.err

    def test_print_billing_stats_all_fields(self, capsys):
        """
        Test print_billing_stats with all fields.

        Parameters:
            capsys: pytest fixture for capturing output.

        Return:
            None
        """
        from limacharlie.SearchAPI import print_billing_stats

        stats = {
            'bytesScanned': 1048576,  # 1 MB
            'eventsScanned': 10000,
            'eventsMatched': 500,
            'eventsProcessed': 500,
            'estimatedPrice': {'value': 0.0025, 'currency': 'USD'}
        }
        print_billing_stats(stats)

        captured = capsys.readouterr()
        assert "Billing:" in captured.err
        assert "Bytes scanned: 1.00 MB" in captured.err
        assert "Events scanned: 10000" in captured.err
        assert "Events matched: 500" in captured.err
        assert "Events processed: 500" in captured.err
        assert "Estimated price: 0.0025 USD" in captured.err

    def test_print_billing_stats_price_as_float(self, capsys):
        """
        Test print_billing_stats with price as float.

        Parameters:
            capsys: pytest fixture for capturing output.

        Return:
            None
        """
        from limacharlie.SearchAPI import print_billing_stats

        stats = {'estimatedPrice': 0.0050}
        print_billing_stats(stats)

        captured = capsys.readouterr()
        assert "Estimated price: 0.0050 USD" in captured.err

    def test_print_billing_stats_price_with_different_currency(self, capsys):
        """
        Test print_billing_stats with different currency.

        Parameters:
            capsys: pytest fixture for capturing output.

        Return:
            None
        """
        from limacharlie.SearchAPI import print_billing_stats

        stats = {
            'estimatedPrice': {'value': 1.50, 'currency': 'EUR'}
        }
        print_billing_stats(stats)

        captured = capsys.readouterr()
        assert "Estimated price: 1.5000 EUR" in captured.err


class TestSearchAPICoverageScenarios:
    """Test scenarios to improve code coverage for SearchAPI functionality."""

    def test_search_state_cancel_search_success(self, capsys):
        """
        Test SearchState.cancel_search() successfully cancels a search.

        Parameters:
            capsys: pytest fixture for capturing output.

        Return:
            None
        """
        from limacharlie.SearchAPI import SearchState
        from limacharlie import Manager

        state = SearchState()
        state.manager = Manager.__new__(Manager)
        state.query_id = "test-query-id-123"
        state.manager.cancelSearch = Mock()

        # Cancel the search
        state.cancel_search()

        # Verify cancelSearch was called
        state.manager.cancelSearch.assert_called_once_with("test-query-id-123")

        # Verify output
        captured = capsys.readouterr()
        assert "Canceling search query..." in captured.err
        assert "Search query canceled." in captured.err

    def test_search_state_cancel_search_with_error(self, capsys):
        """
        Test SearchState.cancel_search() handles errors gracefully.

        Parameters:
            capsys: pytest fixture for capturing output.

        Return:
            None
        """
        from limacharlie.SearchAPI import SearchState
        from limacharlie import Manager

        state = SearchState()
        state.manager = Manager.__new__(Manager)
        state.query_id = "test-query-id-456"
        state.manager.cancelSearch = Mock(side_effect=Exception("API error"))

        # Cancel the search (should not raise)
        state.cancel_search()

        # Verify error message
        captured = capsys.readouterr()
        assert "Canceling search query..." in captured.err
        assert "Error canceling search: API error" in captured.err

    def test_search_state_cancel_search_no_query(self):
        """
        Test SearchState.cancel_search() does nothing when no query is set.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie.SearchAPI import SearchState
        from limacharlie import Manager

        state = SearchState()
        state.manager = Manager.__new__(Manager)
        state.query_id = None  # No query
        state.manager.cancelSearch = Mock()

        # Cancel should do nothing
        state.cancel_search()

        # Verify cancelSearch was not called
        state.manager.cancelSearch.assert_not_called()

    def test_execute_search_with_facets_results(self):
        """
        Test executeSearch with facets result type.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock initiateSearch
        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})

        # Mock pollSearchResults with facets results
        manager.pollSearchResults = Mock(return_value={
            'completed': True,
            'results': [
                {
                    'type': 'facets',
                    'facets': [
                        {'field': 'event_type', 'value': 'NEW_PROCESS', 'count': 100},
                        {'field': 'event_type', 'value': 'DNS_REQUEST', 'count': 50}
                    ],
                    'nextToken': None
                }
            ]
        })

        # Execute search
        results = list(manager.executeSearch('test query', 1234567890, 1234567900))

        # Verify we got facets results
        assert len(results) == 1
        assert results[0]['type'] == 'facets'
        assert len(results[0]['facets']) == 2
        assert results[0]['facets'][0]['field'] == 'event_type'

    def test_execute_search_with_timeline_results(self):
        """
        Test executeSearch with timeline result type.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock initiateSearch
        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})

        # Mock pollSearchResults with timeline results
        manager.pollSearchResults = Mock(return_value={
            'completed': True,
            'results': [
                {
                    'type': 'timeline',
                    'timeseries': [
                        {'timestamp': 1234567890, 'count': 10},
                        {'timestamp': 1234567900, 'count': 15},
                        {'timestamp': 1234567910, 'count': 8}
                    ],
                    'nextToken': None
                }
            ]
        })

        # Execute search
        results = list(manager.executeSearch('test query', 1234567890, 1234567900))

        # Verify we got timeline results
        assert len(results) == 1
        assert results[0]['type'] == 'timeline'
        assert len(results[0]['timeseries']) == 3
        assert results[0]['timeseries'][0]['timestamp'] == 1234567890

    def test_execute_search_with_mixed_result_types(self):
        """
        Test executeSearch with mixed result types (timeline, facets, events).

        Parameters:
            None

        Return:
            None
        """
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock initiateSearch
        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})

        # Mock pollSearchResults with mixed result types
        manager.pollSearchResults = Mock(return_value={
            'completed': True,
            'results': [
                {
                    'type': 'timeline',
                    'timeseries': [
                        {'timestamp': 1234567890, 'count': 10}
                    ],
                    'nextToken': 'token1'
                },
                {
                    'type': 'facets',
                    'facets': [
                        {'field': 'event_type', 'value': 'NEW_PROCESS', 'count': 100}
                    ],
                    'nextToken': 'token2'
                },
                {
                    'type': 'events',
                    'rows': [
                        {'event_id': '1', 'event_type': 'NEW_PROCESS'}
                    ],
                    'nextToken': None
                }
            ]
        })

        # Execute search
        results = list(manager.executeSearch('test query', 1234567890, 1234567900))

        # Verify we got all three result types
        assert len(results) == 3
        assert results[0]['type'] == 'timeline'
        assert results[1]['type'] == 'facets'
        assert results[2]['type'] == 'events'

    def test_execute_search_with_progress_callback(self):
        """
        Test executeSearch with progress callback.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock initiateSearch
        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})

        # Track progress callback calls
        progress_calls = []
        def progress_callback():
            progress_calls.append(time.time())

        # Create a custom mock that tracks calls and eventually completes
        poll_call_count = [0]
        def mock_poll_results(query_id, token=None, max_attempts=300, poll_interval=2, progress_callback=None):
            poll_call_count[0] += 1
            # Call progress_callback if provided
            if progress_callback:
                progress_callback()
            # Return results after a few polls
            return {
                'completed': True,
                'results': [
                    {
                        'type': 'events',
                        'rows': [{'event_id': '1'}],
                        'nextToken': None
                    }
                ]
            }

        manager.pollSearchResults = Mock(side_effect=mock_poll_results)

        # Execute search with progress callback
        results = list(manager.executeSearch(
            'test query',
            1234567890,
            1234567900,
            progress_callback=progress_callback,
            poll_interval=0.1
        ))

        # Verify progress callback was called
        assert len(progress_calls) >= 1  # At least 1 poll
        assert len(results) == 1

    def test_execute_search_with_on_query_initiated_callback(self):
        """
        Test executeSearch with on_query_initiated callback.

        Parameters:
            None

        Return:
            None
        """
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Track query ID from callback
        initiated_query_id = [None]
        def on_query_initiated(query_id):
            initiated_query_id[0] = query_id

        # Mock initiateSearch
        manager.initiateSearch = Mock(return_value={'queryId': 'test-query-123'})

        # Mock pollSearchResults
        manager.pollSearchResults = Mock(return_value={
            'completed': True,
            'results': [
                {
                    'type': 'events',
                    'rows': [{'event_id': '1'}],
                    'nextToken': None
                }
            ]
        })

        # Execute search with callback
        results = list(manager.executeSearch(
            'test query',
            1234567890,
            1234567900,
            on_query_initiated=on_query_initiated
        ))

        # Verify callback was called with query ID
        assert initiated_query_id[0] == 'test-query-123'
        assert len(results) == 1


class TestSearchAPICLICoverage:
    """Test CLI functionality for additional code coverage."""

    def test_cli_validate_with_error(self, capsys):
        """
        Test CLI validate command with query error.

        Parameters:
            capsys: pytest fixture for capturing output.

        Return:
            None
        """
        from limacharlie.SearchAPI import main
        from limacharlie import Manager
        import sys

        # Create a mock manager
        mock_manager = Manager.__new__(Manager)
        mock_manager._oid = "test-oid-123"
        mock_manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock validation error response
        mock_manager.validateSearch = Mock(return_value={
            'query': 'invalid query',
            'error': 'Syntax error at position 8',
            'startTime': 1234567890,
            'endTime': 1234567900
        })

        # Mock Manager() constructor
        with patch('limacharlie.SearchAPI.Manager', return_value=mock_manager):
            # Run CLI validate command and expect sys.exit(1)
            try:
                main([
                    'validate',
                    '-q', 'invalid query',
                    '-s', '1234567890',
                    '-e', '1234567900'
                ])
                assert False, "Should have exited with code 1"
            except SystemExit as e:
                assert e.code == 1

        # Verify error message was printed
        captured = capsys.readouterr()
        assert "Validation failed" in captured.err
        assert "Syntax error at position 8" in captured.err

    def test_cli_validate_with_time_parse_error(self, capsys):
        """
        Test CLI validate command with time parsing error.

        Parameters:
            capsys: pytest fixture for capturing output.

        Return:
            None
        """
        from limacharlie.SearchAPI import main
        from limacharlie import Manager

        # Mock Manager() constructor
        with patch('limacharlie.SearchAPI.Manager'):
            # Run CLI validate command with invalid time
            try:
                main([
                    'validate',
                    '-q', 'test query',
                    '-s', 'invalid-time-format',
                    '-e', '1234567900'
                ])
                assert False, "Should have exited with code 1"
            except SystemExit as e:
                assert e.code == 1

        # Verify error message was printed
        captured = capsys.readouterr()
        assert "Error parsing time" in captured.err

    def test_cli_execute_with_time_parse_error(self, capsys):
        """
        Test CLI execute command with time parsing error.

        Parameters:
            capsys: pytest fixture for capturing output.

        Return:
            None
        """
        from limacharlie.SearchAPI import main
        from limacharlie import Manager

        # Mock Manager() constructor
        with patch('limacharlie.SearchAPI.Manager'):
            # Run CLI execute command with invalid time
            try:
                main([
                    'execute',
                    '-q', 'test query',
                    '-s', '1234567890',
                    '-e', 'invalid-time-format'
                ])
                assert False, "Should have exited with code 1"
            except SystemExit as e:
                assert e.code == 1

        # Verify error message was printed
        captured = capsys.readouterr()
        assert "Error parsing time" in captured.err

    def test_cli_execute_csv_output_to_file(self, tmp_path):
        """
        Test CLI execute command with CSV output to file.

        Parameters:
            tmp_path: pytest fixture for temporary directory.

        Return:
            None
        """
        from limacharlie.SearchAPI import main
        from limacharlie import Manager
        import csv

        # Create a mock manager
        mock_manager = Manager.__new__(Manager)
        mock_manager._oid = "test-oid-123"
        mock_manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock executeSearch to return events
        mock_manager.executeSearch = Mock(return_value=iter([
            {
                'type': 'events',
                'rows': [
                    {'event_id': '1', 'event_type': 'NEW_PROCESS', 'nested': {'key': 'value'}},
                    {'event_id': '2', 'event_type': 'DNS_REQUEST', 'list_field': ['a', 'b']}
                ],
                'nextToken': None,
                '_page_number': 1,
                '_first_of_type_in_page': True,
                '_billing_stats': {}
            }
        ]))

        # Create output file path
        output_file = tmp_path / "output.csv"

        # Mock Manager() constructor
        with patch('limacharlie.SearchAPI.Manager', return_value=mock_manager):
            # Run CLI execute command with CSV output
            main([
                'execute',
                '-q', 'test query',
                '-s', '1234567890',
                '-e', '1234567900',
                '--output-file', str(output_file),
                '--output-format', 'csv',
                '--non-interactive'
            ])

        # Verify CSV file was created
        assert output_file.exists()

        # Read and verify CSV content
        with open(output_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]['event_id'] == '1'
        assert rows[0]['event_type'] == 'NEW_PROCESS'
        assert rows[0]['nested/key'] == 'value'  # Flattened with / separator
        assert rows[1]['event_id'] == '2'
        assert rows[1]['list_field'] == '["a", "b"]'  # JSON-encoded list

    def test_cli_execute_csv_auto_detect_from_extension(self, tmp_path):
        """
        Test CLI execute command with CSV format auto-detection from .csv extension.

        Parameters:
            tmp_path: pytest fixture for temporary directory.

        Return:
            None
        """
        from limacharlie.SearchAPI import main
        from limacharlie import Manager
        import csv

        # Create a mock manager
        mock_manager = Manager.__new__(Manager)
        mock_manager._oid = "test-oid-123"
        mock_manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock executeSearch to return events
        mock_manager.executeSearch = Mock(return_value=iter([
            {
                'type': 'events',
                'rows': [{'event_id': '1'}],
                'nextToken': None,
                '_page_number': 1,
                '_first_of_type_in_page': True,
                '_billing_stats': {}
            }
        ]))

        # Create output file path with .csv extension
        output_file = tmp_path / "results.csv"

        # Mock Manager() constructor
        with patch('limacharlie.SearchAPI.Manager', return_value=mock_manager):
            # Run CLI execute command without --output-format (auto-detect from .csv)
            main([
                'execute',
                '-q', 'test query',
                '-s', '1234567890',
                '-e', '1234567900',
                '--output-file', str(output_file),
                '--non-interactive'
            ])

        # Verify CSV file was created
        assert output_file.exists()

        # Read and verify it's valid CSV
        with open(output_file, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]['event_id'] == '1'

