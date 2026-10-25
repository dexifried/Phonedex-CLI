# Publishing PhoneDex CLI on PyPI

This repository supports token-free [PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/).

**Important:** PyPI distribution files are public, including the source distribution. This GitHub repository is public too; review both the repository and package artifacts for secrets before each release.

## One-time setup for a new PyPI project

The `phonedex-cli` package is already published. Do not follow these steps to create a duplicate publisher for this project; they describe the initial setup for a new package.

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

   The workflow does not reference a GitHub environment, so leave this blank to match its current configuration.

4. Save the pending publisher. This **does not reserve the PyPI project name**; first successful publishing creates the project. `phonedex-cli` is already published, so do not create a second publisher for a different repository or workflow identity.

**Never paste PyPI passwords, API tokens, or recovery codes into an issue, a commit, or a chat.** No long-lived API token or GitHub secret is needed.

## Create a release

First confirm that the GitHub CI checks on `main` pass, the repository contains no secrets, and the public source and license are intentional.

1. Set a new, unused version in `pyproject.toml`. Version `0.1.0` has already been published and must not be reused.
2. Create and push the matching version tag from the tested commit (using Git locally or GitHub's authenticated tag/release interface). Replace `X.Y.Z` below with the version in `pyproject.toml`:

   ```bash
   git switch main
   git pull --ff-only
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

3. The workflow `.github/workflows/publish.yml` tests and builds the release source, checks the ref/version match, runs `python -m build` and `twine check`, and publishes the wheel and source distribution to PyPI using OIDC (short-lived authentication).
4. Review the [Actions run](https://github.com/dexifried/Phonedex-CLI/actions) and the resulting https://pypi.org/project/phonedex-cli/ page.

The workflow runs for pushed version tags matching `v[0-9]*` and release branches matching `release/v[0-9]*`. A release-branch push builds and tests that commit, then creates its matching version tag; the verified artifacts are published to PyPI. Ordinary pushes and pull requests do not publish. Both release paths cause **real public publication**; never push a release tag or release branch as an experiment.

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
- The GitHub source repository and PyPI distributions are public. Review both surfaces before publishing; changing GitHub visibility does not remove previously published PyPI artifacts.
- If you later enable GitHub Actions environments and require reviewers, ensure the workflow and the PyPI trusted publisher both refer to the **same** environment.
