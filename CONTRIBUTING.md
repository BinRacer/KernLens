# Contributing

Development notes for KernLens.  If you only want to *use* it, the
[README](README.md) has the three-step quickstart and the command
table; nothing here is needed for that.

## Distribution

KernLens is distributed as a source checkout, not as a package.  There is
no PyPI release and there will not be one while the entry point is a file
you source rather than a module you import.

The reason is not laziness.  Every quickstart path ends at `source
/path/to/gdbinit.py`, and `gdbinit.py` is not in the wheel: the wheel is
built from `src/`, and the startup file lives beside it.  Publishing
today would produce a package that installs cleanly and then cannot be
made to work by following the documentation, which is worse than
publishing nothing.

Publishing would require making the startup file package data and adding
an entry point that prints its path -- a real change with its own tests,
not a metadata edit.  Until that happens, `git pull` is the upgrade path
and `uv sync` is for development only.

## Testing and development

The test suite is `unittest`-compatible and also runs under pytest.
All development commands go through uv:

```console
uv sync
uv run pytest --cov=kernlens --cov-report=term-missing
uv run ruff check .
```

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

See [`docs/architecture.md`](docs/architecture.md) for the public API
map, module responsibilities, the SLUB inspection model, and GDB
loading details.  [`docs/naming.md`](docs/naming.md) defines the
command and Python naming rules.  For a guided tour with real output
from a live kernel, start at [`docs/tutorial/`](docs/tutorial/README.md) --
one page per command.  Release history lives in
[`CHANGELOG.md`](CHANGELOG.md).

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
