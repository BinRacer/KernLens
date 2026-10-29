# Attach to the demo VM.  The commands live in demo-commands.gdb; this
# file is only the setup, so `docker run ... kl-slab info dentry` can
# reuse it.
set pagination off
set confirm off
file /opt/demo/vmlinux
target remote :1234
source /opt/kernlens/gdbinit.py
kl-color off
