# `kernlens-addr`

Address analysis

**Alias:** `kl-addr`  
**Category:** addresses & page tables  
**Synopsis:** `kernlens-addr [-h] address [tag_mask]`

Classifies a 64-bit value as an address: canonical or not, which region it falls in, whether it is an error pointer, how it aligns, and -- when it is in the direct map -- what physical page it refers to.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | address or GDB expression to analyse |
|  | (optional) | mask used for pointer-tag analysis (e.g. 0xfff) |

## A direct-map address

### Invocation

```gdb
kernlens-addr 0xffff8cb880400000
```

### Output

```text
Address: 0xffff8cb880400000
Canonical: 48=True  57=True
Region: kernel=True user=False direct=True vmemmap=False vmalloc=False module=False text=False
ERR_PTR: no
Alignment: down=0xffff8cb880400000 up=0xffff8cb880400000
Physical: 0x400000  pfn=1024
page: 0xffffd0a1c0010000
```

### Reading it

`Region` is a set of independent tests, not a single classification: `kernel`, `user`, `direct`, `vmemmap`, `vmalloc`, `module` and `text` are each answered separately, because a vmemmap address is also a kernel address.  `Physical` appears only when the address is in the direct map, since only there is the mapping a constant offset.

## A text address

### Invocation

```gdb
kernlens-addr 0xffffffff91d00000
```

### Output

```text
Address: 0xffffffff91d00000
Canonical: 48=True  57=True
Region: kernel=True user=False direct=False vmemmap=False vmalloc=False module=False text=True
ERR_PTR: no
Alignment: down=0xffffffff91d00000 up=0xffffffff91d00000
```

### Reading it

Now `text=True` and `direct=False`, and there is no `Physical` row: text is mapped by the kernel image's own page tables at its runtime virtual address, not through the direct map.

## A non-canonical value

### Invocation

```gdb
kernlens-addr 0x5
```

### Output

```text
Address: 0x5
Canonical: 48=True  57=True
Region: kernel=False user=True direct=False vmemmap=False vmalloc=False module=False text=False
ERR_PTR: no
Alignment: down=0x0 up=0x1000
```

### Reading it

`user=True` and every kernel region false.  `Canonical` reports both 48-bit and 57-bit forms, which differ only for values in the upper half between the two sign boundaries -- a useful check when a pointer arrives truncated.

## Ignoring a tag

### Invocation

```gdb
kernlens-addr 0xffff8cb880400000 0xfff
```

### Output

```text
Address: 0xffff8cb880400000
Canonical: 48=True  57=True
Region: kernel=True user=False direct=True vmemmap=False vmalloc=False module=False text=False
ERR_PTR: no
Alignment: down=0xffff8cb880400000 up=0xffff8cb880400000
Tags: mask=0xfff tag=0x0 stripped=0xffff8cb880400000
Physical: 0x400000  pfn=1024
page: 0xffffd0a1c0010000
```

### Reading it

The optional second argument masks the low bits before the analysis, which is how an address-tagged or page-offset-carrying value is normalised to its page.

## Notes

The region boundaries are constants (`KERNEL_BASE`, `VMALLOC_START`, ...) for the layout's fixed parts, while `page_offset_base` and `vmemmap_base` are read from the kernel.  A wrong slide changes the former, never the latter.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
