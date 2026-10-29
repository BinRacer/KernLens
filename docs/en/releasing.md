# Releasing

For maintainers.  A release is an annotated tag `vX.Y.Z` on a commit
whose version files agree; `.github/workflows/release.yml` does the rest.
Nothing on this page has to be remembered from the last release: the
checks are in `tools/release.py` and the workflow.

## Before the tag

Three hand-written files carry the version, and they are written at
different moments, which is why they drift:

| File | Must say |
| --- | --- |
| `src/kernlens/__init__.py` | `__version__ = "X.Y.Z"` |
| `CHANGELOG.md` | `## [X.Y.Z] - YYYY-MM-DD`, with at least one entry |
| `CITATION.cff` | `version: X.Y.Z` and the same `date-released` |

`tools/release.py check` compares all three, plus the tag when one is
given:

```console
uv sync --group release
uv run python tools/release.py check v0.3.0
uv run pytest -q
rm -rf dist && uv build
uv run python tools/check_wheel.py dist/*.whl
uv run twine check dist/*
```

The check runs before the tag exists, and that is the point: a tag is
cheap to move before it is pushed and expensive after.  `twine check`
renders the README the way PyPI will, so a metadata error is found here
rather than in a rejected upload.

## The tag

```console
git tag -a v0.3.0 -m "KernLens 0.3.0"
git push origin v0.3.0
```

Annotated, not lightweight: `git describe`, `gh release`, and the
workflow's `github.ref_name` all read the annotation, and a lightweight
tag is easy to create on the wrong commit by accident.

## What the workflow does

1. checks out the tag, syncs the `release` dependency group (twine);
2. runs `tools/release.py check` with the tag, so a mismatch stops here;
3. runs the test suite, because a tag can point at a commit CI never saw;
4. builds the wheel and sdist, checks the wheel's contents and the
   metadata;
5. renders the release notes from the changelog section;
6. publishes to PyPI through trusted publishing;
7. creates the GitHub Release with the wheel, the sdist, the demo cast,
   and those notes.

PyPI is published before the GitHub Release on purpose.  A release that
points at artifacts which failed to upload is worse than a package with
no release yet; the reverse failure is a package that exists and a
release that can be created by hand.

## One-time setup

PyPI has to trust this repository before the first upload.  On the
project page: *Publishing* -> *Add a publisher* -> GitHub, with

| Field | Value |
| --- | --- |
| Owner | `BinRacer` |
| Repository | `KernLens` |
| Workflow | `release.yml` |
| Environment | `pypi` |

TestPyPI takes the same form with the environment `testpypi`.  No token
is stored anywhere: `id-token: write` in the job is the whole credential.

The rehearsal is a manual run, which publishes the *current* version to
TestPyPI and stops:

```console
gh workflow run release.yml -f index=testpypi
```

TestPyPI also refuses a version twice, so a rehearsal is once per
version.  If the rehearsal is wrong, bump the patch version rather than
re-uploading.

## If it goes wrong

- **Wrong tag, nothing published.**  Delete the tag locally and on the
  remote, fix the commit, tag again.  PyPI was never touched.
- **PyPI accepted the version and it is wrong.**  A version cannot be
  replaced.  Yank it -- the files stay downloadable, resolution skips
  them -- fix, and release a patch.
- **The workflow failed after the PyPI step.**  Create the GitHub
  Release by hand from the workflow's artifacts; the package is live.
- **The GitHub Release is wrong.**  Edit it.  It is a page, not an
  artifact store.

## After the release

- **The install command becomes legal.**  Both READMEs deliberately do
  not offer `pip install kernlens` until a release exists;
  `tests/unit/test_structure.py` holds that phrase list.  Remove the
  entries and add the command in the same commit -- the test is the
  tripwire, not a style rule.
- **The documentation URL becomes real.**  Add `[project.urls]
  Documentation` and the README badge after the first Pages deploy, not
  before; until then they point at a 404.
- **A DOI can be minted.**  Connect the repository on Zenodo, cut the
  next release, then put the DOI in `CITATION.cff` and the README.  A
  version DOI cannot be changed afterwards, so it is worth waiting for a
  release you are happy with.
- **A row can be promoted.**  If someone ran the release on an
  environment listed as `expected` in
  [`compatibility.md`](compatibility.md), that row can become
  `measured` -- with the `kernlens doctor` output as its evidence.

## Not automated

- **Name availability.**  Check `https://pypi.org/pypi/kernlens/json`
  before the first upload.  It returned 404 on 2026-10-28, which is what
  made the name available; if that changes, the distribution name has to
  change with it.
- **Repository topics and the social preview.**  GitHub has no API for
  the preview image, and topics are a UI action.
- **The capture.**  A new kernel means regenerating
  `tools/tutorial_capture.json` first, or the tutorial and the demo keep
  describing the old one.
