#!/usr/bin/env python3
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
"""Text, container, layout, and symbol formatting."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import ClassVar, Final

from .palette import Palette


class Styler:
    """Text, ``k=v``, container, layout, numeric, and symbol formatting.

    All color arguments follow these rules:

    * ``key_color`` / ``value_color`` — the two halves of ``k=v``.
    * ``item_color`` — the payload of a container / layout cell.
    * ``bracket_color`` / ``sep_color`` / ``border_color`` —
      structural characters.

    All alignment goes through ``aligns``; it accepts one token
    (``"l"``, ``"r"``, ``"c"``, ``"left"``, ``"right"``, ``"center"``)
    for every column, or a sequence to align each column separately.
    Any column without an explicit token falls back to ``"left"``.

    All cell padding goes through ``fill`` — a single character,
    default ``" "``.
    """

    __slots__: tuple[str, ...] = (
        "_color_enabled", "_key_color", "_value_color"
    )

    #: ``named`` / ``kv_seq`` style -> (open, close).
    _STYLES: ClassVar[dict[str, tuple[str, str]]] = {
        "[]": ("[", "]"),
        "()": ("(", ")"),
        "{}": ("{", "}"),
        "[)": ("[", ")"),
    }

    def __init__(
        self,
        color_enabled: bool = True,
        key_color: Palette | str = Palette.CYAN,
        value_color: Palette | str = "",
    ) -> None:
        self._color_enabled: bool = color_enabled
        self._key_color: str = str(key_color)
        self._value_color: str = str(value_color)

    # --- master color control ------------------------------------------

    @property
    def color_enabled(self) -> bool:
        return self._color_enabled

    def set_color_enabled(self, enabled: bool) -> None:
        self._color_enabled = enabled

    def enable_color(self) -> None:
        self._color_enabled = True

    def disable_color(self) -> None:
        self._color_enabled = False

    # --- default kv colors ---------------------------------------------

    @property
    def key_color(self) -> str:
        return self._key_color

    @property
    def value_color(self) -> str:
        return self._value_color

    def set_key_color(self, color: Palette | str) -> None:
        self._key_color = str(color)

    def set_value_color(self, color: Palette | str) -> None:
        self._value_color = str(color)

    def set_kv_colors(
        self, key_color: Palette | str, value_color: Palette | str,
    ) -> None:
        self._key_color = str(key_color)
        self._value_color = str(value_color)

    # --- primitives -----------------------------------------------------

    def style(self, text: str, color: Palette | str) -> str:
        if not color or not self._color_enabled:
            return text
        return f"{color}{text}{Palette.RESET}"

    def addr(self, value: int) -> str:
        return self.style(f"{value:#x}", Palette.DIM)

    # --- numeric -------------------------------------------------------

    def hex(
        self, value: int, *,
        digits: int | None = None,
        color: Palette | str = Palette.DIM,
    ) -> str:
        if digits is None:
            return self.style(f"{value:#x}", color)
        mask = (1 << (digits * 4)) - 1
        return self.style(f"0x{value & mask:0{digits}x}", color)

    def hex8(self, value: int, color: Palette | str = Palette.DIM) -> str:
        return self.hex(value, digits=2, color=color)

    def hex16(self, value: int, color: Palette | str = Palette.DIM) -> str:
        return self.hex(value, digits=4, color=color)

    def hex32(self, value: int, color: Palette | str = Palette.DIM) -> str:
        return self.hex(value, digits=8, color=color)

    def hex64(self, value: int, color: Palette | str = Palette.DIM) -> str:
        return self.hex(value, digits=16, color=color)

    def dec(self, value: int, color: Palette | str = "") -> str:
        return self.style(str(value), color)

    def size(self, nbytes: int, color: Palette | str = Palette.DIM) -> str:
        out = str(nbytes)
        for unit, shift in (("T", 40), ("G", 30), ("M", 20), ("K", 10)):
            if nbytes >= 1 << shift:
                whole = nbytes >> shift
                rem = nbytes & ((1 << shift) - 1)
                if rem == 0:
                    out = f"{whole}{unit}"
                else:
                    tenths = round(rem * 10 / (1 << shift))
                    if tenths >= 10:
                        # Carry into the next unit instead of reporting
                        # e.g. "1024K" for (1 MiB - 1).
                        return self.size((whole + 1) << shift, color)
                    out = (
                        f"{whole}{unit}" if tenths == 0
                        else f"{whole}.{tenths}{unit}"
                    )
                break
        return self.style(out, color)

    def pfn(self, phys: int, color: Palette | str = Palette.DIM) -> str:
        return self.style(f"{phys >> 12:#x}", color)

    def percent(
        self, num: int, den: int, color: Palette | str = Palette.DIM,
    ) -> str:
        text = "?" if den == 0 else f"{100.0 * num / den:.1f}%"
        return self.style(text, color)

    def bits(
        self, value: int, *,
        width: int = 8,
        color: Palette | str = Palette.DIM,
    ) -> str:
        if width <= 0:
            return ""
        return self.style(
            f"{value & ((1 << width) - 1):0{width}b}", color,
        )

    # --- align / truncate ----------------------------------------------

    def ljust(
        self, text: object, width: int, *,
        fill: str = " ", color: Palette | str = "",
    ) -> str:
        _check_fill(fill)
        plain = str(text)
        pad = max(0, width - len(plain))
        return self.style(plain + fill * pad, color)

    def rjust(
        self, text: object, width: int, *,
        fill: str = " ", color: Palette | str = "",
    ) -> str:
        _check_fill(fill)
        plain = str(text)
        pad = max(0, width - len(plain))
        return self.style(fill * pad + plain, color)

    def center(
        self, text: object, width: int, *,
        fill: str = " ", color: Palette | str = "",
    ) -> str:
        _check_fill(fill)
        plain = str(text)
        pad = max(0, width - len(plain))
        left = pad // 2
        right = pad - left
        return self.style(fill * left + plain + fill * right, color)

    def pad(
        self, text: object, width: int, *,
        align: str = "left", fill: str = " ",
        color: Palette | str = "",
    ) -> str:
        canon = _ALIGN_ALIASES.get(align)
        if canon is None:
            raise ValueError(
                f"unknown align {align!r}; use l/r/c or left/right/center"
            )
        return self._align(text, width, canon, fill, color)

    def truncate(
        self, text: object, width: int, *,
        ellipsis: str = "...", color: Palette | str = "",
    ) -> str:
        return self.style(_truncate(str(text), width, ellipsis), color)

    # --- k=v family -----------------------------------------------------

    def kv(
        self, label: str, value: str, *,
        key_color: Palette | str | None = None,
        value_color: Palette | str | None = None,
    ) -> str:
        kc = self._key_color if key_color is None else str(key_color)
        vc = self._value_color if value_color is None else str(value_color)
        return f"{self.style(label, kc)}={self.style(value, vc)}"

    def kv_int(
        self, label: str, value: int, *,
        key_color: Palette | str | None = None,
        value_color: Palette | str | None = None,
    ) -> str:
        return self.kv(
            label, str(value),
            key_color=key_color, value_color=value_color,
        )

    def kv_hex(
        self, label: str, value: int, *,
        key_color: Palette | str | None = None,
        value_color: Palette | str | None = None,
    ) -> str:
        vc = Palette.DIM if value_color is None else value_color
        return self.kv(
            label, f"{value:#x}",
            key_color=key_color, value_color=vc,
        )

    def kv_bool(
        self, label: str, value: bool, *,
        key_color: Palette | str | None = None,
        true_color: Palette | str | None = None,
        false_color: Palette | str | None = None,
    ) -> str:
        tc = Palette.GREEN if true_color is None else true_color
        fc = Palette.RED if false_color is None else false_color
        return self.kv(
            label, "true" if value else "false",
            key_color=key_color, value_color=tc if value else fc,
        )

    # --- containers -----------------------------------------------------

    def seq(
        self, items: Iterable[object], *,
        open: str = "[", close: str = "]", sep: str = ", ",
        item_color: Palette | str | None = None,
        bracket_color: Palette | str = Palette.DIM,
    ) -> str:
        ic = self._value_color if item_color is None else str(item_color)
        bc = str(bracket_color)
        body = sep.join(self.style(str(it), ic) for it in items)
        return self.style(open, bc) + body + self.style(close, bc)

    def list(
        self, items: Iterable[object], *,
        item_color: Palette | str | None = None,
        bracket_color: Palette | str = Palette.DIM,
    ) -> str:
        return self.seq(
            items, open="[", close="]",
            item_color=item_color, bracket_color=bracket_color,
        )

    def tuple(
        self, items: Iterable[object], *,
        item_color: Palette | str | None = None,
        bracket_color: Palette | str = Palette.DIM,
    ) -> str:
        return self.seq(
            items, open="(", close=")",
            item_color=item_color, bracket_color=bracket_color,
        )

    def set(
        self, items: Iterable[object], *,
        item_color: Palette | str | None = None,
        bracket_color: Palette | str = Palette.DIM,
    ) -> str:
        return self.seq(
            items, open="{", close="}",
            item_color=item_color, bracket_color=bracket_color,
        )

    def dict(
        self, pairs: dict[object, object] | Iterable[tuple[object, object]], *,
        assign: str = ": ",
        key_color: Palette | str | None = None,
        value_color: Palette | str | None = None,
        bracket_color: Palette | str = Palette.DIM,
    ) -> str:
        kc = self._key_color if key_color is None else str(key_color)
        vc = self._value_color if value_color is None else str(value_color)
        bc = str(bracket_color)
        items = pairs.items() if isinstance(pairs, dict) else pairs
        body = ", ".join(
            f"{self.style(str(key), kc)}{assign}"
            f"{self.style(str(value), vc)}"
            for key, value in items
        )
        return self.style("{", bc) + body + self.style("}", bc)

    def pairs(
        self, pairs: dict[object, object] | Iterable[tuple[object, object]], *,
        assign: str = "=",
        key_color: Palette | str | None = None,
        value_color: Palette | str | None = None,
        bracket_color: Palette | str = Palette.DIM,
    ) -> str:
        return self.dict(
            pairs, assign=assign,
            key_color=key_color, value_color=value_color,
            bracket_color=bracket_color,
        )

    def range(
        self, start: int, end: int, *,
        open: str = "[", close: str = ")",
        hex_fmt: bool = True,
        item_color: Palette | str | None = None,
        bracket_color: Palette | str = Palette.DIM,
    ) -> str:
        fmt = (lambda n: f"{n:#x}") if hex_fmt else (lambda n: str(n))
        return self.seq(
            [fmt(start), fmt(end)], open=open, close=close,
            item_color=item_color, bracket_color=bracket_color,
        )

    def named(
        self, name: str, items: Iterable[object], *,
        style: str = "[]",
        name_color: Palette | str | None = None,
        item_color: Palette | str | None = None,
        bracket_color: Palette | str = Palette.DIM,
    ) -> str:
        op, cl = _lookup_style(style)
        nc = self._key_color if name_color is None else str(name_color)
        body = self.seq(
            items, open=op, close=cl,
            item_color=item_color, bracket_color=bracket_color,
        )
        return self.style(name, nc) + body

    def kv_seq(
        self, label: str,
        items: Iterable[object] | dict[object, object], *,
        style: str = "[]",
        key_color: Palette | str | None = None,
        item_color: Palette | str | None = None,
        value_color: Palette | str | None = None,
        bracket_color: Palette | str = Palette.DIM,
        assign: str = ": ",
    ) -> str:
        op, cl = _lookup_style(style)
        kc = self._key_color if key_color is None else str(key_color)
        if style == "{}":
            body = self.dict(
                items,  # type: ignore[arg-type]
                assign=assign,
                key_color=item_color, value_color=value_color,
                bracket_color=bracket_color,
            )
        else:
            body = self.seq(
                items,  # type: ignore[arg-type]
                open=op, close=cl,
                item_color=value_color, bracket_color=bracket_color,
            )
        return self.style(label, kc) + "=" + body

    # --- layout ---------------------------------------------------------

    def table(
        self,
        headers: Sequence[object],
        rows: Iterable[Sequence[object]], *,
        header_color: Palette | str = Palette.CYAN,
        item_color: Palette | str | None = None,
        bracket_color: Palette | str = Palette.DIM,
        col_sep: str = "  ",
        rule: str | None = "-",
        fill: str = " ",
        aligns: str | Sequence[str] | None = None,
        max_col_width: int | None = None,
    ) -> str:
        """Format *headers* and *rows* as an aligned text table.

        ``rule`` is the character used for the dashed separator under
        the header; ``None`` disables it.  ``aligns`` / ``fill`` /
        ``max_col_width`` behave as documented at the class level.
        """
        _check_fill(fill)
        prepared, widths = _prepare_table(headers, rows, max_col_width)
        if not widths:
            return ""
        col_aligns = _normalize_aligns(aligns, len(widths))
        ic = self._value_color if item_color is None else str(item_color)
        ncols = len(widths)

        def _render(cells: Sequence[str], color: Palette | str) -> str:
            return col_sep.join(
                self._align(
                    cells[i] if i < len(cells) else "",
                    widths[i], col_aligns[i], fill, color,
                )
                for i in range(ncols)
            ).rstrip()

        lines = [_render(prepared[0], header_color)]
        if rule is not None:
            if len(rule) != 1:
                raise ValueError(
                    f"rule must be 1 character or None, got {rule!r}"
                )
            rule_text = col_sep.join(
                rule * widths[i] for i in range(ncols)
            ).rstrip()
            lines.append(self.style(rule_text, bracket_color))
        for row in prepared[1:]:
            lines.append(_render(row, ic))
        return "\n".join(lines)

    def box(
        self,
        headers: Sequence[object],
        rows: Iterable[Sequence[object]], *,
        header_color: Palette | str = Palette.CYAN,
        item_color: Palette | str | None = None,
        border_color: Palette | str = Palette.DIM,
        chars: str = "┌┐└┘─│",
        joints: str = "┬┴┼├┤",
        fill: str = " ",
        aligns: str | Sequence[str] | None = None,
        max_col_width: int | None = None,
    ) -> str:
        """Format *headers* and *rows* as a bordered table.

        ``chars`` is six characters: ``top-left, top-right,
        bottom-left, bottom-right, horizontal, vertical``.  ``joints``
        is five characters used where borders meet:
        ``top, bottom, middle-cross, middle-left, middle-right``.
        """
        _check_fill(fill)
        if len(chars) != 6:
            raise ValueError(
                f"chars must be 6 characters, got {len(chars)!r}"
            )
        if len(joints) != 5:
            raise ValueError(
                f"joints must be 5 characters, got {len(joints)!r}"
            )
        tl, tr, bl, br, hz, vt = chars
        top_joint, bottom_joint, mid_joint, mid_left, mid_right = joints
        prepared, widths = _prepare_table(headers, rows, max_col_width)
        if not widths:
            return ""
        col_aligns = _normalize_aligns(aligns, len(widths))
        ic = self._value_color if item_color is None else str(item_color)
        bc = str(border_color)
        ncols = len(widths)
        vt_s = self.style(vt, bc)
        hz_s = self.style(hz, bc)

        def _rule(
            left: str, junction: str, right: str,
        ) -> str:
            segments = [
                hz_s * (widths[i] + 2) for i in range(ncols)
            ]
            body = self.style(junction, bc).join(segments)
            return self.style(left, bc) + body + self.style(right, bc)

        def _render(cells: Sequence[str], color: Palette | str) -> str:
            rendered: list[str] = []
            for i in range(ncols):
                text = cells[i] if i < len(cells) else ""
                rendered.append(
                    " " + self._align(
                        text, widths[i], col_aligns[i], fill, color,
                    ) + " "
                )
            return vt_s + vt_s.join(rendered) + vt_s

        lines = [
            _rule(tl, top_joint, tr),
            _render(prepared[0], header_color),
            _rule(mid_left, mid_joint, mid_right),
        ]
        for row in prepared[1:]:
            lines.append(_render(row, ic))
        lines.append(_rule(bl, bottom_joint, br))
        return "\n".join(lines)

    def chain(
        self, items: Iterable[object], *,
        sep: str = " -> ",
        item_color: Palette | str | None = None,
        sep_color: Palette | str = Palette.DIM,
    ) -> str:
        ic = self._value_color if item_color is None else str(item_color)
        styled_sep = self.style(sep, sep_color)
        return styled_sep.join(self.style(str(it), ic) for it in items)

    def cols(
        self, items: Iterable[object], n: int, *,
        item_color: Palette | str | None = None,
        col_sep: str = "  ",
        pad: int = 2,
        fill: str = " ",
        aligns: str | Sequence[str] | None = None,
        max_col_width: int | None = None,
    ) -> str:
        """Lay *items* out in *n* columns.

        ``aligns`` may be a single token (applies to every column) or a
        sequence with one token per column.  ``pad`` is extra spacing
        added after each cell, on top of the natural column width.
        """
        if n <= 0:
            raise ValueError(f"n must be > 0, got {n}")
        if pad < 0:
            raise ValueError(f"pad must be >= 0, got {pad}")
        _check_fill(fill)
        if max_col_width is not None and max_col_width <= 0:
            raise ValueError(
                f"max_col_width must be > 0, got {max_col_width}"
            )
        texts = [str(it) for it in items]
        if max_col_width is not None:
            texts = [_truncate(text, max_col_width) for text in texts]
        if not texts:
            return ""
        ic = self._value_color if item_color is None else str(item_color)
        cell_w = max(len(text) for text in texts) + pad
        per_col_align = _normalize_aligns(aligns, n)
        lines: list[str] = []
        for start in range(0, len(texts), n):
            chunk = texts[start:start + n]
            rendered = [
                self._align(text, cell_w, per_col_align[i], fill, ic)
                for i, text in enumerate(chunk)
            ]
            lines.append(col_sep.join(rendered).rstrip())
        return "\n".join(lines)

    def block(
        self, title: str, lines: Iterable[str], *,
        width: int = 0,
        border_color: Palette | str = Palette.DIM,
        title_color: Palette | str = Palette.CYAN,
        chars: str = "┌┐└┘─",
        vertical: str = "│",
    ) -> str:
        """Wrap *lines* in a bordered block with *title* in the top edge.

        ``width`` is the minimum interior width; ``0`` sizes the block
        to its contents.  ``chars`` is five characters:
        ``top-left, top-right, bottom-left, bottom-right, horizontal``.
        """
        if len(chars) != 5:
            raise ValueError(
                f"chars must be 5 characters, got {len(chars)!r}"
            )
        if len(vertical) != 1:
            raise ValueError(
                f"vertical must be exactly 1 character, got {vertical!r}"
            )
        tl, tr, bl, br, hz = chars
        body = [str(line) for line in lines]
        natural = max(
            [len(title) + 2] + [len(line) + 2 for line in body]
        ) if body else len(title) + 2
        inner = max(width, natural)
        tl_s = self.style(tl, border_color)
        tr_s = self.style(tr, border_color)
        bl_s = self.style(bl, border_color)
        br_s = self.style(br, border_color)
        hz_s = self.style(hz, border_color)
        vt_s = self.style(vertical, border_color)
        title_s = self.style(f" {title} ", title_color)
        top_pad = max(0, inner - len(title) - 2)
        out = [tl_s + title_s + hz_s * top_pad + tr_s]
        for line in body:
            pad = max(0, inner - len(line) - 1)
            out.append(vt_s + " " + line + " " * pad + vt_s)
        out.append(bl_s + hz_s * inner + br_s)
        return "\n".join(out)

    # --- text transforms -------------------------------------------------

    def highlight(
        self, text: str, pattern: str, *,
        color: Palette | str = Palette.BRIGHT_YELLOW_BOLD,
    ) -> str:
        if not pattern:
            return text
        return self.style(pattern, color).join(text.split(pattern))

    def indent(self, text: str, *, level: int = 1, width: int = 2) -> str:
        if level <= 0 or width <= 0:
            return text
        pad = " " * (level * width)
        return "\n".join(pad + line for line in text.split("\n"))

    # --- groups ---------------------------------------------------------

    def fields(
        self, pairs: Iterable[tuple[str, object]], *,
        sep: str = "  ",
        key_color: Palette | str | None = None,
        value_color: Palette | str | None = None,
    ) -> str:
        return sep.join(
            self.kv(
                key, str(value),
                key_color=key_color, value_color=value_color,
            )
            for key, value in pairs
        )

    def kv_group(
        self, pairs: Iterable[tuple[str, object]], *,
        assign: str = " = ",
        key_color: Palette | str | None = None,
        value_color: Palette | str | None = None,
        assign_color: Palette | str = Palette.DIM,
    ) -> str:
        """Format *pairs* as multiple ``k=v`` lines with the ``=`` aligned.

        ``assign`` is the full text between the (right-padded) key and
        the value: ``" = "`` for ``k = v``, ``": "`` for ``k: v``, etc.
        ``assign_color`` colors that connector.
        """
        pairs = [(str(key), str(value)) for key, value in pairs]
        if not pairs:
            return ""
        width = max(len(key) for key, _ in pairs)
        kc = self._key_color if key_color is None else str(key_color)
        vc = self._value_color if value_color is None else str(value_color)
        connector = self.style(assign, assign_color)
        return "\n".join(
            self.style(key.rjust(width), kc)
            + connector + self.style(value, vc)
            for key, value in pairs
        )

    # --- status symbols --------------------------------------------------

    def tick(self, color: Palette | str = Palette.GREEN) -> str:
        return self.style("✓", color)

    def cross(self, color: Palette | str = Palette.RED) -> str:
        return self.style("✗", color)

    def bullet(self, color: Palette | str = Palette.DIM) -> str:
        return self.style("•", color)

    def arrow(self, color: Palette | str = Palette.DIM) -> str:
        return self.style("→", color)

    # --- progress --------------------------------------------------------

    def bar(
        self, value: int, max_value: int, *,
        width: int = 20,
        filled_char: str = "█", empty_char: str = "░",
        filled_color: Palette | str = Palette.BRIGHT_GREEN,
        empty_color: Palette | str = Palette.DIM,
        show_ratio: bool = True,
        bracket_color: Palette | str = Palette.DIM,
    ) -> str:
        if width <= 0:
            return ""
        if max_value <= 0:
            filled = 0
        else:
            filled = round(
                width * max(0, min(value, max_value)) / max_value
            )
        body = (
            self.style(filled_char * filled, filled_color)
            + self.style(empty_char * (width - filled), empty_color)
        )
        out = (
            self.style("[", bracket_color)
            + body
            + self.style("]", bracket_color)
        )
        if show_ratio:
            out += f" {value}/{max_value}"
        return out

    # --- internals ------------------------------------------------------

    def _align(
        self, text: object, width: int, align: str,
        fill: str, color: Palette | str,
    ) -> str:
        if align == "left":
            return self.ljust(text, width, fill=fill, color=color)
        if align == "right":
            return self.rjust(text, width, fill=fill, color=color)
        return self.center(text, width, fill=fill, color=color)


# =========================================================================


# Module-level helpers
# =========================================================================


#: Alignment alias -> canonical name.  Shared by :class:`Styler` and the
#: module helpers below.
_ALIGN_ALIASES: Final[dict[str, str]] = {
    "l": "left", "r": "right", "c": "center",
    "left": "left", "right": "right", "center": "center",
}


def _check_fill(fill: str) -> None:
    """Raise ``ValueError`` unless *fill* is exactly one character."""
    if len(fill) != 1:
        raise ValueError(
            f"fill must be exactly 1 character, got {fill!r}"
        )


def _truncate(text: str, width: int, ellipsis: str = "...") -> str:
    """Truncate *text* to *width* characters (``"..."`` marker)."""
    if width < 0:
        raise ValueError(f"width must be >= 0, got {width}")
    if len(text) <= width:
        return text
    if len(ellipsis) >= width:
        return text[:width]
    return text[:width - len(ellipsis)] + ellipsis


def _lookup_style(style: str) -> tuple[str, str]:
    """Return the (open, close) pair for a named style."""
    pair = Styler._STYLES.get(style)
    if pair is None:
        raise ValueError(
            f"unknown style {style!r}; use one of {sorted(Styler._STYLES)}"
        )
    return pair


def _normalize_aligns(
    aligns: str | Sequence[str] | None, ncols: int,
) -> list[str]:
    """Expand *aligns* to a canonical list of length *ncols*."""
    if aligns is None:
        return ["left"] * ncols
    if isinstance(aligns, str):
        canon = _ALIGN_ALIASES.get(aligns)
        if canon is None:
            raise ValueError(
                f"unknown align {aligns!r}; use l/r/c or left/right/center"
            )
        return [canon] * ncols
    out: list[str] = []
    for align in aligns:
        canon = _ALIGN_ALIASES.get(align)
        if canon is None:
            raise ValueError(
                f"unknown align {align!r}; use l/r/c or left/right/center"
            )
        out.append(canon)
    if len(out) < ncols:
        out.extend(["left"] * (ncols - len(out)))
    return out[:ncols]


def _prepare_table(
    headers: Sequence[object],
    rows: Iterable[Sequence[object]],
    max_col_width: int | None,
) -> tuple[list[list[str]], list[int]]:
    """Truncate, stringify, and size rows for ``table`` / ``box``."""
    if max_col_width is not None and max_col_width <= 0:
        raise ValueError(
            f"max_col_width must be > 0, got {max_col_width}"
        )
    head = [str(header) for header in headers]
    body = [[str(cell) for cell in row] for row in rows]
    if max_col_width is not None:
        head = [_truncate(header, max_col_width) for header in head]
        body = [
            [_truncate(cell, max_col_width) for cell in row] for row in body
        ]
    ncols = len(head)
    if ncols == 0:
        return [], []
    widths = [len(header) for header in head]
    for row in body:
        for i in range(ncols):
            cell = row[i] if i < len(row) else ""
            widths[i] = max(widths[i], len(cell))
    return [head, *body], widths

__all__ = ["Styler"]
