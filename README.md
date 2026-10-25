# PhoneDex CLI

**An optional, colorful terminal control deck for [PhoneDex](https://github.com/dexifried/Phonedex).**

A Rich-powered ASCII dashboard, short startup animations, step-by-step setup, diagnostic panels, a managed-controller switchboard, and safe calling controls. **PhoneDex CLI is a separate frontend**, not a fork of the SIP bridge. Uninstalling it leaves PhoneDex's existing installation, config, and calls intact.

```text
  ____  _                     ____
 |  _ \| |__   ___  _ __   ___|  _ \  _____  __
 | |_) | '_ \ / _ \| '_ \ / _ \ | | |/ _ \ \/ /
 |  __/| | | | (_) | | | |  __/ |_| |  __/>  <
 |_|   |_| |_|\___/|_| |_|\___|____/ \___/_/\_\

    TERMINAL CONTROL // an optional PhoneDex companion
```

## Quickstart

Requires Python **3.11+**. Linux, macOS and Windows use the same commands. Git is needed **only** if you want the CLI to clone PhoneDex for you.

```bash
# Clone or unpack this separate phonedex-cli project
cd phonedex-cli
python -m pip install -e .

# First-time users: interactive setup wizard
phonedex-cli wizard

# Regular users: animated control deck
phonedex-cli
```

On some systems use `python3` and `python3 -m pip`. The installation above is editable/developer mode; end users can instead use `python -m pip install .` from the unpacked project. For isolation use a dedicated virtual environment. **This repository has not yet been released on PyPI.** Do not assume `pip install phonedex-cli` works from PyPI.

### Existing PhoneDex installation?

Either choose **existing** in `phonedex-cli wizard` or use:

```bash
phonedex-cli --checkout /path/to/Phonedex status
phonedex-cli --checkout /path/to/Phonedex doctor --mode local
```

`PHONEDEX_HOME=/path/to/Phonedex` is also supported. The wizard saves the source path to a local config file, not the PhoneDex checkout. It never overwrites an existing `.env`.

### Commands

| Command | Behavior |
| --- | --- |
| `phonedex-cli` or `phonedex-cli menu` | Interactive ASCII/Rich terminal dashboard |
| `phonedex-cli wizard` | Link/clone source, run optional bootstrap, local Codex login, delegate to official setup, inspect diagnostics |
| `phonedex-cli doctor --mode local` | Official read-only source checks; change to `remote` when using a Worker |
| `phonedex-cli setup --mode local` | Delegates to the existing core setup wizard |
| `phonedex-cli status` | Local checkout, Codex command presence, privacy mode, CLI-managed process state |
| `phonedex-cli start` | Start a CLI-managed controller **only with confirmation**; queued work can dispatch calls |
| `phonedex-cli stop` | Stop **only** the controller this CLI started and recorded |
| `phonedex-cli restart` | Confirm and restart a CLI-managed controller |
| `phonedex-cli logs --lines 40` | Recent managed-controller logs (best-effort masking of secret-bearing lines) |
| `phonedex-cli settings` | Private local editor: transcripts, retention, daily call cap, allowlisted phone numbers |
| `phonedex-cli dial --to +14165550123` | Allowlisted **dry run** (no call) |
| `phonedex-cli dial --to +14165550123 --place-call` | Explicit, **potentially billable** real call, requires confirmation |

Use `--no-color --no-animation` for inaccessible or non-interactive terminals. Animation is automatically disabled when the output isn't a terminal or when `CI` is set. `--yes` applies **only** to `dial --place-call` and bypasses its second confirmation for deliberate automation; it still requires an allowlisted number and upstream PhoneDex safeguards.

## Architecture and privacy

```text
phonedex-cli (optional UI)
     │
     ├─ ~/.config/phonedex-cli/config.json  → installed source path only
     ├─ controller.json / controller.log    → CLI-managed subprocess only
     │
     └─ invokes official PhoneDex commands:
          phonedex.py setup / doctor / dial / controller
                         │
          core .env, SIP gateway, GPT Live, optional Worker
```

- The CLI does **not** request or store SIP passwords, OAuth tokens, or AgentPhone keys. The official PhoneDex setup handles provider secrets privately.
- The separate CLI only edits four whitelisted **non-secret** `.env` settings. It uses owner-restricted atomic replacement on POSIX, preserves unrelated variables and comments, and refuses symlink writes.
- Configuration edits take effect for new PhoneDex processes. An already-running controller generally needs a restart; this CLI never restarts it automatically.
- The CLI does **not** configure DNS, TLS certificates, Cloudflare resources, firewalls, port forwarding, telephony numbers, or SIP trunks.
- Setup, status, diagnostics, and default dialing perform **no real phone call**. Starting the controller can execute requests already queued in a configured Worker; it requires confirmation.
- Transcript storage defaults to `off` in the core. Choosing `worker` or `both` shares transcript text with **your own** Worker/KV. Changes apply to new calls and don't erase existing data.
- The log viewer masks lines with common secret labels on a best-effort basis. Logs may still reveal phone numbers, call content, and metadata. Do not publish raw logs.
- The controller PID registry records creation time and exact script path. **Stop will refuse** to terminate an unrelated process or a stale/reused PID. Controllers started outside this CLI are deliberately not managed.
- Operational correctness and carrier compatibility depend on the PhoneDex core and your provider. Use [PhoneDex's release status](https://github.com/dexifried/Phonedex/blob/main/docs/RELEASE_STATUS.md).

**Note:** PhoneDex uses an undocumented GPT Live subscription endpoint. Its availability and permission to use it may change. This CLI provides no guarantee of service or compliant use and is not affiliated with OpenAI, Codex, or AgentPhone.

## Development

```bash
python -m pip install -e . pytest
python -m pytest -q
python -m phonedex_cli --no-animation --no-color status
```

Offline tests cover config preservation, allowlisting, confirmation gates, symlink protection, stale-process safety, and dry-run defaults. CI is configured for Windows, Linux and macOS, but actual results depend on running the workflow. Live carrier calls are **not** part of these tests.

Licensed MIT. © 2026 Austin Harvey.
