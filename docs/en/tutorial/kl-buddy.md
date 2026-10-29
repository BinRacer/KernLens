# `kl-buddy`

Locate an address in the buddy allocator

**Canonical:** `kernlens-buddy`  
**Category:** memory & symbols  
**Synopsis:** `kl-buddy [-h] [-z ZONE] [-o ORDER] [-m MTYPE] [-n NODE] [-v]
                [--limit LIMIT] [-p] [-c CPU] [-f FIND]
                [--MIGRATE_TYPES COUNT]
                [command ...]`

Answers 'what is this page' for the page allocator: which zone it belongs to, whether it is free, and if so which free block it is part of and where inside that block.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | command | list [-z ZONE] [-o ORDER] [-m MTYPE] [-n NODE] \| info <addr> \| freelist -o ORDER [-m MTYPE] \| dump [-z ZONE] [-o ORDER] [-m MTYPE] [-n NODE] [-f ADDR] \| <addr> |
| `-z`, `--zone` | — | restrict to one zone (e.g. Normal). |
| `-o`, `--order` | — | restrict to one buddy order (decimal). |
| `-m`, `--mtype` | — | restrict to one migratetype (e.g. Movable). |
| `-n`, `--node` | — | restrict to one NUMA node. |
| `-v`, `--verbose` | — | expand (freelist) or add detail (info). |
| `--limit` | — | max blocks to expand with freelist -v (default 64). |
| `-p`, `--pcp-only` | — | displays/searches only PCP lists. |
| `-c`, `--cpu` | — | CPU number for searching PCP. |
| `-f`, `--find` | — | an address to search for in the page free lists. |
| `--MIGRATE_TYPES` | COUNT | ignored; the migratetype count is read from the image |

## Free blocks, per order

### Invocation

```gdb
kl-buddy list
```

### Output

```text
buddy free lists  (all)
zone   node  order  nr_free  pages(1<<order)
-----  ----  -----  -------  ---------------
DMA    0     5      1        32
DMA    0     6      1        64
DMA    0     7      1        128
DMA    0     9      1        512
DMA    0     10     3        3072
DMA32  0     0      147      147
DMA32  0     1      55       110
DMA32  0     2      30       120
DMA32  0     3      7        56
DMA32  0     4      4        64
DMA32  0     5      3        96
DMA32  0     6      1        64
DMA32  0     8      1        256
DMA32  0     9      2        1024
DMA32  0     10     1        1024
15 non-empty order(s)
```

### Reading it

One row per non-empty order per zone.  `nr_free` is the kernel's per-ORDER counter, so it counts *blocks* of `1 << order` pages, not pages; `pages(1<<order)` multiplies it out.  There is deliberately no migratetype column: `free_area.nr_free` is a single counter covering all migratetypes, and reading it at a migratetype stride reads the next `free_area`'s list pointers instead.

## One zone

### Invocation

```gdb
kl-buddy list -z DMA
```

### Output

```text
buddy free lists  (zone=DMA)
zone  node  order  nr_free  pages(1<<order)
----  ----  -----  -------  ---------------
DMA   0     5      1        32
DMA   0     6      1        64
DMA   0     7      1        128
DMA   0     9      1        512
DMA   0     10     3        3072
5 non-empty order(s)
```

### Reading it

Same table, filtered.  The DMA zone on this machine has no order-8 block, which the list shows by omission rather than by a zero row.

## By pfn

### Invocation

```gdb
kl-buddy info pfn:1024
```

### Output

```text
Input: pfn:1024
Physical: 0x400000  pfn=0x400
Page: 0xffffcd3b80010000
Zone: DMA  node=0  start_pfn=0x1  end_pfn=0x1000
Status: free  (on a buddy free list)
Order: 10      1024 pages  4096 KiB  4 MiB
Block base: order 10  page 0xffffcd3b80010000  pfn=0x400  phys=0x400000
Position: 0 / 1024 pages  (block head)
Own block head: order 10  (this pfn is aligned to its own block)
```

### Reading it

`Zone` gives the containing span and the node; `Status: free` means the head page is on a buddy free list.  `Order: 10` says the containing block is 1024 pages, and `Position: 0 / 1024 pages (block head)` says this pfn is the block's own head.  `Own block head` answers the different question 'is this page itself the head of a block?', which is what you need before touching `page->private`.

## By virtual address

### Invocation

```gdb
kl-buddy info 0xffff90c340400000
```

### Output

```text
Input: 0xffff90c340400000
Physical: 0x400000  pfn=0x400
Page: 0xffffcd3b80010000
Zone: DMA  node=0  start_pfn=0x1  end_pfn=0x1000
Status: free  (on a buddy free list)
Order: 10      1024 pages  4096 KiB  4 MiB
Block base: order 10  page 0xffffcd3b80010000  pfn=0x400  phys=0x400000
Position: 0 / 1024 pages  (block head)
Own block head: order 10  (this pfn is aligned to its own block)
```

### Reading it

A direct-map address is translated exactly once and gives the same answer as `pfn:1024`.  `virt:`, `phys:`, `page:` and `pfn:` prefixes force one reading; a bare value is tried as vmemmap, then direct map, then physical, and the first plausible one wins.  The vmemmap range sits above `page_offset_base`, so the narrower interpretation must be tried first or a `struct page` pointer would be mistaken for a direct-map address.

## Verbose

### Invocation

```gdb
kl-buddy info pfn:1024 -v
```

### Output

```text
Input: pfn:1024
Physical: 0x400000  pfn=0x400
Page: 0xffffcd3b80010000
Zone: DMA  node=0  start_pfn=0x1  end_pfn=0x1000
Status: free  (on a buddy free list)
Order: 10      1024 pages  4096 KiB  4 MiB
Block base: order 10  page 0xffffcd3b80010000  pfn=0x400  phys=0x400000
Position: 0 / 1024 pages  (block head)
Own block head: order 10  (this pfn is aligned to its own block)
Block span: pfn 0x400-0x7ff  phys 0x400000-0x7fffff
Buddy: pfn=0x0  phys=0x0  status=allocated (or merged into a larger block)
zone: DMA  spanned=4095 pages  present=3998 pages
```

### Reading it

Adds the block's span, its buddy, and the zone's page counts.  `Buddy: pfn=0x0 ... (or merged into a larger block)` is the honest answer for an order-10 block: its buddy is outside the zone, so nothing is there to merge with.  `spanned` counts what the zone covers and `present` what is actually backed by RAM; the gap is reserved holes.

## One free list

### Invocation

```gdb
kl-buddy freelist -z DMA -o 10 -m Movable
```

### Output

```text
buddy free lists  (zone=DMA order=10 mtype=Movable)
zone  node  order  nr_free  pages(1<<order)
----  ----  -----  -------  ---------------
DMA   0     10     3        3072
1 non-empty order(s)
```

### Reading it

A per-migratetype view, which is what `list` cannot give: this walks the actual `free_list[mtype]`.  It needs all three of zone, order and migratetype, because a partial specification would silently pick one.

## Free list contents

### Invocation

```gdb
kl-buddy freelist -z DMA -o 10 -m Movable -v
```

### Output

```text
free_area[order 10]  mtype=Movable  zone=DMA  node=0  nr_free=3  pages=3072
    - #0 pfn=0x400 phys=0x400000 virt=0xffff90c340400000
    - #1 pfn=0x800 phys=0x800000 virt=0xffff90c340800000
    - #2 pfn=0xc00 phys=0xc00000 virt=0xffff90c340c00000
```

### Reading it

Each block's pfn, physical address and direct-map alias.  `nr_free=3` matches the three blocks listed, which is the cross-check that per-order counts and per-type lists agree: the order-10 blocks are all Movable, and the other migratetypes hold none.

## An empty list

### Invocation

```gdb
kl-buddy freelist -z DMA -o 10 -m Unmovable -v
```

### Output

```text
free_area[order 10]  mtype=Unmovable  zone=DMA  node=0  nr_free=3  pages=3072
    (this migratetype list is empty)
    ... (truncated, 0 of 3 block(s))
```

### Reading it

Empty is reported as empty, and the header still shows the per-order total so the relationship between the two commands stays visible: `nr_free=3` counts all migratetypes, while this particular list holds zero.

## Every free page, in list order

### Invocation

```gdb
kl-buddy dump
```

### Output

```text
zone: all order=None mtype=all
    - [0x00] 0xffff90c340120000 [page: 0xffffcd3b80004800, phys: 0x120000]
    - [0x01] 0xffff90c340140000 [page: 0xffffcd3b80005000, phys: 0x140000]
    - [0x02] 0xffff90c340180000 [page: 0xffffcd3b80006000, phys: 0x180000]
    - [0x03] 0xffff90c340200000 [page: 0xffffcd3b80008000, phys: 0x200000]
    - [0x04] 0xffff90c340400000 [page: 0xffffcd3b80010000, phys: 0x400000]
    - [0x05] 0xffff90c340800000 [page: 0xffffcd3b80020000, phys: 0x800000]
    - [0x06] 0xffff90c340c00000 [page: 0xffffcd3b80030000, phys: 0xc00000]
    - [0x07] 0xffff90c34717d000 [page: 0xffffcd3b801c5f40, phys: 0x717d000]
    - [0x08] 0xffff90c3471c6000 [page: 0xffffcd3b801c7180, phys: 0x71c6000]
    - [0x09] 0xffff90c346a5b000 [page: 0xffffcd3b801a96c0, phys: 0x6a5b000]
    - [0x0a] 0xffff90c347184000 [page: 0xffffcd3b801c6100, phys: 0x7184000]
    - [0x0b] 0xffff90c346ac3000 [page: 0xffffcd3b801ab0c0, phys: 0x6ac3000]
    - [0x0c] 0xffff90c346bed000 [page: 0xffffcd3b801afb40, phys: 0x6bed000]
    - [0x0d] 0xffff90c3471a2000 [page: 0xffffcd3b801c6880, phys: 0x71a2000]
    - [0x0e] 0xffff90c346bb3000 [page: 0xffffcd3b801aecc0, phys: 0x6bb3000]
    - [0x0f] 0xffff90c346481000 [page: 0xffffcd3b80192040, phys: 0x6481000]
... (truncated, 258 page(s) total)
... (1 more line(s), 19 total)
```

*The capture has 19 lines; the first 18 are shown.  Run the command to see the rest.*

### Reading it

pwndbg's `buddydump` view, kept as a subcommand because it reports the same `free_area` lists in a different shape.  Each row is `[index] virtual [page: ptr, phys: addr]`.  The index is the position in the list, so consecutive blocks of the same order appear consecutively -- the physical addresses jump around after the first few because the lists interleave low-order blocks from across the zone.

## Restricting the dump

### Invocation

```gdb
kl-buddy dump -z DMA
```

### Output

```text
zone: DMA order=None mtype=all
    - [0x00] 0xffff90c340120000 [page: 0xffffcd3b80004800, phys: 0x120000]
    - [0x01] 0xffff90c340140000 [page: 0xffffcd3b80005000, phys: 0x140000]
    - [0x02] 0xffff90c340180000 [page: 0xffffcd3b80006000, phys: 0x180000]
    - [0x03] 0xffff90c340200000 [page: 0xffffcd3b80008000, phys: 0x200000]
    - [0x04] 0xffff90c340400000 [page: 0xffffcd3b80010000, phys: 0x400000]
    - [0x05] 0xffff90c340800000 [page: 0xffffcd3b80020000, phys: 0x800000]
    - [0x06] 0xffff90c340c00000 [page: 0xffffcd3b80030000, phys: 0xc00000]
7 free page(s)
```

### Reading it

The same filters as `list` (`-z`, `-o`, `-m`, `-n`) apply.  The DMA zone here is small and its blocks are the largest ones, so the first rows are the same order-10 and order-9 blocks `kl-buddy list` counts.

## Searching for an address

### Invocation

```gdb
kl-buddy dump -f 0xffff90c340400000
```

### Output

```text
zone: all order=None mtype=all
    - [0x04] 0xffff90c340400000 [page: 0xffffcd3b80010000, phys: 0x400000]
1 free page(s)
```

### Reading it

`-f/--find` matches against the virtual address, the physical address, or the `struct page`, so any of the three forms identifies the block.  It accepts hex, which matters because the value is an address.  `--MIGRATE_TYPES` is accepted for pwndbg parity and ignored: the count is read from the image's `migratetype_names` symbol, and overriding it could only make the walk wrong.

## Notes

PCP (per-CPU page) lists are not covered yet: a page can be free in a PCP list without appearing here.  `--limit` caps the rows printed for very large zones, and `dump -p/--pcp-only` says so instead of silently showing buddy lists.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
