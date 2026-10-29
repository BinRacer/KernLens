# `kl-walk`

Walk the page tables

**Canonical:** `kernlens-walk`  
**Category:** addresses & page tables  
**Synopsis:** `kl-walk [-h] [-p ROOT] [-s {levels,pwndbg}] va [{4,5}]`

Follows the live tables from CR3 down to the leaf, decoding each entry.  This is the authoritative answer for `what is this address mapped to`, as opposed to what the index arithmetic suggests.  `--style pwndbg` prints the same walk in pwndbg's layout, which is what `kl-pagewalk` did.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | virtual address to translate |
|  | `4` \| `5` | force 4-level or 5-level paging (default: auto) |
| `-p`, `--pgd` | — | top-level table to start from (default: the live CR3) |
| `-s`, `--style` | `levels` \| `pwndbg` | presentation: one row per level, or pwndbg's pagewalk order (default: levels) |

## A 2 MiB huge-page mapping

### Invocation

```gdb
kl-walk 0xffff90c340400000
```

### Output

```text
VA: 0xffff90c340400000
Paging: 4-level  root=0x7056000
pgd      : idx=0x121 entry=0x7056908 value=0x4a01067 -> 0x4a01000
pud      : idx=0x10d entry=0x4a01868 value=0x4a02067 -> 0x4a02000
pmd      : idx=0x2 entry=0x4a02010 value=0x80000000004000e3 (huge leaf)
Leaf: 2 MiB huge pa=0x400000 offset=0x0
Flags: P RW A D PAT PS NX
```

### Reading it

Each level row is `name: idx= entry= value=`, so the entry's address and content are both visible.  The walk stops at the first level whose entry has the `PS` bit set -- here `pmd`, marked `(huge leaf)` -- because a huge mapping has no lower levels.  `Leaf: 2 MiB` then gives the physical base and the offset inside the huge page.  `root=` is CR3 with its low control bits masked off.  `$cr3` is physical, so table pages are read at `page_offset_base + phys`.

## Forcing 5-level paging

### Invocation

```gdb
kl-walk 0xffff90c340400000 5
```

### Output

```text
VA: 0xffff90c340400000
Paging: 5-level  root=0x7056000
pgd      : idx=0x1ff entry=0x7056ff8 value=0x3015067 -> 0x3015000
p4d      : idx=0x121 entry=0x3015908 value=0x0
Note: p4d entry is not present
```

### Reading it

The optional second argument forces the mode.  Here the walk reports an absent `p4d` entry, which is the correct answer: the CPU is running with 4-level paging (`no5lvl` is on the command line), so the tables have no P4D level and the address is not mapped in that mode.

## The pwndbg layout

### Invocation

```gdb
kl-walk 0xffff90c340400000 --style pwndbg
```

### Output

```text
pmd    @ 0x4a02010 [002] pmde: 0x80000000004000e3  P RW A D PAT PS NX (huge)
pud    @ 0x4a01868 [10d] pude: 0x4a02067 -> 0x4a02000  P RW US A D
pgd    @ 0x7056908 [121] pgde: 0x4a01067 -> 0x4a01000  P RW US A D
pagewalk result: 0xffff90c340400000 [phys: 0x400000]
```

### Reading it

The order is reversed relative to the default view -- the leaf is printed first -- because that is what pwndbg's command does and scripts may parse it.  Each row shows the level, the entry's address, the index in brackets, the raw value, the decoded flags, and the next table.  The final line is the translated address, or the physical address when the walk reached a leaf.

## Notes

`-p/--pgd` walks a table other than the live CR3: a saved one, or a foreign process's, so another task's page table can be followed without switching to it.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
