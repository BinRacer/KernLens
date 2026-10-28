# Compatibility

Which environments KernLens has actually been run in, which ones it is
expected to work in, and which ones it does not claim.  The distinction
is the point of the page: a bug report that contradicts an *expected*
row is useful, and a row that quietly became a promise is not.

## The four words

| Word | Means | What backs it |
| --- | --- | --- |
| **measured** | someone ran it on that stack and the result is in this repository | a capture, a recorded command, or a CI log |
| **measured in tests** | the code path is exercised, but on synthetic input, not on that stack | a test in `tests/` |
| **expected** | nothing in the path is distribution-specific and the stated requirement is met, but nobody ran it | the requirement itself |
| **unsupported** | outside the claims; it may run, but a result from it is not a claim | the design, or a refusal |

`unsupported` is not "we have not got to it".  For x86_64-only decoding it
is a deliberate boundary; for a GDB without Python it is physics.

## Two interpreters, not one

The most common first-run failure is reading "Python 3.10+" as one
requirement.  It is two, and they are unrelated:

| | Host Python | GDB's embedded Python |
| --- | --- | --- |
| runs | the `kernlens` console script, `install.sh`, `kernlens doctor` | the startup file, every command, every `kernlens.*` import |
| floor | 3.10 (`requires-python`) | 3.10 (the package is imported, not reimplemented) |
| printed by | `kernlens doctor` → `python` | `kernlens doctor` → `gdb-python` |

On the measured machine below they happen to be close -- 3.12.11 and
3.12.3 -- and that is a coincidence, not a requirement.  What crosses
between them is files on disk, not the interpreter: the startup file adds
the parent of its own package to `sys.path`, so the package and its
dependencies resolve from the same `site-packages` the host installed
them into.

What would *not* cross is a compiled extension built for the host's
interpreter.  KernLens is pure Python and has no such dependency today;
this is the thing to check before adding one, not a problem to solve now.

## Matrix

| Environment | GDB | GDB's Python | Host Python | Kernel | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| Ubuntu 24.04.5 host, x86_64 QEMU guest | 15.1 (Ubuntu 15.1-1ubuntu1~24.04.1) | 3.12.3 | 3.12.11 | 6.1.134, 4-level, KASLR on, SLUB, 4 CPUs | `measured` | `tools/tutorial_capture.json`; `kernlens doctor` |
| Ubuntu 24.04.5, wheel in a clean venv, load only | 15.1 | 3.12.3 | 3.12 | none (no debuggee) | `measured` | `source $(kernlens path)` prints `KernLens 0.3.0 loaded` |
| Ubuntu 24.04.5, no `vmlinux` and no target | 15.1 | 3.12.3 | 3.12.11 | host 7.0.0-38-generic, BTF readable | `measured` | `kernlens doctor` reports `btf ok`; `kl-status` prints `?` instead of a guess |
| 4-level paging with a 2 MiB huge leaf | 15.1 | 3.12.3 | 3.12.11 | 6.1.134 | `measured` | `kl-walk` and `kl-pagewalk` in the capture |
| 5-level paging | none (fake `gdb`) | n/a | 3.10 -- 3.13 | synthetic tables | `measured in tests` | `tests/integration/test_gdb_facade.py` walks complete 4- and 5-level tables; the capture only attempts 5-level on a 4-level kernel and reports `p4d entry is not present` |
| Fallback layouts without DWARF or BTF | none (fake `gdb`) | n/a | 3.10 -- 3.13 | 6.1.134 layout values | `measured in tests` | `tests/integration/test_gdb_facade.py`; the command layer warns when a fallback is used |
| Any Linux, any GDB built with Python 3.10+ | any | 3.10 -- 3.13 | 3.10 -- 3.13 | any x86_64 with DWARF or BTF | `expected` | requirements met; not run |
| GDB built `--without-python` | any | none | any | any | `unsupported` | there is no interpreter to source a Python file; `doctor` reports it |
| GDB whose embedded Python is below 3.10 | any | < 3.10 | any | any | `unsupported` | `requires-python` is 3.10; the package is imported by that interpreter |
| arm64, ppc64le, riscv64 | any | any | any | any | `unsupported` | page-table and `struct page` decoding are written against x86_64 |
| `vmcore` / crash dump / the `crash` utility | any | any | any | any | `unsupported` | commands read memory through a live `target remote` |
| Kernel without DWARF or BTF, version outside the fallback table | any | any | any | any | `unsupported` | no registry entry; commands print `not in the fallback registry` |

Rows 1, 3 and 4 are the host or the QEMU guest it debugged; row 2 is a
clean venv on that host; rows 5 and 6 never load a debugger, which is why
their GDB column says `none`.  Row 3 is what a host with no `vmlinux` and
no target looks like: `btf ok` means the fallback is readable, and
`kl-status` prints `?` for what it cannot resolve -- the documented
refusal, not a failure.

The fallback table is not a substitute for DWARF.  Offsets depend on
`CONFIG_*` options, so an entry can be wrong for another build of the same
version; that is why using it prints a warning, and why its row is
`measured in tests` rather than `measured` on a kernel.

No minimum GDB version is claimed.  The oldest release this has been run
on is 15.1, the measured row.  The API surface used -- `gdb.Command`,
`parse_and_eval`, `execute`, `selected_inferior`, `newest_frame`,
`lookup_type` -- has existed for far longer than that, which is an
argument that older releases work, not a measurement.  A `measured` row on
an older GDB is what would turn the argument into a claim.

## What a new row needs

To turn an *expected* row into a *measured* one, a pull request should
carry:

- the `kernlens doctor` report (host side), pasted as a code block;
- the `kl-status --doctor` report (in-session side), if the row claims a
  kernel;
- the kernel version and its page-table level, if the row claims kernel
  coverage -- for a full capture, that is the same version
  `tools/tutorial_capture.json` records.

A row without those is prose, and prose is what this page exists to
replace.  `tests/unit/test_compatibility.py` checks the parts that can be
checked without a debuggee: the status vocabulary, the Python range
against `pyproject.toml` and the CI matrix, and the measured kernel
against the capture.

## Support window

This is not a distribution support promise.  Fixes land on `main` and in
the newest release; older releases are not back-patched.  See
[`SECURITY.md`](../SECURITY.md) for what counts as a vulnerability and
for the version table.
