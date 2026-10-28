"""Host-side installation: where the startup file is, and its block.

Three commands need to agree on the same three facts: ``kernlens path``
prints the startup file, ``kernlens install`` writes a block that sources
it, and ``kernlens doctor`` looks for that block.  Keeping the marker and
the path here means the installer cannot write something the doctor does
not recognise, and the shell installer can be checked against the same
constants.

The block is deliberately small and idempotent: rewriting it is how an
upgrade moves the ``source`` line when the checkout moves, without
appending a second one.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

#: Markers around the block.  ``install.sh`` writes the same two lines;
#: ``tests/unit/test_install.py`` compares them so the two installers
#: cannot drift apart.
MARKER_START = "# >>> kernlens >>>"
MARKER_END = "# <<< kernlens <<<"


def startup_path() -> Path:
    """The startup file shipped with this copy of KernLens.

    Works for a checkout (``src/kernlens/gdbinit.py``) and for a wheel
    (``site-packages/kernlens/gdbinit.py``) because the file is package
    data in both.
    """
    return Path(__file__).resolve().parent / "gdbinit.py"


def block(startup: Path | None = None) -> str:
    """The marked block that sources *startup* (default: this copy).

    The path is deliberately unquoted.  GDB's ``source`` takes the rest
    of the line as the filename and does *not* strip quotes, so
    ``source "/path"`` looks for a file whose name starts with a quote.
    """
    target = startup if startup is not None else startup_path()
    return f'{MARKER_START}\nsource {target}\n{MARKER_END}\n'


def _strip(text: str) -> str:
    """Remove every marked block, including a half-written one."""
    kept: list[str] = []
    inside = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == MARKER_START:
            inside = True
            continue
        if stripped == MARKER_END:
            inside = False
            continue
        if not inside:
            kept.append(line)
    return "\n".join(kept)


def add_block(text: str, startup: Path | None = None) -> str:
    """Return *text* with exactly one block, at the end."""
    base = _strip(text).rstrip("\n")
    addition = block(startup).rstrip("\n")
    if not base:
        return addition + "\n"
    return f"{base}\n\n{addition}\n"


def remove_block(text: str) -> str:
    """Return *text* without the block, preserving the other lines."""
    base = _strip(text).rstrip("\n")
    return base + "\n" if base else ""


def _write(path: Path, text: str, *, dry_run: bool) -> None:
    """Replace *path* atomically, keeping its mode when it already exists."""
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        dir=str(path.parent), prefix=path.name + ".",
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        else:
            os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    except BaseException:
        os.unlink(temporary)
        raise


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def install(
    gdbinit: Path,
    *,
    startup: Path | None = None,
    dry_run: bool = False,
) -> list[str]:
    """Add or refresh the block in *gdbinit*; return what happened."""
    target = startup if startup is not None else startup_path()
    if not target.is_file():
        raise FileNotFoundError(f"startup file not found: {target}")
    before = _read(gdbinit)
    after = add_block(before, target)
    messages = [
        f"{'would write' if dry_run else 'wrote'} {gdbinit} "
        f"(source {target})"
    ]
    if before == after:
        messages = [f"{gdbinit} already sources {target}"]
    _write(gdbinit, after, dry_run=dry_run)
    return messages


def uninstall(gdbinit: Path, *, dry_run: bool = False) -> list[str]:
    """Remove the block from *gdbinit*; leave the rest untouched."""
    before = _read(gdbinit)
    after = remove_block(before)
    if before == after:
        return [f"{gdbinit} has no KernLens block"]
    _write(gdbinit, after, dry_run=dry_run)
    verb = "would remove" if dry_run else "removed"
    return [f"{verb} the KernLens block from {gdbinit}"]
