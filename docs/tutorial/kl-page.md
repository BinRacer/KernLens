# `kernlens-page`

Page for an address

**Alias:** `kl-page`  
**Category:** addresses & page tables  
**Synopsis:** `kernlens-page [-h] [-v] address`

Classifies an address and, for a direct-map address, prints the physical address, pfn and the `struct page` that describes it in one place.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | address or GDB expression to classify |
| `-v`, `--verbose` | — | add the full KAddr analysis (canonicality, alignment, tags) |

## The default view

### Invocation

```gdb
kernlens-page 0xffff992880400000
```

### Output

```text
Address: 0xffff992880400000
Class: kernel=True user=False direct=True vmemmap=False vmalloc=False module=False text=False
Physical: 0x400000  pfn=1024
page: 0xffffd62040010000
bases: page_offset=0xffff992880000000 vmemmap=0xffffd62040000000
```

### Reading it

`Class` is the region set from `kl-addr`.  `Physical` and `page` follow from the direct map and the vmemmap, both of which are printed as `bases:` so the arithmetic can be checked by hand: `page = vmemmap + pfn * sizeof(struct page)`.

## Verbose

### Invocation

```gdb
kernlens-page 0xffff992880400000 -v
```

### Output

```text
Address: 0xffff992880400000
Canonical: 48=True  57=True
Region: kernel=True user=False direct=True vmemmap=False vmalloc=False module=False text=False
ERR_PTR: no
Alignment: down=0xffff992880400000 up=0xffff992880400000
Physical: 0x400000  pfn=1024
page: 0xffffd62040010000
```

### Reading it

`-v` adds the full `kl-addr` block -- canonicality, the `ERR_PTR` check, and the alignment pair -- before the same translation.  It is the 'explain this address completely' form.

## Notes

`sizeof(struct page)` is read from the debug info (64 bytes here), never assumed: it changes with `CONFIG_*` options, and using `PAGE_SIZE` instead is a classic error that produces `struct page` pointers 64x too far apart.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
