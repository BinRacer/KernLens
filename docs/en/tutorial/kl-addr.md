# `kl-addr`

Analyse an address

**Canonical:** `kernlens-addr`  
**Category:** addresses & page tables  
**Synopsis:** `kl-addr [-h] [-b] address [tag_mask]`

Every question KernLens can answer about a bare address: canonicality, the region it falls in, whether it is an `ERR_PTR`, how it aligns, its pointer tag, and -- for a direct-map address -- the physical address, pfn, and `struct page`.  `--brief` stops after the region and the translation, which is what `kl-page` printed.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | address or GDB expression to analyse |
|  | (optional) | mask used for pointer-tag analysis (e.g. 0xfff) |
| `-b`, `--brief` | — | only the class, the translation, and the two bases |

## The full analysis

### Invocation

```gdb
kl-addr 0xffff9762c0400000
```

### Output

```text
Address: 0xffff9762c0400000
Canonical: 48=True  57=True
Region: kernel=True user=False direct=True vmemmap=False vmalloc=False module=False text=False
ERR_PTR: no
Alignment: down=0xffff9762c0400000 up=0xffff9762c0400000
Physical: 0x400000  pfn=1024
page: 0xffffd4fe00010000
```

### Reading it

`Canonical` checks both widths, because a 57-bit kernel accepts addresses a 48-bit one would reject as non-canonical.  `Region` is the set of range tests that apply, and `direct=True` is what makes the translation below meaningful.  `Alignment` gives the containing page and the next boundary.

## Pointer tags

### Invocation

```gdb
kl-addr 0xffff9762c0400000 0xfff
```

### Output

```text
Address: 0xffff9762c0400000
Canonical: 48=True  57=True
Region: kernel=True user=False direct=True vmemmap=False vmalloc=False module=False text=False
ERR_PTR: no
Alignment: down=0xffff9762c0400000 up=0xffff9762c0400000
Tags: mask=0xfff tag=0x0 stripped=0xffff9762c0400000
Physical: 0x400000  pfn=1024
page: 0xffffd4fe00010000
```

### Reading it

The optional mask separates a tagged pointer from the address inside it -- the last step, for a value that carried a page offset or a tag, back to the page it names.

## The brief form

### Invocation

```gdb
kl-addr 0xffff9762c0400000 --brief
```

### Output

```text
Address: 0xffff9762c0400000
Class: kernel=True user=False direct=True vmemmap=False vmalloc=False module=False text=False
Physical: 0x400000  pfn=1024
page: 0xffffd4fe00010000
bases: page_offset=0xffff9762c0000000 vmemmap=0xffffd4fe00000000
```

### Reading it

`Class` is the region set, `Physical` and `page` follow from the direct map and the vmemmap, and `bases:` prints `page_offset_base` and `vmemmap_base` so the arithmetic can be checked by hand: `page = vmemmap + pfn * sizeof(struct page)`.  `sizeof(struct page)` is read from the debug info (64 bytes here), never assumed: it changes with `CONFIG_*` options, and using `PAGE_SIZE` instead is a classic error that produces `struct page` pointers 64x too far apart.

## Notes

The region boundaries are constants (`KERNEL_BASE`, `VMALLOC_START`, ...) for the layout's fixed parts, while `page_offset_base` and `vmemmap_base` are read from the kernel.  A wrong slide changes the former, never the latter.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
