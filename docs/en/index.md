---
hide:
  - title
---

<!-- Generated from README.md by tools/gen_docs_site.py. Edit the source, not this file. -->

<div align="center">
  <a href="https://github.com/BinRacer/KernLens">
    <img src="https://raw.githubusercontent.com/BinRacer/KernLens/main/images/banner.svg" alt="KernLens" style="width:100%; max-width:100%; margin-top:0; margin-bottom:-0.5rem">
  </a>

  

  <p>
    Read a live Linux kernel from GDB: page tables at every level, SLUB
    caches and object chains, <code>struct page</code>, symbols, KASLR.
  </p>

  <p>
    <a href="https://github.com/BinRacer/KernLens/actions/workflows/ci.yml"><img src="https://github.com/BinRacer/KernLens/actions/workflows/ci.yml/badge.svg" alt="CI status"></a>
    <a href="https://github.com/BinRacer/KernLens"><img src="https://img.shields.io/badge/GitHub-KernLens-181717.svg" alt="GitHub: KernLens"></a>
    <a href="https://github.com/BinRacer/KernLens/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="License: GPL v3"></a>
    <img src="https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-informational" alt="Python 3.10-3.13">
    <img src="https://img.shields.io/badge/commands-40-informational" alt="40 commands">
  </p>
</div>

KernLens adds **40 commands** to GDB for reading a running Linux kernel.
Each one reads real memory through a single reader, decodes it with
arithmetic you can check by hand, and prints the answer with the entry it
came from -- so a wrong result looks wrong instead of looking plausible.

`core/` and `output/` are pure Python and run without GDB at all; only
the `gdb/` package needs a debuggee.

## See it run

<p align="center">
  <img src="assets/demo.svg" alt="A replay of kl-walk decoding a 2 MiB page-table mapping and kl-slab details decoding a SLUB freelist pointer" width="100%">
</p>

A replay of two commands from the 6.1.134 capture, not a live recording:
the text is verbatim from [`tools/tutorial_capture.json`](https://github.com/BinRacer/KernLens/blob/main/tools/tutorial_capture.json),
and the same session is in [`docs/assets/demo.cast`](../assets/demo.cast)
for `asciinema play`. Every number is re-derived from the kernel at run
time rather than assumed.

## What it looks like

A 2 MiB mapping, walked level by level. The walk stops where the hardware
does:

```text
VA: 0xffff975280400000
Paging: 4-level  root=0x3010000
pgd      : idx=0x12e entry=0x3010970 value=0x4a01067 -> 0x4a01000
pud      : idx=0x14a entry=0x4a01a50 value=0x4a02067 -> 0x4a02000
pmd      : idx=0x2 entry=0x4a02010 value=0x80000000004000e3 (huge leaf)
Leaf: 2 MiB huge pa=0x400000 offset=0x0
Flags: P RW A D PAT PS NX
```

Each row shows the index, the *address of the entry*, the raw value, and
where the next level is. The `PS` bit at `pmd` is why there is no `pte`
row. Compare with the same address forced to 5-level paging:

```text
VA: 0xffff975280400000
Paging: 5-level  root=0x3010000
pgd      : idx=0x1ff entry=0x3010ff8 value=0x3015067 -> 0x3015000
p4d      : idx=0x12e entry=0x3015970 value=0x0
Note: p4d entry is not present
```

The SLUB allocator, where `Size` and `Obj Size` differ when a cache rounds
up for alignment or adds metadata -- the gap an amplification attack cares
about (three rows of the 170-cache list):

```text
Name                         # Objects  Size  Obj Size  order
ext4_groupinfo_4k            22         184   184       0
AF_VSOCK                     25         1280  1232      3
MPTCPv6                      15         2112  2064      3
```

And the freelist encoding, which is the part a use-after-free tracer has
to get right. The stored word is not a pointer; `freeptr` and the decoded
`next` are printed together:

```text
Slab @ 0xffff975286c57840 page: 0xffffee5d001b15c0
    cache: 0xffff975284e1bc00 dentry  page_bytes=64
    freeptr: offset=96 random=0xae939aafdb096690
    freelist: 0xffff975286c57c00
    objects: 21  inuse=19  frozen=1
    state: frozen
    slab_size: 0x1000
    next: 0x3110c87b0f5be96f decoded=0xffff975286c57000
```

The arithmetic is `next = stored ^ random ^ swab(slot_address)`; `kl-slab
details` shows the operands so you can recompute it. The remaining rows
(`cpu`, `node`) are omitted here and present in the command's output.

## Install

From a shell, one command:

```console
curl -fsSL https://raw.githubusercontent.com/BinRacer/KernLens/main/install.sh | sh
```

It clones the checkout under `~/.local/share/kernlens`, adds one marked
block to `~/.gdbinit`, and writes a `kernlens` wrapper to
`~/.local/bin`. Running it again updates the checkout instead of adding a
second block; `sh install.sh --uninstall` removes the block and the
wrapper and leaves the checkout alone. Read [`install.sh`](https://github.com/BinRacer/KernLens/blob/main/install.sh)
before piping it, as with any installer.

If you would rather manage the checkout yourself:

```console
git clone https://github.com/BinRacer/KernLens
echo "source $(pwd)/KernLens/gdbinit.py" >> ~/.gdbinit
```

Then:

```gdb
(gdb) file vmlinux
(gdb) target remote :1234
(gdb) kl-base            # recover the KASLR slide and apply it
(gdb) kl-help            # every command, grouped by category
```

`kl-base` first, always: on a KASLR kernel every symbol in the vmlinux is
at its link-time address, and nothing resolved before the slide is
applied. Loading `gdbinit.py` never installs a breakpoint and is safe
before `file vmlinux`.

Check the load path before debugging a kernel:

```console
kernlens doctor
```

It reports the host Python, the Python GDB embeds, whether `~/.gdbinit`
sources an existing startup file, whether GDB can actually import
`kernlens`, and whether a target is attached. `kl-status --doctor` adds
the in-session half. Paste the report into an issue.

There is no PyPI release yet. The startup file is package data now and a
`kernlens` console script prints its path, so a wheel built from this
checkout is loadable even though GDB runs its own interpreter:

```console
pip install .
gdb -q -ex "source $(kernlens path)"
```

`kernlens install` writes the same marked block as `install.sh`, and
`kernlens path` prints the file without touching anything. Until the
first release is published, the installer above is the shorter path, and
`git pull` (or re-running it) is the upgrade. Contributor setup is in
[`CONTRIBUTING.md`](https://github.com/BinRacer/KernLens/blob/main/CONTRIBUTING.md).

## Try it in a container

The demo image compiles a small 6.1 kernel, boots it under QEMU, and
attaches GDB with KernLens sourced. No debug target, no kernel source
tree, and no `/dev/kvm` are needed:

```console
docker build -f demo/Dockerfile -t kernlens-demo .
docker run --rm -it kernlens-demo
```

The tour runs `kl-status`, `kl-kbase`, `kl-kconfig`, `kl-slab info`,
`kl-sym`, and `kl-pagewalk`. Pass a command instead of the tour to run
just that one:

```console
docker run --rm -it kernlens-demo kl-slab info dentry
```

The kernel is built from source in the image and stripped of DWARF, so
the session is also a test of the BTF path. What is inside, and why it is
built rather than downloaded, is in
[`docs/en/demo-container.md`](demo-container.md).

## The 40 commands

Grouped as `kl-help` groups them. The `kl-` form is what you type at the
prompt; the canonical `kernlens-` form is what scripts and the generated
tutorial use. Both always work. Every command, every alias, and a
one-line description is in [`docs/en/commands.md`](commands.md).

| Category | Commands |
| --- | --- |
| overview (1) | `kl-status` |
| kernel base & KASLR (4) | `kl-base`, `kl-kbase`, `kl-kaslr`, `kl-kaslr-offset` |
| kernel metadata (8) | `kl-kchecksec`, `kl-kcmdline`, `kl-kconfig`, `kl-kdmesg`, `kl-klookup`, `kl-kmod`, `kl-ksyscalls`, `kl-kversion` |
| addresses & page tables (9) | `kl-addr`, `kl-p2v`, `kl-page`, `kl-pageinfo`, `kl-pagewalk`, `kl-pt`, `kl-pte`, `kl-v2p`, `kl-walk` |
| memory & symbols (11) | `kl-bt`, `kl-buddy`, `kl-buddydump`, `kl-chain`, `kl-kbpf`, `kl-kdmabuf`, `kl-kvar`, `kl-read`, `kl-read-field`, `kl-slab`, `kl-sym` |
| CPU topology (3) | `kl-cpu`, `kl-msr`, `kl-percpu` |
| bit & integer primitives (2) | `kl-bits`, `kl-int` |
| output (1) | `kl-color` |
| help (1) | `kl-help` |

Every command has a page in [`docs/en/tutorial/`](tutorial/README.md) with real
captured output, its options, and a note on how to read the result.

Two things the command list does not show. `kl-help <command>` gives usage
and worked examples, and `--help` works on every command with a guided
error message rather than a bare usage line. And the commands never
`stop()` the debuggee: they read memory and return, so they compose inside
a breakpoint handler. `kl-msr --write` is the one exception -- it sets an
MSR through GDB's register interface -- and it is opt-in, never taken as
a side effect of a read.

## Use it as a library

The commands are a thin layer over a Python API. From a sourced script:

```python
# any file you source after gdbinit.py -- the names are already installed
print(split_4(0xffff888000001234))       # KPageTable, no memory read
print(read_kvar("jiffies"))              # live read through the facade
print(LE.unpack_u32(b"\x34\x12\x00\x00"))  # LE is a ByteOrderCodec
```

Or import it normally:

```python
from kernlens import KAddr, KPageTable

# (0x111, 0x0, 0x0, 0x1, 0x234) -- one index per level, outermost first
KPageTable.split_4(0xffff888000001234)
KAddr.is_direct_map(0xffff888000001234)  # True
```

The arithmetic half needs no debugger, which is what makes it testable on
the host. The full reference is [`docs/en/api.md`](api.md).

## How it stays true

Every claim this repository makes about itself is checked by a machine,
because the alternative is prose that is correct on the day it is written:

- `docs/en/tutorial/` is **generated** from a capture taken on a running
  kernel; `gen_tutorial.py --check` fails when a page and the capture
  disagree.
- The README demo and `docs/en/commands.md` are generated too:
  `tools/gen_demo.py --check` compares the animation with the capture,
  and `tools/gen_commands.py --check` compares the command table with the
  registered metadata.
- Example coverage is declared in `tools/example_manifest.py` and enforced
  by `tools/check_examples.py --check`: a claim without the code fails,
  and so does a command named in prose but never executed.
- The examples that can run without a debugger are executed in CI; the
  rest are replayed under GDB and recorded, and the record is compared
  against the source on every push.
- The repository tree in `docs/en/architecture.md` and the numbers in
  `examples/README.md` are checked against the real tree and the real
  measurement, not typed by hand.
- The wheel is checked, not assumed: CI builds it and
  `tools/check_wheel.py` fails when the startup file or the console
  script is missing -- the exact failure the old source-only policy
  existed to prevent.

The `kl-*` command count on this page is checked against the command
registry by the test suite, so it cannot quietly become false.

## Documentation

| Document | What is in it |
| --- | --- |
| [`docs/en/tutorial/`](tutorial/README.md) | one page per command, real output |
| [`docs/en/demo-container.md`](demo-container.md) | a kernel under QEMU, built from source and ready to attach |
| [`docs/en/commands.md`](commands.md) | every command and alias, generated |
| [`docs/en/api.md`](api.md) | the Python API reference |
| [`docs/en/architecture.md`](architecture.md) | package layout, API map, design notes |
| [`docs/en/compatibility.md`](compatibility.md) | what has been run, what is expected, what is not claimed |
| [`examples/`](https://github.com/BinRacer/KernLens/blob/main/examples/README.md) | runnable scripts, grouped by intent |
| [`docs/en/naming.md`](naming.md) | command and filename conventions |
| [`CONTRIBUTING.md`](https://github.com/BinRacer/KernLens/blob/main/CONTRIBUTING.md) | setup, tests, the layout generator |
| [`SECURITY.md`](https://github.com/BinRacer/KernLens/blob/main/SECURITY.md) | what counts as a vulnerability, and how to report one privately |
| [`CITATION.cff`](https://github.com/BinRacer/KernLens/blob/main/CITATION.cff) | how to cite the project, and the version being cited |
| [`CHANGELOG.md`](https://github.com/BinRacer/KernLens/blob/main/CHANGELOG.md) | every change, newest first |

## Requirements and license

Python 3.10+ and a GDB built with Python 3.10+. Those are two
interpreters, not one: `kernlens doctor` prints both, because a GDB whose
embedded Python cannot see the package is the most common first-run
failure. x86_64 kernels only -- the page-table and `struct page` decoding
are written against that architecture. On Python below 3.12 the only
runtime dependency is `typing-extensions`. Which combinations have
actually been run, and which are only expected, is in
[`docs/en/compatibility.md`](compatibility.md).

No package is published yet. Installation is the one-line installer, a
`git clone`, or a wheel built from this checkout; see [Install](#install).
The wheel ships the startup file and `kernlens path` prints it, because
GDB sources that file from its own interpreter.

GPL-3.0-or-later. See [`LICENSE`](https://github.com/BinRacer/KernLens/blob/main/LICENSE); third-party attribution is in
[`CREDITS.md`](https://github.com/BinRacer/KernLens/blob/main/CREDITS.md).
