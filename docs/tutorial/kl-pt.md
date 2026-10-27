# `kernlens-pt`

Page-table indices

**Alias:** `kl-pt`  
**Category:** addresses & page tables  
**Synopsis:** `kernlens-pt [-h] va`

Shows the index extracted at each level for a virtual address, in both 4-level and 5-level form, plus the huge-page bases it falls inside.  This is pure arithmetic -- nothing is read from the target.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | virtual address to split |

## A direct-map address

### Invocation

```gdb
kernlens-pt 0xffff8cb880400000
```

### Output

```text
VA: 0xffff8cb880400000
4-level: pgd=281 pud=226 pmd=2 pte=0 off=0x0
5-level: pgd=511 p4d=281 pud=226 pmd=2 pte=0 off=0x0
huge: 2m_base=0xffff8cb880400000 1g_base=0xffff8cb880000000
aligned: 2m=True 1g=False page_offset=0x0
canonical: 4-level=0xffff8cb880400000 5-level=0xffff8cb880400000
```

### Reading it

The 4-level row shows five entries (pgd/pud/pmd/pte/off) and the 5-level row six (with p4d), which is the whole difference between the modes: 5-level adds one level and shrinks the offset.  `huge` gives the base of the 2 MiB and 1 GiB regions containing the address, and `aligned` says whether the address sits exactly on one -- the pair answers 'could this be mapped by a huge page?'.  `page_offset` is the byte offset within a 4 KiB page.

## A text address

### Invocation

```gdb
kernlens-pt 0xffffffff91d00000
```

### Output

```text
VA: 0xffffffff91d00000
4-level: pgd=511 pud=510 pmd=142 pte=256 off=0x0
5-level: pgd=511 p4d=511 pud=510 pmd=142 pte=256 off=0x0
huge: 2m_base=0xffffffff91c00000 1g_base=0xffffffff80000000
aligned: 2m=False 1g=False page_offset=0x0
canonical: 4-level=0xffffffff91d00000 5-level=0xffffffff91d00000
```

### Reading it

The upper-half indices are near their maximum (`pgd=511`, `pud=510`) because the kernel image sits at the very top of the address space.  This is also where the two modes disagree most visibly: 5-level paging widens `pgd` but the kernel still occupies the top.

## Notes

Indices are computed from the address widths, so they do not depend on the live tables at all.  `kl-walk` is the command that then reads each level.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
