"""Windows-first guided PhoneDex setup.

Every external change is an explicit prompt. The AgentPhone API integration
uses GET only; bearer tokens are never written to disk or echoed.
"""
from __future__ import annotations

import getpass
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from . import core

IS_WINDOWS = os.name == "nt"

AGENTPHONE_URL = "https://agentphone.ai"
AGENTPHONE_DOCS = "https://docs.agentphone.ai/api-reference/sip-trunks/list-sip-trunks-v-1-sip-trunks-get"
AGENTPHONE_ENDPOINT = "https://api.agentphone.ai/v1/sip-trunks"
GIT_WINGET_ID = "Git.Git"
NODE_WINGET_ID = "OpenJS.NodeJS.LTS"
PYTHON_WINGET_ID = "Python.Python.3.13"


class _NoRedirect(HTTPRedirectHandler):
    """Do not forward a user's API credential to a redirect destination."""
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def agentphone_trunks(api_key: str) -> list[dict]:
    """List trunks using read-only authenticated HTTPS. Never persist the key."""
    if not api_key or "\r" in api_key or "\n" in api_key:
        raise ValueError("Invalid AgentPhone API key")
    request = Request(
        AGENTPHONE_ENDPOINT,
        headers={"Authorization": "Bearer " + api_key,
                 "Accept": "application/json",
                 "User-Agent": "PhoneDex-CLI-Setup/0.1"},
        method="GET",
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=12) as response:
            raw = response.read(262145)
    except HTTPError as exc:
        # Never echo API response bodies, authorization or remote URLs.
        raise RuntimeError(f"AgentPhone couldn't list trunks (HTTP {exc.code})") from None
    except (URLError, OSError, TimeoutError):
        raise RuntimeError("Couldn't reach AgentPhone. Check your network and API key.") from None
    if len(raw) > 262144:
        raise RuntimeError("AgentPhone response too large")
    try:
        obj = json.loads(raw.decode("utf-8"))
        entries = obj.get("data", [])
    except (ValueError, AttributeError):
        raise RuntimeError("Unexpected AgentPhone response format") from None
    if not isinstance(entries, list):
        raise RuntimeError("Unexpected AgentPhone trunk list")
    return [item for item in entries[:100] if isinstance(item, dict)]


def create_agentphone_trunk(api_key: str) -> dict:
    """Explicit, single-attempt provider resource creation. NEVER auto-retry."""
    if not api_key or "\r" in api_key or "\n" in api_key:
        raise ValueError("Invalid AgentPhone API key")
    request = Request(
        AGENTPHONE_ENDPOINT, data=b"{}",
        headers={"Authorization": "Bearer " + api_key,
                 "Accept": "application/json",
                 "Content-Type": "application/json",
                 "User-Agent": "PhoneDex-CLI-Setup/0.1"},
        method="POST",
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=20) as response:
            raw = response.read(262145)
    except HTTPError as exc:
        raise RuntimeError(f"AgentPhone declined trunk creation (HTTP {exc.code}); check dashboard before retrying") from None
    except (URLError, OSError, TimeoutError):
        raise RuntimeError("AgentPhone creation result is unknown; check your account before attempting again") from None
    if len(raw) > 262144:
        raise RuntimeError("AgentPhone response too large; check your account for a new trunk")
    try:
        obj = json.loads(raw.decode("utf-8"))
    except ValueError:
        raise RuntimeError("Provider response unclear; check your account before retrying") from None
    if not isinstance(obj, dict):
        raise RuntimeError("Provider response unclear; check your account before retrying")
    result = obj.get("data", obj)
    if not isinstance(result, dict):
        raise RuntimeError("Provider response unclear; check your account before retrying")
    return result


def local_ipv4() -> str | None:
    """Resolve Windows' outbound LAN interface without sending a packet."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("1.1.1.1", 53))
            address = sock.getsockname()[0]
            return str(ipaddress.IPv4Address(address))
    except (OSError, ValueError):
        return None


def _tool(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt":
        system = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        locations = {
            "git": [system / "Git" / "cmd" / "git.exe"],
            "npm": [system / "nodejs" / "npm.cmd"],
            "codex": [
                Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))) /
                "npm" / "codex.cmd",
                Path.home() / ".local" / "bin" / "codex.exe",
                Path.home() / ".codex" / "bin" / "codex.exe",
            ],
        }
        for item in locations.get(name, []):
            if item.is_file():
                return str(item)
    return None


def _load_onboarding(root: Path):
    """Reuse the core project's validation and atomic private configuration writer."""
    name = "_phonedex_local_onboarding"
    spec = importlib.util.spec_from_file_location(name, root / "onboarding.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("PhoneDex core onboarding module not found")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup_snapshot(root: Path) -> dict:
    """Readiness is a local diagnostic, never a claim of completed PSTN calling."""
    argv = core.core_argv(root, "setup", "--check", "--mode", "local")
    try:
        result = core.safe_exec(argv, cwd=root)
    except (OSError, subprocess.TimeoutExpired):
        return {"local_ready": False, "missing": ["PhoneDex diagnostic failed"],
                "checks": {}, "details": ""}
    lines = result.stdout.splitlines()
    missing = [line.partition("TODO")[2].strip() for line in lines if line.strip().startswith("TODO")]
    pairs = {}
    for line in lines:
        if "=" in line and "\n" not in line:
            k, v = line.partition("=")[::2]
            pairs[k.strip()] = v.strip()
    critical = (
        "Python 3.11+", "Python packages", "Codex CLI", "Codex login",
        "SIP termination", "Public IPv4", "Caller ID", "SIP credentials",
        "Dial allowlist", "SRTP UDP forwarding",
    )
    # The core's setup --check returns 0 even if there are TODOs, so parse
    # its *content* rather than treating exit code 0 as ready.
    ready = result.returncode == 0 and not missing and all(
        any("OK" in line and label in line for line in lines) for label in critical
    )
    return {"local_ready": ready, "missing": missing, "checks": pairs,
            "details": core.redact(result.stdout)}


def _install_tool(name: str, console) -> bool:
    """Optional, exact-ID Windows package installation. No shell interpolation."""
    winget = _tool("winget")
    if not winget:
        console.print("[yellow]Windows Package Manager (winget) wasn't found. Install it from Microsoft App Installer, then reopen this terminal.[/yellow]")
        return False
    package_id = {"git": GIT_WINGET_ID, "node": NODE_WINGET_ID, "python": PYTHON_WINGET_ID}[name]
    console.print(f"Installer: winget install --exact --id {package_id}")
    if not Confirm.ask("Install this prerequisite through Windows Package Manager?", default=False):
        return False
    return subprocess.call([winget, "install", "--exact", "--id", package_id,
                            "--accept-package-agreements", "--accept-source-agreements"]) == 0


def _ensure_git(console) -> bool:
    if _tool("git"):
        console.print("[green]✓[/green] Git detected")
        return True
    console.print("Git is needed to clone PhoneDex. You may also select an existing checkout.")
    _install_tool("git", console)
    if _tool("git"):
        return True
    console.print("[yellow]Git isn't available yet. Reopen the terminal after installing it, or use an existing checkout.[/yellow]")
    return False


def _ensure_codex(console) -> bool:
    if _tool("codex"):
        console.print("[green]✓[/green] Codex CLI detected")
        return True
    console.print("Codex CLI is needed for PhoneDex's subscription-backed GPT Live.")
    npm = _tool("npm")
    if not npm:
        console.print("The Windows npm installation method needs Node.js LTS.")
        if _install_tool("node", console):
            npm = _tool("npm")
    if npm and Confirm.ask("Install the official @openai/codex CLI globally with npm?", default=False):
        result = subprocess.call([npm, "install", "-g", "@openai/codex"])
        if result:
            console.print("[yellow]Codex install wasn't successful.[/yellow]")
    if _tool("codex"):
        return True
    console.print("[yellow]Codex not yet detected. Install it, then reopen the terminal and resume this wizard.[/yellow]")
    console.print("Official installation reference: https://github.com/openai/codex")
    return False


def _choose_checkout(cockpit) -> Path | None:
    console = cockpit.console
    root = cockpit.root()
    if root and Confirm.ask(f"Use existing PhoneDex checkout at {root}?", default=True):
        return root
    choice = Prompt.ask("PhoneDex source", choices=["clone", "existing"], default="clone")
    if choice == "existing":
        candidate = Prompt.ask("Path to your existing PhoneDex checkout")
        try:
            root = core.validate_checkout(Path(candidate).expanduser())
        except (ValueError, OSError):
            console.print("[yellow]That folder isn't a compatible PhoneDex checkout.[/yellow]")
            return None
    else:
        if not _ensure_git(console):
            return None
        path = Path(Prompt.ask("Install PhoneDex into", default=str(Path.home() / "PhoneDex"))).expanduser()
        if path.exists():
            try:
                root = core.validate_checkout(path)
            except (ValueError, OSError):
                console.print("[yellow]That folder already exists and isn't a PhoneDex checkout. Choose a different path.[/yellow]")
                return None
            console.print("[green]Existing checkout found; no clone needed.[/green]")
        else:
            if not Confirm.ask(f"Clone the official public repository into {path}?", default=True):
                return None
            core.clone_checkout(path)
            root = core.validate_checkout(path)
    core.set_checkout(root)
    return root


def _bootstrap(root: Path, cockpit) -> bool:
    console = cockpit.console
    if importlib.util.find_spec("venv") is None:
        console.print("[yellow]Current Python is a stripped/embedded build without venv support.[/yellow]")
        _install_tool("python", console)
        console.print("Restart PowerShell with a full Python installation, then resume the wizard.")
        return False
    venv = root / ".venv" / "Scripts" / "python.exe"
    if venv.is_file():
        console.print("[green]✓[/green] Isolated PhoneDex Python environment found.")
        if not Confirm.ask("Reinstall/update core Python dependencies?", default=False):
            return True
    else:
        console.print("Next: create a private Python environment and install PhoneDex dependencies.")
        if not Confirm.ask("Run official core bootstrap? (installs only into .venv)", default=True):
            return False
    # --yes approves only the local Python environment bootstrap.
    result = subprocess.call([sys.executable, str(root / "scripts" / "bootstrap.py"), "--yes"], cwd=root)
    if result != 0:
        console.print("[yellow]Bootstrap failed; review the package output above and retry.[/yellow]")
    return result == 0 and venv.is_file()


def _codex_login(root: Path, cockpit) -> bool:
    console = cockpit.console
    check = setup_snapshot(root)
    if "OK  Codex login" in check["details"]:
        console.print("[green]✓[/green] Codex account already signed in.")
        return True
    exe = _tool("codex")
    if not exe:
        return False
    console.print("Sign in to Codex using its own browser-based login. PhoneDex never needs your password.")
    if Confirm.ask("Launch Codex login now?", default=True):
        subprocess.call([exe, "login"])
    # Verify with core's own OAuth status instead of assuming login succeeded.
    success = "OK  Codex login" in setup_snapshot(root)["details"]
    console.print("[green]✓[/green] Codex login ready." if success else "[yellow]Codex login still incomplete.[/yellow]")
    return success


def _agentphone_preset(console) -> dict:
    console.print(Panel(
        "Use your AgentPhone account and an existing SIP trunk.\n"
        "AgentPhone account: " + AGENTPHONE_URL + "\n"
        "Trunk docs: " + AGENTPHONE_DOCS + "\n"
        "The default action only READS trunks. Creating one requires a separate explicit confirmation.",
        title="AgentPhone SIP setup"))
    if not Confirm.ask("List your AgentPhone trunks securely using your API key?", default=False):
        return {}
    key = getpass.getpass("AgentPhone API key (hidden; not saved): ")
    try:
        trunks = agentphone_trunks(key)
        if not trunks:
            console.print("[yellow]No existing SIP trunks found.[/yellow]")
            console.print("Creating a trunk changes your AgentPhone account. Check any provider billing or limits first.")
            if not Confirm.ask("CREATE one new AgentPhone SIP trunk now? (external account change)", default=False):
                return {}
            console.print("Sending a single trunk-creation request. No automatic retry on uncertain results.")
            selected = create_agentphone_trunk(key)
        else:
            table = Table(title="Available SIP trunks")
            table.add_column("#")
            table.add_column("Name")
            table.add_column("TLS")
            table.add_column("Media")
            for index, trunk in enumerate(trunks, start=1):
                table.add_row(str(index), str(trunk.get("name", "Unnamed"))[:60],
                              str(trunk.get("transport", "?"))[:20],
                              str(trunk.get("mediaEncryption", "?"))[:20])
            console.print(table)
            choice = Prompt.ask("Use which trunk? (0 = manual entry)",
                                choices=[str(i) for i in range(0, len(trunks)+1)], default="1")
            if choice == "0":
                return {}
            selected = trunks[int(choice)-1]
        if str(selected.get("transport", "")).lower() not in ("tls", "tcp/tls"):
            console.print("[yellow]This trunk may not use TLS SIP signaling. Verify compatibility before calling.[/yellow]")
        uri = selected.get("terminationSipUri")
        credentials = selected.get("credentials") or []
        first = next((x for x in credentials if isinstance(x, dict) and x.get("username")), {})
        return {
            "uri": uri if isinstance(uri, str) else "",
            "username": str(first.get("username", "")),
            "password": str(first.get("password") or ""),
        }
    finally:
        key = None


def _provider_configuration(root: Path, cockpit) -> bool:
    console = cockpit.console
    env = root / ".env"
    if env.exists():
        console.print("[green]✓[/green] Existing private .env found; credentials will NOT be overwritten.")
        console.print("[dim]For changes, review .env locally or use CLI settings for non-secret fields.[/dim]")
        return True
    console.print(Panel(
        "Choose your SIP provider. PhoneDex does not purchase phone numbers.\n"
        "For AgentPhone, it can read existing trunks and optionally create a new trunk "
        "only after explicit approval. Your API key is never saved.",
        title="Provider and phone credentials"))
    provider = Prompt.ask("SIP provider", choices=["agentphone", "other"], default="agentphone")
    preset = {}
    if provider == "agentphone":
        try:
            preset = _agentphone_preset(console)
        except (ValueError, RuntimeError) as exc:
            console.print(f"[yellow]{exc}[/yellow]")
        if not preset and not Confirm.ask("Continue with manual SIP credentials?", default=True):
            return False
    onboarding = _load_onboarding(root)
    def field(label, validator, default="", *, hidden=False):
        while True:
            if default and not hidden:
                answer = Prompt.ask(label, default=default)
            elif hidden:
                answer = getpass.getpass(label + " (hidden): ")
            else:
                answer = Prompt.ask(label)
            try:
                return validator(answer)
            except (ValueError, TypeError) as exc:
                console.print(f"[yellow]{exc}[/yellow]")

    console.print("Everything here stays in the private core .env, except the AgentPhone API key (discarded).")
    uri = field("Provider SIP termination URI", onboarding.sip_target,
                preset.get("uri") or "")
    console.print("Your caller ID must be a number your provider permits you to originate from.")
    caller_id = field("Approved caller ID (+country code)", onboarding.e164)

    console.print("Use the public IPv4 your router exposes; do not enter your LAN 192.168.x.x address.")
    console.print("You can look it up in your own browser: https://api.ipify.org")
    public_ip = field("Your public IPv4 address", onboarding.public_ipv4)

    username = field("Provider SIP username", onboarding.checked_field,
                     preset.get("username") or "")
    # Some carriers return redacted passwords (e.g. ****) on a trunk GET.
    password = preset.get("password") or ""
    if not password or "*" in password:
        password = field("Provider SIP password", onboarding.checked_field, hidden=True)
    else:
        console.print("[green]✓[/green] Using SIP password returned by the selected trunk (not displayed).")

    console.print("Specify only numbers you own or have permission to call.")
    allowlist = field("Approved test recipients (comma-separated E.164)",
                      onboarding.approved_recipients)
    values = {
        "PHONEDEX_TERMINATION_URI": uri,
        "PHONEDEX_PUBLIC_IP": public_ip,
        "PHONEDEX_MEDIA_PORT": "41002",
        "PHONEDEX_MEDIA_PORT_FORWARDED": "0",
        "PHONEDEX_CALLER_ID": caller_id,
        "PHONEDEX_SIP_USERNAME": username,
        "PHONEDEX_SIP_PASSWORD": password,
        "PHONEDEX_ALLOWED_RECIPIENTS": allowlist,
        "PHONEDEX_MAX_CALLS_PER_DAY": "12",
        "PHONEDEX_TRANSCRIPT_MODE": "off",
        "PHONEDEX_TRANSCRIPT_RETENTION_DAYS": "7",
    }
    if not Confirm.ask("Save this SIP configuration in a new private .env? (plaintext local credential file)", default=True):
        console.print("[yellow]Configuration not saved.[/yellow]")
        return False
    try:
        onboarding.save_env(root, values)
    except (OSError, ValueError, FileExistsError) as exc:
        console.print(f"[red]Configuration could not be saved: {type(exc).__name__}[/red]")
        return False
    finally:
        values["PHONEDEX_SIP_PASSWORD"] = ""
        password = ""
    console.print("[green]✓[/green] Saved private PhoneDex settings. No calls or provider changes were made.")
    return True


def _network_guide(root: Path, cockpit) -> None:
    console = cockpit.console
    env = root / ".env"
    values = core.parse_env(env)
    port = int(values.get("PHONEDEX_MEDIA_PORT", "41002"))
    lan = local_ipv4()
    console.print(Panel(
        f"1. Find your Windows PC's LAN address: {lan or 'run ipconfig'}.\n"
        f"2. In the router's port forwarding settings, direct UDP {port} "
        f"to that computer's UDP {port}.\n"
        f"3. In Windows Defender Firewall, allow inbound UDP {port} "
        "only from your trusted SIP carrier's media endpoints if feasible.\n"
        "4. Verify the mapping using a real carrier/network test. "
        "A checkbox cannot prove NAT traversal.\n"
        "Windows Firewall: wf.msc  |  Router: your own router settings.",
        title="Windows network and RTP"))
    if values.get("PHONEDEX_MEDIA_PORT_FORWARDED") == "1":
        console.print("[yellow]Media forwarding was previously marked as confirmed. It has not been externally retested.[/yellow]")
        return
    if Confirm.ask("Have you configured BOTH UDP forwarding and Windows firewall access, and verified externally?", default=False):
        core.update_env(env, "PHONEDEX_MEDIA_PORT_FORWARDED", "1")
        console.print("[green]Marked complete based on your confirmation.[/green] A real SIP call is still necessary to confirm audio.")
    else:
        console.print("[yellow]Media forwarding remains disabled (safe default). You can resume later.[/yellow]")


def run(cockpit) -> bool:
    """Guided, resumable setup on native Windows; never claim an untested call works."""
    console = cockpit.console
    cockpit.banner()
    console.print(Panel(
        "[bold]1[/bold] Prerequisites and checkout\n"
        "[bold]2[/bold] Isolated Python installation\n"
        "[bold]3[/bold] Codex sign-in\n"
        "[bold]4[/bold] AgentPhone / SIP provider\n"
        "[bold]5[/bold] Windows firewall and router\n"
        "[bold]6[/bold] Readiness diagnostics\n"
        "[bold]7[/bold] Optional first test call",
        title="PhoneDex Windows setup · Start to finish", border_style="bright_cyan"))
    if not IS_WINDOWS:
        console.print("[yellow]This guided journey targets native Windows. Use the standard PhoneDex core setup on other platforms.[/yellow]")
        return False
    if sys.version_info < (3,11):
        console.print("[red]Python 3.11+ is required. Install it and rerun this command.[/red]")
        return False

    console.rule("[cyan]1 / 7  PhoneDex checkout[/cyan]")
    root = _choose_checkout(cockpit)
    if root is None:
        return False

    console.rule("[cyan]2 / 7  Python packages[/cyan]")
    _bootstrap(root, cockpit)

    console.rule("[cyan]3 / 7  Codex authentication[/cyan]")
    if _ensure_codex(console):
        _codex_login(root, cockpit)

    console.rule("[cyan]4 / 7  SIP provider[/cyan]")
    _provider_configuration(root, cockpit)

    console.rule("[cyan]5 / 7  Network setup[/cyan]")
    if (root / ".env").is_file():
        _network_guide(root, cockpit)
    else:
        console.print("[yellow]Provider configuration is incomplete. No network changes made.[/yellow]")

    console.rule("[cyan]6 / 7  Readiness checks[/cyan]")
    report = setup_snapshot(root)
    console.print(Panel(report["details"] or "Core readiness diagnostics unavailable.",
                        title="PhoneDex core readiness", border_style="cyan", highlight=False))
    console.print("[yellow]No external SIP/PSTN test has been performed yet.[/yellow]")
    if not report["local_ready"]:
        console.print("[yellow]Setup incomplete. Fix the TODO items and rerun phonedex-cli wizard to resume.[/yellow]")
        return False

    console.rule("[cyan]7 / 7  Authorized first call[/cyan]")
    console.print("[green]Local configuration checks passed.[/green] SIP carrier compatibility and audio are still unverified.")
    if not Confirm.ask("Run a zero-cost local dial dry run?", default=True):
        return True
    allowed = [x.strip() for x in core.parse_env(root / ".env").get(
        "PHONEDEX_ALLOWED_RECIPIENTS", "").split(",") if x.strip()]
    if not allowed:
        console.print("[yellow]No approved destination configured.[/yellow]")
        return False
    dest = Prompt.ask("Approved test number", default=allowed[0])
    if dest not in allowed:
        console.print("[yellow]That number is not on your outbound allowlist.[/yellow]")
        return False
    if cockpit.dial(dest, duration=30) != 0:
        console.print("[yellow]Dry run failed. Review the output above.[/yellow]")
        return False
    if Confirm.ask("Place a REAL, potentially billable 30-second test call to this approved number?", default=False):
        cockpit.dial(dest, duration=30, place_call=True)
        console.print("Confirm ringing, audio in BOTH directions and clean hangup yourself.")
    else:
        console.print("No real call placed; carrier and media remain unverified.")
    return True
