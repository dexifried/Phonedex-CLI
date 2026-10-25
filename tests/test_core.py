import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from phonedex_cli import core


def valid_root(tmp_path):
    for rel in ["phonedex.py", "onboarding.py", "scripts/bootstrap.py"]:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# stub\n")
    return tmp_path


def test_checkout_validation(tmp_path):
    with pytest.raises(ValueError, match="missing phonedex.py"):
        core.validate_checkout(tmp_path)
    assert core.validate_checkout(valid_root(tmp_path)) == tmp_path.resolve()


def test_preference_keeps_checkout_without_touching_core(tmp_path, monkeypatch):
    monkeypatch.setenv("PHONEDEX_CLI_HOME", str(tmp_path / "settings"))
    src = valid_root(tmp_path / "core")
    core.set_checkout(src)
    assert core.get_checkout() == src.resolve()
    assert not (src / ".env").exists()
    assert json.loads(core.preferences_file().read_text())["checkout"] == str(src)


def test_update_env_preserves_existing_secrets_and_comments(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# private settings\nPHONEDEX_SIP_PASSWORD=do-not-leak\nPHONEDEX_TRANSCRIPT_MODE=off\n", encoding="utf-8")
    core.update_env(p, "PHONEDEX_TRANSCRIPT_MODE", "local")
    content = p.read_text()
    assert "PHONEDEX_SIP_PASSWORD=do-not-leak" in content
    assert "# private settings" in content
    assert "PHONEDEX_TRANSCRIPT_MODE=local" in content
    assert core.parse_env(p)["PHONEDEX_TRANSCRIPT_MODE"] == "local"
    if os.name != "nt":
        assert (p.stat().st_mode & 0o077) == 0


def test_update_env_guards(tmp_path):
    p = tmp_path / ".env"
    p.write_text("PHONEDEX_ALLOWED_RECIPIENTS=\n")
    for bad in ["123", "+1212\nPHONEDEX_SIP_PASSWORD=pwn", "+12125550101,+12125550101"]:
        with pytest.raises(ValueError):
            core.update_env(p, "PHONEDEX_ALLOWED_RECIPIENTS", bad)
    with pytest.raises(ValueError):
        core.update_env(p, "PHONEDEX_SIP_PASSWORD", "change-me")
    with pytest.raises(ValueError):
        core.update_env(p, "PHONEDEX_TRANSCRIPT_MODE", "everything")
    core.update_env(p, "PHONEDEX_ALLOWED_RECIPIENTS", "+12125550101,+14165550123")
    assert core.parse_env(p)["PHONEDEX_ALLOWED_RECIPIENTS"] == "+12125550101,+14165550123"
    for bad in ["0", "91", "-1", "2x"]:
        with pytest.raises(ValueError):
            core.update_env(p, "PHONEDEX_TRANSCRIPT_RETENTION_DAYS", bad)


def test_update_env_rejects_duplicate_key(tmp_path):
    path = tmp_path / ".env"
    path.write_text("PHONEDEX_TRANSCRIPT_MODE=off\nPHONEDEX_TRANSCRIPT_MODE=both\n")
    with pytest.raises(ValueError, match="Duplicate"):
        core.update_env(path, "PHONEDEX_TRANSCRIPT_MODE", "local")


def test_update_env_refuses_symlink(tmp_path):
    original = tmp_path / "target"
    original.write_text("PHONEDEX_TRANSCRIPT_MODE=off\n")
    link = tmp_path / ".env"
    try:
        link.symlink_to(original)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unsupported")
    with pytest.raises(ValueError, match="symlink"):
        core.update_env(link, "PHONEDEX_TRANSCRIPT_MODE", "local")


def test_no_arbitrary_git_url(tmp_path, monkeypatch):
    monkeypatch.setattr(core.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError, match="Git was not found"):
        core.clone_checkout(tmp_path / "fresh")
    with pytest.raises(ValueError, match="exists"):
        core.clone_checkout(tmp_path)


def test_pid_reuse_cannot_target_another_process(tmp_path):
    process = MagicMock()
    process.is_running.return_value = True
    process.status.return_value = "running"
    process.create_time.return_value = 1234
    process.cmdline.return_value = ["python", "something-else.py", "controller"]
    record = {"pid": 50001, "created": 1234, "script": str(tmp_path / "phonedex.py"), "root": str(tmp_path)}
    with patch.object(core.psutil, "Process", return_value=process):
        assert core._matches(record) is None
    process.cmdline.return_value = ["python", str(tmp_path / "phonedex.py"), "controller"]
    process.create_time.return_value = 1
    with patch.object(core.psutil, "Process", return_value=process):
        assert core._matches(record) is None


def test_controller_cannot_stop_unmanaged(tmp_path, monkeypatch):
    monkeypatch.setenv("PHONEDEX_CLI_HOME", str(tmp_path / "settings"))
    assert core.stop_controller(tmp_path) is False
    core._private_write(core.managed_file(), json.dumps({"pid": 99999, "created": 20, "script": "/other", "root": "/other"}))
    with patch.object(core.psutil, "Process", side_effect=core.psutil.NoSuchProcess(99999)):
        assert core.stop_controller(tmp_path) is False


def test_redacts_secret_lines():
    value = "SIP_PASSWORD=hunter2\nCHECK_MODE=local\nAuthorization: Bearer test\n"
    result = core.redact(value)
    assert "hunter2" not in result
    assert "Bearer test" not in result
    assert "CHECK_MODE=local" in result
