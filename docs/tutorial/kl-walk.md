# `kernlens-walk`

Walk the page tables

**Alias:** `kl-walk`  
**Category:** addresses & page tables  
**Synopsis:** `kernlens-walk [-h] [-p ROOT] va [{4,5}]`

Follows the live tables from CR3 down to the leaf, decoding each entry.  This is the authoritative answer for `what is this address mapped to`, as opposed to what the index arithmetic suggests.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | virtual address to translate |
|  | `4` \| `5` | force 4-level or 5-level paging (default: auto) |
| `-p`, `--pgd` | — | top-level table to start from (default: the live CR3) |

## A 2 MiB huge-page mapping

### Invocation

```gdb
kernlens-walk 0xffff8cb880400000
```

### Output

```text
VA: 0xffff8cb880400000
Paging: 4-level  root=0x6ad2000
pgd      : idx=0x119 entry=0x6ad28c8 value=0x4a01067 -> 0x4a01000
pud      : idx=0xe2 entry=0x4a01710 value=0x4a02067 -> 0x4a02000
pmd      : idx=0x2 entry=0x4a02010 value=0x80000000004000e3 (huge leaf)
Leaf: 2 MiB huge pa=0x400000 offset=0x0
Flags: P RW A D PAT PS NX
```

### Reading it

Each level row is `name: idx= entry= value=`, so the entry's address and content are both visible.  The walk stops at the first level whose entry has the `PS` bit set -- here `pmd`, marked `(huge leaf)` -- because a huge mapping has no lower levels.  `Leaf: 2 MiB` then gives the physical base and the offset inside the huge page.  `root=` is CR3 with its low control bits masked off.

## Forcing 5-level paging

### Invocation

```gdb
kernlens-walk 0xffff8cb880400000 5
```

### Output

```text
VA: 0xffff8cb880400000
Paging: 5-level  root=0x6ad2000
pgd      : idx=0x1ff entry=0x6ad2ff8 value=0x3015067 -> 0x3015000
p4d      : idx=0x119 entry=0x30158c8 value=0x0
Note: p4d entry is not present
```

### Reading it

The optional second argument forces the mode.  Here the walk reports an absent `p4d` entry, which is the correct answer: the CPU is running with 4-level paging (`no5lvl` is on the command line), so the tables have no P4D level and the address is not mapped in that mode.

## Notes

`$cr3` is physical, so table pages are read at `page_offset_base + phys`.  `-p/--pgd` walks a table other than the live CR3: a saved one, or a foreign process's.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
