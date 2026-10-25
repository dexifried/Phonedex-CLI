from pathlib import Path
from unittest.mock import patch

import pytest

from phonedex_cli import app
from phonedex_cli import core


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        app.main(["--version"])
    assert exc.value.code == 0
    assert "0.1.1" in capsys.readouterr().out


def test_dial_requires_existing_checkout():
    with patch.object(core, "get_checkout", return_value=None):
        assert app.main(["--no-animation", "dial", "--to", "+12125550123"]) == 2


def test_dial_dry_run_default(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("PHONEDEX_ALLOWED_RECIPIENTS=+12125550123\n")
    with patch.object(core, "get_checkout", return_value=tmp_path):
        with patch.object(app.subprocess, "call", return_value=0) as call:
            assert app.main(["--no-color", "--no-animation", "dial", "--to", "+12125550123"]) == 0
            argv = call.call_args[0][0]
            assert "--place-call" not in argv
            assert "dial" in argv


def test_dial_not_allowlisted(tmp_path):
    (tmp_path / ".env").write_text("PHONEDEX_ALLOWED_RECIPIENTS=\n")
    with patch.object(core, "get_checkout", return_value=tmp_path):
        with patch.object(app.subprocess, "call") as call:
            assert app.main(["--no-animation", "dial", "--to", "+12125550123", "--place-call", "--yes"]) == 2
            call.assert_not_called()


def test_real_call_requires_confirmation(tmp_path):
    (tmp_path / ".env").write_text("PHONEDEX_ALLOWED_RECIPIENTS=+12125550123\n")
    with patch.object(core, "get_checkout", return_value=tmp_path):
        with patch.object(app.Confirm, "ask", return_value=False):
            with patch.object(app.subprocess, "call") as call:
                assert app.main(["--no-animation", "dial", "--to", "+12125550123", "--place-call"]) == 0
                call.assert_not_called()


def test_start_requires_explicit_confirmation(tmp_path):
    with patch.object(core, "get_checkout", return_value=tmp_path):
        with patch.object(app.Confirm, "ask", return_value=False):
            with patch.object(core, "start_controller") as start:
                assert app.main(["--no-animation", "start"]) == 0
                start.assert_not_called()
