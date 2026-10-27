# `kernlens-kdmesg`

Kernel log

**Alias:** `kl-kdmesg`  
**Category:** kernel metadata  
**Synopsis:** `kernlens-kdmesg [-h] [-T]`

Prints the ring buffer (`dmesg`) by walking the `prb`/`printk_info` records directly, which works even when `dmesg` is restricted for unprivileged users.

## Options

| Option | Argument | Meaning |
| --- | --- | --- |
| `-T`, `--ctime` | — | print human-readable (wall-clock) timestamps |

## The ring buffer

### Invocation

```gdb
kernlens-kdmesg
```

### Output

```text
[    0.000000] Linux version 6.1.134 (bogon@bogon) (gcc (Ubuntu 14.2.0-4ubuntu2~24.04.1) 14.2.0, GNU ld (GNU Binutils for Ubuntu) 2.42) #1 SMP PREEMPT_DYNAMIC Sat Oct 17 22:41:31 CST 2026
[    0.000000] Command line: root=/dev/sda console=ttyS0 rw loglevel=3 oops=panic panic=1 net.ifnames=0 biosdevname=0 no5lvl kaslr pti=on
[    0.000000] KERNEL supported cpus:
[    0.000000]   Intel GenuineIntel
[    0.000000]   AMD AuthenticAMD
[    0.000000]   Hygon HygonGenuine
[    0.000000]   Centaur CentaurHauls
[    0.000000]   zhaoxin   Shanghai  
[    0.000000] BIOS-provided physical RAM map:
[    0.000000] BIOS-e820: [mem 0x0000000000000000-0x000000000009fbff] usable
[    0.000000] BIOS-e820: [mem 0x000000000009fc00-0x000000000009ffff] reserved
[    0.000000] BIOS-e820: [mem 0x00000000000f0000-0x00000000000fffff] reserved
[    0.000000] BIOS-e820: [mem 0x0000000000100000-0x0000000007fdffff] usable
[    0.000000] BIOS-e820: [mem 0x0000000007fe0000-0x0000000007ffffff] reserved
[    0.000000] BIOS-e820: [mem 0x00000000fffc0000-0x00000000ffffffff] reserved
[    0.000000] BIOS-e820: [mem 0x000000fd00000000-0x000000ffffffffff] reserved
[    0.000000] NX (Execute Disable) protection: active
[    0.000000] SMBIOS 3.0.0 present.
[    0.000000] DMI: QEMU Ubuntu 24.04 PC v2 (i440FX + PIIX, arch_caps fix, 1996), BIOS 1.16.3-debian-1.16.3-2 04/01/2014
[    0.000000] tsc: Fast TSC calibration using PIT
[    0.000000] tsc: Detected 3686.263 MHz processor
[    0.005603] e820: update [mem 0x00000000-0x00000fff] usable ==> reserved
[    0.005778] e820: remove [mem 0x000a0000-0x000fffff] usable
[    0.005982] last_pfn = 0x7fe0 max_arch_pfn = 0x400000000
... (445 more line(s), 469 total)
```

*The capture has 469 lines; the first 24 are shown.  Run the command to see the rest.*

### Reading it

Each line is `[seconds.microseconds] message`, matching the usual `dmesg` format.  The records are read from the ring buffer's descriptor array, so the order is the kernel's own, not a re-sort.  The buffer starts with the version banner and the command line, which is a convenient cross-check against `kl-kversion` and `kl-kcmdline`.

## Wall-clock timestamps

### Invocation

```gdb
kernlens-kdmesg --ctime
```

### Output

```text
[Thu Jan  1 10:03:58 1970] Linux version 6.1.134 (bogon@bogon) (gcc (Ubuntu 14.2.0-4ubuntu2~24.04.1) 14.2.0, GNU ld (GNU Binutils for Ubuntu) 2.42) #1 SMP PREEMPT_DYNAMIC Sat Oct 17 22:41:31 CST 2026
[Thu Jan  1 10:03:58 1970] Command line: root=/dev/sda console=ttyS0 rw loglevel=3 oops=panic panic=1 net.ifnames=0 biosdevname=0 no5lvl kaslr pti=on
[Thu Jan  1 10:03:58 1970] KERNEL supported cpus:
[Thu Jan  1 10:03:58 1970]   Intel GenuineIntel
[Thu Jan  1 10:03:58 1970]   AMD AuthenticAMD
[Thu Jan  1 10:03:58 1970]   Hygon HygonGenuine
[Thu Jan  1 10:03:58 1970]   Centaur CentaurHauls
[Thu Jan  1 10:03:58 1970]   zhaoxin   Shanghai  
[Thu Jan  1 10:03:58 1970] BIOS-provided physical RAM map:
[Thu Jan  1 10:03:58 1970] BIOS-e820: [mem 0x0000000000000000-0x000000000009fbff] usable
[Thu Jan  1 10:03:58 1970] BIOS-e820: [mem 0x000000000009fc00-0x000000000009ffff] reserved
[Thu Jan  1 10:03:58 1970] BIOS-e820: [mem 0x00000000000f0000-0x00000000000fffff] reserved
[Thu Jan  1 10:03:58 1970] BIOS-e820: [mem 0x0000000000100000-0x0000000007fdffff] usable
[Thu Jan  1 10:03:58 1970] BIOS-e820: [mem 0x0000000007fe0000-0x0000000007ffffff] reserved
[Thu Jan  1 10:03:58 1970] BIOS-e820: [mem 0x00000000fffc0000-0x00000000ffffffff] reserved
[Thu Jan  1 10:03:58 1970] BIOS-e820: [mem 0x000000fd00000000-0x000000ffffffffff] reserved
[Thu Jan  1 10:03:58 1970] NX (Execute Disable) protection: active
[Thu Jan  1 10:03:58 1970] SMBIOS 3.0.0 present.
[Thu Jan  1 10:03:58 1970] DMI: QEMU Ubuntu 24.04 PC v2 (i440FX + PIIX, arch_caps fix, 1996), BIOS 1.16.3-debian-1.16.3-2 04/01/2014
[Thu Jan  1 10:03:58 1970] tsc: Fast TSC calibration using PIT
[Thu Jan  1 10:03:58 1970] tsc: Detected 3686.263 MHz processor
[Thu Jan  1 10:03:58 1970] e820: update [mem 0x00000000-0x00000fff] usable ==> reserved
[Thu Jan  1 10:03:58 1970] e820: remove [mem 0x000a0000-0x000fffff] usable
[Thu Jan  1 10:03:58 1970] last_pfn = 0x7fe0 max_arch_pfn = 0x400000000
[Thu Jan  1 10:03:58 1970] x86/PAT: Configuration [0-7]: WB  WC  UC- UC  WB  WP  UC- WT  
[Thu Jan  1 10:03:58 1970] found SMP MP-table at [mem 0x000f5480-0x000f548f]
[Thu Jan  1 10:03:58 1970] Kernel/User page tables isolation: force enabled on command line.
[Thu Jan  1 10:03:58 1970] Using GB pages for direct mapping
[Thu Jan  1 10:03:58 1970] ACPI: Early table checksum verification disabled
[Thu Jan  1 10:03:58 1970] ACPI: RSDP 0x00000000000F5290 000014 (v00 BOCHS )
[Thu Jan  1 10:03:58 1970] ACPI: RSDT 0x0000000007FE1D69 000034 (v01 BOCHS  BXPC     00000001 BXPC 00000001)
[Thu Jan  1 10:03:58 1970] ACPI: FACP 0x0000000007FE1C05 000074 (v01 BOCHS  BXPC     00000001 BXPC 00000001)
[Thu Jan  1 10:03:58 1970] ACPI: DSDT 0x0000000007FE0040 001BC5 (v01 BOCHS  BXPC     00000001 BXPC 00000001)
[Thu Jan  1 10:03:58 1970] ACPI: FACS 0x0000000007FE0000 000040
[Thu Jan  1 10:03:58 1970] ACPI: APIC 0x0000000007FE1C79 000090 (v03 BOCHS  BXPC     00000001 BXPC 00000001)
[Thu Jan  1 10:03:58 1970] ACPI: HPET 0x0000000007FE1D09 000038 (v01 BOCHS  BXPC     00000001 BXPC 00000001)
[Thu Jan  1 10:03:58 1970] ACPI: WAET 0x0000000007FE1D41 000028 (v01 BOCHS  BXPC     00000001 BXPC 00000001)
[Thu Jan  1 10:03:58 1970] ACPI: Reserving FACP table memory at [mem 0x7fe1c05-0x7fe1c78]
[Thu Jan  1 10:03:58 1970] ACPI: Reserving DSDT table memory at [mem 0x7fe0040-0x7fe1c04]
[Thu Jan  1 10:03:58 1970] ACPI: Reserving FACS table memory at [mem 0x7fe0000-0x7fe003f]
[Thu Jan  1 10:03:58 1970] ACPI: Reserving APIC table memory at [mem 0x7fe1c79-0x7fe1d08]
[Thu Jan  1 10:03:58 1970] ACPI: Reserving HPET table memory at [mem 0x7fe1d09-0x7fe1d40]
[Thu Jan  1 10:03:58 1970] ACPI: Reserving WAET table memory at [mem 0x7fe1d41-0x7fe1d68]
[Thu Jan  1 10:03:58 1970] No NUMA configuration found
[Thu Jan  1 10:03:58 1970] Faking a node at [mem 0x0000000000000000-0x0000000007fdffff]
[Thu Jan  1 10:03:58 1970] NODE_DATA(0) allocated [mem 0x07fb5000-0x07fdffff]
[Thu Jan  1 10:03:58 1970] Zone ranges:
[Thu Jan  1 10:03:58 1970]   DMA      [mem 0x0000000000001000-0x0000000000ffffff]
[Thu Jan  1 10:03:58 1970]   DMA32    [mem 0x0000000001000000-0x0000000007fdffff]
[Thu Jan  1 10:03:58 1970]   Normal   empty
[Thu Jan  1 10:03:58 1970]   Device   empty
[Thu Jan  1 10:03:58 1970] Movable zone start for each node
[Thu Jan  1 10:03:58 1970] Early memory node ranges
[Thu Jan  1 10:03:58 1970]   node   0: [mem 0x0000000000001000-0x000000000009efff]
[Thu Jan  1 10:03:58 1970]   node   0: [mem 0x0000000000100000-0x0000000007fdffff]
[Thu Jan  1 10:03:58 1970] Initmem setup node 0 [mem 0x0000000000001000-0x0000000007fdffff]
[Thu Jan  1 10:03:58 1970] On node 0, zone DMA: 1 pages in unavailable ranges
[Thu Jan  1 10:03:58 1970] On node 0, zone DMA: 97 pages in unavailable ranges
[Thu Jan  1 10:03:58 1970] On node 0, zone DMA32: 32 pages in unavailable ranges
[Thu Jan  1 10:03:58 1970] ACPI: PM-Timer IO Port: 0x608
[Thu Jan  1 10:03:58 1970] ACPI: LAPIC_NMI (acpi_id[0xff] dfl dfl lint[0x1])
[Thu Jan  1 10:03:58 1970] IOAPIC[0]: apic_id 0, version 32, address 0xfec00000, GSI 0-23
[Thu Jan  1 10:03:58 1970] ACPI: INT_SRC_OVR (bus 0 bus_irq 0 global_irq 2 dfl dfl)
[Thu Jan  1 10:03:58 1970] ACPI: INT_SRC_OVR (bus 0 bus_irq 5 global_irq 5 high level)
[Thu Jan  1 10:03:58 1970] ACPI: INT_SRC_OVR (bus 0 bus_irq 9 global_irq 9 high level)
[Thu Jan  1 10:03:58 1970] ACPI: INT_SRC_OVR (bus 0 bus_irq 10 global_irq 10 high level)
[Thu Jan  1 10:03:58 1970] ACPI: INT_SRC_OVR (bus 0 bus_irq 11 global_irq 11 high level)
[Thu Jan  1 10:03:58 1970] ACPI: Using ACPI (MADT) for SMP configuration information
[Thu Jan  1 10:03:58 1970] ACPI: HPET id: 0x8086a201 base: 0xfed00000
[Thu Jan  1 10:03:58 1970] smpboot: Allowing 4 CPUs, 0 hotplug CPUs
[Thu Jan  1 10:03:58 1970] PM: hibernation: Registered nosave memory: [mem 0x00000000-0x00000fff]
[Thu Jan  1 10:03:58 1970] PM: hibernation: Registered nosave memory: [mem 0x0009f000-0x0009ffff]
[Thu Jan  1 10:03:58 1970] PM: hibernation: Registered nosave memory: [mem 0x000a0000-0x000effff]
[Thu Jan  1 10:03:58 1970] PM: hibernation: Registered nosave memory: [mem 0x000f0000-0x000fffff]
[Thu Jan  1 10:03:58 1970] [mem 0x08000000-0xfffbffff] available for PCI devices
[Thu Jan  1 10:03:58 1970] Booting paravirtualized kernel on bare hardware
[Thu Jan  1 10:03:58 1970] clocksource: refined-jiffies: mask: 0xffffffff max_cycles: 0xffffffff, max_idle_ns: 7645519600211568 ns
[Thu Jan  1 10:03:58 1970] setup_percpu: NR_CPUS:8192 nr_cpumask_bits:4 nr_cpu_ids:4 nr_node_ids:1
[Thu Jan  1 10:03:58 1970] percpu: Embedded 62 pages/cpu s217088 r8192 d28672 u524288
[Thu Jan  1 10:03:58 1970] pcpu-alloc: s217088 r8192 d28672 u524288 alloc=1*2097152
[Thu Jan  1 10:03:58 1970] pcpu-alloc: [0] 0 1 2 3 
[Thu Jan  1 10:03:58 1970] Fallback order for Node 0: 0 
[Thu Jan  1 10:03:58 1970] Built 1 zonelists, mobility grouping on.  Total pages: 31968
[Thu Jan  1 10:03:58 1970] Policy zone: DMA32
[Thu Jan  1 10:03:58 1970] Kernel command line: root=/dev/sda console=ttyS0 rw loglevel=3 oops=panic panic=1 net.ifnames=0 biosdevname=0 no5lvl kaslr pti=on
[Thu Jan  1 10:03:58 1970] Unknown kernel command line parameters "no5lvl kaslr biosdevname=0 pti=on", will be passed to user space.
[Thu Jan  1 10:03:58 1970] random: crng init done
[Thu Jan  1 10:03:58 1970] Dentry cache hash table entries: 16384 (order: 5, 131072 bytes, linear)
[Thu Jan  1 10:03:58 1970] Inode-cache hash table entries: 8192 (order: 4, 65536 bytes, linear)
[Thu Jan  1 10:03:58 1970] mem auto-init: stack:all(zero), heap alloc:on, heap free:off
[Thu Jan  1 10:03:58 1970] Memory: 66744K/130552K available (22536K kernel code, 4577K rwdata, 6520K rodata, 3188K init, 18692K bss, 63548K reserved, 0K cma-reserved)
[Thu Jan  1 10:03:58 1970] SLUB: HWalign=64, Order=0-3, MinObjects=0, CPUs=4, Nodes=1
[Thu Jan  1 10:03:58 1970] Kernel/User page tables isolation: enabled
[Thu Jan  1 10:03:58 1970] ftrace: allocating 55010 entries in 215 pages
[Thu Jan  1 10:03:58 1970] ftrace: allocated 215 pages with 6 groups
[Thu Jan  1 10:03:58 1970] Dynamic Preempt: voluntary
[Thu Jan  1 10:03:58 1970] rcu: Preemptible hierarchical RCU implementation.
[Thu Jan  1 10:03:58 1970] rcu: 	RCU restricting CPUs from NR_CPUS=8192 to nr_cpu_ids=4.
[Thu Jan  1 10:03:58 1970] 	Trampoline variant of Tasks RCU enabled.
[Thu Jan  1 10:03:58 1970] 	Rude variant of Tasks RCU enabled.
[Thu Jan  1 10:03:58 1970] 	Tracing variant of Tasks RCU enabled.
[Thu Jan  1 10:03:58 1970] rcu: RCU calculated value of scheduler-enlistment delay is 25 jiffies.
[Thu Jan  1 10:03:58 1970] rcu: Adjusting geometry for rcu_fanout_leaf=16, nr_cpu_ids=4
[Thu Jan  1 10:03:58 1970] NR_IRQS: 524544, nr_irqs: 456, preallocated irqs: 16
[Thu Jan  1 10:03:58 1970] rcu: srcu_init: Setting srcu_struct sizes based on contention.
[Thu Jan  1 10:03:58 1970] Console: colour VGA+ 80x25
[Thu Jan  1 10:03:58 1970] printk: console [ttyS0] enabled
[Thu Jan  1 10:03:58 1970] ACPI: Core revision 20220331
[Thu Jan  1 10:03:58 1970] clocksource: hpet: mask: 0xffffffff max_cycles: 0xffffffff, max_idle_ns: 19112604467 ns
[Thu Jan  1 10:03:58 1970] APIC: Switch to symmetric I/O mode setup
[Thu Jan  1 10:03:58 1970] ..TIMER: vector=0x30 apic1=0 pin1=2 apic2=-1 pin2=-1
[Thu Jan  1 10:03:58 1970] tsc: Marking TSC unstable due to TSCs unsynchronized
[Thu Jan  1 10:03:58 1970] Calibrating delay loop (skipped), value calculated using timer frequency.. 7372.52 BogoMIPS (lpj=14745052)
[Thu Jan  1 10:03:58 1970] x86/cpu: User Mode Instruction Prevention (UMIP) activated
[Thu Jan  1 10:03:58 1970] Last level iTLB entries: 4KB 0, 2MB 0, 4MB 0
[Thu Jan  1 10:03:58 1970] Last level dTLB entries: 4KB 0, 2MB 0, 4MB 0, 1GB 0
[Thu Jan  1 10:03:58 1970] Spectre V1 : Mitigation: usercopy/swapgs barriers and __user pointer sanitization
[Thu Jan  1 10:03:58 1970] Spectre V2 : Mitigation: Retpolines
[Thu Jan  1 10:03:58 1970] Spectre V2 : Spectre v2 / SpectreRSB mitigation: Filling RSB on context switch
[Thu Jan  1 10:03:58 1970] Spectre V2 : Spectre v2 / SpectreRSB : Filling RSB on VMEXIT
[Thu Jan  1 10:03:58 1970] Speculative Store Bypass: Vulnerable
[Thu Jan  1 10:03:58 1970] x86/fpu: Supporting XSAVE feature 0x001: 'x87 floating point registers'
[Thu Jan  1 10:03:58 1970] x86/fpu: Supporting XSAVE feature 0x002: 'SSE registers'
[Thu Jan  1 10:03:58 1970] x86/fpu: Supporting XSAVE feature 0x004: 'AVX registers'
[Thu Jan  1 10:03:58 1970] x86/fpu: Supporting XSAVE feature 0x008: 'MPX bounds registers'
[Thu Jan  1 10:03:58 1970] x86/fpu: Supporting XSAVE feature 0x010: 'MPX CSR'
[Thu Jan  1 10:03:58 1970] x86/fpu: Supporting XSAVE feature 0x200: 'Protection Keys User registers'
[Thu Jan  1 10:03:58 1970] x86/fpu: xstate_offset[2]:  576, xstate_sizes[2]:  256
[Thu Jan  1 10:03:58 1970] x86/fpu: xstate_offset[3]:  960, xstate_sizes[3]:   64
[Thu Jan  1 10:03:58 1970] x86/fpu: xstate_offset[4]: 1024, xstate_sizes[4]:   64
[Thu Jan  1 10:03:58 1970] x86/fpu: xstate_offset[9]: 2688, xstate_sizes[9]:    8
[Thu Jan  1 10:03:58 1970] x86/fpu: Enabled xstate features 0x21f, context size is 2696 bytes, using 'standard' format.
[Thu Jan  1 10:03:58 1970] Freeing SMP alternatives memory: 44K
[Thu Jan  1 10:03:58 1970] pid_max: default: 32768 minimum: 301
[Thu Jan  1 10:03:58 1970] LSM: Security Framework initializing
[Thu Jan  1 10:03:58 1970] landlock: Up and running.
[Thu Jan  1 10:03:58 1970] Yama: becoming mindful.
[Thu Jan  1 10:03:58 1970] AppArmor: AppArmor initialized
[Thu Jan  1 10:03:58 1970] Mount-cache hash table entries: 512 (order: 0, 4096 bytes, linear)
[Thu Jan  1 10:03:58 1970] Mountpoint-cache hash table entries: 512 (order: 0, 4096 bytes, linear)
[Thu Jan  1 10:03:58 1970] smpboot: CPU0: AMD QEMU TCG CPU version 2.5+ (family: 0x6, model: 0x6, stepping: 0x3)
[Thu Jan  1 10:03:58 1970] cblist_init_generic: Setting adjustable number of callback queues.
[Thu Jan  1 10:03:58 1970] cblist_init_generic: Setting shift to 2 and lim to 1.
[Thu Jan  1 10:03:58 1970] cblist_init_generic: Setting adjustable number of callback queues.
[Thu Jan  1 10:03:58 1970] cblist_init_generic: Setting shift to 2 and lim to 1.
[Thu Jan  1 10:03:58 1970] cblist_init_generic: Setting adjustable number of callback queues.
[Thu Jan  1 10:03:58 1970] cblist_init_generic: Setting shift to 2 and lim to 1.
[Thu Jan  1 10:03:58 1970] Performance Events: PMU not available due to virtualization, using software events only.
[Thu Jan  1 10:03:58 1970] signal: max sigframe size: 3632
[Thu Jan  1 10:03:58 1970] rcu: Hierarchical SRCU implementation.
[Thu Jan  1 10:03:58 1970] rcu: 	Max phase no-delay instances is 1000.
[Thu Jan  1 10:03:58 1970] NMI watchdog: Perf NMI watchdog permanently disabled
[Thu Jan  1 10:03:58 1970] smp: Bringing up secondary CPUs ...
[Thu Jan  1 10:03:58 1970] x86: Booting SMP configuration:
[Thu Jan  1 10:03:58 1970] .... node  #0, CPUs:      #1 #2 #3
[Thu Jan  1 10:03:58 1970] smp: Brought up 1 node, 4 CPUs
[Thu Jan  1 10:03:58 1970] smpboot: Max logical packages: 1
[Thu Jan  1 10:03:58 1970] smpboot: Total of 4 processors activated (29644.93 BogoMIPS)
[Thu Jan  1 10:03:58 1970] devtmpfs: initialized
[Thu Jan  1 10:03:58 1970] x86/mm: Memory block size: 128MB
[Thu Jan  1 10:03:58 1970] clocksource: jiffies: mask: 0xffffffff max_cycles: 0xffffffff, max_idle_ns: 7645041785100000 ns
[Thu Jan  1 10:03:58 1970] futex hash table entries: 1024 (order: 4, 65536 bytes, linear)
[Thu Jan  1 10:03:58 1970] pinctrl core: initialized pinctrl subsystem
[Thu Jan  1 10:03:58 1970] PM: RTC time: 17:33:19, date: 2026-10-27
[Thu Jan  1 10:03:58 1970] NET: Registered PF_NETLINK/PF_ROUTE protocol family
[Thu Jan  1 10:03:58 1970] DMA: preallocated 128 KiB GFP_KERNEL pool for atomic allocations
[Thu Jan  1 10:03:58 1970] DMA: preallocated 128 KiB GFP_KERNEL|GFP_DMA pool for atomic allocations
[Thu Jan  1 10:03:58 1970] DMA: preallocated 128 KiB GFP_KERNEL|GFP_DMA32 pool for atomic allocations
[Thu Jan  1 10:03:58 1970] audit: initializing netlink subsys (disabled)
[Thu Jan  1 10:03:58 1970] audit: type=2000 audit(1793122399.620:1): state=initialized audit_enabled=0 res=1
[Thu Jan  1 10:03:58 1970] thermal_sys: Registered thermal governor 'fair_share'
[Thu Jan  1 10:03:58 1970] thermal_sys: Registered thermal governor 'bang_bang'
[Thu Jan  1 10:03:58 1970] thermal_sys: Registered thermal governor 'step_wise'
[Thu Jan  1 10:03:58 1970] thermal_sys: Registered thermal governor 'user_space'
[Thu Jan  1 10:03:58 1970] thermal_sys: Registered thermal governor 'power_allocator'
[Thu Jan  1 10:03:58 1970] cpuidle: using governor ladder
[Thu Jan  1 10:03:58 1970] cpuidle: using governor menu
[Thu Jan  1 10:03:58 1970] acpiphp: ACPI Hot Plug PCI Controller Driver version: 0.5
[Thu Jan  1 10:03:58 1970] PCI: Using configuration type 1 for base access
[Thu Jan  1 10:03:58 1970] mtrr: your CPUs had inconsistent fixed MTRR settings
[Thu Jan  1 10:03:58 1970] mtrr: your CPUs had inconsistent variable MTRR settings
[Thu Jan  1 10:03:58 1970] mtrr: your CPUs had inconsistent MTRRdefType settings
[Thu Jan  1 10:03:58 1970] mtrr: probably your BIOS does not setup all CPUs.
[Thu Jan  1 10:03:58 1970] mtrr: corrected configuration.
[Thu Jan  1 10:03:58 1970] kprobes: kprobe jump-optimization is enabled. All kprobes are optimized if possible.
[Thu Jan  1 10:03:58 1970] HugeTLB: registered 1.00 GiB page size, pre-allocated 0 pages
[Thu Jan  1 10:03:58 1970] HugeTLB: 16380 KiB vmemmap can be freed for a 1.00 GiB page
[Thu Jan  1 10:03:58 1970] HugeTLB: registered 2.00 MiB page size, pre-allocated 0 pages
[Thu Jan  1 10:03:58 1970] HugeTLB: 28 KiB vmemmap can be freed for a 2.00 MiB page
[Thu Jan  1 10:03:58 1970] cryptd: max_cpu_qlen set to 1000
[Thu Jan  1 10:03:58 1970] ACPI: Added _OSI(Module Device)
[Thu Jan  1 10:03:58 1970] ACPI: Added _OSI(Processor Device)
[Thu Jan  1 10:03:58 1970] ACPI: Added _OSI(3.0 _SCP Extensions)
[Thu Jan  1 10:03:58 1970] ACPI: Added _OSI(Processor Aggregator Device)
[Thu Jan  1 10:03:58 1970] ACPI: 1 ACPI AML tables successfully acquired and loaded
[Thu Jan  1 10:03:58 1970] ACPI: Interpreter enabled
[Thu Jan  1 10:03:58 1970] ACPI: PM: (supports S0 S3 S4 S5)
[Thu Jan  1 10:03:58 1970] ACPI: Using IOAPIC for interrupt routing
[Thu Jan  1 10:03:58 1970] PCI: Using host bridge windows from ACPI; if necessary, use "pci=nocrs" and report a bug
[Thu Jan  1 10:03:58 1970] PCI: Using E820 reservations for host bridge windows
[Thu Jan  1 10:03:58 1970] ACPI: Enabled 2 GPEs in block 00 to 0F
[Thu Jan  1 10:03:58 1970] ACPI: PCI Root Bridge [PCI0] (domain 0000 [bus 00-ff])
[Thu Jan  1 10:03:58 1970] acpi PNP0A03:00: _OSC: OS supports [ASPM ClockPM Segments MSI EDR HPX-Type3]
[Thu Jan  1 10:03:58 1970] acpi PNP0A03:00: _OSC: not requesting OS control; OS requires [ExtendedConfig ASPM ClockPM MSI]
[Thu Jan  1 10:03:58 1970] acpi PNP0A03:00: fail to add MMCONFIG information, can't access extended PCI configuration space under this bridge.
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [3] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [4] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [5] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [6] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [7] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [8] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [9] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [10] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [11] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [12] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [13] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [14] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [15] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [16] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [17] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [18] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [19] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [20] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [21] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [22] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [23] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [24] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [25] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [26] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [27] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [28] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [29] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [30] registered
[Thu Jan  1 10:03:58 1970] acpiphp: Slot [31] registered
[Thu Jan  1 10:03:58 1970] PCI host bridge to bus 0000:00
[Thu Jan  1 10:03:58 1970] pci_bus 0000:00: root bus resource [io  0x0000-0x0cf7 window]
[Thu Jan  1 10:03:58 1970] pci_bus 0000:00: root bus resource [io  0x0d00-0xffff window]
[Thu Jan  1 10:03:58 1970] pci_bus 0000:00: root bus resource [mem 0x000a0000-0x000bffff window]
[Thu Jan  1 10:03:58 1970] pci_bus 0000:00: root bus resource [mem 0x08000000-0xfebfffff window]
[Thu Jan  1 10:03:58 1970] pci_bus 0000:00: root bus resource [mem 0x100000000-0x17fffffff window]
[Thu Jan  1 10:03:58 1970] pci_bus 0000:00: root bus resource [bus 00-ff]
[Thu Jan  1 10:03:58 1970] pci 0000:00:00.0: [8086:1237] type 00 class 0x060000
[Thu Jan  1 10:03:58 1970] pci 0000:00:01.0: [8086:7000] type 00 class 0x060100
[Thu Jan  1 10:03:58 1970] pci 0000:00:01.1: [8086:7010] type 00 class 0x010180
[Thu Jan  1 10:03:58 1970] pci 0000:00:01.1: reg 0x20: [io  0xc040-0xc04f]
[Thu Jan  1 10:03:58 1970] pci 0000:00:01.1: legacy IDE quirk: reg 0x10: [io  0x01f0-0x01f7]
[Thu Jan  1 10:03:58 1970] pci 0000:00:01.1: legacy IDE quirk: reg 0x14: [io  0x03f6]
[Thu Jan  1 10:03:58 1970] pci 0000:00:01.1: legacy IDE quirk: reg 0x18: [io  0x0170-0x0177]
[Thu Jan  1 10:03:58 1970] pci 0000:00:01.1: legacy IDE quirk: reg 0x1c: [io  0x0376]
[Thu Jan  1 10:03:58 1970] pci 0000:00:01.3: [8086:7113] type 00 class 0x068000
[Thu Jan  1 10:03:58 1970] pci 0000:00:01.3: quirk: [io  0x0600-0x063f] claimed by PIIX4 ACPI
[Thu Jan  1 10:03:58 1970] pci 0000:00:01.3: quirk: [io  0x0700-0x070f] claimed by PIIX4 SMB
[Thu Jan  1 10:03:58 1970] pci 0000:00:02.0: [1234:1111] type 00 class 0x030000
[Thu Jan  1 10:03:58 1970] pci 0000:00:02.0: reg 0x10: [mem 0xfd000000-0xfdffffff pref]
[Thu Jan  1 10:03:58 1970] pci 0000:00:02.0: reg 0x18: [mem 0xfebb0000-0xfebb0fff]
[Thu Jan  1 10:03:58 1970] pci 0000:00:02.0: reg 0x30: [mem 0xfeba0000-0xfebaffff pref]
[Thu Jan  1 10:03:58 1970] pci 0000:00:02.0: Video device with shadowed ROM at [mem 0x000c0000-0x000dffff]
[Thu Jan  1 10:03:58 1970] pci 0000:00:03.0: [8086:100e] type 00 class 0x020000
[Thu Jan  1 10:03:58 1970] pci 0000:00:03.0: reg 0x10: [mem 0xfeb80000-0xfeb9ffff]
[Thu Jan  1 10:03:58 1970] pci 0000:00:03.0: reg 0x14: [io  0xc000-0xc03f]
[Thu Jan  1 10:03:58 1970] pci 0000:00:03.0: reg 0x30: [mem 0xfeb00000-0xfeb7ffff pref]
[Thu Jan  1 10:03:58 1970] ACPI: PCI: Interrupt link LNKA configured for IRQ 10
[Thu Jan  1 10:03:58 1970] ACPI: PCI: Interrupt link LNKB configured for IRQ 10
[Thu Jan  1 10:03:58 1970] ACPI: PCI: Interrupt link LNKC configured for IRQ 11
[Thu Jan  1 10:03:58 1970] ACPI: PCI: Interrupt link LNKD configured for IRQ 11
[Thu Jan  1 10:03:58 1970] ACPI: PCI: Interrupt link LNKS configured for IRQ 9
[Thu Jan  1 10:03:58 1970] iommu: Default domain type: Translated 
[Thu Jan  1 10:03:58 1970] iommu: DMA domain TLB invalidation policy: lazy mode 
[Thu Jan  1 10:03:58 1970] SCSI subsystem initialized
[Thu Jan  1 10:03:58 1970] libata version 3.00 loaded.
[Thu Jan  1 10:03:58 1970] ACPI: bus type USB registered
[Thu Jan  1 10:03:58 1970] usbcore: registered new interface driver usbfs
[Thu Jan  1 10:03:58 1970] usbcore: registered new interface driver hub
[Thu Jan  1 10:03:58 1970] usbcore: registered new device driver usb
[Thu Jan  1 10:03:58 1970] pps_core: LinuxPPS API ver. 1 registered
[Thu Jan  1 10:03:58 1970] pps_core: Software ver. 5.3.6 - Copyright 2005-2007 Rodolfo Giometti <giometti@linux.it>
[Thu Jan  1 10:03:58 1970] PTP clock support registered
[Thu Jan  1 10:03:58 1970] EDAC MC: Ver: 3.0.0
[Thu Jan  1 10:03:58 1970] NetLabel: Initializing
[Thu Jan  1 10:03:58 1970] NetLabel:  domain hash size = 128
[Thu Jan  1 10:03:58 1970] NetLabel:  protocols = UNLABELED CIPSOv4 CALIPSO
[Thu Jan  1 10:03:58 1970] NetLabel:  unlabeled traffic allowed by default
[Thu Jan  1 10:03:58 1970] mctp: management component transport protocol core
[Thu Jan  1 10:03:58 1970] NET: Registered PF_MCTP protocol family
[Thu Jan  1 10:03:58 1970] PCI: Using ACPI for IRQ routing
[Thu Jan  1 10:03:58 1970] PCI: pci_cache_line_size set to 64 bytes
[Thu Jan  1 10:03:58 1970] e820: reserve RAM buffer [mem 0x0009fc00-0x0009ffff]
[Thu Jan  1 10:03:58 1970] e820: reserve RAM buffer [mem 0x07fe0000-0x07ffffff]
[Thu Jan  1 10:03:58 1970] pci 0000:00:02.0: vgaarb: setting as boot VGA device
[Thu Jan  1 10:03:58 1970] pci 0000:00:02.0: vgaarb: bridge control possible
[Thu Jan  1 10:03:58 1970] pci 0000:00:02.0: vgaarb: VGA device added: decodes=io+mem,owns=io+mem,locks=none
[Thu Jan  1 10:03:58 1970] vgaarb: loaded
[Thu Jan  1 10:03:58 1970] hpet0: at MMIO 0xfed00000, IRQs 2, 8, 0
[Thu Jan  1 10:03:58 1970] hpet0: 3 comparators, 64-bit 100.000000 MHz counter
[Thu Jan  1 10:03:58 1970] clocksource: Switched to clocksource hpet
[Thu Jan  1 10:03:58 1970] VFS: Disk quotas dquot_6.6.0
[Thu Jan  1 10:03:58 1970] VFS: Dquot-cache hash table entries: 512 (order 0, 4096 bytes)
[Thu Jan  1 10:03:58 1970] AppArmor: AppArmor Filesystem Enabled
[Thu Jan  1 10:03:58 1970] pnp: PnP ACPI init
[Thu Jan  1 10:03:58 1970] pnp 00:02: [dma 2]
[Thu Jan  1 10:03:58 1970] pnp: PnP ACPI: found 6 devices
[Thu Jan  1 10:03:59 1970] clocksource: acpi_pm: mask: 0xffffff max_cycles: 0xffffff, max_idle_ns: 2085701024 ns
[Thu Jan  1 10:03:59 1970] NET: Registered PF_INET protocol family
[Thu Jan  1 10:03:59 1970] IP idents hash table entries: 2048 (order: 2, 16384 bytes, linear)
[Thu Jan  1 10:03:59 1970] tcp_listen_portaddr_hash hash table entries: 256 (order: 0, 4096 bytes, linear)
[Thu Jan  1 10:03:59 1970] Table-perturb hash table entries: 65536 (order: 6, 262144 bytes, linear)
[Thu Jan  1 10:03:59 1970] TCP established hash table entries: 1024 (order: 1, 8192 bytes, linear)
[Thu Jan  1 10:03:59 1970] TCP bind hash table entries: 1024 (order: 3, 32768 bytes, linear)
[Thu Jan  1 10:03:59 1970] TCP: Hash tables configured (established 1024 bind 1024)
[Thu Jan  1 10:03:59 1970] MPTCP token hash table entries: 256 (order: 0, 6144 bytes, linear)
[Thu Jan  1 10:03:59 1970] UDP hash table entries: 256 (order: 1, 8192 bytes, linear)
[Thu Jan  1 10:03:59 1970] UDP-Lite hash table entries: 256 (order: 1, 8192 bytes, linear)
[Thu Jan  1 10:03:59 1970] NET: Registered PF_UNIX/PF_LOCAL protocol family
[Thu Jan  1 10:03:59 1970] NET: Registered PF_XDP protocol family
[Thu Jan  1 10:03:59 1970] pci_bus 0000:00: resource 4 [io  0x0000-0x0cf7 window]
[Thu Jan  1 10:03:59 1970] pci_bus 0000:00: resource 5 [io  0x0d00-0xffff window]
[Thu Jan  1 10:03:59 1970] pci_bus 0000:00: resource 6 [mem 0x000a0000-0x000bffff window]
[Thu Jan  1 10:03:59 1970] pci_bus 0000:00: resource 7 [mem 0x08000000-0xfebfffff window]
[Thu Jan  1 10:03:59 1970] pci_bus 0000:00: resource 8 [mem 0x100000000-0x17fffffff window]
[Thu Jan  1 10:03:59 1970] pci 0000:00:01.0: PIIX3: Enabling Passive Release
[Thu Jan  1 10:03:59 1970] pci 0000:00:00.0: Limiting direct PCI/PCI transfers
[Thu Jan  1 10:03:59 1970] PCI: CLS 0 bytes, default 64
[Thu Jan  1 10:03:59 1970] Initialise system trusted keyrings
[Thu Jan  1 10:03:59 1970] Key type blacklist registered
[Thu Jan  1 10:03:59 1970] workingset: timestamp_bits=36 max_order=15 bucket_order=0
[Thu Jan  1 10:03:59 1970] zbud: loaded
[Thu Jan  1 10:03:59 1970] squashfs: version 4.0 (2009/01/31) Phillip Lougher
[Thu Jan  1 10:03:59 1970] fuse: init (API version 7.38)
[Thu Jan  1 10:03:59 1970] integrity: Platform Keyring initialized
[Thu Jan  1 10:03:59 1970] integrity: Machine keyring initialized
[Thu Jan  1 10:03:59 1970] NET: Registered PF_ALG protocol family
[Thu Jan  1 10:03:59 1970] Key type asymmetric registered
[Thu Jan  1 10:03:59 1970] Asymmetric key parser 'x509' registered
[Thu Jan  1 10:03:59 1970] alg: self-tests for CTR-KDF (hmac(sha256)) passed
[Thu Jan  1 10:03:59 1970] Block layer SCSI generic (bsg) driver version 0.4 loaded (major 243)
[Thu Jan  1 10:03:59 1970] io scheduler mq-deadline registered
[Thu Jan  1 10:03:59 1970] shpchp: Standard Hot Plug PCI Controller Driver version: 0.4
[Thu Jan  1 10:03:59 1970] input: Power Button as /devices/LNXSYSTM:00/LNXPWRBN:00/input/input0
[Thu Jan  1 10:03:59 1970] ACPI: button: Power Button [PWRF]
[Thu Jan  1 10:03:59 1970] Serial: 8250/16550 driver, 32 ports, IRQ sharing enabled
[Thu Jan  1 10:03:59 1970] 00:04: ttyS0 at I/O 0x3f8 (irq = 4, base_baud = 115200) is a 16550A
[Thu Jan  1 10:03:59 1970] Linux agpgart interface v0.103
[Thu Jan  1 10:03:59 1970] loop: module loaded
[Thu Jan  1 10:03:59 1970] dummy-irq: no IRQ given.  Use irq=N
[Thu Jan  1 10:03:59 1970] ata_piix 0000:00:01.1: version 2.13
[Thu Jan  1 10:03:59 1970] scsi host0: ata_piix
[Thu Jan  1 10:03:59 1970] scsi host1: ata_piix
[Thu Jan  1 10:03:59 1970] ata1: PATA max MWDMA2 cmd 0x1f0 ctl 0x3f6 bmdma 0xc040 irq 14
[Thu Jan  1 10:03:59 1970] ata2: PATA max MWDMA2 cmd 0x170 ctl 0x376 bmdma 0xc048 irq 15
[Thu Jan  1 10:03:59 1970] tun: Universal TUN/TAP device driver, 1.6
[Thu Jan  1 10:03:59 1970] e100: Intel(R) PRO/100 Network Driver
[Thu Jan  1 10:03:59 1970] e100: Copyright(c) 1999-2006 Intel Corporation
[Thu Jan  1 10:03:59 1970] e1000: Intel(R) PRO/1000 Network Driver
[Thu Jan  1 10:03:59 1970] e1000: Copyright (c) 1999-2006 Intel Corporation.
[Thu Jan  1 10:03:59 1970] ACPI: \_SB_.LNKC: Enabled at IRQ 11
[Thu Jan  1 10:03:59 1970] ata2: found unknown device (class 0)
[Thu Jan  1 10:03:59 1970] ata1: found unknown device (class 0)
[Thu Jan  1 10:03:59 1970] ata2.00: ATAPI: QEMU DVD-ROM, 2.5+, max UDMA/100
[Thu Jan  1 10:03:59 1970] ata1.00: ATA-7: QEMU HARDDISK, 2.5+, max UDMA/100
[Thu Jan  1 10:03:59 1970] ata1.00: 524288 sectors, multi 16: LBA48 
[Thu Jan  1 10:03:59 1970] scsi 0:0:0:0: Direct-Access     ATA      QEMU HARDDISK    2.5+ PQ: 0 ANSI: 5
[Thu Jan  1 10:03:59 1970] scsi 0:0:0:0: Attached scsi generic sg0 type 0
[Thu Jan  1 10:03:59 1970] sd 0:0:0:0: [sda] 524288 512-byte logical blocks: (268 MB/256 MiB)
[Thu Jan  1 10:03:59 1970] scsi 1:0:0:0: CD-ROM            QEMU     QEMU DVD-ROM     2.5+ PQ: 0 ANSI: 5
[Thu Jan  1 10:03:59 1970] sd 0:0:0:0: [sda] Write Protect is off
[Thu Jan  1 10:03:59 1970] sd 0:0:0:0: [sda] Mode Sense: 00 3a 00 00
[Thu Jan  1 10:03:59 1970] sd 0:0:0:0: [sda] Write cache: enabled, read cache: enabled, doesn't support DPO or FUA
[Thu Jan  1 10:03:59 1970] sd 0:0:0:0: [sda] Preferred minimum I/O size 512 bytes
[Thu Jan  1 10:03:59 1970] sd 0:0:0:0: [sda] Attached SCSI disk
[Thu Jan  1 10:03:59 1970] sr 1:0:0:0: [sr0] scsi3-mmc drive: 4x/4x cd/rw xa/form2 tray
[Thu Jan  1 10:03:59 1970] cdrom: Uniform CD-ROM driver Revision: 3.20
[Thu Jan  1 10:03:59 1970] sr 1:0:0:0: Attached scsi CD-ROM sr0
[Thu Jan  1 10:03:59 1970] sr 1:0:0:0: Attached scsi generic sg1 type 5
[Thu Jan  1 10:03:59 1970] e1000 0000:00:03.0 eth0: (PCI:33MHz:32-bit) 52:54:00:12:34:56
[Thu Jan  1 10:03:59 1970] e1000 0000:00:03.0 eth0: Intel(R) PRO/1000 Network Connection
[Thu Jan  1 10:03:59 1970] e1000e: Intel(R) PRO/1000 Network Driver
[Thu Jan  1 10:03:59 1970] e1000e: Copyright(c) 1999 - 2015 Intel Corporation.
[Thu Jan  1 10:03:59 1970] PPP generic driver version 2.4.2
[Thu Jan  1 10:03:59 1970] VFIO - User Level meta-driver version: 0.3
[Thu Jan  1 10:03:59 1970] i8042: PNP: PS/2 Controller [PNP0303:KBD,PNP0f13:MOU] at 0x60,0x64 irq 1,12
[Thu Jan  1 10:03:59 1970] serio: i8042 KBD port at 0x60,0x64 irq 1
[Thu Jan  1 10:03:59 1970] serio: i8042 AUX port at 0x60,0x64 irq 12
[Thu Jan  1 10:03:59 1970] mousedev: PS/2 mouse device common for all mice
[Thu Jan  1 10:03:59 1970] rtc_cmos 00:05: RTC can wake from S4
[Thu Jan  1 10:03:59 1970] input: AT Translated Set 2 keyboard as /devices/platform/i8042/serio0/input/input1
[Thu Jan  1 10:03:59 1970] rtc_cmos 00:05: registered as rtc0
[Thu Jan  1 10:03:59 1970] rtc_cmos 00:05: setting system clock to 2026-10-27T17:33:20 UTC (1793122400)
[Thu Jan  1 10:03:59 1970] rtc_cmos 00:05: alarms up to one day, y3k, 242 bytes nvram, hpet irqs
[Thu Jan  1 10:03:59 1970] i2c_dev: i2c /dev entries driver
[Thu Jan  1 10:03:59 1970] device-mapper: core: CONFIG_IMA_DISABLE_HTABLE is disabled. Duplicate IMA measurements will not be recorded in the IMA log.
[Thu Jan  1 10:03:59 1970] device-mapper: uevent: version 1.0.3
[Thu Jan  1 10:03:59 1970] device-mapper: ioctl: 4.47.0-ioctl (2022-07-28) initialised: dm-devel@redhat.com
[Thu Jan  1 10:03:59 1970] ledtrig-cpu: registered to indicate activity on CPUs
[Thu Jan  1 10:03:59 1970] ccp_crypto: Cannot load: there are no available CCPs
[Thu Jan  1 10:03:59 1970] drop_monitor: Initializing network drop monitor service
[Thu Jan  1 10:03:59 1970] netem: version 1.3
[Thu Jan  1 10:03:59 1970] xt_time: kernel timezone is -0000
[Thu Jan  1 10:03:59 1970] Initializing XFRM netlink socket
[Thu Jan  1 10:03:59 1970] IPsec XFRM device driver
[Thu Jan  1 10:03:59 1970] NET: Registered PF_INET6 protocol family
[Thu Jan  1 10:03:59 1970] Segment Routing with IPv6
[Thu Jan  1 10:03:59 1970] In-situ OAM (IOAM) with IPv6
[Thu Jan  1 10:03:59 1970] NET: Registered PF_PACKET protocol family
[Thu Jan  1 10:03:59 1970] Key type dns_resolver registered
[Thu Jan  1 10:03:59 1970] NET: Registered PF_VSOCK protocol family
[Thu Jan  1 10:03:59 1970] IPI shorthand broadcast: enabled
[Thu Jan  1 10:03:59 1970] AVX2 version of gcm_enc/dec engaged.
[Thu Jan  1 10:03:59 1970] AES CTR mode by8 optimization enabled
[Thu Jan  1 10:03:59 1970] registered taskstats version 1
[Thu Jan  1 10:03:59 1970] Loading compiled-in X.509 certificates
[Thu Jan  1 10:03:59 1970] Loaded X.509 cert 'Build time autogenerated kernel key: 016f2e88ccccba8cf44c14faef0bf9414e1f70c8'
[Thu Jan  1 10:03:59 1970] zswap: loaded using pool lzo/zbud
[Thu Jan  1 10:03:59 1970] Key type .fscrypt registered
[Thu Jan  1 10:03:59 1970] Key type fscrypt-provisioning registered
[Thu Jan  1 10:03:59 1970] Key type encrypted registered
[Thu Jan  1 10:03:59 1970] AppArmor: AppArmor sha1 policy hashing enabled
[Thu Jan  1 10:03:59 1970] ima: No TPM chip found, activating TPM-bypass!
[Thu Jan  1 10:03:59 1970] Loading compiled-in module X.509 certificates
[Thu Jan  1 10:03:59 1970] Loaded X.509 cert 'Build time autogenerated kernel key: 016f2e88ccccba8cf44c14faef0bf9414e1f70c8'
[Thu Jan  1 10:03:59 1970] ima: Allocated hash algorithm: sha1
[Thu Jan  1 10:03:59 1970] ima: No architecture policies found
[Thu Jan  1 10:03:59 1970] evm: Initialising EVM extended attributes:
[Thu Jan  1 10:03:59 1970] evm: security.selinux
[Thu Jan  1 10:03:59 1970] evm: security.SMACK64
[Thu Jan  1 10:03:59 1970] evm: security.SMACK64EXEC
[Thu Jan  1 10:03:59 1970] evm: security.SMACK64TRANSMUTE
[Thu Jan  1 10:03:59 1970] evm: security.SMACK64MMAP
[Thu Jan  1 10:03:59 1970] evm: security.apparmor
[Thu Jan  1 10:03:59 1970] evm: security.ima
[Thu Jan  1 10:03:59 1970] evm: security.capability
[Thu Jan  1 10:03:59 1970] evm: HMAC attrs: 0x1
[Thu Jan  1 10:03:59 1970] PM:   Magic number: 14:886:593
[Thu Jan  1 10:03:59 1970] RAS: Correctable Errors collector initialized.
[Thu Jan  1 10:03:59 1970] Unstable clock detected, switching default tracing clock to "global"
[Thu Jan  1 10:03:59 1970] If you want to keep using the local clock, then add:
[Thu Jan  1 10:03:59 1970]   "trace_clock=local"
[Thu Jan  1 10:03:59 1970] on the kernel command line
[Thu Jan  1 10:03:59 1970] clk: Disabling unused clocks
[Thu Jan  1 10:03:59 1970] md: Waiting for all devices to be available before autodetect
[Thu Jan  1 10:03:59 1970] md: If you don't use raid, use raid=noautodetect
[Thu Jan  1 10:03:59 1970] md: Autodetecting RAID arrays.
[Thu Jan  1 10:03:59 1970] md: autorun ...
[Thu Jan  1 10:03:59 1970] md: ... autorun DONE.
[Thu Jan  1 10:03:59 1970] EXT4-fs (sda): mounted filesystem with ordered data mode. Quota mode: none.
[Thu Jan  1 10:03:59 1970] VFS: Mounted root (ext4 filesystem) on device 8:0.
[Thu Jan  1 10:03:59 1970] devtmpfs: mounted
[Thu Jan  1 10:03:59 1970] Freeing unused decrypted memory: 2036K
[Thu Jan  1 10:04:00 1970] Freeing unused kernel image (initmem) memory: 3188K
[Thu Jan  1 10:04:00 1970] Write protecting the kernel read-only data: 32768k
[Thu Jan  1 10:04:00 1970] Freeing unused kernel image (text/rodata gap) memory: 2036K
[Thu Jan  1 10:04:00 1970] Freeing unused kernel image (rodata/data gap) memory: 1672K
[Thu Jan  1 10:04:00 1970] x86/mm: Checked W+X mappings: passed, no W+X pages found.
[Thu Jan  1 10:04:00 1970] x86/mm: Checking user space page tables
[Thu Jan  1 10:04:00 1970] x86/mm: Checked W+X mappings: passed, no W+X pages found.
[Thu Jan  1 10:04:00 1970] Run /sbin/init as init process
[Thu Jan  1 10:04:00 1970]   with arguments:
[Thu Jan  1 10:04:00 1970]     /sbin/init
[Thu Jan  1 10:04:00 1970]     no5lvl
[Thu Jan  1 10:04:00 1970]     kaslr
[Thu Jan  1 10:04:00 1970]   with environment:
[Thu Jan  1 10:04:00 1970]     HOME=/
[Thu Jan  1 10:04:00 1970]     TERM=linux
[Thu Jan  1 10:04:00 1970]     biosdevname=0
[Thu Jan  1 10:04:00 1970]     pti=on
[Thu Jan  1 10:04:03 1970] EXT4-fs (sda): re-mounted. Quota mode: none.
[Thu Jan  1 10:04:05 1970] udevd[702]: starting version 3.2.14
[Thu Jan  1 10:04:05 1970] udevd[702]: starting eudev-3.2.14
[Thu Jan  1 10:04:07 1970] e1000: eth0 NIC Link is Up 1000 Mbps Full Duplex, Flow Control: RX
[Thu Jan  1 10:04:07 1970] IPv6: ADDRCONF(NETDEV_CHANGE): eth0: link becomes ready
```

### Reading it

`--ctime` converts the monotonic timestamps to wall-clock form using the boot time the kernel recorded.  It is useful for correlating with an exploit run that has its own timestamps.

## Notes

`printk_info.text_len` is a `u16` and the sequence number lives in `printk_info`, not in the text blob: reading either from the wrong place produces plausible but wrong lines.  NUL bytes are stripped because GDB aborts the write on them.

---

Part of the [KernLens tutorial](README.md).  Every output block on this page was captured from the kernel described in the [tutorial index](README.md#the-capture-kernel).
