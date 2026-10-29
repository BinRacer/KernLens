"""Render the README demo from the tutorial capture.

The front page needs something to watch, and the honest source for it is
the same capture that generates ``docs/tutorial/``.  This script turns
two recorded invocations into:

* ``docs/assets/demo.svg`` -- an animated terminal that GitHub renders
  inline (no binary, no font dependency, and the text stays selectable);
* ``docs/assets/demo.cast`` -- an asciinema v2 replay for anyone who
  wants to step through it.

Both are replays, not live recordings, and the SVG says so.  The output
is verbatim from the capture; only the prompt and the timing are added.

Usage::

    python tools/gen_demo.py
    python tools/gen_demo.py --check
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CAPTURE = ROOT / "tools" / "tutorial_capture.json"
DEFAULT_SVG = ROOT / "docs" / "assets" / "demo.svg"
DEFAULT_CAST = ROOT / "docs" / "assets" / "demo.cast"

#: ANSI SGR sequences.  Removed before the capture is laid out: the SVG is
#: XML, where a raw ``\x1b`` is not a legal character, and the ``.cast``
#: records plain text too.  Neither artifact can express colour, so the
#: sequences have to go rather than be escaped.
_SGR = re.compile(r"\x1b\[[0-9;]*m")

#: Canvas geometry, in SVG user units.
WIDTH = 1000
HEIGHT = 640
PAD_X = 30
TOP = 92
LINE_HEIGHT = 22
FONT_SIZE = 13

#: Rows visible without animation, so a still frame (a screenshot, a
#: client with animations disabled) is not an empty terminal.
STATIC_ROWS = 3

#: Seconds a line waits before appearing, and the hold at the end.
STEP = 0.10
COMMAND_HOLD = 0.55
BETWEEN = 0.80
FINAL_HOLD = 2.5


def _pick(cases: list[dict[str, Any]]) -> list[tuple[str, str]]:
    """Return ``(display command, output)`` for the two demo commands."""
    walk = next(
        (
            case for case in cases
            if case["invocation"].startswith("kernlens-walk ")
            and "huge leaf" in case["output"]
        ),
        None,
    )
    slab = next(
        (
            case for case in cases
            if case["invocation"].startswith("kernlens-slab details ")
        ),
        None,
    )
    if walk is None or slab is None:
        raise SystemExit(
            "the capture no longer contains a huge-page walk and a slab "
            "details case; update tools/gen_demo.py"
        )
    picked = [walk, slab]
    return [
        (case["invocation"].replace("kernlens-", "kl-", 1), _SGR.sub("", case["output"]))
        for case in picked
    ]


def build_lines(capture: Path) -> list[tuple[str, str]]:
    """Flatten the selected cases into ``(kind, text)`` rows."""
    data = json.loads(capture.read_text(encoding="utf-8"))
    rows: list[tuple[str, str]] = []
    for index, (command, output) in enumerate(_pick(data["cases"])):
        if index:
            rows.append(("blank", ""))
        rows.append(("cmd", command))
        for line in output.rstrip("\n").splitlines():
            rows.append(("out", line))
    return rows


def _timing(rows: list[tuple[str, str]]) -> tuple[list[float], float]:
    """Return the start time of every row and the total cycle length."""
    starts: list[float] = []
    now = 0.6
    for kind, _ in rows:
        starts.append(now)
        if kind == "cmd":
            now += COMMAND_HOLD
        elif kind == "blank":
            now += BETWEEN
        else:
            now += STEP
    return starts, now + FINAL_HOLD


def _colour(text: str) -> str:
    """Pick a class for an output line, so the interesting bits stand out."""
    if "huge leaf" in text or text.startswith("Leaf:"):
        return "hl"
    if "decoded=" in text or "freeptr:" in text or "freelist:" in text:
        return "accent"
    if text.startswith("Flags:"):
        return "flags"
    return "out"


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_svg(rows: list[tuple[str, str]]) -> str:
    """Render the animated terminal."""
    starts, total = _timing(rows)
    lines: list[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" xml:space="preserve" '
        f'width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" '
        'role="img" aria-labelledby="demo-title demo-desc">',
        "  <title id=\"demo-title\">KernLens reading a live kernel</title>",
        "  <desc id=\"demo-desc\">A replay of two commands from the "
        "6.1.134 capture: kl-walk decodes a 2 MiB page-table mapping, and "
        "kl-slab details decodes a SLUB freelist pointer.</desc>",
        "  <style>",
        "    text { font-family: ui-monospace, SFMono-Regular, Menlo, "
        "Consolas, 'DejaVu Sans Mono', monospace; "
        f"font-size: {FONT_SIZE}px; white-space: pre; }}",
        "    .cmd { fill: #e6edf3; }",
        "    .out { fill: #c9d1d9; }",
        "    .hl { fill: #e3b341; }",
        "    .accent { fill: #79c0ff; }",
        "    .flags { fill: #a5d6ff; }",
        "    .prompt { fill: #7ee787; }",
        "    .meta { fill: #8b949e; font-size: 11px; }",
        "    .cursor { fill: #e6edf3; animation: blink 1.1s steps(1) infinite; }",
        "    @keyframes blink { 50% { opacity: 0; } }",
        "    @media (prefers-reduced-motion: reduce) {",
        "      text { animation: none !important; opacity: 1 !important; }",
        "    }",
    ]
    for index, start in enumerate(starts):
        before = max(start / total * 100.0, 0.01)
        after = min((start + 0.22) / total * 100.0, 99.99)
        lines.append(
            f"    @keyframes k{index} {{ 0% {{ opacity: 0; }} "
            f"{before:.3f}% {{ opacity: 0; }} "
            f"{after:.3f}% {{ opacity: 1; }} }}"
        )
    lines.append("  </style>")
    lines.append(f'  <rect width="{WIDTH}" height="{HEIGHT}" rx="12" '
                 'fill="#0d1117"/>')
    lines.append(f'  <rect width="{WIDTH}" height="42" rx="12" '
                 'fill="#161b22"/>')
    lines.append(f'  <rect y="30" width="{WIDTH}" height="12" fill="#161b22"/>')
    for offset, colour in ((24, "#ff5f56"), (46, "#ffbd2e"), (68, "#27c93f")):
        lines.append(
            f'  <circle cx="{offset}" cy="21" r="6" fill="{colour}"/>'
        )
    lines.append(
        f'  <text x="{WIDTH // 2}" y="26" text-anchor="middle" '
        'class="meta">gdb — KernLens</text>'
    )
    for index, (kind, text) in enumerate(rows):
        y = TOP + index * LINE_HEIGHT
        if kind == "blank":
            continue
        style = (
            ""
            if index < STATIC_ROWS
            else f' style="animation: k{index} {total:.2f}s linear infinite both"'
        )
        if kind == "cmd":
            lines.append(
                f'  <text x="{PAD_X}" y="{y}"{style}>'
                '<tspan class="prompt">(gdb) </tspan>'
                f'<tspan class="cmd">{_escape(text)}</tspan></text>'
            )
        else:
            lines.append(
                f'  <text x="{PAD_X}" y="{y}" class="{_colour(text)}"{style}>'
                f"{_escape(text)}</text>"
            )
    cursor_y = TOP + len(rows) * LINE_HEIGHT
    lines.append(
        f'  <rect x="{PAD_X}" y="{cursor_y - 11}" width="8" height="14" '
        'class="cursor"/>'
    )
    lines.append(
        f'  <text x="{PAD_X}" y="{HEIGHT - 18}" class="meta">'
        "replay of the 6.1.134 capture — docs/tutorial/</text>"
    )
    lines.append("</svg>")
    return "\n".join(lines) + "\n"


def render_cast(rows: list[tuple[str, str]]) -> str:
    """Render an asciinema v2 cast of the same replay."""
    header = {
        "version": 2,
        "width": 110,
        "height": 32,
        "timestamp": 0,
        "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"},
    }
    events: list[tuple[float, str]] = []
    now = 0.6
    for kind, text in rows:
        if kind == "blank":
            now += BETWEEN
            events.append((now, "\r\n"))
        elif kind == "cmd":
            events.append((now, f"(gdb) {text}\r\n"))
            now += COMMAND_HOLD
        else:
            events.append((now, f"{text}\r\n"))
            now += STEP
    lines = [json.dumps(header)]
    for stamp, text in events:
        lines.append(json.dumps([round(stamp, 3), "o", text]))
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write both assets, or compare them with ``--check``."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", type=Path, default=DEFAULT_CAPTURE)
    parser.add_argument("--svg", type=Path, default=DEFAULT_SVG)
    parser.add_argument("--cast", type=Path, default=DEFAULT_CAST)
    parser.add_argument(
        "--check", action="store_true",
        help="fail when the assets differ instead of writing them",
    )
    args = parser.parse_args(argv)

    rows = build_lines(args.capture)
    rendered = {args.svg: render_svg(rows), args.cast: render_cast(rows)}
    if args.check:
        for path, text in rendered.items():
            try:
                current = path.read_text(encoding="utf-8")
            except OSError as exc:
                print(f"{path}: {exc}", file=sys.stderr)
                return 1
            if current != text:
                print(
                    f"{path} does not match {args.capture}; "
                    "run tools/gen_demo.py",
                    file=sys.stderr,
                )
                return 1
        print("demo assets match the capture")
        return 0

    for path, text in rendered.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
