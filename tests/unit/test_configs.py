"""
Unit tests for limacharlie.Configs module.

Tests CLI argument parsing and hive configuration for the configs command.
"""

import io
import sys
from unittest import mock

import pytest


class TestConfigsCliExternalAdapterArg:
    """Tests for --hive-external-adapter CLI argument in the configs command."""

    def test_external_adapter_flag_recognized_in_help(self, capsys):
        """Test that --hive-external-adapter appears in CLI help output."""
        from limacharlie.Configs import main

        with pytest.raises(SystemExit) as exc_info:
            main(['--help'])

        # argparse exits with 0 on --help
        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert '--hive-external-adapter' in captured.out
        assert 'external adapters' in captured.out.lower()

    def test_external_adapter_flag_sets_hive_in_fetch(self):
        """Test that --hive-external-adapter flag passes external_adapter to fetch."""
        from limacharlie.Configs import main

        with mock.patch('limacharlie.Configs.Configs') as MockConfigs:
            mock_instance = MockConfigs.return_value
            mock_instance.fetch = mock.Mock()

            # Call main with --hive-external-adapter flag
            main(['fetch', '-o', '00000000-0000-0000-0000-000000000000',
                  '--hive-external-adapter', '-c', '/tmp/test.yaml'])

            # Verify fetch was called with external_adapter in isHives
            mock_instance.fetch.assert_called_once()
            call_kwargs = mock_instance.fetch.call_args[1]
            assert 'isHives' in call_kwargs
            assert call_kwargs['isHives'].get('external_adapter') is True

    def test_external_adapter_flag_sets_hive_in_push(self):
        """Test that --hive-external-adapter flag passes external_adapter to push."""
        from limacharlie.Configs import main

        with mock.patch('limacharlie.Configs.Configs') as MockConfigs:
            mock_instance = MockConfigs.return_value
            # push() is a generator, so we need to mock it as one
            mock_instance.push = mock.Mock(return_value=iter([]))

            # Call main with --hive-external-adapter flag
            main(['push', '-o', '00000000-0000-0000-0000-000000000000',
                  '--hive-external-adapter', '-c', '/tmp/test.yaml'])

            # Verify push was called with external_adapter in isHives
            mock_instance.push.assert_called_once()
            call_kwargs = mock_instance.push.call_args[1]
            assert 'isHives' in call_kwargs
            assert call_kwargs['isHives'].get('external_adapter') is True

    def test_external_adapter_not_set_when_flag_omitted(self):
        """Test that external_adapter is not in hives when flag is not provided."""
        from limacharlie.Configs import main

        with mock.patch('limacharlie.Configs.Configs') as MockConfigs:
            mock_instance = MockConfigs.return_value
            mock_instance.fetch = mock.Mock()

            # Call main with only --hive-cloud-sensor (not external_adapter)
            main(['fetch', '-o', '00000000-0000-0000-0000-000000000000',
                  '--hive-cloud-sensor', '-c', '/tmp/test.yaml'])

            # Verify fetch was called without external_adapter in isHives
            mock_instance.fetch.assert_called_once()
            call_kwargs = mock_instance.fetch.call_args[1]
            assert 'isHives' in call_kwargs
            assert call_kwargs['isHives'].get('external_adapter') is not True


class TestConfigsAllFlag:
    """Tests for --all flag including external_adapter hive."""

    def test_all_flag_includes_external_adapter_in_fetch(self):
        """Test that --all flag includes external_adapter in hives for fetch."""
        from limacharlie.Configs import main

        with mock.patch('limacharlie.Configs.Configs') as MockConfigs:
            mock_instance = MockConfigs.return_value
            mock_instance.fetch = mock.Mock()

            # Call main with --all flag
            main(['fetch', '-o', '00000000-0000-0000-0000-000000000000',
                  '--all', '-c', '/tmp/test.yaml'])

            # Verify fetch was called with external_adapter in isHives
            mock_instance.fetch.assert_called_once()
            call_kwargs = mock_instance.fetch.call_args[1]
            assert 'isHives' in call_kwargs
            assert call_kwargs['isHives'].get('external_adapter') is True

    def test_all_flag_includes_external_adapter_in_push(self):
        """Test that --all flag includes external_adapter in hives for push."""
        from limacharlie.Configs import main

        with mock.patch('limacharlie.Configs.Configs') as MockConfigs:
            mock_instance = MockConfigs.return_value
            mock_instance.push = mock.Mock(return_value=iter([]))

            # Call main with --all flag
            main(['push', '-o', '00000000-0000-0000-0000-000000000000',
                  '--all', '-c', '/tmp/test.yaml'])

            # Verify push was called with external_adapter in isHives
            mock_instance.push.assert_called_once()
            call_kwargs = mock_instance.push.call_args[1]
            assert 'isHives' in call_kwargs
            assert call_kwargs['isHives'].get('external_adapter') is True

    def test_all_flag_includes_all_expected_hives(self):
        """Test that --all flag includes all 14 expected hives."""
        from limacharlie.Configs import main

        expected_hives = {
            'dr-general',
            'dr-managed',
            'dr-service',
            'fp',
            'cloud_sensor',
            'extension_config',
            'yara',
            'lookup',
            'secret',
            'query',
            'playbook',
            'ai_agent',
            'external_adapter',
        }

        with mock.patch('limacharlie.Configs.Configs') as MockConfigs:
            mock_instance = MockConfigs.return_value
            mock_instance.fetch = mock.Mock()

            main(['fetch', '-o', '00000000-0000-0000-0000-000000000000',
                  '--all', '-c', '/tmp/test.yaml'])

            call_kwargs = mock_instance.fetch.call_args[1]
            actual_hives = set(call_kwargs['isHives'].keys())

            assert actual_hives == expected_hives, \
                f"Missing hives: {expected_hives - actual_hives}, " \
                f"Extra hives: {actual_hives - expected_hives}"


class TestConfigsMultipleHiveFlags:
    """Tests for combining multiple hive flags."""

    def test_multiple_hive_flags_combined(self):
        """Test that multiple hive flags are combined correctly."""
        from limacharlie.Configs import main

        with mock.patch('limacharlie.Configs.Configs') as MockConfigs:
            mock_instance = MockConfigs.return_value
            mock_instance.fetch = mock.Mock()

            # Call main with multiple hive flags
            main(['fetch', '-o', '00000000-0000-0000-0000-000000000000',
                  '--hive-external-adapter', '--hive-cloud-sensor', '--hive-lookup',
                  '-c', '/tmp/test.yaml'])

            call_kwargs = mock_instance.fetch.call_args[1]
            hives = call_kwargs['isHives']

            # All three should be present
            assert hives.get('external_adapter') is True
            assert hives.get('cloud_sensor') is True
            assert hives.get('lookup') is True

            # Others should not be present
            assert hives.get('playbook') is not True
            assert hives.get('secret') is not True
