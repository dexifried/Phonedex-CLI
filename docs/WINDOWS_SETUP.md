# PhoneDex CLI — Windows-first complete setup

The Windows setup is **resumable**. Run `phonedex-cli wizard` again after
finishing a prerequisite or router change; it does not wipe previous settings.

## Start here

Open PowerShell on a Windows 10/11 computer.

1. Install **Python 3.11+**, ideally from [python.org](https://www.python.org/downloads/windows/) with the standard `venv` component and PATH enabled.
2. Install the PhoneDex CLI in an isolated environment:

   ```powershell
   py -m pip install --user pipx
   py -m pipx ensurepath
   # Restart PowerShell so pipx is on PATH.
   pipx install phonedex-cli
   phonedex-cli wizard
   ```

   Already using a Python virtual environment? `python -m pip install phonedex-cli`
   works too.

3. Follow the **seven on-screen steps**. The wizard can offer to install Git
   through Windows Package Manager (`winget`) and the official Codex CLI
   with `npm`. Those installations are never silent. If installing Node or Git
   updates PATH, reopen PowerShell and rerun the wizard.

## Seven setup stages

| Stage | What PhoneDex helps with | What remains your decision |
| --- | --- | --- |
| 1. Core checkout | Select an existing repository or clone the official source | Approve cloning/install location |
| 2. Python | Create `.venv` and install the core's dependencies | Approve local package installation |
| 3. Codex | Find/install CLI, launch local ChatGPT login and check OAuth status | Authenticate in the official login flow |
| 4. SIP provider | Guide AgentPhone trunk selection, or input any compatible provider; validate and privately save configuration | Provide your account, trunk, credentials and authorized caller ID |
| 5. Windows networking | Show your LAN address, required UDP port and router/firewall steps | Configure your router and firewall, independently verify forwarding |
| 6. Diagnostics | Run the core's existing readiness checks and explain missing requirements | Fix reported TODO items |
| 7. Call test | Dry-run an allowlisted destination and offer a separate, explicitly approved real call | Authorize and pay for any real call |

For an existing core `.env`, the wizard does **not** overwrite credentials.
The file can contain plaintext provider secrets: protect your Windows user
account and drive. Never upload or paste the file.

## AgentPhone setup

The CLI defaults to AgentPhone as the provider. Sign into
[agentphone.ai](https://agentphone.ai) and prepare a SIP trunk. For a convenient
read-only lookup of your existing trunks (or separately approved trunk creation), the wizard can accept an AgentPhone
API key in a private, hidden terminal prompt:

- By default it requests **GET** `https://api.agentphone.ai/v1/sip-trunks` over HTTPS.
- If no trunk exists, you may separately approve **one POST** to create a trunk. Creation changes your provider account; check any billing/limits before agreeing. The wizard never automatically retries an ambiguous response.
- It **never** stores the AgentPhone API key or sends it to PhoneDex Worker/KV.
- It shows trunk names and transport/media information, **not** SIP passwords.
- It can prefill a trunk's termination SIP URI and SIP credentials if available.
- If the provider returns a masked or missing SIP password, you enter it
  through a separate private prompt.

You can skip API access and enter all SIP settings manually. The wizard does not provision a phone number or change the routing of existing
numbers. New SIP trunk creation is optional and separately confirmed. See AgentPhone's [official SIP trunk documentation](https://docs.agentphone.ai/api-reference/sip-trunks/list-sip-trunks-v-1-sip-trunks-get).

Your number must be a provider-approved caller ID, and you must explicitly
allowlist every test recipient. The default daily call limit is 12 and
transcript storage defaults to `off`.

## Windows firewall and router

For outbound SIP calls, the PhoneDex core currently defaults to local UDP
media port **41002**. Real carrier compatibility requires the correct
signaling/TLS connection and return SRTP from the carrier. The CLI guides you
through forwarding UDP 41002 to your computer's LAN IP and setting an
appropriate Windows Defender Firewall rule (`wf.msc`).

**Important:** Simply entering the settings or checking a confirmation prompt
does not verify NAT traversal. The wizard leaves
`PHONEDEX_MEDIA_PORT_FORWARDED=0` until *you* confirm you have configured
and independently tested the mapping. It never runs `netsh`, opens router
ports, changes the firewall or starts a listening public service by itself.

Inbound SIP hosting remains an advanced manual setup. The core release does
not include automatic inbound trunk routing or a verified human transfer.

## Honest readiness vs. successful phone call

The final diagnostics are **local readiness only**. They do not guarantee
carrier authentication, PSTN ringing, two-way audio, media encryption
negotiation or successful end-to-end teardown. A real call is always separate
and requires explicit confirmation. If you decline it, **no call is placed**.

To resume later:

```powershell
phonedex-cli wizard
phonedex-cli doctor --mode local
phonedex-cli status
```

The CLI uses the installed PhoneDex core commands; it is a companion UI,
not a separate SIP stack. It does not require Cloudflare for local outbound
testing. Cloudflare remote agent control is a later, optional path.
