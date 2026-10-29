#!/bin/sh
# Boot the demo kernel under QEMU, wait for userspace, attach GDB.
#
# The kernel runs without `-S`, so it boots normally; GDB attaches to the
# running VM through the gdbstub and interrupts it.  The console goes to
# a file rather than stdio, because GDB needs the terminal for its own
# output and the two would interleave.
set -eu

DEMO=/opt/demo
CONSOLE=/tmp/kernlens-demo-console.log

rm -f "$CONSOLE"
# `-serial file:` buffers in QEMU and stays empty until exit; redirecting
# stdio is what makes the boot marker visible while the VM runs.
qemu-system-x86_64 \
    -M microvm \
    -cpu qemu64 \
    -m 512M \
    -smp 4 \
    -kernel "$DEMO/bzImage" \
    -initrd "$DEMO/initramfs.cpio.gz" \
    -append "console=ttyS0 loglevel=4 panic=-1" \
    -display none \
    -monitor none \
    -serial stdio \
    -no-reboot \
    -s >"$CONSOLE" 2>&1 &
qemu=$!
trap 'kill "$qemu" 2>/dev/null || true' EXIT INT TERM

# 240 * 0.25s = 60s.  TCG boot is a few seconds; the timeout is for a
# machine that is merely slow, not for one that is broken.
i=0
while [ "$i" -lt 240 ]; do
    if grep -q 'kernlens-demo: init running' "$CONSOLE" 2>/dev/null; then
        break
    fi
    if ! kill -0 "$qemu" 2>/dev/null; then
        echo "qemu exited before the guest booted:" >&2
        cat "$CONSOLE" >&2 || true
        exit 1
    fi
    sleep 0.25
    i=$((i + 1))
done

if ! grep -q 'kernlens-demo: init running' "$CONSOLE" 2>/dev/null; then
    echo "the guest did not boot within 60s:" >&2
    tail -40 "$CONSOLE" >&2 || true
    exit 1
fi

# `demo.gdb` is setup only.  With arguments, run the one command the
# caller asked for; without, run the scripted tour.  Neither uses `exec`:
# the shell has to survive GDB so the trap can stop QEMU.
if [ "$#" -gt 0 ]; then
    gdb -q -batch -nx -x "$DEMO/demo.gdb" -ex "$*"
else
    gdb -q -batch -nx -x "$DEMO/demo.gdb" -x "$DEMO/demo-commands.gdb"
fi
