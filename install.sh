#!/bin/sh
#
# Copyright (c) 2026 BinRacer <native.lab@outlook.com>
#
# This work is licensed under the terms of the GNU GPL, version 3 or later.
#
# See the LICENSE file in the top-level directory for details.
#
# Install KernLens from a checkout with one command:
#
#     curl -fsSL https://raw.githubusercontent.com/BinRacer/KernLens/main/install.sh | sh
#
# The installer clones the repository under
# ${XDG_DATA_HOME:-~/.local/share}/kernlens, adds one marked block to
# ~/.gdbinit, and writes a small ``kernlens`` wrapper into ~/.local/bin.
# It is idempotent: running it again updates the checkout and rewrites
# the block instead of appending a second one.
#
#     sh install.sh --uninstall     remove the block and the wrapper
#     sh install.sh --dry-run       print what would change
#
set -eu

repo=${KERNLENS_REPO_URL:-https://github.com/BinRacer/KernLens.git}
ref=${KERNLENS_REF:-main}
dir=${KERNLENS_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/kernlens}
prefix=${KERNLENS_PREFIX:-$HOME/.local}
gdbinit=${KERNLENS_GDBINIT:-$HOME/.gdbinit}
dry_run=0
uninstall=0

marker_start='# >>> kernlens >>>'
marker_end='# <<< kernlens <<<'

usage() {
    cat <<'EOF'
Install KernLens from a checkout.

Usage: install.sh [options]

  --repo URL        git remote to clone (default: the GitHub repository)
  --ref REF         branch, tag, or commit to check out (default: main)
  --dir DIR         checkout location (default: ~/.local/share/kernlens)
  --prefix DIR      where the kernlens wrapper goes (default: ~/.local)
  --gdbinit FILE    GDB startup file to edit (default: ~/.gdbinit)
  --dry-run         print the actions without changing anything
  --uninstall       remove the source line and the wrapper
  -h, --help        show this help

Environment: KERNLENS_REPO_URL, KERNLENS_REF, KERNLENS_DIR,
KERNLENS_PREFIX, KERNLENS_GDBINIT.
EOF
}

say() {
    printf '%s\n' "$*"
}

fail() {
    printf 'install.sh: %s\n' "$*" >&2
    exit 1
}

need() {
    command -v "$1" >/dev/null 2>&1 || fail "$1 is required but not on PATH"
}

while [ $# -gt 0 ]; do
    case $1 in
        --repo) repo=$2; shift 2 ;;
        --ref) ref=$2; shift 2 ;;
        --dir) dir=$2; shift 2 ;;
        --prefix) prefix=$2; shift 2 ;;
        --gdbinit) gdbinit=$2; shift 2 ;;
        --dry-run) dry_run=1; shift ;;
        --uninstall) uninstall=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) fail "unknown option: $1 (try --help)" ;;
    esac
done

case $dir in
    /*) ;;
    *) dir=$(pwd)/$dir ;;
esac
case $prefix in
    /*) ;;
    *) prefix=$(pwd)/$prefix ;;
esac
case $gdbinit in
    /*) ;;
    *) gdbinit=$(pwd)/$gdbinit ;;
esac

wrapper=$prefix/bin/kernlens

# ---------------------------------------------------------------------------
# Uninstall
# ---------------------------------------------------------------------------

if [ "$uninstall" -eq 1 ]; then
    if [ "$dry_run" -eq 1 ]; then
        say "would remove the KernLens block from $gdbinit"
        say "would remove $wrapper"
        say "would leave the checkout at $dir"
        exit 0
    fi
    if [ -f "$gdbinit" ]; then
        tmp=$(mktemp "${gdbinit}.XXXXXX")
        awk -v start="$marker_start" -v end="$marker_end" '
            $0 == start { skip = 1; next }
            $0 == end   { skip = 0; next }
            skip != 1   { print }
        ' "$gdbinit" > "$tmp"
        mv "$tmp" "$gdbinit"
        say "removed the KernLens block from $gdbinit"
    else
        say "$gdbinit does not exist; nothing to remove"
    fi
    if [ -f "$wrapper" ] && grep -q "KernLens install.sh" "$wrapper"; then
        rm -f "$wrapper"
        say "removed $wrapper"
    fi
    say "checkout left at $dir (remove it manually if you want it gone)"
    exit 0
fi

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

need git
need python3

if [ -e "$dir" ] && [ ! -d "$dir/.git" ]; then
    fail "$dir exists and is not a git checkout; pass --dir elsewhere"
fi

if [ -d "$dir/.git" ]; then
    if [ "$dry_run" -eq 1 ]; then
        say "would update $dir to $ref"
    else
        git -C "$dir" fetch --depth 1 origin "$ref" >/dev/null 2>&1 \
            || fail "cannot fetch $ref from $repo"
        git -C "$dir" checkout -q --detach FETCH_HEAD \
            || fail "cannot check out $ref in $dir"
        say "updated $dir to $ref"
    fi
else
    if [ "$dry_run" -eq 1 ]; then
        say "would clone $repo ($ref) into $dir"
    else
        mkdir -p "$(dirname "$dir")"
        if ! git clone --depth 1 --branch "$ref" "$repo" "$dir" \
                >/dev/null 2>&1; then
            rm -rf "$dir"
            git clone --depth 1 "$repo" "$dir" >/dev/null 2>&1 \
                || fail "cannot clone $repo"
            git -C "$dir" fetch --depth 1 origin "$ref" >/dev/null 2>&1 \
                || fail "cannot fetch $ref from $repo"
            git -C "$dir" checkout -q --detach FETCH_HEAD \
                || fail "cannot check out $ref in $dir"
        fi
        say "cloned $repo ($ref) into $dir"
    fi
fi

startup=$dir/gdbinit.py
if [ "$dry_run" -eq 0 ]; then
    [ -f "$startup" ] || fail "$dir does not contain gdbinit.py"
fi

if [ "$dry_run" -eq 1 ]; then
    say "would add '$marker_start / source $startup / $marker_end' to $gdbinit"
    say "would write $wrapper"
else
    mkdir -p "$(dirname "$gdbinit")"
    tmp=$(mktemp "${gdbinit}.XXXXXX")
    if [ -f "$gdbinit" ]; then
        awk -v start="$marker_start" -v end="$marker_end" '
            $0 == start { skip = 1; next }
            $0 == end   { skip = 0; next }
            skip != 1   { print }
        ' "$gdbinit" > "$tmp"
    fi
    {
        printf '\n%s\n' "$marker_start"
        printf 'source %s\n' "$startup"
        printf '%s\n' "$marker_end"
    } >> "$tmp"
    mv "$tmp" "$gdbinit"
    say "added the KernLens block to $gdbinit"

    mkdir -p "$prefix/bin"
    {
        printf '#!/bin/sh\n'
        printf '# Generated by KernLens install.sh\n'
        printf 'PYTHONPATH="%s/src${PYTHONPATH:+:$PYTHONPATH}"\n' "$dir"
        printf 'export PYTHONPATH\n'
        printf 'exec "${KERNLENS_PYTHON:-python3}" -m kernlens.cli "$@"\n'
    } > "$wrapper"
    chmod +x "$wrapper"
    say "wrote $wrapper"
fi

say ""
say "KernLens is installed."
say "Next: gdb -q -ex 'file vmlinux' -ex 'target remote :1234' -ex kl-base"
say "Check: $wrapper doctor"
case ":$PATH:" in
    *":$prefix/bin:"*) ;;
    *) say "Note: add $prefix/bin to PATH to run 'kernlens' from anywhere." ;;
esac
