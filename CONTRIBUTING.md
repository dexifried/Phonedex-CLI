# Contributing

Thanks for helping improve PhoneDex CLI. Keep changes focused on the optional terminal frontend and its integration with the public PhoneDex core.

## Development setup

Use Python 3.11 or newer:

```bash
python -m pip install -e . pytest
python -m pytest -q
phonedex-cli --no-animation --no-color status
```

The tests are offline. They must not place a real call, contact a live carrier, or depend on a user's Codex login. Do not add tests that modify a real PhoneDex checkout or read a user's `.env`.

## Safety and privacy

- Keep secrets, local `.env` files, Codex authentication state, phone numbers belonging to real people, and call transcripts out of commits and issue reports.
- Preserve the default dry-run behavior for `dial` and its allowlist and confirmation checks.
- Keep `stop` scoped to the controller process recorded by this CLI.
- Treat controller logs and transcript text as private even when secret-label masking is enabled.
- Do not describe PhoneDex CLI as the SIP engine; that code belongs to the separate PhoneDex project.

## Pull requests

Describe the user-visible behavior and its impact on local files or processes. Include test output and note explicitly if you could not verify Windows, macOS or Linux behavior. Do not push release tags from unreviewed changes. For PyPI release steps, see [docs/PUBLISHING.md](docs/PUBLISHING.md).
