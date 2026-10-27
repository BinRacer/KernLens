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
    - [0x00] 0xffff8cb880120000 [page: 0xffffd0a1c0004800, phys: 0x120000]
    - [0x01] 0xffff8cb880140000 [page: 0xffffd0a1c0005000, phys: 0x140000]
    - [0x02] 0xffff8cb880180000 [page: 0xffffd0a1c0006000, phys: 0x180000]
    - [0x03] 0xffff8cb880200000 [page: 0xffffd0a1c0008000, phys: 0x200000]
    - [0x04] 0xffff8cb880400000 [page: 0xffffd0a1c0010000, phys: 0x400000]
    - [0x05] 0xffff8cb880800000 [page: 0xffffd0a1c0020000, phys: 0x800000]
    - [0x06] 0xffff8cb880c00000 [page: 0xffffd0a1c0030000, phys: 0xc00000]
    - [0x07] 0xffff8cb886d43000 [page: 0xffffd0a1c01b50c0, phys: 0x6d43000]
    - [0x08] 0xffff8cb886a1c000 [page: 0xffffd0a1c01a8700, phys: 0x6a1c000]
    - [0x09] 0xffff8cb886d13000 [page: 0xffffd0a1c01b44c0, phys: 0x6d13000]
    - [0x0a] 0xffff8cb886d15000 [page: 0xffffd0a1c01b4540, phys: 0x6d15000]
    - [0x0b] 0xffff8cb886d21000 [page: 0xffffd0a1c01b4840, phys: 0x6d21000]
    - [0x0c] 0xffff8cb886d97000 [page: 0xffffd0a1c01b65c0, phys: 0x6d97000]
    - [0x0d] 0xffff8cb886d56000 [page: 0xffffd0a1c01b5580, phys: 0x6d56000]
    - [0x0e] 0xffff8cb886b81000 [page: 0xffffd0a1c01ae040, phys: 0x6b81000]
    - [0x0f] 0xffff8cb886cc8000 [page: 0xffffd0a1c01b3200, phys: 0x6cc8000]
... (truncated, 203 page(s) total)
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
    - [0x00] 0xffff8cb880120000 [page: 0xffffd0a1c0004800, phys: 0x120000]
    - [0x01] 0xffff8cb880140000 [page: 0xffffd0a1c0005000, phys: 0x140000]
    - [0x02] 0xffff8cb880180000 [page: 0xffffd0a1c0006000, phys: 0x180000]
    - [0x03] 0xffff8cb880200000 [page: 0xffffd0a1c0008000, phys: 0x200000]
    - [0x04] 0xffff8cb880400000 [page: 0xffffd0a1c0010000, phys: 0x400000]
    - [0x05] 0xffff8cb880800000 [page: 0xffffd0a1c0020000, phys: 0x800000]
    - [0x06] 0xffff8cb880c00000 [page: 0xffffd0a1c0030000, phys: 0xc00000]
7 free page(s)
```

### Reading it

The DMA zone here is small and its blocks are the largest ones, so the first rows are the same order-10 and order-9 blocks `kl-buddy list` counts.

## Searching for an address

### Invocation

```gdb
kernlens-buddydump -f 0xffff8cb880400000
```

### Output

```text
zone: all order=None mtype=all
    - [0x04] 0xffff8cb880400000 [page: 0xffffd0a1c0010000, phys: 0x400000]
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
    - [0x00] 0xffff8cb880120000 [page: 0xffffd0a1c0004800, phys: 0x120000]
    - [0x01] 0xffff8cb880140000 [page: 0xffffd0a1c0005000, phys: 0x140000]
    - [0x02] 0xffff8cb880180000 [page: 0xffffd0a1c0006000, phys: 0x180000]
    - [0x03] 0xffff8cb880200000 [page: 0xffffd0a1c0008000, phys: 0x200000]
    - [0x04] 0xffff8cb880400000 [page: 0xffffd0a1c0010000, phys: 0x400000]
    - [0x05] 0xffff8cb880800000 [page: 0xffffd0a1c0020000, phys: 0x800000]
    - [0x06] 0xffff8cb880c00000 [page: 0xffffd0a1c0030000, phys: 0xc00000]
    - [0x07] 0xffff8cb886d43000 [page: 0xffffd0a1c01b50c0, phys: 0x6d43000]
    - [0x08] 0xffff8cb886a1c000 [page: 0xffffd0a1c01a8700, phys: 0x6a1c000]
    - [0x09] 0xffff8cb886d13000 [page: 0xffffd0a1c01b44c0, phys: 0x6d13000]
    - [0x0a] 0xffff8cb886d15000 [page: 0xffffd0a1c01b4540, phys: 0x6d15000]
    - [0x0b] 0xffff8cb886d21000 [page: 0xffffd0a1c01b4840, phys: 0x6d21000]
    - [0x0c] 0xffff8cb886d97000 [page: 0xffffd0a1c01b65c0, phys: 0x6d97000]
    - [0x0d] 0xffff8cb886d56000 [page: 0xffffd0a1c01b5580, phys: 0x6d56000]
    - [0x0e] 0xffff8cb886b81000 [page: 0xffffd0a1c01ae040, phys: 0x6b81000]
    - [0x0f] 0xffff8cb886cc8000 [page: 0xffffd0a1c01b3200, phys: 0x6cc8000]
... (truncated, 203 page(s) total)
203 free page(s)
```

### Reading it

`--MIGRATE_TYPES` overrides the discovered count.  It exists for images whose `migratetype_names` symbol is missing; getting it wrong misplaces every list after the first, so the command normally reads the array instead of guessing.

## Notes

Overlaps `kl-buddy` on purpose: this is the pwndbg layout, `kl-buddy` is the KernLens one with the per-order totals.  Use `kl-buddy list` for counts and this for the individual blocks.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
