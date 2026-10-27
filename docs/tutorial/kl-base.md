# `kernlens-base`

Active base and slide

**Alias:** `kl-base`  
**Category:** kernel base & KASLR  
**Synopsis:** `kernlens-base [-h]`

Prints the base KernLens is *using right now* and how it decided on it.  Unlike `kl-kbase`, which searches, this only reports: it never changes the slide.

## The active base

### Invocation

```gdb
kernlens-base
```

### Output

```text
kernel base: 0xffffffff91c00000 (runtime)
KASLR offset: +0x10c00000
link _text: 0xffffffff81000000
method: symbol
status: kernel running
```

### Reading it

`kernel base` is the runtime `_text`; `KASLR offset` is the difference from the link-time address.  `method` names the source -- `symbol` means the `_text` symbol resolved, which is the strongest evidence available.  `status` reports whether there is a live inferior at all, since the slide can also be known from a core file.

## Notes

12+ call sites add the slide to a link-time address themselves, which is why `link_text()` keeps returning the link-time value and this command is what reports the runtime one.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
