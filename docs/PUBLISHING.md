# Publishing PhoneDex CLI on PyPI

This repository supports token-free [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/).

**Important:** PyPI distribution files are public, including the source distribution, even if the GitHub repository is private. Publishing does not make GitHub's private repository public, but it distributes this project's Python code.

## One-time setup

1. Create or sign in to your PyPI account at https://pypi.org/ (enable 2FA as required).
2. Go to https://pypi.org/manage/account/publishing/ and choose **Add a new pending publisher** for GitHub Actions.
3. Fill in these exact fields:

   | PyPI field | Value |
   | --- | --- |
   | PyPI project name | `phonedex-cli` |
   | GitHub owner | `dexifried` |
   | Repository name | `Phonedex-CLI` |
   | Workflow filename | `publish.yml` |
   | Environment name | **Leave blank** |

   The workflow does not reference a GitHub environment. This supports a private repository without relying on paid environment features. You can add an environment and protection rules in a later hardening pass, but PyPI's publisher configuration must be updated to match.

4. Save the pending publisher. This **does not reserve the PyPI project name**; first successful publishing creates the project. If the name is unavailable, stop and choose a new name deliberately.

**Never paste PyPI passwords, API tokens, or recovery codes into an issue, a commit, or a chat.** No long-lived API token or GitHub secret is needed.

## Create a release

First confirm that the GitHub CI checks on `main` pass, the repository contains no secrets, and the public source and license are intentional.

1. Set the desired version in `pyproject.toml`; for the first release this is `0.1.0`.
2. Create and push a matching tag from the tested commit (using Git locally or GitHub's authenticated tag/release interface):

   ```bash
   git switch main
   git pull --ff-only
   git tag v0.1.0
   git push origin v0.1.0
   ```

3. The workflow `.github/workflows/publish.yml` tests the tagged source, checks the tag/version match, runs `python -m build` and `twine check`, and publishes the wheel and source distribution to PyPI using OIDC (short-lived authentication).
4. Review the [Actions run](https://github.com/dexifried/Phonedex-CLI/actions) and the resulting https://pypi.org/project/phonedex-cli/ page.

The workflow is triggered **only by pushed version tags** matching `v[0-9]*`. Ordinary pushes or pull requests do not publish. A tag triggers **real public publication** after trusted publishing is configured; never push a release tag as an experiment.

Once released, users can run:

```bash
pipx install phonedex-cli
phonedex-cli wizard
```

Alternatively: `python -m pip install phonedex-cli`.

## Subsequent releases

Update `pyproject.toml` to a version not previously used, ensure the offline CI checks pass, review the packaged source, then create the corresponding `vX.Y.Z` tag. PyPI distribution filenames are effectively immutable: uploading revised code under the same version normally fails. Do not rewrite or move an existing release tag; use a new version.

## Security and scope

- A successful package publish doesn't install SIP credentials or configure a provider. The CLI setup wizard remains separate from the PhoneDex core.
- Only push tags from reviewed commits. A tag on a different commit would publish code from that commit.
- The `publish` job grants `id-token: write` only to the PyPI upload job; it does not store a PyPI API token.
- This repository is presently private. If you want the source repository publicly readable in addition to public PyPI distributions, change GitHub visibility deliberately as a separate action.
- If you later enable GitHub Actions environments and require reviewers, ensure the workflow and the PyPI trusted publisher both refer to the **same** environment.
