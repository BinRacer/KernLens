# `kernlens-pte`

Decode a page-table entry

**Alias:** `kl-pte`  
**Category:** addresses & page tables  
**Synopsis:** `kernlens-pte [-h] entry [va]`

Takes one page-table entry's raw value and decodes the flag bits and the physical address it encodes.  No memory is read: the value is the argument.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | raw page-table entry value |
|  | (optional) | address used for the leaf translations |

## Flags and physical address

### Invocation

```gdb
kernlens-pte 0x8000000000120063
```

### Output

```text
PTE: 0x8000000000120063 present=True bit7=PS/PAT
Flags: P RW A D NX
Physical: 0x120000  pfn=288
```

### Reading it

`present=True` comes from bit 0.  The flag list names each set bit: `P` present, `RW` writable, `US` user, `A` accessed, `D` dirty, `PS` page-size (huge), `NX` no-execute.  `bit7=PS/PAT` is called out separately because bit 7 means page-size at the PMD level and PAT elsewhere; only the level resolves it, so the command reports the ambiguity rather than picking one.

## With an address for context

### Invocation

```gdb
kernlens-pte 0x8000000000120063 0xffff8cb880400000
```

### Output

```text
PTE: 0x8000000000120063 present=True bit7=PS/PAT
Flags: P RW A D NX
Physical: 0x120000  pfn=288
VA: 0xffff8cb880400000
4k leaf: 0x120000
2m leaf: 0x0
1g leaf: 0x400000
```

### Reading it

Giving the address lets the command label the three leaf interpretations of the same bits: what the value would mean as a 4 KiB, 2 MiB or 1 GiB leaf.  This is how a rounding mistake becomes obvious -- the same entry reads differently at each level.

## Notes

Removing the low 12 bits gives the physical page frame; the `NX` bit is the top bit of the 64-bit value, which is why the entry starts with `0x8`.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
