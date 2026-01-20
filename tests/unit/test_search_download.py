"""Tests for the search download SDK methods and CLI commands.

These tests verify that:
1. The Manager download methods correctly call the API
2. The CLI commands correctly parse arguments and call SDK methods
3. Error handling works correctly
4. The getJWT method correctly generates tokens with custom expiry
"""

import json
import time
from unittest.mock import MagicMock, patch, call

import pytest

from limacharlie import Manager
from limacharlie.SearchDownload import main as search_download_cli
from limacharlie.utils import LcApiException


class TestManagerGetJWT:
    """Tests for the Manager.getJWT method."""

    def test_get_jwt_with_custom_expiry(self):
        """Test getJWT generates a token with custom expiry timestamp."""
        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._secret_api_key = 'test-api-key'
            manager._oid = 'test-oid'
            manager._uid = None
            manager._oauth_creds = None
            manager._jwt = None
            manager._onRefreshAuth = None

            custom_expiry = int(time.time()) + 8 * 3600  # 8 hours from now

            with patch('limacharlie.Manager.urlopen') as mock_urlopen:
                mock_response = MagicMock()
                mock_response.read.return_value = b'{"jwt": "test-jwt-token"}'
                mock_urlopen.return_value = mock_response

                result = manager.getJWT(expiry_seconds=custom_expiry)

                assert result == 'test-jwt-token'
                assert manager._jwt == 'test-jwt-token'

                # Verify the request included the expiry parameter
                call_args = mock_urlopen.call_args
                request = call_args[0][0]
                request_data = request.data.decode()
                assert f'expiry={custom_expiry}' in request_data

    def test_get_jwt_without_expiry(self):
        """Test getJWT works without custom expiry (uses default)."""
        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._secret_api_key = 'test-api-key'
            manager._oid = 'test-oid'
            manager._uid = None
            manager._oauth_creds = None
            manager._jwt = None
            manager._onRefreshAuth = None

            with patch('limacharlie.Manager.urlopen') as mock_urlopen:
                mock_response = MagicMock()
                mock_response.read.return_value = b'{"jwt": "default-jwt-token"}'
                mock_urlopen.return_value = mock_response

                result = manager.getJWT()

                assert result == 'default-jwt-token'
                assert manager._jwt == 'default-jwt-token'

                # Verify no expiry parameter in request
                call_args = mock_urlopen.call_args
                request = call_args[0][0]
                request_data = request.data.decode()
                assert 'expiry=' not in request_data

    def test_get_jwt_updates_internal_token(self):
        """Test that getJWT updates the internal _jwt token for subsequent calls."""
        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._secret_api_key = 'test-api-key'
            manager._oid = 'test-oid'
            manager._uid = None
            manager._oauth_creds = None
            manager._jwt = 'old-token'
            manager._onRefreshAuth = None

            with patch('limacharlie.Manager.urlopen') as mock_urlopen:
                mock_response = MagicMock()
                mock_response.read.return_value = b'{"jwt": "new-long-lived-token"}'
                mock_urlopen.return_value = mock_response

                result = manager.getJWT(expiry_seconds=int(time.time()) + 3600)

                # Both the return value and internal token should be updated
                assert result == 'new-long-lived-token'
                assert manager._jwt == 'new-long-lived-token'

    def test_get_jwt_failure_raises_exception(self):
        """Test that getJWT raises LcApiException on failure."""
        from io import BytesIO
        from urllib.error import HTTPError

        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._secret_api_key = 'test-api-key'
            manager._oid = 'test-oid'
            manager._uid = None
            manager._oauth_creds = None
            manager._jwt = None
            manager._onRefreshAuth = None

            with patch('limacharlie.Manager.urlopen') as mock_urlopen:
                # Create a proper HTTPError with a readable body
                error_body = BytesIO(b'{"error": "Unauthorized"}')
                http_error = HTTPError(
                    'https://jwt.limacharlie.io',
                    401,
                    'Unauthorized',
                    {},
                    error_body
                )
                mock_urlopen.side_effect = http_error

                with pytest.raises(LcApiException) as exc_info:
                    manager.getJWT(expiry_seconds=int(time.time()) + 3600)

                assert 'failed to get jwt' in str(exc_info.value).lower()


class TestManagerSearchDownloadMethods:
    """Tests for the Manager search download SDK methods."""

    def test_initiate_search_download_success(self):
        """Test initiating a download job successfully."""
        mock_response = {
            'jobId': 'test-job-123',
            'estimatedStats': {
                'eventsScanned': 50000,
                'eventsMatched': 1000,
                'estimatedPrice': {'price': 0.25, 'currency': 'USD'}
            },
            'tokenExpiry': '2025-01-01T12:00:00Z'
        }

        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._oid = 'test-oid'
            manager._jwt = 'test-jwt'
            manager._search_url = None

            # Mock _getSearchUrl and _restCall
            manager._getSearchUrl = MagicMock(return_value='https://search.limacharlie.io/v1/search')
            manager._restCall = MagicMock(return_value=(200, mock_response))

            result = manager.initiateSearchDownload(
                query='event_type = *',
                start_time=1700000000,
                end_time=1700086400,
                compression='zip',
                stream='event',
                metadata={'purpose': 'test'}
            )

            assert result['jobId'] == 'test-job-123'
            assert 'estimatedStats' in result

            # Verify the API call
            manager._restCall.assert_called_once()
            call_args = manager._restCall.call_args
            assert call_args[0][0] == 'download'
            assert call_args[0][1] == 'POST'

    def test_initiate_search_download_token_too_short(self):
        """Test that appropriate error is raised when token expires too soon."""
        error_response = {
            'error': 'JWT token expires too soon for download job',
            'tokenExpiry': '2025-01-01T00:30:00Z',
            'minRequiredLifetime': '6h0m0s'
        }

        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._oid = 'test-oid'
            manager._jwt = 'test-jwt'
            manager._search_url = None

            manager._getSearchUrl = MagicMock(return_value='https://search.limacharlie.io/v1/search')
            manager._restCall = MagicMock(return_value=(400, error_response))

            with pytest.raises(LcApiException) as exc_info:
                manager.initiateSearchDownload(
                    query='*',
                    start_time=1700000000,
                    end_time=1700086400
                )

            assert 'token expires too soon' in str(exc_info.value).lower()

    def test_get_search_download_status_success(self):
        """Test getting download job status successfully."""
        mock_status = {
            'jobId': 'test-job-123',
            'status': 'running',
            'progress': {
                'eventsProcessed': 5000,
                'pagesProcessed': 10,
                'bytesProcessed': 1024000
            }
        }

        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._oid = 'test-oid'
            manager._jwt = 'test-jwt'
            manager._search_url = None

            manager._getSearchUrl = MagicMock(return_value='https://search.limacharlie.io/v1/search')
            manager._restCall = MagicMock(return_value=(200, mock_status))

            result = manager.getSearchDownloadStatus('test-job-123')

            assert result['status'] == 'running'
            assert result['progress']['eventsProcessed'] == 5000

    def test_get_search_download_status_not_found(self):
        """Test getting status for non-existent job."""
        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._oid = 'test-oid'
            manager._jwt = 'test-jwt'
            manager._search_url = None

            manager._getSearchUrl = MagicMock(return_value='https://search.limacharlie.io/v1/search')
            manager._restCall = MagicMock(return_value=(404, {'error': 'Job not found'}))

            with pytest.raises(LcApiException) as exc_info:
                manager.getSearchDownloadStatus('nonexistent-job')

            assert 'not found' in str(exc_info.value).lower()

    def test_list_search_downloads_success(self):
        """Test listing download jobs successfully."""
        mock_response = {
            'jobs': [
                {'jobId': 'job-1', 'status': 'completed'},
                {'jobId': 'job-2', 'status': 'running'}
            ]
        }

        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._oid = 'test-oid'
            manager._jwt = 'test-jwt'
            manager._search_url = None

            manager._getSearchUrl = MagicMock(return_value='https://search.limacharlie.io/v1/search')
            manager._restCall = MagicMock(return_value=(200, mock_response))

            result = manager.listSearchDownloads(limit=10, offset=0)

            assert len(result) == 2
            assert result[0]['jobId'] == 'job-1'

            # Verify query params
            call_args = manager._restCall.call_args
            query_params = call_args[1]['queryParams']
            assert query_params['limit'] == '10'
            assert query_params['offset'] == '0'

    def test_cancel_search_download_success(self):
        """Test canceling a download job successfully."""
        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._oid = 'test-oid'
            manager._jwt = 'test-jwt'
            manager._search_url = None

            manager._getSearchUrl = MagicMock(return_value='https://search.limacharlie.io/v1/search')
            manager._restCall = MagicMock(return_value=(204, {}))

            result = manager.cancelSearchDownload('test-job-123')

            assert result is True
            manager._restCall.assert_called_once()

    def test_cancel_search_download_already_completed(self):
        """Test canceling an already completed job."""
        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._oid = 'test-oid'
            manager._jwt = 'test-jwt'
            manager._search_url = None

            manager._getSearchUrl = MagicMock(return_value='https://search.limacharlie.io/v1/search')
            manager._restCall = MagicMock(return_value=(409, {'error': 'Job already completed'}))

            with pytest.raises(LcApiException) as exc_info:
                manager.cancelSearchDownload('completed-job')

            assert 'cannot cancel' in str(exc_info.value).lower()

    def test_wait_for_search_download_completes(self):
        """Test waiting for a download job to complete."""
        status_sequence = [
            {'status': 'running', 'progress': {'eventsProcessed': 100}},
            {'status': 'running', 'progress': {'eventsProcessed': 500}},
            {'status': 'merging', 'progress': {'eventsProcessed': 1000}},
            {'status': 'completed', 'resultUrl': 'https://storage.example.com/result.zip'}
        ]
        call_count = [0]

        def mock_get_status(job_id):
            result = status_sequence[min(call_count[0], len(status_sequence) - 1)]
            call_count[0] += 1
            return result

        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._oid = 'test-oid'
            manager._jwt = 'test-jwt'

            manager.getSearchDownloadStatus = MagicMock(side_effect=mock_get_status)

            progress_calls = []

            def track_progress(status):
                progress_calls.append(status)

            result = manager.waitForSearchDownload(
                'test-job-123',
                poll_interval=0.01,  # Fast polling for test
                progress_callback=track_progress
            )

            assert result['status'] == 'completed'
            assert result['resultUrl'] == 'https://storage.example.com/result.zip'
            assert len(progress_calls) >= 3

    def test_wait_for_search_download_fails(self):
        """Test waiting for a job that fails."""
        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._oid = 'test-oid'
            manager._jwt = 'test-jwt'

            manager.getSearchDownloadStatus = MagicMock(return_value={
                'status': 'failed',
                'error': 'Out of memory'
            })

            with pytest.raises(LcApiException) as exc_info:
                manager.waitForSearchDownload('test-job-123', poll_interval=0.01)

            assert 'failed' in str(exc_info.value).lower()
            assert 'out of memory' in str(exc_info.value).lower()

    def test_wait_for_search_download_timeout(self):
        """Test that waiting times out correctly."""
        with patch.object(Manager, '__init__', lambda self, **kwargs: None):
            manager = Manager()
            manager._oid = 'test-oid'
            manager._jwt = 'test-jwt'

            # Always return running status
            manager.getSearchDownloadStatus = MagicMock(return_value={
                'status': 'running',
                'progress': {'eventsProcessed': 100}
            })

            with pytest.raises(LcApiException) as exc_info:
                manager.waitForSearchDownload(
                    'test-job-123',
                    poll_interval=0.01,
                    timeout=0.05  # Very short timeout
                )

            assert 'timeout' in str(exc_info.value).lower()


class TestSearchDownloadCLI:
    """Tests for the search-download CLI commands."""

    def test_cli_start_basic(self, monkeypatch, capsys):
        """Test the start command with basic options."""
        mock_manager = MagicMock()
        mock_manager._oid = 'test-oid'
        mock_manager.getJWT.return_value = 'test-jwt'
        mock_manager.initiateSearchDownload.return_value = {
            'jobId': 'cli-job-123',
            'estimatedStats': {'eventsMatched': 1000}
        }

        with patch('limacharlie.SearchDownload.Manager', return_value=mock_manager):
            search_download_cli([
                'start',
                '-q', 'event_type = *',
                '-s', 'now-1h',
                '-e', 'now'
            ])

        captured = capsys.readouterr()
        assert 'cli-job-123' in captured.out

    def test_cli_start_json_output(self, monkeypatch, capsys):
        """Test the start command with JSON output."""
        mock_manager = MagicMock()
        mock_manager._oid = 'test-oid'
        mock_manager.getJWT.return_value = 'test-jwt'
        mock_manager.initiateSearchDownload.return_value = {
            'jobId': 'json-job-456',
            'estimatedStats': {'eventsMatched': 500}
        }

        with patch('limacharlie.SearchDownload.Manager', return_value=mock_manager):
            search_download_cli([
                'start',
                '-q', '*',
                '-s', 'now-1h',
                '-e', 'now',
                '--json'
            ])

        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output['jobId'] == 'json-job-456'

    def test_cli_status_command(self, monkeypatch, capsys):
        """Test the status command."""
        mock_manager = MagicMock()
        mock_manager.getSearchDownloadStatus.return_value = {
            'jobId': 'status-job-789',
            'status': 'running',
            'progress': {'eventsProcessed': 5000}
        }

        with patch('limacharlie.SearchDownload.Manager', return_value=mock_manager):
            search_download_cli(['status', 'status-job-789'])

        captured = capsys.readouterr()
        assert 'status-job-789' in captured.out
        assert 'running' in captured.out.lower()

    def test_cli_list_command(self, monkeypatch, capsys):
        """Test the list command."""
        mock_manager = MagicMock()
        mock_manager.listSearchDownloads.return_value = [
            {'jobId': 'list-job-1', 'status': 'completed'},
            {'jobId': 'list-job-2', 'status': 'running'}
        ]

        with patch('limacharlie.SearchDownload.Manager', return_value=mock_manager):
            search_download_cli(['list', '--limit', '10'])

        captured = capsys.readouterr()
        assert 'list-job-1' in captured.out
        assert 'list-job-2' in captured.out

    def test_cli_cancel_command(self, monkeypatch, capsys):
        """Test the cancel command."""
        mock_manager = MagicMock()
        mock_manager.cancelSearchDownload.return_value = True

        with patch('limacharlie.SearchDownload.Manager', return_value=mock_manager):
            search_download_cli(['cancel', 'cancel-job-123'])

        captured = capsys.readouterr()
        assert 'cancelled' in captured.out.lower()

    def test_cli_url_command_completed_job(self, monkeypatch, capsys):
        """Test the url command for a completed job."""
        mock_manager = MagicMock()
        mock_manager.getSearchDownloadStatus.return_value = {
            'jobId': 'url-job-123',
            'status': 'completed',
            'resultUrl': 'https://storage.example.com/results.zip'
        }

        with patch('limacharlie.SearchDownload.Manager', return_value=mock_manager):
            search_download_cli(['url', 'url-job-123'])

        captured = capsys.readouterr()
        assert 'https://storage.example.com/results.zip' in captured.out

    def test_cli_url_command_not_completed(self, monkeypatch, capsys):
        """Test the url command for a job that's not completed."""
        mock_manager = MagicMock()
        mock_manager.getSearchDownloadStatus.return_value = {
            'jobId': 'running-job-123',
            'status': 'running'
        }

        with patch('limacharlie.SearchDownload.Manager', return_value=mock_manager):
            with pytest.raises(SystemExit) as exc_info:
                search_download_cli(['url', 'running-job-123'])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert 'not completed' in captured.err.lower()

    def test_cli_wait_command(self, monkeypatch, capsys):
        """Test the wait command."""
        status_sequence = [
            {'status': 'running', 'progress': {'eventsProcessed': 100}},
            {'status': 'completed', 'resultUrl': 'https://example.com/result.zip'}
        ]
        call_count = [0]

        def mock_get_status(job_id):
            result = status_sequence[min(call_count[0], len(status_sequence) - 1)]
            call_count[0] += 1
            return result

        mock_manager = MagicMock()
        mock_manager.getSearchDownloadStatus.side_effect = mock_get_status
        mock_manager.waitForSearchDownload.return_value = status_sequence[-1]

        with patch('limacharlie.SearchDownload.Manager', return_value=mock_manager):
            search_download_cli(['wait', 'wait-job-123', '--quiet', '--poll-interval', '1'])

        captured = capsys.readouterr()
        # With --quiet, minimal output expected
        assert 'completed' in captured.out.lower() or 'wait-job-123' in captured.out

    def test_cli_start_with_metadata(self, monkeypatch, capsys):
        """Test start command with custom metadata."""
        mock_manager = MagicMock()
        mock_manager._oid = 'test-oid'
        mock_manager.getJWT.return_value = 'test-jwt'
        mock_manager.initiateSearchDownload.return_value = {'jobId': 'meta-job-123'}

        captured_metadata = None

        def capture_init_call(**kwargs):
            nonlocal captured_metadata
            captured_metadata = kwargs.get('metadata')
            return {'jobId': 'meta-job-123'}

        mock_manager.initiateSearchDownload.side_effect = capture_init_call

        with patch('limacharlie.SearchDownload.Manager', return_value=mock_manager):
            search_download_cli([
                'start',
                '-q', '*',
                '-s', 'now-1h',
                '-e', 'now',
                '--metadata', '{"purpose": "forensics", "ticket": "INC-123"}'
            ])

        assert captured_metadata == {'purpose': 'forensics', 'ticket': 'INC-123'}

    def test_cli_start_invalid_metadata_json(self, monkeypatch, capsys):
        """Test start command with invalid metadata JSON."""
        mock_manager = MagicMock()

        with patch('limacharlie.SearchDownload.Manager', return_value=mock_manager):
            with pytest.raises(SystemExit):
                search_download_cli([
                    'start',
                    '-q', '*',
                    '-s', 'now-1h',
                    '-e', 'now',
                    '--metadata', 'not-valid-json'
                ])

        captured = capsys.readouterr()
        assert 'error parsing metadata' in captured.err.lower()

    def test_cli_start_with_wait(self, monkeypatch, capsys):
        """Test start command with --wait flag waits for job completion."""
        mock_manager = MagicMock()
        mock_manager._oid = 'test-oid'
        mock_manager.getJWT.return_value = 'test-jwt'
        mock_manager.initiateSearchDownload.return_value = {
            'jobId': 'wait-start-job-123',
            'estimatedStats': {'eventsMatched': 1000}
        }
        mock_manager.waitForSearchDownload.return_value = {
            'jobId': 'wait-start-job-123',
            'status': 'completed',
            'resultUrl': 'https://storage.example.com/results.zip',
            'progress': {
                'eventsProcessed': 1000,
                'runtimeSeconds': 120
            }
        }

        with patch('limacharlie.SearchDownload.Manager', return_value=mock_manager):
            search_download_cli([
                'start',
                '-q', 'event_type = *',
                '-s', 'now-1h',
                '-e', 'now',
                '--wait'
            ])

        # Verify waitForSearchDownload was called with the job ID
        mock_manager.waitForSearchDownload.assert_called_once()
        call_args = mock_manager.waitForSearchDownload.call_args
        assert call_args[0][0] == 'wait-start-job-123'

        captured = capsys.readouterr()
        # Should show job started and final completed status
        assert 'wait-start-job-123' in captured.out
        assert 'completed' in captured.out.lower()

    def test_cli_start_with_wait_json_output(self, monkeypatch, capsys):
        """Test start command with --wait and --json outputs final status as JSON."""
        mock_manager = MagicMock()
        mock_manager._oid = 'test-oid'
        mock_manager.getJWT.return_value = 'test-jwt'
        mock_manager.initiateSearchDownload.return_value = {
            'jobId': 'wait-json-job-456',
            'estimatedStats': {'eventsMatched': 500}
        }
        final_status = {
            'jobId': 'wait-json-job-456',
            'status': 'completed',
            'resultUrl': 'https://storage.example.com/final-results.zip',
            'progress': {
                'eventsProcessed': 500,
                'bytesProcessed': 1024000
            }
        }
        mock_manager.waitForSearchDownload.return_value = final_status

        with patch('limacharlie.SearchDownload.Manager', return_value=mock_manager):
            search_download_cli([
                'start',
                '-q', '*',
                '-s', 'now-1h',
                '-e', 'now',
                '--wait',
                '--json'
            ])

        captured = capsys.readouterr()
        # With --json and --wait, the output should be the final status as JSON
        # The output will have two JSON objects: initial response and final status
        output_lines = captured.out.strip().split('\n')

        # Parse the outputs - there should be two JSON blocks
        json_blocks = []
        current_block = []
        for line in output_lines:
            current_block.append(line)
            try:
                json_blocks.append(json.loads('\n'.join(current_block)))
                current_block = []
            except json.JSONDecodeError:
                continue

        # Should have at least the final status
        assert len(json_blocks) >= 1
        # The last JSON block should be the final status
        last_block = json_blocks[-1]
        assert last_block['status'] == 'completed'
        assert last_block['resultUrl'] == 'https://storage.example.com/final-results.zip'

    def test_cli_start_with_wait_job_fails(self, monkeypatch, capsys):
        """Test start command with --wait when job fails."""
        mock_manager = MagicMock()
        mock_manager._oid = 'test-oid'
        mock_manager.getJWT.return_value = 'test-jwt'
        mock_manager.initiateSearchDownload.return_value = {
            'jobId': 'fail-job-789'
        }
        # Simulate job failure during wait
        mock_manager.waitForSearchDownload.side_effect = LcApiException(
            'Download job failed: Query timeout exceeded'
        )

        with patch('limacharlie.SearchDownload.Manager', return_value=mock_manager):
            with pytest.raises(SystemExit) as exc_info:
                search_download_cli([
                    'start',
                    '-q', '*',
                    '-s', 'now-1h',
                    '-e', 'now',
                    '--wait'
                ])

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert 'error' in captured.err.lower()
