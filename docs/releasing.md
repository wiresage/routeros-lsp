# Releasing

`routeros-lsp` is published to [PyPI](https://pypi.org/project/routeros-lsp/) by GitHub Actions. Nobody uploads anything by hand
and no PyPI token is stored anywhere: the upload uses PyPI trusted publishing (OpenID Connect).

## How a release happens

```
pull request --> ci.yml (lint, types, tests on 3.10 to 3.13 and Windows, wheel smoke test)
      |
      v  merge to master, and the merge changed src/** or pyproject.toml
publish.yml:  version --> build --> publish --> tag + GitHub release
                   \--> test (3.10 to 3.13) --/
```

1. **Version.** [GitVersion](https://gitversion.net) reads the Conventional Commit messages since the last tag
   ([GitVersion.yml](../GitVersion.yml)):

   | Commit | Effect |
   |---|---|
   | `feat:` | minor bump, `0.2.0` to `0.3.0` |
   | `fix:` `perf:` `refactor:` `build:` `ci:` `chore:` `test:` `style:` `revert:` | patch bump, `0.2.0` to `0.2.1` |
   | `docs:` | no bump |
   | footer `+semver: breaking` | major bump; the major version stays 0 until the server is declared stable |

   The package, the git tag (`v0.2.1`) and the GitHub release all carry the same `MAJOR.MINOR.PATCH`.
2. **Build.** The placeholder `version = "0.0.0"` in `pyproject.toml` is replaced with the computed one, the wheel and sdist are
   built and checked with `twine check`, then the wheel is installed in an empty virtual environment and
   [`tools/smoke_test.py`](../tools/smoke_test.py) starts the installed command, opens a document over real stdio and checks the
   diagnostics. That catches a wheel without the command database or with a broken entry point.
3. **Test.** The full suite runs on Python 3.10, 3.11, 3.12 and 3.13.
4. **Publish.** Both jobs above must pass. The upload uses `pypa/gh-action-pypi-publish` in the `pypi` environment;
   `skip-existing` makes a re-run of the same version harmless.
5. **Tag and release.** Only after the package is on PyPI, so a tag never points at a version that does not exist there.

### What triggers a release

Only a push to `master` that changes a shipped file: `src/**` or `pyproject.toml`. A change to docs, the README, tests, the Claude
Code plugin, `research/`, `tools/` or the workflows does nothing, so a typo fix does not produce a version. The consequence is that
the PyPI page shows the README of the last release; a README-only fix appears with the next release.

Merging a pull request is therefore the release decision. Use `docs:` for commits that only change documentation inside a pull
request that also touches `src/**`, and keep `feat:` for behaviour users can see.

## One-time setup (repository owner)

None of this can be done from a workflow, and none of it involves a secret that has to be pasted into the repository.

1. **PyPI trusted publisher.** The project does not exist on PyPI yet, so register a *pending* publisher at
   <https://pypi.org/manage/account/publishing/> with:

   | Field | Value |
   |---|---|
   | PyPI project name | `routeros-lsp` |
   | Owner | `wiresage` |
   | Repository name | `routeros-lsp` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

   The first successful run creates the project and turns the pending publisher into a normal one.
2. **GitHub environment.** Repository settings, Environments, New environment, named `pypi`. Optionally add yourself as a required
   reviewer if you want a manual approval before every upload.
3. **Claude Code workflow (optional).** [`claude.yml`](../.github/workflows/claude.yml) answers `@claude` mentions. It needs the
   repository secret `CLAUDE_CODE_OAUTH_TOKEN`; without it the workflow fails and nothing else is affected.
4. **Repository protection.** Enable secret scanning and push protection (Settings, Code security), and consider a branch
   protection rule on `master` that requires the `CI` checks, since a merge there publishes.

Do these before the first merge to `master` that changes `src/**`. If the publisher is missing, the `publish` job fails, no tag is
created, and re-running the failed workflow after fixing the setup releases the same version.

## Trying it locally

```bash
sed -i 's/^version = ".*"/version = "0.0.1"/' pyproject.toml     # then git checkout pyproject.toml afterwards
python -m build
twine check dist/*
python -m venv /tmp/smoke && /tmp/smoke/bin/python -m pip install dist/*.whl
python tools/smoke_test.py /tmp/smoke/bin/routeros-lsp --expect-version 0.0.1
```

On Windows the executable is `Scripts\routeros-lsp.exe` inside the environment.

## Notes

- `plugin/.claude-plugin/plugin.json` has its own version. It describes the plugin, which only starts the `routeros-lsp` command,
  and is not changed by the pipeline. Change it by hand when the plugin itself changes.
- The command database (`src/routeros_lsp/data/`) is part of the wheel. A new RouterOS version means regenerating it with
  `tools/gen_schema.py` (see [CONTRIBUTING.md](../CONTRIBUTING.md)); the file with the highest version number is the one used.
- If a published version turns out to be bad, yank it on PyPI (never delete) and merge a fix; the next release gets the next number.
