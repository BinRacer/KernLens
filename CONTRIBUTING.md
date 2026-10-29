# Contributing

Development notes for KernLens.  If you only want to *use* it, the
[README](README.md) has the one-command install and the command
table; nothing here is needed for that.

## Distribution

KernLens ships two ways from the same tree.  `install.sh` clones a
checkout, writes one marked block into `~/.gdbinit`, and leaves a
`kernlens` wrapper; `pip install .` builds a wheel that contains the same
startup file.  There is no PyPI release yet, and the docs must not offer
a PyPI install command until one exists.

The startup file is the part that constrains the design.  GDB *sources*
it rather than importing it, so it has to run in GDB's `__main__`
namespace and make `kernlens` importable from its own location: `src/` in
a checkout, `site-packages` in a wheel.  `src/kernlens/gdbinit.py` does
both; the root `gdbinit.py` is a shim so existing `~/.gdbinit` lines keep
working.

The console script is host-side only.  `kernlens path` prints the startup
file, `kernlens install` edits `~/.gdbinit`, `kernlens doctor` checks the
load path, and `kernlens version` prints the version.  None of them
imports `kernlens.gdb`, because the host interpreter has no `gdb` module.

Publishing is a release step, not a code step.  The order, the checks,
and the one-time trusted-publishing setup are in
[`docs/en/releasing.md`](docs/en/releasing.md).  `tools/check_wheel.py` is the
gate that the built wheel actually contains the startup file and the
console script; until it runs in CI against a real build, a green test
suite says nothing about the package.

## Testing and development

The test suite is `unittest`-compatible and also runs under pytest.
All development commands go through uv:

```console
uv sync
uv run pytest --cov=kernlens --cov-report=term-missing
uv run ruff check .
uv run pyright
uv run mypy
uv run python tools/gen_commands.py --check
uv run python tools/gen_demo.py --check
uv run python tools/gen_docs_site.py --check
```

`pyright` and `mypy` are both gates: the package ships an empty
`py.typed`, and the two checkers disagree often enough that each one
finds annotations the other accepts.  Both read the `gdb` stub from the
`types-gdb` dev dependency, so no debugger is needed to run them.

The stdlib runner remains available inside the uv environment:

```console
uv run python -m unittest discover -s tests/unit
uv run python -m unittest discover -s tests/integration
```

The integration tests install a fake `gdb` module, so no debugger or
kernel is required.  `tests/integration/test_gdbinit.py` additionally
runs the real `gdbinit.py` against a fake `gdb` and a stub facade, so
command registration, argument parsing, and output formatting are
covered without GDB.  `uv sync` installs the package, so `uv run`
commands import the installed distribution rather than relying on
`PYTHONPATH`; `pyproject.toml` also sets `pythonpath = ["src"]` so a
bare `pytest` run works from a checkout.

### History: linear for the maintainer, forgiving for everyone else

The maintainer commits to `main` directly, so `main` is linear by
construction.  That is a statement about one person's habit, not a rule
imposed on contributors.

An outside contribution may land by **squash**, **rebase**, or **merge**.
All three produce the same files when there is no conflict, and all three
are tested the same way: `pull_request` runs against
`refs/pull/<n>/merge`, the result of combining the branch with `main`, and
`push: main` runs again against whatever commit actually lands.  So a merge
commit is not an untested commit, and the choice is about the shape of the
log, not about safety.

**Merge is explicitly allowed**, because the alternatives tax the
contributor rather than the maintainer.  A rebase makes a contributor
resolve conflicts they did not create and force-push a branch they may have
opened from a fork they cannot rewrite; in that situation the merge cost
falls on the maintainer and the rebase cost falls on a stranger.  Landing a
merge commit is the cheaper of the two, and the log is the right place to
spend that.

```console
# contributor
git pull --rebase origin main       # optional, keeps the PR on top of main
git push --force-with-lease         # only if you rebased

# maintainer, on a contribution
gh pr merge <n> --merge --delete-branch
```

Squash is still the default when a branch carries fixup commits that add
nothing to the story -- it is the one option that asks the contributor for
nothing at all.  Rebase keeps each commit when they each stand on their own
and the branch is already current.

The only cost of a merge commit is that `git bisect` can land on a node
with two parents, where the build may be broken for a reason that belongs
to neither side.  If that ever happens, `git bisect --first-parent` skips
merge commits and bisects the history the way it was reviewed.

The one thing that is not negotiable is the *shape of each commit*, not the
shape of the graph: one concern per commit, a message that says why, and no
merge commit that also carries unreviewed content.  Everything in this
section about landing method is a preference; that is the requirement.

See [`docs/en/architecture.md`](docs/en/architecture.md) for the public API
map, module responsibilities, the SLUB inspection model, and GDB
loading details.  [`docs/en/naming.md`](docs/en/naming.md) defines the
command and Python naming rules.  For a guided tour with real output
from a live kernel, start at [`docs/en/tutorial/`](docs/en/tutorial/README.md) --
one page per command.  Release history lives in
[`CHANGELOG.md`](CHANGELOG.md).

### Documentation site

The site is the same Markdown as the checkout, built by mkdocs and
deployed to GitHub Pages.  The theme is its own dependency group, so
`uv sync` does not download it:

```console
uv sync --group docs
uv run --group docs mkdocs serve      # http://127.0.0.1:8000/KernLens/
uv run --group docs mkdocs build --strict
```

`--strict` is the gate CI uses: a broken internal link or a page missing
from the nav fails the build.  `docs/en/index.md` and `docs/zh-CN/index.md`
are generated from the two READMEs, and `docs/llms.txt` from the nav in
`mkdocs.yml` -- edit those sources, then run
`uv run python tools/gen_docs_site.py`.  A new page needs a nav entry and
a one-line description in `PAGE_NOTES`, or `--check` fails.

### Struct layouts: DWARF, then BTF, then a verified fallback

Every struct field offset is resolved on first use through a three-tier
chain, so the inspectors track the exact kernel image they run against --
offsets shift with the kernel version and with `CONFIG_*` (for example
`CONFIG_SECURITY` inserts a `void *security` before
`struct bpf_map::map_type`):

1. **DWARF** -- the loaded `vmlinux`'s debug info (`gdb.parse_and_eval`),
   exact for the build at hand;
2. **BTF** -- the type database embedded in the image
   (`CONFIG_DEBUG_INFO_BTF`), parsed directly by `kernlens.gdb.btf`
   (no `bpftool`, no `libbpf`), for a build whose DWARF is absent;
3. **the fallback registry** in `kernlens/gdb/layouts.py` -- only when
   neither is available.

Each registry entry records where the struct is defined and which kernel
it was verified against (`layouts.VERIFIED_KERNEL`, currently Linux
7.0), and gates its variants on the version and `CONFIG_*`.  Because
those values are only known-good for one configuration, every command
prints a one-time warning when the fallback tier is used:

```console
kl-kbpf: struct bpf_map, struct dma_buf: no debug info; using built-in
fallback layouts that may not match this kernel. Load a matching vmlinux
for exact struct offsets.
```

A BTF blob can also be supplied explicitly (for a remote target with no
usable `.BTF` section) by setting `kdbg.reader.config.btf_path` to a raw
blob or to a `vmlinux` carrying a `.BTF` section.

`tools/gen_layouts.py` keeps the registry honest.  It probes a real
kernel -- a `vmlinux` through GDB's DWARF, or a BTF blob through the
project's own parser (no `bpftool`, no `libbpf`) -- and can verify the
registry against it:

```console
uv run python tools/gen_layouts.py --vmlinux /path/to/vmlinux --check
uv run python tools/gen_layouts.py --btf /sys/kernel/btf/vmlinux --check
uv run python tools/gen_layouts.py --vmlinux /path/to/vmlinux   # report
uv run python tools/gen_layouts.py --btf /sys/kernel/btf/vmlinux \
    --coverage --version "$(uname -r | cut -d- -f1)"         # CI form
```

`--check` exits non-zero on any drift, so it can guard a table update in
CI.  `--coverage` is the weaker claim CI actually makes: it asserts only
that the probe resolved every struct the registry *claims for that
release*, and says nothing about the offsets.  That distinction matters
because a struct can legitimately disappear -- `struct kmem_cache_cpu`
was replaced by sheaves at 7.0 -- so a coverage check that ignored the
version would report a healthy probe as broken.  Without `--version` it
falls back to demanding every entry, which is the strict reading wanted
when the kernel cannot be identified.

`tools/abi_ranges.py` decides *which releases need their own row* before
any of that.  The kernel has changed these structures across releases, so
a row verified against one kernel is silently wrong for another -- the
registry's `struct slab.slab_cache` was read from a 7.0 kernel and
reports `0x8` on every release, while 5.17-6.1 really has `0x18`.  The
tool reads a local `linux-stable` clone, resolves each release's struct
body into a flat member list for one `CONFIG_*` set, and reports the
ranges where that list is unchanged:

```console
uv run python tools/abi_ranges.py struct slab
uv run python tools/abi_ranges.py --with-layouts --since v5.15 struct kmem_cache
uv run python tools/abi_ranges.py --config-file /boot/config-$(uname -r)
```

It needs a `linux-stable` checkout (`--repo`, or `$KERNLENS_LINUX_STABLE`)
and is a *scout*, not an oracle: a member list says which releases moved,
never what the new offset is, so the values still have to come from
`gen_layouts.py` on a real kernel.
