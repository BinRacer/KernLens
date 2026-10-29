# `kl-pt`

Page-table indices and entries

**Canonical:** `kernlens-pt`  
**Category:** addresses & page tables  
**Synopsis:** `kl-pt [-h] [-e] [--paging {4,5}] [VALUE ...]`

Address arithmetic in both directions: a virtual address split into its per-level indices, or a raw page-table entry decoded into flags and a physical address.  `--entry` selects the second, which is what `kl-pte` did.  Nothing is read from the target -- the value is the argument.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | VALUE | virtual address [leaf address used for the translations] |
| `-e`, `--entry` | — | treat VALUE as a raw page-table entry instead of an address |
| `--paging` | `4` \| `5` | force one geometry instead of printing both |

## A direct-map address

### Invocation

```gdb
kl-pt 0xffff90c340400000
```

### Output

```text
VA: 0xffff90c340400000
4-level: pgd=289 pud=269 pmd=2 pte=0 off=0x0
5-level: pgd=511 p4d=289 pud=269 pmd=2 pte=0 off=0x0
huge: 2m_base=0xffff90c340400000 1g_base=0xffff90c340000000
aligned: 2m=True 1g=False page_offset=0x0
canonical: 4-level=0xffff90c340400000 5-level=0xffff90c340400000
```

### Reading it

The 4-level row shows five entries (pgd/pud/pmd/pte/off) and the 5-level row six (with p4d), which is the whole difference between the modes: 5-level adds one level and shrinks the offset.  `huge` gives the base of the 2 MiB and 1 GiB regions containing the address, and `aligned` says whether the address sits exactly on one -- the pair answers 'could this be mapped by a huge page?'.  `page_offset` is the byte offset within a 4 KiB page.

## A text address

### Invocation

```gdb
kl-pt 0xffffffffae900000
```

### Output

```text
VA: 0xffffffffae900000
4-level: pgd=511 pud=510 pmd=372 pte=256 off=0x0
5-level: pgd=511 p4d=511 pud=510 pmd=372 pte=256 off=0x0
huge: 2m_base=0xffffffffae800000 1g_base=0xffffffff80000000
aligned: 2m=False 1g=False page_offset=0x0
canonical: 4-level=0xffffffffae900000 5-level=0xffffffffae900000
```

### Reading it

The upper-half indices are near their maximum (`pgd=511`, `pud=510`) because the kernel image sits at the very top of the address space.  This is also where the two modes disagree most visibly: 5-level paging widens `pgd` but the kernel still occupies the top.

## Decoding an entry

### Invocation

```gdb
kl-pt --entry 0x8000000000120063
```

### Output

```text
PTE: 0x8000000000120063 present=True bit7=PS/PAT
Flags: P RW A D NX
Physical: 0x120000  pfn=288
```

### Reading it

`present=True` comes from bit 0.  The flag list names each set bit: `P` present, `RW` writable, `US` user, `A` accessed, `D` dirty, `PS` page-size (huge), `NX` no-execute.  `bit7=PS/PAT` is called out separately because bit 7 means page-size at the PMD level and PAT elsewhere; only the level resolves it, so the command reports the ambiguity rather than picking one.  Removing the low 12 bits gives the physical page frame, and `NX` is the top bit of the 64-bit value -- which is why the entry starts with `0x8`.

## An entry with an address for context

### Invocation

```gdb
kl-pt --entry 0x8000000000120063 0xffff90c340400000
```

### Output

```text
PTE: 0x8000000000120063 present=True bit7=PS/PAT
Flags: P RW A D NX
Physical: 0x120000  pfn=288
VA: 0xffff90c340400000
4k leaf: 0x120000
2m leaf: 0x0
1g leaf: 0x400000
```

### Reading it

Giving the address lets the command label the three leaf interpretations of the same bits: what the value would mean as a 4 KiB, 2 MiB or 1 GiB leaf.  This is how a rounding mistake becomes obvious -- the same entry reads differently at each level.

## Notes

Indices are computed from the address widths, so they do not depend on the live tables at all; `kl-walk` is the command that then reads each level.  `--paging 4` or `--paging 5` prints one geometry when you are looking at a specific one.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
