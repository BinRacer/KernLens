# `kernlens-pagewalk`

Pagewalk (pwndbg format)

**Alias:** `kl-pagewalk`  
**Category:** addresses & page tables  
**Synopsis:** `kernlens-pagewalk [-h] [-p ENTRY] vaddr`

The same walk as `kl-walk`, printed in pwndbg's `pagewalk` layout: leaf first, root last.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | virtual address to walk |
| `-p`, `--pgd` | — | Top-level table address |

## The pwndbg layout

### Invocation

```gdb
kernlens-pagewalk 0xffff992880400000
```

### Output

```text
pmd    @ 0x4a02010 [002] pmde: 0x80000000004000e3  P RW A D PAT PS NX (huge)
pud    @ 0x4a01510 [0a2] pude: 0x4a02067 -> 0x4a02000  P RW US A D
pgd    @ 0x3010990 [132] pgde: 0x4a01067 -> 0x4a01000  P RW US A D
pagewalk result: 0xffff992880400000 [phys: 0x400000]
```

### Reading it

The order is reversed relative to `kl-walk` -- the leaf is printed first -- because that is what pwndbg's command does and scripts may parse it.  Each row shows the level, the entry's address, the index in brackets, the raw value, the decoded flags, and the next table.  The final line is the translated address, or the physical address when the walk reached a leaf.

## Notes

Kept alongside `kl-walk` deliberately: `kl-walk` is the KernLens view (root-down, with the failure reason inline), and this is the pwndbg-compatible one.  Neither is redundant for a user who has pwndbg muscle memory.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
