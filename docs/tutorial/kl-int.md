# `kernlens-int`

Integer view

**Alias:** `kl-int`  
**Category:** bit & integer primitives  
**Synopsis:** `kernlens-int [-h] value [width]`

Shows one value as signed and unsigned at 8/16/32/64 bits, reports which widths it fits in, and dumps its little- and big-endian byte layouts.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
|  | — | integer to inspect |
|  | (optional) | width in bits: 8, 16, 32, or 64 (default 64) |

## Default width

### Invocation

```gdb
kernlens-int 0xff
```

### Output

```text
value: 255  hex=0x00000000000000ff  0000000000000000000000000000000000000000000000000000000011111111
view: unsigned=255  signed=255  in_u=True  in_i=True
range: U64[0..18446744073709551615]  I64[-9223372036854775808..9223372036854775807]
LE bytes: ff 00 00 00 00 00 00 00
BE bytes: 00 00 00 00 00 00 00 ff
```

### Reading it

`view:` gives the unsigned and signed readings plus `in_u`/`in_i`, which say whether the value fits the width as unsigned and as signed.  `range:` prints the full U64 and I64 bounds.  `LE bytes` and `BE bytes` are the same value in memory order and network order, which is the quickest way to spot a byte-order bug: on x86 the little-endian form is what a memory dump shows.

## A specific width

### Invocation

```gdb
kernlens-int 0x1234 16
```

### Output

```text
value: 4660  hex=0x1234  0001001000110100
view: unsigned=4660  signed=4660  in_u=True  in_i=True
range: U16[0..65535]  I16[-32768..32767]
LE bytes: 34 12
BE bytes: 12 34
```

### Reading it

The second argument restricts the analysis to that width, so the signed/unsigned split and the `range:` line describe 16-bit integers rather than 64-bit ones.

## A negative value

### Invocation

```gdb
kernlens-int -1 32
```

### Output

```text
value: -1  hex=0xffffffff  11111111111111111111111111111111
view: unsigned=4294967295  signed=-1  in_u=False  in_i=True
range: U32[0..4294967295]  I32[-2147483648..2147483647]
LE bytes: ff ff ff ff
BE bytes: ff ff ff ff
```

### Reading it

A negative value is interpreted as two's complement and masked to the width, so `-1` at 32 bits is `0xffffffff`, unsigned `4294967295`, signed `-1`.  This is the case where the four views differ most, and the reason the command reports all of them instead of picking one.

## Notes

Only 8, 16, 32 and 64 are accepted as widths; anything else is rejected with the list, because an arbitrary width would make the byte dumps ambiguous.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
