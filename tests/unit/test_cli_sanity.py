"""
This module contains some very basic sanity tests for all the CLI commands.
"""

import limacharlie.utils
from limacharlie.__main__ import cli

# We exclude interactive action such as:
# - login
# - query
# - who
# Or actions that require config to be set up.
AVAILABLE_ACTIONS_WITHOUT_ARGUMENTS = [
    "version",
]

AVAILABLE_ACTIONS_WITH_ARGUMENTS = [
    "use",
    "dr",
    "search",
    "search-api",
    "replay",
    "sync",
    "configs",
    "spotcheck",
    "spout",
    "detections",
    "events",
    "audit",
    "hive",
    "extension",
    "model",
    "create_org",
    "schema",
    "mass-tag",
    "mass-upgrade",
    "sensors",
    "sensors_with_ip",
    "mitre-report",
    "users",
]


# NOTE: We don't have uniform and consistent arg handling across
# commands so writting tests like that in robust manner is hard.
# Some commands throw (or exit with non zero) on errors, others don't.
def test_basic_arg_parsing_sanity_commands_with_arguments(capsys):
    for action in AVAILABLE_ACTIONS_WITH_ARGUMENTS:
        print("Testing action: %s" % action)

        try:
            cli(["limacharlie", action])
        except (Exception, SystemExit):
            pass
        captured = capsys.readouterr()
        assert len(captured.out) >= 10


def test_basic_arg_parsing_sanity_commands_without_arguments(capsys):
    for action in AVAILABLE_ACTIONS_WITHOUT_ARGUMENTS:
        print("Testing action: %s" % action)

        cli(["limacharlie", action])
        captured = capsys.readouterr()
        assert len(captured.out) >= 10
