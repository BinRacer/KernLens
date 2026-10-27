# `kernlens-read-field`

Read a struct field

**Alias:** `kl-read-field`  
**Category:** memory & symbols  
**Synopsis:** `kernlens-read-field [-h] address type path`

Reads one field out of a struct at a given address, following a dotted path into nested members.  This is the command to use when you can compute an address but not read the struct in one go.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | struct instance |
|  | — | C type name (e.g. 'struct slab') |
|  | — | field path (e.g. freelist or node[0]) |

## A nested path

### Invocation

```gdb
kernlens-read-field 0xffffd62040010000 'struct page' _refcount.counter
```

### Output

```text
field: ((struct page *)0xffffd62040010000)->_refcount.counter
value: 0x0
```

### Reading it

The `field:` row echoes the exact expression that was evaluated, so the path can be checked against the debug info.  `_refcount` is a nested `{ counter }` struct on this kernel, which is why the path has two components: asking for `_refcount` alone would try to print a struct as an integer.

## Notes

The type name is quoted so the shell (and GDB's own argument lexer) keeps `struct page` together.  A field that cannot be read prints `<unreadable>` rather than `0`, because a zero refcount and an unreadable one mean very different things.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
