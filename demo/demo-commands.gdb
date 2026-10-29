# The scripted tour.  Every command here works on any x86_64 kernel with
# DWARF or BTF; none of the addresses are baked in.
kl-status
kl-kbase
kl-kconfig RANDOMIZE_BASE
kl-slab info kmalloc-1k
python
addr = reader.kvar_addr("init_task")
if not addr:
    raise gdb.GdbError("init_task is not resolvable on this kernel")
gdb.execute("kl-sym 0x%x" % addr)
gdb.execute("kl-pagewalk 0x%x" % addr)
end
