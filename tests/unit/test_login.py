import builtins
import getpass
import yaml
import stat
import os
import tempfile

import pytest

import limacharlie.utils
from limacharlie.__main__ import cli


def test_login_default_alias_success(monkeypatch, capsys):
    _, file_path = tempfile.mkstemp()

    monkeypatch.setattr(limacharlie.utils, "CONFIG_FILE_PATH", file_path)

    # oid, name, uuid
    input_responses = iter(["85f82429-79d1-42ce-a1d4-e7aae18b271f", "", "", ""])

    # secret api key
    getpass_responses = iter(["bf4af732-bd6c-42c0-adfe-27ae851f2146"])

    # Monkeypatch builtins.input to return the next value on each call.
    monkeypatch.setattr(builtins, "input", lambda prompt: next(input_responses))
    monkeypatch.setattr(getpass, "getpass", lambda prompt: next(getpass_responses))

    cli(["limacharlie", "login"])

    captured = capsys.readouterr()
    assert "Credentials have been stored to: %s" % file_path in captured.out

    file_stat = os.stat(file_path)
    actual_mode = stat.S_IMODE(file_stat.st_mode)
    assert actual_mode == 0o600

    assert file_stat.st_uid == os.getuid()
    assert file_stat.st_gid == os.getgid()

    with open(file_path, "r") as f:
        conf = yaml.safe_load(f)
    
    assert conf == {
        "oid": "85f82429-79d1-42ce-a1d4-e7aae18b271f",
        "api_key": "bf4af732-bd6c-42c0-adfe-27ae851f2146"
    }


def test_login_custom_alias_success(monkeypatch, capsys):
    _, file_path = tempfile.mkstemp()

    monkeypatch.setattr(limacharlie.utils, "CONFIG_FILE_PATH", file_path)

    # oid, name, uuid
    input_responses = iter(["85f82429-79d1-42ce-a1d4-e7aae18b272f", "org-1", "", ""])

    # secret api key
    getpass_responses = iter(["bf4af732-bd6c-42c0-adfe-27ae851f2142"])

    # Monkeypatch builtins.input to return the next value on each call.
    monkeypatch.setattr(builtins, "input", lambda prompt: next(input_responses))
    monkeypatch.setattr(getpass, "getpass", lambda prompt: next(getpass_responses))

    cli(["limacharlie", "login"])

    captured = capsys.readouterr()
    assert "Credentials have been stored to: %s" % file_path in captured.out

    file_stat = os.stat(file_path)
    actual_mode = stat.S_IMODE(file_stat.st_mode)
    assert actual_mode == 0o600

    assert file_stat.st_uid == os.getuid()
    assert file_stat.st_gid == os.getgid()


    with open(file_path, "r") as f:
        conf = yaml.safe_load(f)
    
    assert conf == {
        "env": {
            "org-1": {
                "oid": "85f82429-79d1-42ce-a1d4-e7aae18b272f",
                "api_key": "bf4af732-bd6c-42c0-adfe-27ae851f2142"
            }
        }
    }


def test_login_custom_alias_with_existing_file_merging_success(monkeypatch, capsys):
    _, file_path = tempfile.mkstemp()

    monkeypatch.setattr(limacharlie.utils, "CONFIG_FILE_PATH", file_path)

    # oid, name, uuid
    input_responses = iter(["85f82429-79d1-42ce-a1d4-e7aae18b273f", "org-2", "", ""])

    # secret api key
    getpass_responses = iter(["bf4af732-bd6c-42c0-adfe-27ae851f2143"])

    # Monkeypatch builtins.input to return the next value on each call.
    monkeypatch.setattr(builtins, "input", lambda prompt: next(input_responses))
    monkeypatch.setattr(getpass, "getpass", lambda prompt: next(getpass_responses))

    # Write existing config entry to a file to test merging
    with open(file_path, "w") as f:
        f.write(yaml.safe_dump({"env": {"org-1": {"oid": "85f82429-79d1-42ce-a1d4-e7aae18b272f", "api_key": "bf4af732-bd6c-42c0-adfe-27ae851f2142"}}}))

    cli(["limacharlie", "login"])

    captured = capsys.readouterr()
    assert "Credentials have been stored to: %s" % file_path in captured.out

    file_stat = os.stat(file_path)
    actual_mode = stat.S_IMODE(file_stat.st_mode)
    assert actual_mode == 0o600

    assert file_stat.st_uid == os.getuid()
    assert file_stat.st_gid == os.getgid()

    with open(file_path, "r") as f:
        conf = yaml.safe_load(f)

    assert conf == {
        "env": {
            "org-1": {
                "oid": "85f82429-79d1-42ce-a1d4-e7aae18b272f",
                "api_key": "bf4af732-bd6c-42c0-adfe-27ae851f2142"
            },
            "org-2": {
                "oid": "85f82429-79d1-42ce-a1d4-e7aae18b273f",
                "api_key": "bf4af732-bd6c-42c0-adfe-27ae851f2143"
            }
        }
    }

    # Merge in default environment values

    # oid, name, uuid
    input_responses = iter(["85f82429-79d1-42ce-a1d4-e7aae18b277f", "", "", ""])

    # secret api key
    getpass_responses = iter(["bf4af732-bd6c-42c0-adfe-27ae851f2147"])

    # Monkeypatch builtins.input to return the next value on each call.
    monkeypatch.setattr(builtins, "input", lambda prompt: next(input_responses))
    monkeypatch.setattr(getpass, "getpass", lambda prompt: next(getpass_responses))

    cli(["limacharlie", "login"])

    captured = capsys.readouterr()
    assert "Credentials have been stored to: %s" % file_path in captured.out

    with open(file_path, "r") as f:
        conf = yaml.safe_load(f)

    assert conf == {
        "oid": "85f82429-79d1-42ce-a1d4-e7aae18b277f",
        "api_key": "bf4af732-bd6c-42c0-adfe-27ae851f2147",
        "env": {
            "org-1": {
                "oid": "85f82429-79d1-42ce-a1d4-e7aae18b272f",
                "api_key": "bf4af732-bd6c-42c0-adfe-27ae851f2142"
            },
            "org-2": {
                "oid": "85f82429-79d1-42ce-a1d4-e7aae18b273f",
                "api_key": "bf4af732-bd6c-42c0-adfe-27ae851f2143"
            }
        }
    }


def test_login_invalid_oid_failure(monkeypatch, capsys):
    # oid, name, uuid
    input_responses = iter(["invalid-79d1-42ce-a1d4-e7aae18b273f", "org-2", "", ""])

    # secret api key
    getpass_responses = iter(["bf4af732-bd6c-42c0-adfe-27ae851f2146"])

    # Monkeypatch builtins.input to return the next value on each call.
    monkeypatch.setattr(builtins, "input", lambda prompt: next(input_responses))
    monkeypatch.setattr(getpass, "getpass", lambda prompt: next(getpass_responses))

    with pytest.raises(SystemExit):
        cli(["limacharlie", "login"])

    captured = capsys.readouterr()
    assert "Invalid OID" in captured.out


def test_login_invalid_api_secret_failure(monkeypatch, capsys):
    # oid, name, uuid
    input_responses = iter(["invalid-79d1-42ce-a1d4-e7aae18b271f", "", "", ""])

    # secret api key
    getpass_responses = iter(["invalid-bd6c-42c0-adfe-27ae851f2146"])

    # Monkeypatch builtins.input to return the next value on each call.
    monkeypatch.setattr(builtins, "input", lambda prompt: next(input_responses))
    monkeypatch.setattr(getpass, "getpass", lambda prompt: next(getpass_responses))

    with pytest.raises(SystemExit):
        cli(["limacharlie", "login"])

    captured = capsys.readouterr()
    assert "Invalid OID" in captured.out


def test_login_invalid_uid_failure(monkeypatch, capsys):
    # oid, name, uuid
    input_responses = iter(["85f82429-79d1-42ce-a1d4-e7aae18b273f", "org-2", "invalid", ""])

    # secret api key
    getpass_responses = iter(["bf4af732-bd6c-42c0-adfe-27ae851f2143"])

    # Monkeypatch builtins.input to return the next value on each call.
    monkeypatch.setattr(builtins, "input", lambda prompt: next(input_responses))
    monkeypatch.setattr(getpass, "getpass", lambda prompt: next(getpass_responses))

    with pytest.raises(SystemExit):
        cli(["limacharlie", "login"])

    captured = capsys.readouterr()
    assert "UID must be maximum 20 characters long" in captured.out