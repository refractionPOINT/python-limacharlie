import os

from limacharlie.__main__ import cli
import limacharlie.utils


def test_invite_user_already_exists(oid, key, uid, capsys):
    # TODO: Move to conftest.py once #156 with new tests directory layout is merged
    # TODO: Talk with Maxime to provisione another user scoped API key for tests
    return
    os.environ["LC_OID"] = oid
    os.environ["LC_API_KEY"] = key
    os.environ["LC_UID"] = uid

    cli(["limacharlie", "invite-user", "--email=tomaz@tomaz.me"])

    captured = capsys.readouterr()
    assert "User with email tomaz+test10@tomaz.me already exists / has already been invited" in captured.out


def test_invite_user_invalid_email(oid, key, uid, capsys):
    # TODO: Update once we change error message on the backend
    return
    cli(["limacharlie", "invite-user", "--email=invalid"])

    captured = capsys.readouterr()
    assert "Error: Api failure (400): malformed email string: \"invalid\"" in captured.out