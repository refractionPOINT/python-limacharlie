import tempfile
from unittest.mock import patch

import pytest

import limacharlie.utils
import limacharlie.User
from limacharlie.__main__ import cli


def test_missing_action_cli_arg(capsys):
    with pytest.raises(SystemExit, match="2"):
        cli(["limacharlie", "users"])

    captured = capsys.readouterr()
    assert "usage: limacharlie users [-h] {invite}" in captured.err


@patch("limacharlie.User.Manager")
def test_invite_single_user_missing_args(mock_manager, capsys):
    with pytest.raises(ValueError, match="Please provide either --email or --file option."):
        cli(["limacharlie", "users", "invite"])


@patch("limacharlie.User.Manager")
def test_invite_single_user_mutually_exclusive_args(mock_manager, capsys):
    with pytest.raises(ValueError, match="--email and --file are mutually exclusive, please provide only one."):
        cli(["limacharlie", "users", "invite", "--email=test@example.com", "--file=1.txt"])


@patch("limacharlie.User.Manager.__init__", return_value=None)
@patch("limacharlie.User.Manager.inviteUser", return_value={})
def test_invite_single_user_new_user_success(_a, _b, capsys):
    cli(["limacharlie", "users", "invite", "--email=test@example.com"])

    captured = capsys.readouterr()
    assert "User with email test@example.com has been invited" in captured.out


@patch("limacharlie.User.Manager.__init__", return_value=None)
@patch("limacharlie.User.Manager.inviteUser", return_value={"exists": True})
def test_invite_single_user_already_exists_success(_a, _b, capsys):
    cli(["limacharlie", "users", "invite", "--email=test2@example.com"])

    captured = capsys.readouterr()
    assert "User with email test2@example.com already exists / has already been invited." in captured.out


@patch("limacharlie.User.Manager.__init__", return_value=None)
@patch("limacharlie.User.Manager.inviteUser", return_value={})
def test_invite_multiple_users_email_arg_success(_a, _b, capsys):
    cli(["limacharlie", "users", "invite", "--email=test1@example.com,test2@example.com,test3@example.com"])

    captured = capsys.readouterr()
    assert "User with email test1@example.com has been invited" in captured.out
    assert "User with email test2@example.com has been invited" in captured.out
    assert "User with email test3@example.com has been invited" in captured.out


@patch("limacharlie.User.Manager.__init__", return_value=None)
@patch("limacharlie.User.Manager.inviteUser", return_value={})
def test_invite_multiple_users_file_arg_unix_newline_success(_a, _b, capsys):
    emails = [
        "test1-file@example.com",
        "test2-file@example.com",
        "test3-file@example.com",
        "test4-file@example.com",
    ]
    _, file_path = tempfile.mkstemp()

    with open(file_path, "w") as fp:
        fp.write("\n".join(emails))

    cli(["limacharlie", "users", "invite", "--file=%s" % (file_path)])

    captured = capsys.readouterr()
    assert "User with email test1-file@example.com has been invited" in captured.out
    assert "User with email test2-file@example.com has been invited" in captured.out
    assert "User with email test3-file@example.com has been invited" in captured.out
    assert "User with email test4-file@example.com has been invited" in captured.out


@patch("limacharlie.User.Manager.__init__", return_value=None)
@patch("limacharlie.User.Manager.inviteUser", return_value={})
def test_invite_multiple_users_file_arg_windows_newline_success(_a, _b, capsys):
    emails = [
        "test1-file@example.com",
        "test2-file@example.com",
        "test3-file@example.com",
        "test4-file@example.com",
    ]
    _, file_path = tempfile.mkstemp()

    with open(file_path, "w") as fp:
        fp.write("\r\n".join(emails))

    cli(["limacharlie", "users", "invite", "--file=%s" % (file_path)])

    captured = capsys.readouterr()
    assert "User with email test1-file@example.com has been invited" in captured.out
    assert "User with email test2-file@example.com has been invited" in captured.out
    assert "User with email test3-file@example.com has been invited" in captured.out
    assert "User with email test4-file@example.com has been invited" in captured.out

@patch("limacharlie.User.Manager.__init__", return_value=None)
@patch("limacharlie.User.Manager.inviteUser", return_value={})
def test_invite_multiple_users_file_arg_mac_newline_success(_a, _b, capsys):
    emails = [
        "test1-file@example.com",
        "test2-file@example.com",
        "test3-file@example.com",
        "test4-file@example.com",
    ]
    _, file_path = tempfile.mkstemp()

    with open(file_path, "w") as fp:
        fp.write("\r".join(emails))

    cli(["limacharlie", "users", "invite", "--file=%s" % (file_path)])

    captured = capsys.readouterr()
    assert "User with email test1-file@example.com has been invited" in captured.out
    assert "User with email test2-file@example.com has been invited" in captured.out
    assert "User with email test3-file@example.com has been invited" in captured.out
    assert "User with email test4-file@example.com has been invited" in captured.out