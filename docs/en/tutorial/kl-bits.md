# `kernlens-bits`

Bit-level view

**Alias:** `kl-bits`  
**Category:** bit & integer primitives  
**Synopsis:** `kernlens-bits [-h] value [bit]`

Shows a 64-bit value in binary and reports the bit statistics that come up in exploit work: population count, leading and trailing zeros, highest and lowest set bit, and whether the value is a power of two.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | value to inspect (0x hex, decimal, bare hex) |
|  | (optional) | bit index 0-63 to test/set/clear/toggle |

## With a bit to test

### Invocation

```gdb
kernlens-bits 0xff 3
```

### Output

```text
value: 0xff  0000000000000000000000000000000000000000000000000000000011111111
scan: popcount=8 leading_zeros=56 trailing_zeros=0 first_set=1 last_set=8
power: is_power_of_2=False  log2_floor=7  log2_ceil=8
bit 3: test=True  set=0xff  clear=0xf7  toggle=0xf7
```

### Reading it

The `value:` row pairs the hex form with a 64-bit binary rendering, so the bit positions can be counted directly.  `scan:` gives `popcount`, the leading and trailing zero counts (1-based `first_set`/`last_set`), and `power:` reports the floor and ceiling log2 -- equal values mean the number IS a power of two.  The final row tests, sets, clears and toggles the given bit, showing each result, so one invocation answers all four questions.

## An address

### Invocation

```gdb
kernlens-bits 0xffffffffa7700000
```

### Output

```text
value: 0xffffffffa7700000  1111111111111111111111111111111110100111011100000000000000000000
scan: popcount=40 leading_zeros=0 trailing_zeros=20 first_set=21 last_set=64
power: is_power_of_2=False  log2_floor=63  log2_ceil=64
```

### Reading it

`trailing_zeros=20` is the page offset of this address (2 MiB aligned), which is the kind of fact that jumps out of the binary rendering and is tedious to compute by hand.  `log2_ceil=64` on a value with the top bit set is correct, not a bug: the next power of two above it does not fit in 64 bits.

## Notes

The value is masked to 64 bits, so a negative input is read as its two's-complement form -- which is what you want when analysing a raw register.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
