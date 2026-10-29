# `kl-kdmabuf`

dma-buf objects

**Canonical:** `kernlens-kdmabuf`  
**Category:** memory & symbols  
**Synopsis:** `kl-kdmabuf [-h]`

Walks the dma-buf export list and prints each buffer with its attachment chain.  dma-bufs are a common cross-device use-after-free surface, so enumerating them is usually the first step.

## The list

### Invocation

```gdb
kl-kdmabuf
```

### Output

```text
no dma-bufs found (needs the db_list/debugfs_list symbol and at least one exported buffer)
```

### Reading it

One row per exported buffer: size, the exporter's name, and the attachment count.  When there are none, the message names the two things it needs -- the list symbol and at least one exported buffer -- so an empty result is not confused with a broken symbol lookup.

## Notes

The entry point is `db_list` (or `debugfs_list` on older kernels); which one exists is probed, not assumed.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
