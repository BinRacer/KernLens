# `kernlens-pageinfo`

Describe a struct page

**Alias:** `kl-pageinfo`  
**Category:** addresses & page tables  
**Synopsis:** `kernlens-pageinfo [-h] page`

The reverse direction: given a `struct page` pointer, prints the virtual address it backs, the physical address, the pfn, and what the page currently is.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | address of a struct page (head page) |

## From struct page to address

### Invocation

```gdb
kernlens-pageinfo 0xffffee5d00010000
```

### Output

```text
Virtual: 0xffff975280400000
Physical: 0x400000
page: 0xffffee5d00010000
PFN: 1024  type: buddy
refcount: 0
```

### Reading it

`type: buddy` is the most useful field: it says the page is on a buddy free list, which is what you expect for a free page.  `refcount: 0` agrees.  On a 6.1 kernel the type comes from the `PG_buddy` flag, since the `page_type` ordinals used by 6.12+ do not exist yet -- the probe decides which encoding applies by asking whether `enum pageflags` still defines `PG_slab`.

## Notes

A page that is allocated but not on any list reports a type of `unknown` or `initialized`; that is not a failure, it is the absence of a type tag.  Use `kl-slab details` for a page that is a slab.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
