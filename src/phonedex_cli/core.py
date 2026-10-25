"""Side-effect-aware local integration with the public PhoneDex checkout.

Nothing in this module provisions a SIP trunk, forwards ports or places a call.
The CLI delegates actual SIP work and configuration validation to PhoneDex.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import psutil

UPSTREAM = "https://github.com/dexifried/Phonedex.git"
E164 = re.compile(r"\+[1-9]\d{6,14}\Z")
CONFIGURABLE = {"PHONEDEX_TRANSCRIPT_MODE", "PHONEDEX_TRANSCRIPT_RETENTION_DAYS",
                "PHONEDEX_MAX_CALLS_PER_DAY", "PHONEDEX_ALLOWED_RECIPIENTS",
                "PHONEDEX_MEDIA_PORT_FORWARDED"}
SENSITIVE = re.compile(r"(password|token|secret|api.?key|authorization|bearer)", re.I)


def home_dir() -> Path:
    override = os.environ.get("PHONEDEX_CLI_HOME")
    if override:
        return Path(override).expanduser()
    if os.name == "nt" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "PhoneDexCLI"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "phonedex-cli"


def preferences_file() -> Path:
    return home_dir() / "config.json"


def managed_file() -> Path:
    return home_dir() / "controller.json"


def _private_write(path: Path, data: str) -> None:
    """Atomic owner-only write on POSIX; inherits local user ACLs on Windows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"Refusing to write through symlink: {path}")
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def preferences() -> dict:
    try:
        val = json.loads(preferences_file().read_text(encoding="utf-8"))
        return val if isinstance(val, dict) else {}
    except (OSError, ValueError):
        return {}


def set_checkout(path: Path) -> None:
    path = validate_checkout(path)
    prefs = preferences()
    prefs["checkout"] = str(path)
    _private_write(preferences_file(), json.dumps(prefs, indent=2) + "\n")


def get_checkout(explicit: str | None = None) -> Path | None:
    raw = explicit or os.environ.get("PHONEDEX_HOME") or preferences().get("checkout")
    if not raw:
        return None
    try:
        return validate_checkout(Path(raw))
    except (ValueError, OSError):
        return None


def validate_checkout(path: Path) -> Path:
    candidate = path.expanduser().resolve()
    for file in ("phonedex.py", "onboarding.py", "scripts/bootstrap.py"):
        if not (candidate / file).is_file():
            raise ValueError(f"Not a compatible PhoneDex checkout (missing {file}): {candidate}")
    return candidate


def core_python(root: Path) -> str:
    if os.name == "nt":
        venv = root / ".venv" / "Scripts" / "python.exe"
    else:
        venv = root / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


def core_argv(root: Path, *args: str) -> list[str]:
    return [core_python(root), str(root / "phonedex.py"), *args]


def safe_exec(argv: list[str], *, cwd: Path | None = None, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, text=True, encoding="utf-8", errors="replace",
                          capture_output=True, timeout=timeout, check=False)


def parse_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        key = k.strip()
        if not re.fullmatch(r"PHONEDEX_[A-Z0-9_]+", key):
            continue
        v = v.strip()
        if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
            v = v[1:-1]
        result[key] = v
    return result


def update_env(path: Path, key: str, value: str) -> None:
    if key not in CONFIGURABLE:
        raise ValueError(f"Setting not supported by CLI editor: {key}")
    if path.is_symlink():
        raise ValueError("Refusing to edit symlinked .env")
    if not path.is_file():
        raise ValueError("No .env found. Run PhoneDex setup first.")
    if "\n" in value or "\r" in value or "#" in value:
        raise ValueError("Invalid configuration value")
    if key == "PHONEDEX_TRANSCRIPT_MODE" and value not in {"off", "local", "worker", "both"}:
        raise ValueError("Invalid transcript mode")
    if key == "PHONEDEX_TRANSCRIPT_RETENTION_DAYS" and not (value.isascii() and value.isdecimal() and 1 <= int(value) <= 90):
        raise ValueError("Retention must be 1–90 days")
    if key == "PHONEDEX_MAX_CALLS_PER_DAY" and not (value.isascii() and value.isdecimal() and 1 <= int(value) <= 1000):
        raise ValueError("Daily limit must be 1–1000")
    if key == "PHONEDEX_MEDIA_PORT_FORWARDED" and value not in {"0", "1"}:
        raise ValueError("Port-forwarding confirmation must be 0 or 1")
    if key == "PHONEDEX_ALLOWED_RECIPIENTS":
        numbers = [n.strip() for n in value.split(",") if n.strip()]
        if any(not E164.fullmatch(n) for n in numbers) or len(numbers) != len(set(numbers)):
            raise ValueError("Only unique E.164 phone numbers are allowed")
        value = ",".join(numbers)
    original = path.read_text(encoding="utf-8-sig")
    parts = original.splitlines(keepends=True)
    found = False
    for i, line in enumerate(parts):
        if re.match(r"^\s*" + re.escape(key) + r"\s*=", line):
            if found:
                raise ValueError("Duplicate setting present; resolve it manually")
            parts[i] = key + "=" + value + ("\r\n" if line.endswith("\r\n") else "\n")
            found = True
    if not found:
        if parts and not parts[-1].endswith(("\r", "\n")):
            parts.append("\n")
        parts.append(key + "=" + value + "\n")
    _private_write(path, "".join(parts))


def _record() -> dict:
    try:
        record = json.loads(managed_file().read_text(encoding="utf-8"))
        return record if isinstance(record, dict) else {}
    except (OSError, ValueError):
        return {}


def _matches(record: dict) -> psutil.Process | None:
    try:
        pid, created, script, root = int(record["pid"]), float(record["created"]), record["script"], record["root"]
        if pid == os.getpid():
            return None
        proc = psutil.Process(pid)
        if not proc.is_running() or proc.status() == psutil.STATUS_ZOMBIE or abs(proc.create_time() - created) >= 2:
            return None
        cmd = proc.cmdline()
        # A stale or PID-reused record must never terminate another process.
        if str(Path(script).resolve()) not in [str(Path(c).resolve()) for c in cmd]:
            return None
        if "controller" not in cmd:
            return None
        if str(Path(script).resolve().parent) != str(Path(root).resolve()):
            return None
        return proc
    except (psutil.Error, OSError, ValueError, KeyError, TypeError):
        return None


def controller_status(root: Path | None = None) -> tuple[str, dict]:
    record = _record()
    if not record:
        return "stopped", {}
    proc = _matches(record)
    if proc is None:
        return "stale", record
    if root is not None and Path(record["root"]).resolve() != root.resolve():
        return "other-checkout", record
    return "running", record


def start_controller(root: Path) -> int:
    state, _ = controller_status()
    if state == "running":
        raise RuntimeError("A controller managed by this CLI is already running")
    logfile = home_dir() / "controller.log"
    logfile.parent.mkdir(parents=True, exist_ok=True)
    argv = core_argv(root, "controller")
    options = {"cwd": root, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        options["start_new_session"] = True
    with logfile.open("a", encoding="utf-8") as output:
        proc = subprocess.Popen(argv, stdout=output, stderr=subprocess.STDOUT, **options)
    try:
        started = psutil.Process(proc.pid).create_time()
        _private_write(managed_file(), json.dumps({"pid": proc.pid, "created": started,
                  "root": str(root.resolve()), "script": str((root / "phonedex.py").resolve()),
                  "log": str(logfile)}, indent=2) + "\n")
    except Exception:
        # Never orphan a controller if we cannot register it safely.
        proc.terminate()
        raise
    time.sleep(0.2)
    if proc.poll() is not None:
        return_code = proc.returncode
        managed_file().unlink(missing_ok=True)
        raise RuntimeError(f"Controller exited during startup (code {return_code}); view logs")
    return proc.pid


def stop_controller(root: Path) -> bool:
    state, record = controller_status(root)
    if state != "running":
        return False
    proc = _matches(record)
    if proc is None:
        return False
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except psutil.TimeoutExpired:
        # Do not force-kill; callers can inspect process and stop it manually.
        raise RuntimeError("Controller did not stop within 8 seconds; not force-killing")
    managed_file().unlink(missing_ok=True)
    return True


def clone_checkout(dest: Path) -> None:
    if dest.exists():
        raise ValueError("Destination already exists; refusing to overwrite it")
    git = shutil.which("git")
    if not git:
        raise RuntimeError("Git was not found; install Git or point the CLI to an existing checkout")
    # Public upstream only; no credentials or local arbitrary URLs.
    completed = safe_exec([git, "clone", "--depth", "1", UPSTREAM, str(dest)], timeout=180)
    if completed.returncode:
        raise RuntimeError("Git clone failed: " + completed.stderr[-1500:])
    validate_checkout(dest)


def redact(text: str) -> str:
    """Best-effort log/output redaction; never claim complete sanitization."""
    clean = []
    for line in text.splitlines():
        if SENSITIVE.search(line):
            clean.append("[redacted sensitive line]")
        else:
            clean.append(line)
    return "\n".join(clean)
