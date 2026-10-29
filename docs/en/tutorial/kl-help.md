# `kernlens-help`

Command reference

**Alias:** `kl-help`  
**Category:** help  
**Synopsis:** `kernlens-help [-h] [COMMAND]`

`kl-help` is the only command that needs no debuggee: it reads the command registry that `@Command` decorated functions populate.  A bare invocation lists every command grouped by category; giving a name prints that command's full help.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | COMMAND | kernlens-* name or kl-* alias to describe (default: list all) |

## Listing every command

### Invocation

```gdb
kernlens-help
```

### Output

```text
KernLens 0.3.0 — command reference
  type kl-help kl-<command> for usage, options, and examples

overview
  kernlens-status [-h] [--doctor]     Shows the KernLens version, color mode, KASLR slide, and layout.

kernel base & KASLR
  kernlens-base [-h] [-v] [-r] [command ...]  Reports the runtime kernel text base and KASLR slide.

kernel metadata
  kernlens-kcmdline [-h]              Return the kernel command line (/proc/cmdline).
  kernlens-kversion [-h]              Outputs the kernel version (/proc/version).
  kernlens-kconfig [-h] [-l FILE_PATH] [-c] [config_name]  Outputs the kernel config (/proc/config.gz).
  kernlens-kmod [-h] [-l PATH] [module_name]  Displays the loaded Linux kernel modules.
  kernlens-ksyscalls [-h] [syscall_name]  Displays the Linux syscall table, including names and addresses of syscalls.
  kernlens-kdmesg [-h] [-T]           Displays the kernel ring buffer (dmesg) contents.

addresses & page tables
  kernlens-addr [-h] [-b] address [tag_mask]  Classifies an address and reports where it maps.
  kernlens-pt [-h] [-e] [--paging {4,5}] [VALUE ...]  Splits a virtual address into page-table indices, or decodes a page-table entry.
  kernlens-walk [-h] [-p ROOT] [-s {levels,pwndbg}] va [{4,5}]  Walks the live page tables and decodes every level.
  kernlens-p2v [-h] paddr             Translates a physical address to virtual + struct page.
  kernlens-v2p [-h] vaddr             Translates a virtual address (live page tables) to physical.
  kernlens-pageinfo [-h] page         Translates a struct page to virtual and physical addresses.

memory & symbols
  kernlens-buddy [-h] [-z ZONE] [-o ORDER] [-m MTYPE] [-n NODE] [-v]
                      [--limit LIMIT] [-p] [-c CPU] [-f FIND]
                      [--MIGRATE_TYPES COUNT]
                      [command ...]  Locates an address in the buddy allocator: its zone, its free block, and where it sits inside that block.
  kernlens-slab [-h] [-v] [-c CPU] [-n NODE] [-p] [-a] [-i] [-r]
                     [--reclaim] [--ctor]
                     [command ...]  Prints information about the linux kernel's slab allocator SLUB.
  kernlens-sym [-h] [-f] [-a] [query]  Resolves an address to a symbol, or finds symbols by name.
  kernlens-bt [-h] [--chain] [depth]  Prints a formatted kernel backtrace.
  kernlens-read [-h] [-m {ascii}] address [count]  Dumps kernel memory as 64-bit words with symbol annotations.
  kernlens-kvar [-h] symbol           Reads a KASLR-aware kernel global variable.
  kernlens-read-field [-h] address type path  Reads a struct field (including nested paths) as an integer.
  kernlens-kbpf [-h] [-v] [-b NTH] [-p] [-m] [--values]  Prints information about the linux kernel bpf progs and maps.
  kernlens-kdmabuf [-h]               Prints DMA buf info.

CPU topology
  kernlens-cpu [-h] [cpu]             Displays CPU topology, the online mask, and per-CPU offsets.
  kernlens-percpu [-h] symbol [cpu]   Resolves a per-CPU symbol to its runtime address for a CPU.
  kernlens-msr [-h] [-w [write_value]] [-l] [-r [MSR_RANGE]] [msr]  Reads or writes x86_64 model-specific registers (via GDB).

bit & integer primitives
  kernlens-bits [-h] value [bit]      Inspects a 64-bit value; optionally test/set/clear a bit.
  kernlens-int [-h] value [width]     Shows signed/unsigned and LE/BE integer views.

output
  kernlens-color [-h] [{on,off,toggle}]  Enable, disable, or toggle ANSI color output.

help
  kernlens-help [-h] [COMMAND]        Lists every KernLens command, or explains one in detail.
```

### Reading it

Commands are grouped by the category the decorator declared.  The usage column is the command's own `argparse` usage string, so it always matches what the parser accepts.  Only `kernlens-` names are listed: the `kl-` aliases are one-to-one and would double the output.

## Explaining one command

### Invocation

```gdb
kernlens-help kl-walk
```

### Output

```text
usage: kernlens-walk [-h] [-p ROOT] [-s {levels,pwndbg}] va [{4,5}]

Walks the live page tables and decodes every level.

positional arguments:
  va                    virtual address to translate
  {4,5}                 force 4-level or 5-level paging (default: auto)

options:
  -h, --help            show this help message and exit
  -p ROOT, --pgd ROOT   top-level table to start from (default: the live CR3)
  -s {levels,pwndbg}, --style {levels,pwndbg}
                        presentation: one row per level, or pwndbg's pagewalk
                        order (default: levels)

Examples:
kl-walk 0xffff888000001234
kl-walk 0xffff800000201234 5
kl-walk 0xffff888000001234 --pgd 0x10000
kl-walk 0xffff888000001234 --style pwndbg

Notes:
``-p/--pgd`` walks a table other than the live CR3 -- a saved or
foreign root, so a page table of another task can be followed
without switching to it.

``-s/--style pwndbg`` prints the deepest level first, in
``kl-pagewalk``'s layout; ``levels`` (the default) prints one row
per level from the top down.  It is one walk either way, so it
is one command.

Alias: kl-walk
```

### Reading it

The argument must be namespaced.  `kl-help walk` is rejected with a hint to try `kl-walk`, because the bare names exist in pwndbg and GDB but never in KernLens' registry -- accepting them would make the help depend on what else happens to be loaded.

## A command with subcommands

### Invocation

```gdb
kernlens-help kernlens-slab
```

### Output

```text
usage: kernlens-slab [-h] [-v] [-c CPU] [-n NODE] [-p] [-a] [-i] [-r]
                     [--reclaim] [--ctor]
                     [command ...]

Prints information about the linux kernel's slab allocator SLUB.

positional arguments:
  command               list [filter] | info <name>... | contains <addr>... |
                        details <addr>... | <addr>

options:
  -h, --help            show this help message and exit
  -v, --verbose         display more detailed information (with `info`)
  -c CPU, --cpu CPU     CPU to display
  -n NODE, --node NODE
  -p, --partial         displays partial lists
  -a, --active          displays the active list
  -i, --inuse           also show the object stride including metadata (with
                        `info`)
  -r, --random          also show the freelist randomisation key (with `info`)
  --reclaim             also show whether SLAB_RECLAIM_ACCOUNT is set (with
                        `info`)
  --ctor                also show the cache's constructor symbol (with `info`)

Examples:
kl-slab list
kl-slab list kmalloc
kl-slab info kmalloc-1k -v
kl-slab contains 0xffff8880032a1c40
kl-slab details 0xffff8880032a1c40 -c 0
kl-slab 0xffff8880032a1c40            # legacy bare-address form

Aliases: kl-slab, kl-slabs
```

### Reading it

Subcommands appear in the positional argument's help text rather than as argparse subparsers, because KernLens dispatches them itself to keep pwndbg's `slab list` / `slab info` spellings working.

## Notes

The `Examples:` and `Notes:` lines at the bottom of each page come from the decorator, not from the parser, so they can carry the longer explanation that would clutter `--help`.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
