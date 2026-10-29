# `kernlens-status`

Session status

**Alias:** `kl-status`  
**Category:** overview  
**Synopsis:** `kernlens-status [-h] [--doctor]`

One-screen check that KernLens is attached to a kernel it can read, and what it currently believes about that kernel.  Run it first when a command behaves unexpectedly.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
| `--doctor` | — | also print what GDB loaded: the object file, DWARF/BTF availability, and whether a target is attached |

## The status block

### Invocation

```gdb
kernlens-status
```

### Output

```text
KernLens 0.3.0 — color: off
    KASLR slide: +0x26600000
    _text: link=0xffffffff81000000 runtime=0xffffffffa7600000
    page_offset: 0xffff8c3640000000
    vmemmap: 0xffffd66f00000000
    topology: nr_cpus=4 nr_nodes=1

kl-help lists every command, kl-help kl-<command> explains one
```

### Reading it

`KASLR slide` is the value the **reader** is using, derived from the live IDT if nothing has set it yet -- it is not a cached attribute that stays zero.  `_text` shows the link-time and runtime addresses side by side, which is the quickest way to spot a slide that is wrong by a constant.  `page_offset` and `vmemmap` are the two bases every address translation depends on; both are kernel variables chosen at boot.

## Notes

Everything here is read through the facade, so it works on a stripped kernel with no debug info: the slide is recovered from the IDT, and the version from the banner.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
