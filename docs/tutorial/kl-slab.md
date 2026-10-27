# `kernlens-slab`

SLUB cache inspection

**Alias:** `kl-slab`, `kl-slabs`  
**Category:** memory & symbols  
**Synopsis:** `kernlens-slab [-h] [-v] [-c CPU] [-n NODE] [-p] [-a] [-i] [-r]
                     [--reclaim] [--ctor]
                     [command ...]`

Inspects the SLUB allocator at three levels: the caches the kernel has, one cache's shape and per-CPU state, and one object's slab.  The subcommand form (`list`/`info`/`contains`/`details`) is pwndbg's; a bare address still works for compatibility.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | command | list [filter] \| info <name>... \| contains <addr>... \| details <addr>... \| <addr> |
| `-v`, `--verbose` | — | display more detailed information (with `info`) |
| `-c`, `--cpu` | — | CPU to display |
| `-n`, `--node` | — | _(no help text)_ |
| `-p`, `--partial` | — | displays partial lists |
| `-a`, `--active` | — | displays the active list |
| `-i`, `--inuse` | — | also show the object stride including metadata (with `info`) |
| `-r`, `--random` | — | also show the freelist randomisation key (with `info`) |
| `--reclaim` | — | also show whether SLAB_RECLAIM_ACCOUNT is set (with `info`) |
| `--ctor` | — | also show the cache's constructor symbol (with `info`) |

## Every cache

### Invocation

```gdb
kernlens-slab list
```

### Output

```text
Name                         # Objects  Size  Obj Size  order
---------------------------  ---------  ----  --------  -----
ext4_groupinfo_4k            22         184   184       0
fsverity_info                16         256   256       0
AF_VSOCK                     25         1280  1232      3
MPTCPv6                      15         2112  2064      3
ip6-frags                    22         184   184       0
PINGv6                       26         1216  1200      3
RAWv6                        26         1216  1200      3
UDPv6                        24         1344  1344      3
tw_sock_TCPv6                30         272   264       1
request_sock_TCPv6           26         312   304       1
TCPv6                        13         2432  2400      3
kcopyd_job                   10         3240  3240      3
dm_uevent                    11         2888  2888      3
scsi_sense_cache             32         128   96        0
bio-136                      21         192   136       0
mqueue_inode_cache           17         960   952       2
fuse_request                 26         152   152       0
fuse_inode                   19         832   824       2
... (154 more line(s), 174 total)
```

*The capture has 174 lines; the first 20 are shown.  Run the command to see the rest.*

### Reading it

One row per cache: name, object count, pages per slab (`Size`), object size, and the order the slab is allocated at.  `Size` and `Obj Size` differ when the cache rounds up for alignment or adds metadata -- that gap is the per-object overhead an amplification attack cares about.

## Filtering caches

### Invocation

```gdb
kernlens-slab list kmalloc
```

### Output

```text
Name             # Objects  Size  Obj Size  order
---------------  ---------  ----  --------  -----
dma-kmalloc-8k   4          8192  8192      3
dma-kmalloc-4k   8          4096  4096      3
dma-kmalloc-2k   16         2048  2048      3
dma-kmalloc-1k   16         1024  1024      2
dma-kmalloc-512  16         512   512       1
dma-kmalloc-256  16         256   256       0
dma-kmalloc-192  21         192   192       0
dma-kmalloc-128  32         128   128       0
dma-kmalloc-96   42         96    96        0
dma-kmalloc-64   64         64    64        0
dma-kmalloc-32   128        32    32        0
dma-kmalloc-16   256        16    16        0
dma-kmalloc-8    512        8     8         0
kmalloc-rcl-8k   4          8192  8192      3
kmalloc-rcl-4k   8          4096  4096      3
kmalloc-rcl-2k   16         2048  2048      3
kmalloc-rcl-1k   16         1024  1024      2
kmalloc-rcl-512  16         512   512       1
... (36 more line(s), 56 total)
```

*The capture has 56 lines; the first 20 are shown.  Run the command to see the rest.*

### Reading it

A filter is a substring match, so `kmalloc` catches all three families: `dma-kmalloc-*` (DMA-capable), `kmalloc-rcl-*` (reclaimable), and plain `kmalloc-*`.  The trailing `of N cache(s) shown` line is what tells you the list was filtered rather than short.

## One cache in full

### Invocation

```gdb
kernlens-slab info dentry
```

### Output

```text
Slab Cache @ 0xffff975284e1bc00
    Name: dentry
    Flags: SLAB_RECLAIM_ACCOUNT | SLAB_PANIC
    Offset: 0x60
    Slab size: 0x1000
    Size (including metadata): 0xc0
    Align: 0x8
    Object Size: 0xc0
    Usercopy region offset: 56
    Usercopy region size: 32
    oo_order: 0  oo_objects=21
    cpu 0: active=0xffffee5d001b15c0 freelist=0xffff975286c57840
    cpu 1: active=0xffffee5d001b1740 freelist=0xffff975286c5de40
    cpu 2: active=0xffffee5d001b06c0 freelist=0xffff975286c1b9c0
    cpu 3: active=0xffffee5d001b2940 freelist=0xffff975286ca5540
    node 0: nr_partial=0x8/ min_partial=0x5
    head: 0xffffee5d001b1500 freelist=0xffff975286c54a80
```

### Reading it

`Offset` is the freelist pointer's offset inside the object; `Size (including metadata)` is the stride the allocator actually uses.  `Slab size` is the page-order size of one slab (`PAGE_SIZE << oo_order`).  The usercopy window is the range the hardened usercopy checks allow: `dentry` has a real window (56/32), while a plain kmalloc cache stores the whole object and reports `usersize == object_size`.  The per-CPU rows are the live `kmem_cache_cpu` state, and the node row is the partial list's length against `min_partial`.

## Cache internals

### Invocation

```gdb
kernlens-slab info dentry -i -r --reclaim --ctor
```

### Output

```text
Slab Cache @ 0xffff975284e1bc00
    Name: dentry
    Flags: SLAB_RECLAIM_ACCOUNT | SLAB_PANIC
    Offset: 0x60
    Slab size: 0x1000
    Size (including metadata): 0xc0
    Align: 0x8
    Object Size: 0xc0
    Usercopy region offset: 56
    Usercopy region size: 32
    oo_order: 0  oo_objects=21
    inuse: 192
    random: 0xae939aafdb096690
    reclaim: set  (SLAB_RECLAIM_ACCOUNT)
    ctor: none
    cpu 0: active=0xffffee5d001b15c0 freelist=0xffff975286c57840
    cpu 1: active=0xffffee5d001b1740 freelist=0xffff975286c5de40
    cpu 2: active=0xffffee5d001b06c0 freelist=0xffff975286c1b9c0
    cpu 3: active=0xffffee5d001b2940 freelist=0xffff975286ca5540
    node 0: nr_partial=0x8/ min_partial=0x5
    head: 0xffffee5d001b1500 freelist=0xffff975286c54a80
```

### Reading it

Four opt-in rows, none of which changes the default output: `inuse` is the object stride including metadata, `random` is the freelist randomisation key (`CONFIG_SLAB_FREELIST_RANDOM`), `reclaim` says whether `SLAB_RECLAIM_ACCOUNT` is set, and `ctor` names the constructor (or `none`).  These are KernLens-only additions: the shared `info` block must stay byte-identical to pwndbg's.

## Partial slabs only

### Invocation

```gdb
kernlens-slab info dentry -p
```

### Output

```text
Slab Cache @ 0xffff975284e1bc00
    Name: dentry
    Flags: SLAB_RECLAIM_ACCOUNT | SLAB_PANIC
    Offset: 0x60
    Slab size: 0x1000
    Size (including metadata): 0xc0
    Align: 0x8
    Object Size: 0xc0
    Usercopy region offset: 56
    Usercopy region size: 32
    oo_order: 0  oo_objects=21
    node 0: nr_partial=0x8/ min_partial=0x5
    head: 0xffffee5d001b1500 freelist=0xffff975286c54a80
```

### Reading it

Restricts the per-CPU rows and shows the node's partial list head instead.  `nr_partial=0x17/ min_partial=0x5` is the current length against the watermark the kernel keeps before it starts freeing empty slabs; `min_partial` lives in `struct kmem_cache` (not the node), which is why it is reported as the same value for every node.  It is `max(MIN_PARTIAL, ilog2(object_size)/2)`.

## Active slabs only

### Invocation

```gdb
kernlens-slab info dentry -a
```

### Output

```text
Slab Cache @ 0xffff975284e1bc00
    Name: dentry
    Flags: SLAB_RECLAIM_ACCOUNT | SLAB_PANIC
    Offset: 0x60
    Slab size: 0x1000
    Size (including metadata): 0xc0
    Align: 0x8
    Object Size: 0xc0
    Usercopy region offset: 56
    Usercopy region size: 32
    oo_order: 0  oo_objects=21
    cpu 0: active=0xffffee5d001b15c0 freelist=0xffff975286c57840
    cpu 1: active=0xffffee5d001b1740 freelist=0xffff975286c5de40
    cpu 2: active=0xffffee5d001b06c0 freelist=0xffff975286c1b9c0
    cpu 3: active=0xffffee5d001b2940 freelist=0xffff975286ca5540
```

### Reading it

Just the per-CPU active slab and freelist.  `active` is a `struct page` pointer; `freelist` is the next free object in that slab.  Both can legitimately be empty on an idle CPU.

## Which cache owns an object

### Invocation

```gdb
kernlens-slab contains 0xffff975286c57840
```

### Output

```text
0xffff975286c57840 @ dentry  size=192 object_size=192
```

### Reading it

Given an object address, reports the cache it belongs to and the cache's object and slab sizes.  This is the fastest way to identify an unexplained heap pointer.  pwndbg's form is one line; `-v` adds the slab head, the object index within the slab, the slab's state, its counters, and the neighbouring objects.

## One slab in detail

### Invocation

```gdb
kernlens-slab details 0xffff975286c57840
```

### Output

```text
Slab @ 0xffff975286c57840 page: 0xffffee5d001b15c0
    cache: 0xffff975284e1bc00 dentry  page_bytes=64
    freeptr: offset=96 random=0xae939aafdb096690
    freelist: 0xffff975286c57c00
    objects: 21  inuse=19  frozen=1
    state: frozen
    slab_size: 0x1000
    next: 0x3110c87b0f5be96f decoded=0xffff975286c57000
    cpu 0: active=0xffffee5d001b15c0 freelist=0xffff975286c57840
    cpu 1: active=0xffffee5d001b1740 freelist=0xffff975286c5de40
    cpu 2: active=0xffffee5d001b06c0 freelist=0xffff975286c1b9c0
    cpu 3: active=0xffffee5d001b2940 freelist=0xffff975286ca5540
    node 0: partial=8 head=0xffffee5d001b1500 in_partial=False
```

### Reading it

`Slab @` is the `struct page` for the slab (the argument is an object inside it).  `freeptr: offset=96` is where the freelist pointer is stored inside each object, together with the randomisation key.  `objects: 21 inuse=21 frozen=1` decodes the packed counters word (`inuse:16 | objects:15 | frozen:1`); `state: frozen` is derived from `frozen`, not from list membership, because a frozen (per-CPU) slab is on no list at all.  `in_partial=False` agrees: this slab is CPU-owned, not on the node's partial list.

## Notes

`kl-slab` merges what used to be two commands (`kernlens-slab` and `kernlens-slabs`), so `kl-slabs` still resolves as an alias.  The legacy `-d/--detail` flag and the bare-address form remain for scripts written against the older interface.  `kl-slab <addr>` is `contains`, not `details` -- the object first, the slab on request.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
