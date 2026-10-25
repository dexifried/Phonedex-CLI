"""Rich-powered PhoneDex companion. No SIP internals are duplicated here."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from rich import box
from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

from . import __version__
from . import core

ASCII = r"""
  ____  _                     ____
 |  _ \| |__   ___  _ __   ___|  _ \  _____  __
 | |_) | '_ \ / _ \| '_ \ / _ \ | | |/ _ \ \/ /
 |  __/| | | | (_) | | | |  __/ |_| |  __/>  <
 |_|   |_| |_|\___/|_| |_|\___|____/ \___/_/\_\
"""

class Cockpit:
    def __init__(self, *, no_color: bool = False, no_animation: bool = False, checkout: str | None = None):
        self.console = Console(no_color=no_color or bool(os.environ.get("NO_COLOR")))
        self.animations = not no_animation and self.console.is_terminal and not os.environ.get("CI")
        self.checkout_override = checkout

    def banner(self) -> None:
        art = Text(ASCII, style="bold bright_cyan")
        if self.animations:
            # A short, skippable terminal-only text reveal; never animates in CI/pipes.
            with Live(Align.center(Text("Initializing PhoneDex", style="bright_cyan")),
                      console=self.console, transient=True, auto_refresh=False) as live:
                for shown in range(0, len(ASCII) + 16, max(12, len(ASCII) // 9)):
                    live.update(Align.center(Text(ASCII[:shown], style="bold bright_cyan")), refresh=True)
                    time.sleep(0.025)
        self.console.print(Align.center(art))
        self.console.print(Align.center(Text("TERMINAL CONTROL  //  an optional PhoneDex companion", style="bold magenta")))
        self.console.print(Align.center(Text(f"v{__version__} · local-first · separate from the SIP engine", style="dim")))
        self.console.print()

    def transition(self, message: str) -> None:
        if not self.animations:
            return
        with self.console.status(f"[cyan]{message}[/cyan]", spinner="dots12"):
            time.sleep(0.32)

    def root(self) -> Path | None:
        return core.get_checkout(self.checkout_override)

    def require_root(self) -> Path:
        root = self.root()
        if root is None:
            raise RuntimeError("PhoneDex source checkout not configured. Run 'phonedex-cli wizard' first.")
        return root

    def status(self) -> None:
        root = self.root()
        state, record = core.controller_status(root)
        table = Table(title="PhoneDex system overview", box=box.ROUNDED, header_style="bold cyan")
        table.add_column("Component", style="bold")
        table.add_column("Status")
        table.add_column("Detail", overflow="fold")
        table.add_row("Core checkout", "[green]Found[/green]" if root else "[yellow]Not configured[/yellow]", str(root) if root else "Run wizard")
        table.add_row("Python", "[green]Available[/green]" if sys.version_info >= (3, 11) else "[red]Too old[/red]", sys.version.split()[0])
        table.add_row("Codex CLI", "[green]Detected[/green]" if shutil.which("codex") else "[yellow]Not in PATH[/yellow]", "Sign in locally using codex login" if shutil.which("codex") else "Install separately before GPT Live use")
        label = {"running": "[green]Running[/green]", "stopped": "[dim]Stopped[/dim]", "stale": "[yellow]Not running (stale PID)[/yellow]", "other-checkout": "[yellow]Different checkout[/yellow]"}[state]
        table.add_row("Managed controller", label, f"PID {record.get('pid')}" if state == "running" else "")
        if root:
            details = core.parse_env(root / ".env")
            mode = details.get("PHONEDEX_TRANSCRIPT_MODE", "off")
            table.add_row("Local config", "[green]Present[/green]" if (root / ".env").is_file() else "[yellow]Not set up[/yellow]", f"transcripts={mode}; recipients={len([n for n in details.get('PHONEDEX_ALLOWED_RECIPIENTS', '').split(',') if n.strip()])}")
            venv = root / ".venv"
            table.add_row("Python environment", "[green]Isolated[/green]" if venv.is_dir() else "[yellow]Not bootstrapped[/yellow]", str(venv) if venv.is_dir() else "Run wizard bootstrap")
        self.console.print(table)
        self.console.print("[dim]Status shows only processes started by this CLI. It does not inspect or control unrelated live gateways.[/dim]")

    def check(self, mode: str = "local") -> int:
        root = self.require_root()
        self.transition("Reading readiness diagnostics")
        results = [
            ("Setup readiness", core.core_argv(root, "setup", "--mode", mode, "--check")),
            ("Runtime doctor", core.core_argv(root, "doctor", "--mode", mode)),
        ]
        result_code = 0
        for name, command in results:
            self.console.rule(f"[cyan]{name}[/cyan]")
            try:
                result = core.safe_exec(command, cwd=root)
            except (OSError, subprocess.TimeoutExpired) as exc:
                self.console.print(f"[red]{name} could not run:[/red] {exc}")
                result_code = 1
                continue
            for line in core.redact(result.stdout).splitlines():
                if "=" in line and not line.startswith("["):
                    key, _, value = line.partition("=")
                    if value.strip() in {"ok", "valid", "none", "true"}:
                        self.console.print(f"[green]●[/green] {key}: {value}")
                    else:
                        self.console.print(f"[cyan]•[/cyan] {key}: {value}")
                else:
                    self.console.print(line)
            if result.stderr:
                self.console.print("[yellow]Runtime detail:[/yellow] " + core.redact(result.stderr)[-1200:])
            if result.returncode:
                result_code = 1
        self.console.print("[dim]Read-only checks. No call placed, firewall changed, or Worker deployed.[/dim]")
        return result_code

    def setup(self, mode: str = "local") -> int:
        root = self.require_root()
        self.console.print(Panel("This delegates to the [bold]official PhoneDex setup wizard[/bold].\nIt only writes local configuration with your permission; it cannot provision a provider or place calls.", title="Official core setup", border_style="cyan"))
        if (root / ".env").exists():
            self.console.print("[yellow]An existing .env was found. The core wizard refuses to overwrite it.[/yellow]")
        if not Confirm.ask("Launch PhoneDex's local setup now?", default=True):
            return 0
        return subprocess.call(core.core_argv(root, "setup", "--mode", mode), cwd=root)

    def wizard(self) -> None:
        """On Windows, complete the resumable seven-step setup journey."""
        if sys.platform == "win32":
            from . import windows_setup
            windows_setup.run(self)
        else:
            self._legacy_wizard()

    def _legacy_wizard(self) -> None:
        self.banner()
        self.console.print(Panel("[bold]1[/bold]  Connect a PhoneDex checkout\n[bold]2[/bold]  Prepare Python dependencies\n[bold]3[/bold]  Codex login (performed locally)\n[bold]4[/bold]  SIP/provider configuration\n[bold]5[/bold]  Read-only diagnostics", title="First-run wizard", border_style="bright_cyan"))
        root = self.root()
        if root:
            self.console.print(f"[green]✓[/green] Existing PhoneDex checkout: [bold]{root}[/bold]")
            if not Confirm.ask("Use this checkout?", default=True):
                root = None
        if root is None:
            action = Prompt.ask("PhoneDex source", choices=["existing", "clone"], default="clone")
            if action == "existing":
                while True:
                    candidate = Path(Prompt.ask("Absolute or relative path to PhoneDex checkout")).expanduser()
                    try:
                        root = core.validate_checkout(candidate)
                        break
                    except ValueError as exc:
                        self.console.print(f"[red]{exc}[/red]")
                        if not Confirm.ask("Try another path?", default=True):
                            return
            else:
                default = str(Path.home() / "PhoneDex")
                target = Path(Prompt.ask("Clone into", default=default)).expanduser()
                self.console.print("Clone source: [cyan]https://github.com/dexifried/Phonedex[/cyan]")
                if not Confirm.ask(f"Clone the official public source to {target}?", default=True):
                    return
                self.transition("Preparing checkout")
                core.clone_checkout(target)
                root = core.validate_checkout(target)
            core.set_checkout(root)
        self.console.print(f"[green]✓[/green] Source linked: {root}")
        mode = Prompt.ask("Setup mode", choices=["local", "remote"], default="local")
        self.console.print("[dim]Local = outbound calling without Cloudflare. Remote = optional Worker-based agent control.[/dim]")
        if Confirm.ask("Run the official dependency bootstrap?", default=True):
            bootstrap = [sys.executable, str(root / "scripts" / "bootstrap.py")]
            self.console.print("[dim]Core bootstrap asks before creating its .venv or installing dependencies.[/dim]")
            code = subprocess.call(bootstrap, cwd=root)
            if code:
                self.console.print(f"[yellow]Bootstrap exited with code {code}. You can retry from the core checkout.[/yellow]")
        if shutil.which("codex"):
            if Confirm.ask("Open Codex's own local login flow now?", default=False):
                subprocess.call(["codex", "login"])
        else:
            self.console.print("[yellow]Codex CLI is not in PATH. Install it and run 'codex login' before actual use.[/yellow]")
        if Confirm.ask("Open the official PhoneDex SIP setup wizard?", default=True):
            try:
                self.setup(mode)
            except (OSError, FileNotFoundError) as exc:
                self.console.print(f"[yellow]Could not launch setup: {exc}[/yellow]")
        if Confirm.ask("Run read-only readiness checks?", default=True):
            self.check(mode)
        self.console.print(Panel("[bold green]Wizard finished.[/bold green] No calls have been placed.\nCheck networking, provider settings, and the approved-recipient allowlist before any live call.", border_style="green"))

    def start(self) -> None:
        root = self.require_root()
        self.console.print("[yellow]Starting the remote controller can accept queued call requests and potentially trigger billable calls.[/yellow]")
        self.console.print("[dim]Only use this on a configured, trusted Worker with caller allowlisting and billing limits.[/dim]")
        if not Confirm.ask("Start the local PhoneDex controller process?", default=False):
            self.console.print("Cancelled; controller not started.")
            return
        pid = core.start_controller(root)
        self.console.print(f"[green]Controller started[/green] (PID {pid}). Use [bold]phonedex-cli stop[/bold] to stop this CLI-managed process.")

    def stop(self) -> None:
        root = self.require_root()
        if core.stop_controller(root):
            self.console.print("[green]Controller stopped.[/green]")
        else:
            self.console.print("[yellow]No running controller managed by this CLI for this checkout.[/yellow]")

    def restart(self) -> None:
        root = self.require_root()
        state, _ = core.controller_status(root)
        self.console.print("[yellow]Restarting may resume queued call dispatch.[/yellow]")
        if not Confirm.ask("Restart the CLI-managed controller?", default=False):
            return
        if state == "running":
            if not core.stop_controller(root):
                raise RuntimeError("Could not stop controller")
        pid = core.start_controller(root)
        self.console.print(f"[green]Controller running[/green] (PID {pid})")

    def logs(self, lines: int = 40) -> None:
        logfile = core.home_dir() / "controller.log"
        if not logfile.is_file():
            self.console.print("[yellow]No CLI-managed controller logs yet.[/yellow]")
            return
        self.console.print("[yellow]Logs may contain personal call metadata. The viewer masks obvious secret-bearing lines, not phone numbers.[/yellow]")
        # Avoid huge log reads: tail by seeking from end, in binary mode.
        with logfile.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            pos = fh.tell()
            data = bytearray()
            while pos > 0 and data.count(b"\n") <= lines:
                read = min(pos, 4096)
                pos -= read
                fh.seek(pos)
                data[:0] = fh.read(read)
                if len(data) > 1024 * 1024:
                    break
        text = data.decode("utf-8", errors="replace")
        self.console.print(core.redact("\n".join(text.splitlines()[-lines:])), markup=False, highlight=False)

    def settings(self) -> None:
        root = self.require_root()
        env = root / ".env"
        if not env.is_file():
            raise RuntimeError("Core .env not configured. Run wizard or setup first.")
        while True:
            values = core.parse_env(env)
            self.console.print(Panel(f"Transcript storage: [bold]{values.get('PHONEDEX_TRANSCRIPT_MODE','off')}[/bold]\n"
                         f"Local retention: [bold]{values.get('PHONEDEX_TRANSCRIPT_RETENTION_DAYS','7')} days[/bold]\n"
                         f"Daily call cap: [bold]{values.get('PHONEDEX_MAX_CALLS_PER_DAY','12')}[/bold]\n"
                         f"Allowlisted recipients: [bold]{len([v for v in values.get('PHONEDEX_ALLOWED_RECIPIENTS','').split(',') if v.strip()])}[/bold]",
                         title="Private settings", border_style="magenta"))
            choice = Prompt.ask("Edit", choices=["privacy", "retention", "limit", "allowlist", "back"], default="back")
            if choice == "back":
                return
            if choice == "privacy":
                self.console.print("[dim]off=none; local=SQLite; worker=Worker/KV; both=local+Worker. Changes affect new calls only.[/dim]")
                value = Prompt.ask("Transcript mode", choices=["off", "local", "worker", "both"], default=values.get("PHONEDEX_TRANSCRIPT_MODE", "off"))
                if value in ("worker", "both") and not Confirm.ask("This uploads transcript text to your configured Worker. Continue?", default=False):
                    continue
                key = "PHONEDEX_TRANSCRIPT_MODE"
            elif choice == "retention":
                key, value = "PHONEDEX_TRANSCRIPT_RETENTION_DAYS", str(IntPrompt.ask("Local retention (1-90 days)", default=7))
            elif choice == "limit":
                key, value = "PHONEDEX_MAX_CALLS_PER_DAY", str(IntPrompt.ask("Maximum calls per day (1-1000)", default=12))
            else:
                key = "PHONEDEX_ALLOWED_RECIPIENTS"
                self.console.print("[dim]E.164 format, separated by commas. Leave blank to block all outbound recipients.[/dim]")
                value = Prompt.ask("Allowed numbers", default=values.get(key, ""), show_default=False)
            core.update_env(env, key, value)
            self.console.print("[green]Setting saved.[/green] New PhoneDex processes will read it. Restart any already-running controller to apply changes there.")

    def dial(self, to: str, mode: str = "normal", place_call: bool = False, yes: bool = False, duration: int = 60) -> int:
        root = self.require_root()
        if not core.E164.fullmatch(to):
            raise ValueError("Use E.164 recipient format, e.g. +14165550123")
        configured = core.parse_env(root / ".env")
        allowed = {n.strip() for n in configured.get("PHONEDEX_ALLOWED_RECIPIENTS", "").split(",") if n.strip()}
        if to not in allowed:
            raise ValueError("Recipient not in PHONEDEX_ALLOWED_RECIPIENTS (default-deny)")
        if not 20 <= duration <= 300:
            raise ValueError("Duration must be between 20 and 300 seconds")
        argv = core.core_argv(root, "dial", "--to", to, "--mode", mode, "--duration", str(duration))
        if place_call:
            self.console.print(Panel(f"[bold yellow]REAL, POTENTIALLY BILLABLE CALL[/bold yellow]\nRecipient: {to}\nMax duration: {duration} seconds", border_style="yellow"))
            if not yes and not Confirm.ask("Place this live call now?", default=False):
                self.console.print("Call cancelled.")
                return 0
            argv += ["--place-call"]
        else:
            self.console.print("[green]Dry run only.[/green] No live call will be placed.")
        return subprocess.call(argv, cwd=root)

    def menu(self) -> None:
        self.banner()
        while True:
            self.status()
            self.console.print(Panel("[cyan]1[/cyan] Setup wizard     [cyan]2[/cyan] Readiness doctor     [cyan]3[/cyan] Start controller\n"
                                     "[cyan]4[/cyan] Stop controller   [cyan]5[/cyan] Restart controller    [cyan]6[/cyan] View logs\n"
                                     "[cyan]7[/cyan] Settings          [cyan]8[/cyan] Dial (dry run first)  [cyan]0[/cyan] Exit",
                                     border_style="bright_magenta", title="Control deck"))
            choice = Prompt.ask("Select", choices=list("012345678"), default="0")
            if choice == "0":
                return
            try:
                if choice == "1": self.wizard()
                elif choice == "2": self.check()
                elif choice == "3": self.start()
                elif choice == "4": self.stop()
                elif choice == "5": self.restart()
                elif choice == "6": self.logs()
                elif choice == "7": self.settings()
                else:
                    number = Prompt.ask("E.164 destination")
                    minutes = IntPrompt.ask("Max duration (seconds)", default=60)
                    self.dial(number, duration=minutes)
                    if Confirm.ask("Try a real call to this approved number?", default=False):
                        self.dial(number, duration=minutes, place_call=True)
            except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
                self.console.print(f"[red]Action failed:[/red] {exc}")
            self.console.print()


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Optional Rich terminal interface for PhoneDex")
    p.add_argument("--checkout", help="Path to existing official PhoneDex source checkout")
    p.add_argument("--no-color", action="store_true", help="Disable ANSI coloring")
    p.add_argument("--no-animation", action="store_true", help="Disable startup transitions")
    p.add_argument("--version", action="version", version=__version__)
    commands = p.add_subparsers(dest="action")
    commands.add_parser("menu", help="Interactive terminal control deck")
    commands.add_parser("wizard", help="Guided first-run setup")
    commands.add_parser("status", help="Show configuration and managed controller status")
    doc = commands.add_parser("doctor", help="Run official read-only PhoneDex diagnostics")
    doc.add_argument("--mode", choices=["local", "remote"], default="local")
    setup = commands.add_parser("setup", help="Run official PhoneDex setup wizard")
    setup.add_argument("--mode", choices=["local", "remote"], default="local")
    commands.add_parser("start", help="Start local controller with explicit confirmation")
    commands.add_parser("stop", help="Stop only the controller started by this CLI")
    commands.add_parser("restart", help="Restart CLI-managed controller with confirmation")
    logs = commands.add_parser("logs", help="Display recent CLI-managed controller logs")
    logs.add_argument("--lines", type=int, default=40)
    commands.add_parser("settings", help="Change non-secret PhoneDex settings locally")
    dial = commands.add_parser("dial", help="Allowlisted dry run by default; real calls opt-in")
    dial.add_argument("--to", required=True, help="E.164 approved destination")
    dial.add_argument("--mode", choices=["normal", "business"], default="normal")
    dial.add_argument("--duration", type=int, default=60)
    dial.add_argument("--place-call", action="store_true", help="Opt in to an actual carrier call")
    dial.add_argument("--yes", action="store_true", help="Skip interactive live-call confirmation (automation only)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    cli = Cockpit(no_color=args.no_color, no_animation=args.no_animation, checkout=args.checkout)
    action = args.action or "menu"
    try:
        if action == "menu": cli.menu()
        elif action == "wizard": cli.wizard()
        elif action == "status": cli.banner(); cli.status()
        elif action == "doctor": return cli.check(args.mode)
        elif action == "setup": return cli.setup(args.mode)
        elif action == "start": cli.start()
        elif action == "stop": cli.stop()
        elif action == "restart": cli.restart()
        elif action == "logs": cli.logs(max(1, min(args.lines, 500)))
        elif action == "settings": cli.settings()
        elif action == "dial": return cli.dial(args.to, args.mode, args.place_call, args.yes, args.duration)
        return 0
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        cli.console.print(f"[red]PhoneDex CLI:[/red] {exc}")
        return 2
    except KeyboardInterrupt:
        cli.console.print("\n[dim]Exited. Background controller, if running, is unchanged.[/dim]")
        return 130

if __name__ == "__main__":
    raise SystemExit(main())
