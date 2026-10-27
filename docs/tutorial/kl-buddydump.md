# `kernlens-buddydump`

Buddy free-list dump

**Alias:** `kl-buddydump`  
**Category:** memory & symbols  
**Synopsis:** `kernlens-buddydump [-h] [-z ZONE] [-o ORDER] [-m MTYPE] [-p] [-c CPU]
                          [-n NODE] [-f FIND] [--MIGRATE_TYPES MIGRATE_TYPES]`

pwndbg's `buddydump` view: every page on the free lists, in list order, with its `struct page` and physical address.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
| `-z`, `--zone` | — | Displays/searches lists only in the specified zone. |
| `-o`, `--order` | — | Displays/searches lists only with the specified order. |
| `-m`, `--mtype` | — | Displays/searches lists only with the specified mtype. |
| `-p`, `--pcp-only` | — | Displays/searches only PCP lists. |
| `-c`, `--cpu` | — | CPU nr for searching PCP. |
| `-n`, `--node` | — | _(no help text)_ |
| `-f`, `--find` | — | The address to find in page free lists. |
| `--MIGRATE_TYPES` | — | Use the specified MIGRATE_TYPES value |

## Every zone

### Invocation

```gdb
kernlens-buddydump
```

### Output

```text
zone: all order=None mtype=all
    - [0x00] 0xffff975280120000 [page: 0xffffee5d00004800, phys: 0x120000]
    - [0x01] 0xffff975280140000 [page: 0xffffee5d00005000, phys: 0x140000]
    - [0x02] 0xffff975280180000 [page: 0xffffee5d00006000, phys: 0x180000]
    - [0x03] 0xffff975280200000 [page: 0xffffee5d00008000, phys: 0x200000]
    - [0x04] 0xffff975280400000 [page: 0xffffee5d00010000, phys: 0x400000]
    - [0x05] 0xffff975280800000 [page: 0xffffee5d00020000, phys: 0x800000]
    - [0x06] 0xffff975280c00000 [page: 0xffffee5d00030000, phys: 0xc00000]
    - [0x07] 0xffff9752871bf000 [page: 0xffffee5d001c6fc0, phys: 0x71bf000]
    - [0x08] 0xffff97528715f000 [page: 0xffffee5d001c57c0, phys: 0x715f000]
    - [0x09] 0xffff9752870d0000 [page: 0xffffee5d001c3400, phys: 0x70d0000]
    - [0x0a] 0xffff975287142000 [page: 0xffffee5d001c5080, phys: 0x7142000]
    - [0x0b] 0xffff9752871bd000 [page: 0xffffee5d001c6f40, phys: 0x71bd000]
    - [0x0c] 0xffff975287009000 [page: 0xffffee5d001c0240, phys: 0x7009000]
    - [0x0d] 0xffff975286af6000 [page: 0xffffee5d001abd80, phys: 0x6af6000]
    - [0x0e] 0xffff975287169000 [page: 0xffffee5d001c5a40, phys: 0x7169000]
    - [0x0f] 0xffff9752870d3000 [page: 0xffffee5d001c34c0, phys: 0x70d3000]
... (truncated, 311 page(s) total)
... (1 more line(s), 19 total)
```

*The capture has 19 lines; the first 18 are shown.  Run the command to see the rest.*

### Reading it

Each row is `[index] virtual [page: ptr, phys: addr]`.  The index is the position in the list, so consecutive blocks of the same order appear consecutively -- the physical addresses jump around after the first few because the lists interleave low-order blocks from across the zone.

## One zone

### Invocation

```gdb
kernlens-buddydump -z DMA
```

### Output

```text
zone: DMA order=None mtype=all
    - [0x00] 0xffff975280120000 [page: 0xffffee5d00004800, phys: 0x120000]
    - [0x01] 0xffff975280140000 [page: 0xffffee5d00005000, phys: 0x140000]
    - [0x02] 0xffff975280180000 [page: 0xffffee5d00006000, phys: 0x180000]
    - [0x03] 0xffff975280200000 [page: 0xffffee5d00008000, phys: 0x200000]
    - [0x04] 0xffff975280400000 [page: 0xffffee5d00010000, phys: 0x400000]
    - [0x05] 0xffff975280800000 [page: 0xffffee5d00020000, phys: 0x800000]
    - [0x06] 0xffff975280c00000 [page: 0xffffee5d00030000, phys: 0xc00000]
7 free page(s)
```

### Reading it

The DMA zone here is small and its blocks are the largest ones, so the first rows are the same order-10 and order-9 blocks `kl-buddy list` counts.

## Searching for an address

### Invocation

```gdb
kernlens-buddydump -f 0xffff975280400000
```

### Output

```text
zone: all order=None mtype=all
    - [0x04] 0xffff975280400000 [page: 0xffffee5d00010000, phys: 0x400000]
1 free page(s)
```

### Reading it

`-f/--find` matches against the virtual address, the physical address, or the `struct page`, so any of the three forms identifies the block.  It accepts hex, which matters because the value is an address.

## The migratetype count

### Invocation

```gdb
kernlens-buddydump --MIGRATE_TYPES 5
```

### Output

```text
zone: all order=None mtype=all
    - [0x00] 0xffff975280120000 [page: 0xffffee5d00004800, phys: 0x120000]
    - [0x01] 0xffff975280140000 [page: 0xffffee5d00005000, phys: 0x140000]
    - [0x02] 0xffff975280180000 [page: 0xffffee5d00006000, phys: 0x180000]
    - [0x03] 0xffff975280200000 [page: 0xffffee5d00008000, phys: 0x200000]
    - [0x04] 0xffff975280400000 [page: 0xffffee5d00010000, phys: 0x400000]
    - [0x05] 0xffff975280800000 [page: 0xffffee5d00020000, phys: 0x800000]
    - [0x06] 0xffff975280c00000 [page: 0xffffee5d00030000, phys: 0xc00000]
    - [0x07] 0xffff9752871bf000 [page: 0xffffee5d001c6fc0, phys: 0x71bf000]
    - [0x08] 0xffff97528715f000 [page: 0xffffee5d001c57c0, phys: 0x715f000]
    - [0x09] 0xffff9752870d0000 [page: 0xffffee5d001c3400, phys: 0x70d0000]
    - [0x0a] 0xffff975287142000 [page: 0xffffee5d001c5080, phys: 0x7142000]
    - [0x0b] 0xffff9752871bd000 [page: 0xffffee5d001c6f40, phys: 0x71bd000]
    - [0x0c] 0xffff975287009000 [page: 0xffffee5d001c0240, phys: 0x7009000]
    - [0x0d] 0xffff975286af6000 [page: 0xffffee5d001abd80, phys: 0x6af6000]
    - [0x0e] 0xffff975287169000 [page: 0xffffee5d001c5a40, phys: 0x7169000]
    - [0x0f] 0xffff9752870d3000 [page: 0xffffee5d001c34c0, phys: 0x70d3000]
... (truncated, 311 page(s) total)
311 free page(s)
```

### Reading it

`--MIGRATE_TYPES` overrides the discovered count.  It exists for images whose `migratetype_names` symbol is missing; getting it wrong misplaces every list after the first, so the command normally reads the array instead of guessing.

## Notes

Overlaps `kl-buddy` on purpose: this is the pwndbg layout, `kl-buddy` is the KernLens one with the per-order totals.  Use `kl-buddy list` for counts and this for the individual blocks.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
