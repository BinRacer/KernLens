# `kernlens-v2p`

Virtual to physical

**Alias:** `kl-v2p`  
**Category:** addresses & page tables  
**Synopsis:** `kernlens-v2p [-h] vaddr`

Translates a virtual address to physical by consulting the live page tables, falling back to the direct-map arithmetic when the address is in the direct map.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | virtual address to translate |

## A direct-map address

### Invocation

```gdb
kernlens-v2p 0xffff992880400000
```

### Output

```text
Virtual: 0xffff992880400000
Physical: 0x400000
page: 0xffffd62040010000
PFN: 1024  type: buddy
refcount: 0
```

### Reading it

The result matches `kl-p2v 0x400000` in reverse, which is the check that matters.  Because a direct-map address's translation is exactly `virt - page_offset_base`, agreement here means the base is correct; disagreement means the slide or the base is wrong, not that the tables are.

## Notes

For an address outside the direct map this must walk the tables, so it fails where `kl-p2v` cannot: an unmapped page has no physical address even though the arithmetic would produce one.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
