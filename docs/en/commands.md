# Command reference

Every command, in the order `kl-help` prints it.  The `kl-` form is
what you type at the prompt; the canonical `kernlens-` form is what
scripts and the generated tutorial use.  Both always work.

This page is generated from `tools/tutorial_meta.json` by
`tools/gen_commands.py`; edit the command's parser description, not
this table.  Each command has a page in [`tutorial/`](tutorial/README.md)
with captured output and a note on how to read it.

## overview (1)

| Command | Aliases | What it does |
| --- | --- | --- |
| `kernlens-status` | `kl-status` | Shows the KernLens version, color mode, KASLR slide, and layout. |

## kernel base & KASLR (1)

| Command | Aliases | What it does |
| --- | --- | --- |
| `kernlens-base` | `kl-base` | Reports the runtime kernel text base and KASLR slide. |

## kernel metadata (6)

| Command | Aliases | What it does |
| --- | --- | --- |
| `kernlens-kcmdline` | `kl-kcmdline` | Return the kernel command line (/proc/cmdline). |
| `kernlens-kversion` | `kl-kversion` | Outputs the kernel version (/proc/version). |
| `kernlens-kconfig` | `kl-kconfig` | Outputs the kernel config (/proc/config.gz). |
| `kernlens-kmod` | `kl-kmod` | Displays the loaded Linux kernel modules. |
| `kernlens-ksyscalls` | `kl-ksyscalls` | Displays the Linux syscall table, including names and addresses of syscalls. |
| `kernlens-kdmesg` | `kl-kdmesg` | Displays the kernel ring buffer (dmesg) contents. |

## addresses & page tables (6)

| Command | Aliases | What it does |
| --- | --- | --- |
| `kernlens-addr` | `kl-addr` | Classifies an address and reports where it maps. |
| `kernlens-pt` | `kl-pt` | Splits a virtual address into page-table indices, or decodes a page-table entry. |
| `kernlens-walk` | `kl-walk` | Walks the live page tables and decodes every level. |
| `kernlens-p2v` | `kl-p2v` | Translates a physical address to virtual + struct page. |
| `kernlens-v2p` | `kl-v2p` | Translates a virtual address (live page tables) to physical. |
| `kernlens-pageinfo` | `kl-pageinfo` | Translates a struct page to virtual and physical addresses. |

## memory & symbols (9)

| Command | Aliases | What it does |
| --- | --- | --- |
| `kernlens-buddy` | `kl-buddy` | Locates an address in the buddy allocator: its zone, its free block, and where it sits inside that block. |
| `kernlens-slab` | `kl-slab`, `kl-slabs` | Prints information about the linux kernel's slab allocator SLUB. |
| `kernlens-sym` | `kl-sym` | Resolves an address to a symbol, or finds symbols by name. |
| `kernlens-bt` | `kl-bt` | Prints a formatted kernel backtrace. |
| `kernlens-read` | `kl-read` | Dumps kernel memory as 64-bit words with symbol annotations. |
| `kernlens-kvar` | `kl-kvar` | Reads a KASLR-aware kernel global variable. |
| `kernlens-read-field` | `kl-read-field` | Reads a struct field (including nested paths) as an integer. |
| `kernlens-kbpf` | `kl-kbpf` | Prints information about the linux kernel bpf progs and maps. |
| `kernlens-kdmabuf` | `kl-kdmabuf` | Prints DMA buf info. |

## CPU topology (3)

| Command | Aliases | What it does |
| --- | --- | --- |
| `kernlens-cpu` | `kl-cpu` | Displays CPU topology, the online mask, and per-CPU offsets. |
| `kernlens-percpu` | `kl-percpu` | Resolves a per-CPU symbol to its runtime address for a CPU. |
| `kernlens-msr` | `kl-msr` | Reads or writes x86_64 model-specific registers (via GDB). |

## bit & integer primitives (2)

| Command | Aliases | What it does |
| --- | --- | --- |
| `kernlens-bits` | `kl-bits` | Inspects a 64-bit value; optionally test/set/clear a bit. |
| `kernlens-int` | `kl-int` | Shows signed/unsigned and LE/BE integer views. |

## output (1)

| Command | Aliases | What it does |
| --- | --- | --- |
| `kernlens-color` | `kl-color` | Enable, disable, or toggle ANSI color output. |

## help (1)

| Command | Aliases | What it does |
| --- | --- | --- |
| `kernlens-help` | `kl-help` | Lists every KernLens command, or explains one in detail. |
