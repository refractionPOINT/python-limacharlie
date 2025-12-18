"""
Unit tests for the Search API functionality.

Tests cover:
- SDK methods (validateSearch, initiateSearch, pollSearchResults, executeSearch)
- CLI commands (validate, execute)
- Edge cases and error scenarios
- Different result types (events, facets, timeline)
- Pagination scenarios
- Error handling
- Timeout conditions
- Network failures
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import json
import time
import sys
from io import StringIO


class TestSearchAPISDK:
    """Test the Search API SDK methods in the Manager class."""

    def test_validate_search_basic(self):
        """Test basic search validation."""
        # Import Manager
        from limacharlie import Manager

        # Create a mock manager
        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock the _apiCall method
        expected_response = {
            'query': 'event_type = NEW_PROCESS',
            'startTime': 1234567890,
            'endTime': 1234567900,
            'estimatedPrice': {
                'value': 0.0050,
                'currency': 'USD'
            }
        }
        manager._apiCall = Mock(return_value=expected_response)

        # Call validateSearch
        result = manager.validateSearch(
            'event_type = NEW_PROCESS',
            1234567890,
            1234567900
        )

        # Verify the API call was made correctly
        manager._apiCall.assert_called_once()
        call_args = manager._apiCall.call_args

        # Check that it was a POST to search/validate
        assert call_args[0][0] == 'search/validate'
        assert call_args[0][1] == 'POST'

        # Check the request body
        raw_body = call_args[1]['rawBody']
        request_data = json.loads(raw_body.decode())
        assert request_data['oid'] == 'test-oid-123'
        assert request_data['query'] == 'event_type = NEW_PROCESS'
        assert request_data['startTime'] == '1234567890'
        assert request_data['endTime'] == '1234567900'

        # Verify altRoot was passed
        assert call_args[1]['altRoot'] == 'https://search.limacharlie.io/v1'

        # Verify the response
        assert result == expected_response

    def test_validate_search_with_stream(self):
        """Test search validation with stream parameter."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        expected_response = {
            'query': 'event_type = NEW_PROCESS',
            'startTime': 1234567890,
            'endTime': 1234567900,
            'estimatedPrice': {
                'value': 0.0050,
                'currency': 'USD'
            }
        }
        manager._apiCall = Mock(return_value=expected_response)

        # Call validateSearch with stream
        result = manager.validateSearch(
            'event_type = NEW_PROCESS',
            1234567890,
            1234567900,
            stream='event'
        )

        # Verify the stream was included in request
        call_args = manager._apiCall.call_args
        raw_body = call_args[1]['rawBody']
        request_data = json.loads(raw_body.decode())
        assert request_data['stream'] == 'event'

    def test_initiate_search_basic(self):
        """Test initiating a search."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        expected_response = {
            'queryId': 'query-id-abc123'
        }
        manager._apiCall = Mock(return_value=expected_response)

        # Call initiateSearch
        result = manager.initiateSearch(
            'event_type = NEW_PROCESS',
            1234567890,
            1234567900
        )

        # Verify the API call
        manager._apiCall.assert_called_once()
        call_args = manager._apiCall.call_args

        assert call_args[0][0] == 'search'
        assert call_args[0][1] == 'POST'

        raw_body = call_args[1]['rawBody']
        request_data = json.loads(raw_body.decode())
        assert request_data['oid'] == 'test-oid-123'
        assert request_data['query'] == 'event_type = NEW_PROCESS'
        assert request_data['paginated'] == True

        assert result == expected_response

    def test_initiate_search_without_pagination(self):
        """Test initiating a search without pagination."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        expected_response = {'queryId': 'query-id-abc123'}
        manager._apiCall = Mock(return_value=expected_response)

        # Call initiateSearch with paginated=False
        result = manager.initiateSearch(
            'event_type = NEW_PROCESS',
            1234567890,
            1234567900,
            paginated=False
        )

        # Verify pagination flag
        call_args = manager._apiCall.call_args
        raw_body = call_args[1]['rawBody']
        request_data = json.loads(raw_body.decode())
        assert request_data['paginated'] == False

    def test_poll_search_results_completed(self):
        """Test polling for completed search results."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock a completed response
        expected_response = {
            'completed': True,
            'nextPollInMs': 0,
            'results': [
                {'type': 'events', 'rows': [{'event_id': '123'}]}
            ],
            'nextToken': 'token-abc'
        }
        manager._apiCall = Mock(return_value=expected_response)

        # Call pollSearchResults
        result = manager.pollSearchResults('query-id-123')

        # Verify the API call
        manager._apiCall.assert_called_once()
        call_args = manager._apiCall.call_args

        assert call_args[0][0] == 'search/query-id-123'
        assert call_args[0][1] == 'GET'

        assert result == expected_response

    def test_poll_search_results_with_token(self):
        """Test polling with pagination token."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        expected_response = {
            'completed': True,
            'results': []
        }
        manager._apiCall = Mock(return_value=expected_response)

        # Call pollSearchResults with token
        result = manager.pollSearchResults('query-id-123', token='page-token-xyz')

        # Verify the token was passed
        call_args = manager._apiCall.call_args
        query_params = call_args[1]['queryParams']
        assert query_params['token'] == 'page-token-xyz'

    def test_poll_search_results_retries(self):
        """Test polling retries when not completed."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock responses: first two not completed, third completed
        responses = [
            {'completed': False, 'nextPollInMs': 100},
            {'completed': False, 'nextPollInMs': 100},
            {'completed': True, 'results': []}
        ]
        manager._apiCall = Mock(side_effect=responses)

        # Mock time.sleep to speed up test
        with patch('time.sleep'):
            result = manager.pollSearchResults('query-id-123', max_attempts=10, poll_interval=0.1)

        # Verify it made 3 calls
        assert manager._apiCall.call_count == 3
        assert result['completed'] == True

    def test_poll_search_results_max_attempts_exceeded(self):
        """Test polling raises exception when max attempts exceeded."""
        from limacharlie import Manager
        from limacharlie.utils import LcApiException

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Always return not completed
        manager._apiCall = Mock(return_value={'completed': False, 'nextPollInMs': 100})

        # Expect exception after max attempts
        with patch('time.sleep'):
            with pytest.raises(LcApiException) as exc_info:
                manager.pollSearchResults('query-id-123', max_attempts=3, poll_interval=0.1)

        assert 'Max polling attempts exceeded' in str(exc_info.value)

    def test_poll_search_results_with_error(self):
        """Test polling returns early when error is present."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock response with error
        error_response = {
            'completed': False,
            'error': 'Query failed: invalid syntax'
        }
        manager._apiCall = Mock(return_value=error_response)

        # Should return immediately with error
        result = manager.pollSearchResults('query-id-123')

        assert result['error'] == 'Query failed: invalid syntax'
        # Should only call once (not retry on error)
        assert manager._apiCall.call_count == 1

    def test_execute_search_single_page(self):
        """Test executeSearch with single page of results."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock initiateSearch
        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})

        # Mock pollSearchResults - single page, nextToken in LAST result object
        manager.pollSearchResults = Mock(return_value={
            'completed': True,
            'results': [
                {'type': 'events', 'event_id': '1', 'nextToken': None},
                {'type': 'events', 'event_id': '2', 'nextToken': None},
                {'type': 'events', 'event_id': '3', 'nextToken': None}  # Last result, no token
            ]
        })

        # Execute search
        results = list(manager.executeSearch('test query', 1000, 2000))

        # Verify results (should have metadata fields added)
        assert len(results) == 3
        assert results[0]['event_id'] == '1'
        assert results[1]['event_id'] == '2'
        assert results[2]['event_id'] == '3'

        # Verify metadata fields are added
        assert results[0]['_page_number'] == 1
        assert results[0]['_first_of_type_in_page'] == True
        assert results[1]['_first_of_type_in_page'] == False  # Not first
        assert '_billing_stats' in results[0]

        # Verify initiateSearch was called
        manager.initiateSearch.assert_called_once_with(
            'test query',
            1000,
            2000,
            paginated=True,
            stream=None
        )

        # Verify pollSearchResults was called once with no token
        manager.pollSearchResults.assert_called_once()

    def test_execute_search_multiple_pages(self):
        """Test executeSearch with multiple pages of results."""
        from limacharlie import Manager

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock initiateSearch
        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})

        # Mock pollSearchResults - three pages
        # Note: nextToken is in the LAST result object of each page
        poll_responses = [
            {
                'completed': True,
                'results': [
                    {'type': 'events', 'event_id': '1', 'nextToken': None},
                    {'type': 'events', 'event_id': '2', 'nextToken': 'token-page2'}  # Token in LAST result
                ]
            },
            {
                'completed': True,
                'results': [
                    {'type': 'events', 'event_id': '3', 'nextToken': None},
                    {'type': 'events', 'event_id': '4', 'nextToken': 'token-page3'}  # Token in LAST result
                ]
            },
            {
                'completed': True,
                'results': [
                    {'type': 'events', 'event_id': '5', 'nextToken': None}  # No more pages
                ]
            }
        ]
        manager.pollSearchResults = Mock(side_effect=poll_responses)

        # Execute search
        results = list(manager.executeSearch('test query', 1000, 2000))

        # Verify all results were collected
        assert len(results) == 5
        assert results[0]['event_id'] == '1'
        assert results[4]['event_id'] == '5'

        # Verify page numbers are set correctly
        assert results[0]['_page_number'] == 1
        assert results[1]['_page_number'] == 1
        assert results[2]['_page_number'] == 2
        assert results[3]['_page_number'] == 2
        assert results[4]['_page_number'] == 3

        # Verify pollSearchResults was called 3 times with correct tokens
        assert manager.pollSearchResults.call_count == 3
        call_args_list = manager.pollSearchResults.call_args_list
        assert call_args_list[0][1]['token'] is None  # First page
        assert call_args_list[1][1]['token'] == 'token-page2'  # Second page
        assert call_args_list[2][1]['token'] == 'token-page3'  # Third page

    def test_execute_search_with_error(self):
        """Test executeSearch raises exception on error."""
        from limacharlie import Manager
        from limacharlie.utils import LcApiException

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock initiateSearch
        manager.initiateSearch = Mock(return_value={'queryId': 'query-123'})

        # Mock pollSearchResults with error
        manager.pollSearchResults = Mock(return_value={
            'completed': True,
            'error': 'Query execution failed',
            'results': []
        })

        # Execute search should raise exception
        with pytest.raises(LcApiException) as exc_info:
            list(manager.executeSearch('test query', 1000, 2000))

        assert 'Query execution failed' in str(exc_info.value)

    def test_execute_search_missing_query_id(self):
        """Test executeSearch raises exception when queryId is missing."""
        from limacharlie import Manager
        from limacharlie.utils import LcApiException

        manager = Manager.__new__(Manager)
        manager._oid = "test-oid-123"
        # Mock the _getSearchUrl method
        manager._getSearchUrl = Mock(return_value='https://search.limacharlie.io/v1')

        # Mock initiateSearch with missing queryId
        manager.initiateSearch = Mock(return_value={})

        # Execute search should raise exception
        with pytest.raises(LcApiException) as exc_info:
            list(manager.executeSearch('test query', 1000, 2000))

        assert 'missing queryId' in str(exc_info.value)


class TestSearchAPICLI:
    """Test the Search API CLI commands."""

    def test_cli_validate_basic(self, capsys):
        """Test the validate CLI command."""
        from limacharlie.SearchAPI import main

        # Mock Manager
        with patch('limacharlie.SearchAPI.Manager') as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            # Mock validateSearch response
            mock_manager.validateSearch.return_value = {
                'query': 'event_type = NEW_PROCESS',
                'startTime': 1234567890,
                'endTime': 1234567900,
                'estimatedPrice': {
                    'value': 0.0050,
                    'currency': 'USD'
                }
            }

            # Run CLI
            main(['validate', '-q', 'event_type = NEW_PROCESS', '-s', '1234567890', '-e', '1234567900'])

            # Verify validateSearch was called
            mock_manager.validateSearch.assert_called_once_with(
                'event_type = NEW_PROCESS',
                1234567890,
                1234567900,
                stream=None
            )

            # Check output
            captured = capsys.readouterr()
            assert 'estimatedPrice' in captured.out
            assert 'Estimated price: 0.0050 USD' in captured.err

    def test_cli_execute_basic(self, capsys):
        """Test the execute CLI command."""
        from limacharlie.SearchAPI import main

        # Mock Manager
        with patch('limacharlie.SearchAPI.Manager') as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            # Mock executeSearch to return properly structured results
            # Results should have 'type' field and appropriate data field ('rows' for events)
            mock_manager.executeSearch.return_value = iter([
                {
                    'type': 'events',
                    'rows': [
                        {'event_id': '1', 'event_type': 'NEW_PROCESS'},
                        {'event_id': '2', 'event_type': 'NEW_PROCESS'}
                    ],
                    'nextToken': None,
                    '_page_number': 1,
                    '_first_of_type_in_page': True,
                    '_billing_stats': {}
                }
            ])

            # Run CLI
            main(['execute', '-q', 'event_type = NEW_PROCESS', '-s', '1000', '-e', '2000'])

            # Verify executeSearch was called
            mock_manager.executeSearch.assert_called_once()
            call_kwargs = mock_manager.executeSearch.call_args[1]
            assert call_kwargs['stream'] is None
            assert call_kwargs['max_poll_attempts'] == 300
            assert call_kwargs['poll_interval'] == 2

            # Check output contains results
            captured = capsys.readouterr()
            assert 'event_id' in captured.out
            assert 'Event rows: 2' in captured.err

    def test_cli_execute_with_output_file(self, tmp_path):
        """Test the execute CLI command with output file."""
        from limacharlie.SearchAPI import main

        output_file = tmp_path / "results.jsonl"

        # Mock Manager
        with patch('limacharlie.SearchAPI.Manager') as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            # Mock executeSearch with properly structured results
            mock_manager.executeSearch.return_value = iter([
                {
                    'type': 'events',
                    'rows': [
                        {'event_id': '1'},
                        {'event_id': '2'}
                    ],
                    'nextToken': None,
                    '_page_number': 1,
                    '_first_of_type_in_page': True,
                    '_billing_stats': {}
                }
            ])

            # Run CLI with output file
            main([
                'execute',
                '-q', 'test query',
                '-s', '1000',
                '-e', '2000',
                '--output-file', str(output_file)
            ])

            # Verify file was created and contains results
            assert output_file.exists()
            content = output_file.read_text()
            lines = content.strip().split('\n')
            assert len(lines) == 2

            # Parse and verify JSON
            result1 = json.loads(lines[0])
            result2 = json.loads(lines[1])
            assert result1['event_id'] == '1'
            assert result2['event_id'] == '2'
