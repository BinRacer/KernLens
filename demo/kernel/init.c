/*
 * The demo's init.
 *
 * It mounts the three filesystems the kernel commands expect, leaves a
 * few objects in a slab cache for `kl-slab` to decode, prints a marker
 * the entrypoint waits for, and stays alive so the VM can be inspected.
 * A shell would need a second binary and a C library in the initramfs;
 * this needs neither.
 */

#include <string.h>
#include <sys/mount.h>
#include <sys/msg.h>
#include <unistd.h>

/*
 * Leave a few kmalloc-1k objects queued and free the rest, so
 * `kl-slab info kmalloc-1k` has live objects and freed slots to decode
 * instead of an untouched cache.  A SysV message of this size is
 * `sizeof(struct msg_msg) + 900` bytes and lands in kmalloc-1k when
 * cgroup accounting is off, as it is in this kernel.
 */
struct message {
	long type;
	char text[900];
};

static void seed_kmalloc(void)
{
	struct message message;
	int queue;

	queue = msgget(IPC_PRIVATE, IPC_CREAT | 0600);
	if (queue < 0)
		return;
	message.type = 1;
	memset(message.text, 'k', sizeof(message.text));
	for (int i = 0; i < 8; i++)
		msgsnd(queue, &message, sizeof(message.text), 0);
	for (int i = 0; i < 6; i++)
		msgrcv(queue, &message, sizeof(message.text), 0, 0);
}

int main(void)
{
	mount("proc", "/proc", "proc", 0, 0);
	mount("sysfs", "/sys", "sysfs", 0, 0);
	mount("devtmpfs", "/dev", "devtmpfs", 0, 0);
	seed_kmalloc();
	if (write(1, "kernlens-demo: init running\n", 28) < 0)
		return 1;
	for (;;)
		pause();
	return 0;
}
