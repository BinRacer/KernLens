# `kl-p2v`

Physical to virtual

**Canonical:** `kernlens-p2v`  
**Category:** addresses & page tables  
**Synopsis:** `kl-p2v [-h] paddr`

Translates a physical address to its direct-map virtual address and prints the `struct page` and type, the same three facts as `kl-pageinfo`.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | physical address to translate |

## A free page

### Invocation

```gdb
kl-p2v 0x400000
```

### Output

```text
Physical: 0x400000
Virtual: 0xffff9762c0400000
page: 0xffffd4fe00010000
PFN: 1024  type: buddy
refcount: 0
```

### Reading it

`Virtual` is `page_offset_base + phys` exactly, because that is what the direct map is.  The `struct page` and `type: buddy` rows come from the vmemmap, and agree with `kl-v2p` and `kl-pageinfo` for the same page -- running all three is a good way to confirm the two bases are right.

## Notes

No page tables are walked: the direct map is a constant offset, so this works even for a physical address with no valid virtual mapping of its own.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
