# Credits and third-party attribution

KernLens is distributed under the GNU General Public License v3.0 or
later (see `LICENSE`).  It incorporates behaviour and, in places,
adapted source from third-party projects.  Their licenses are listed
below and are compatible with the GPL.

## pwndbg

- Project: pwndbg — https://github.com/pwndbg/pwndbg
- License: MIT
- Used by: `src/kernlens/gdb/kernel.py` (kernel version / command-line /
  `CONFIG_*` / module-list / syscall-table / kallsyms / `struct page` /
  `printk_ringbuffer` / BPF / buddy-allocator inspection) and the
  `kernlens-kcmdline`, `kernlens-kversion`, `kernlens-kconfig`,
  `kernlens-kchecksec`, `kernlens-kmod`, `kernlens-ksyscalls`,
  `kernlens-p2v`, `kernlens-v2p`, `kernlens-pageinfo`,
  `kernlens-pagewalk`, `kernlens-klookup`, `kernlens-msr`,
  `kernlens-kdmesg`, `kernlens-kbpf`, `kernlens-buddydump`,
  `kernlens-slab`, and `kernlens-kdmabuf` commands in the
  `kernlens.commands` package.

The kernel metadata commands and the hardening-option list are adapted
from pwndbg's `pwndbg/commands/kcmdline.py`, `kversion.py`,
`kconfig.py`, `kchecksec.py`, `kmod.py`, `ksyscalls.py`, `klookup.py`,
`msr.py`, `kdmesg.py`, `kbpf.py`, `buddydump.py`, `slab.py`,
`kdmabuf.py`, and `paging.py`, together with the underlying helpers in
`pwndbg/aglib/kernel/` (including `kmod.py`, `kallsyms.py`, `macros.py`,
`bpf.py`, `buddydump.py`, `slab.py`, `dmabuf.py`, and
`kconfig_mod.py`).  The reimplementation keeps
pwndbg's observable behaviour (which symbols are read, how the
compressed `IKCFG` image is inflated, how the module list is walked and
its offsets recovered, how the kallsyms token table is expanded, how
`p2v`/`v2p`/`pageinfo`/`pagewalk` translate and decode a `struct page`,
how the printk ring buffer and its descriptors are walked, how the BPF
XArrays are decoded, how the buddy free lists are traversed, how the
slab cache list is walked and an object is mapped to its cache, how the
dma-buf list and its scatterlists are decoded, and which
hardening options are audited) while using KernLens' own memory reader,
styler, and command layer.  The port targets the x86_64 64-bit layout
only.

```
MIT License

Copyright (c) 2026 Dominik 'Disconnect3d' Czarnota

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be included
in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```