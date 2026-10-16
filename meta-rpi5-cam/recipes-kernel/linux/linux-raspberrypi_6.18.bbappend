# Stay on the Raspberry Pi 6.18 line used by the validated Pi 5 image.
# https://github.com/raspberrypi/linux/commit/4103a989a46196239b830bd07693277e42b8f992
# The inherited kernel-meta pin and board configuration remain in force.
LINUX_VERSION = "6.18.55"
SRCREV_machine = "4103a989a46196239b830bd07693277e42b8f992"

# Stable 6.18.56 IPv4 lifetime fix, pending its Raspberry Pi branch merge.
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
SRC_URI += "file://0001-ipv4-free-options-after-rcu-grace-period.patch"

# Narrow upstream security fixes reviewed against the validated Pi 6.18.55 source.
# Keep the downstream source pin, kernel metadata and board/Hailo configuration.
SRC_URI += " \
    file://0002-arm64-ptrace-sync-syscall-argument.patch \
    file://0003-cfg80211-check-he-eht-elements.patch \
    file://0004-bpf-validate-null-inference.patch \
    file://0005-bpf-check-pointer-offset-bounds.patch \
    file://0006-bpf-mark-syscall-helpers-sleepable.patch \
    file://0007-xfrm-hold-device-under-rcu.patch \
    file://0008-tty-check-registered-cdev.patch \
    file://0009-serial-clear-freed-driver-pointers.patch \
    file://0010-sunrpc-reject-short-mic-tokens.patch \
    file://0011-netlink-protect-group-bitmap-readers.patch \
    file://0012-nfs-zero-referring-call-lists.patch \
    file://0013-btrfs-check-inline-lzo-headers.patch \
"

# 2026-10-13 source-reviewed follow-up. Keep image-specific module exclusions
# in the security assessment; do not suppress source CVEs in recipe metadata.
SRC_URI += " \
    file://0020-fbdev-bound-mode-sysfs-output.patch \
    file://0021-bpf-check-percpu-inner-map-size.patch \
    file://0022-netfilter-bound-bridge-vlan-untag.patch \
    file://0023-blktrace-record-cmdline-after-reservation.patch \
    file://0024-printk-handle-kthread-errors-without-warning.patch \
    file://0025-fbdev-clear-deleted-mode-pointer.patch \
    file://0026-bpf-check-socket-state-before-protocol.patch \
    file://0060-bpf-compare-iterator-pointer-types.patch \
    file://0061-bpf-backtrack-implicit-subprogram-exits.patch \
    file://0062-bpf-bound-kfunc-return-buffer-size.patch \
    file://0063-bpf-record-all-atomic-pointer-types.patch \
    file://0064-bpf-zero-extend-arena-cmpxchg.patch \
    file://0065-mac80211-bound-s1g-tim-payload.patch \
"

# Residual security fixes, reviewed against the same Pi source and configuration.
SRC_URI += " \
    file://0100-preserve-map-identity-in-callbacks.patch \
    file://0101-reject-untrusted-btf-writes.patch \
    file://0102-invalidate-rcu-after-last-unlock.patch \
    file://0103-require-jit-for-unsupported-interpreter-programs.patch \
    file://0104-clear-cloned-socket-storage-before-bailouts.patch \
    file://0105-reject-local-storage-deletion-from-nmi.patch \
    file://0120-ext4-reject-cross-superblock-donor-early.patch \
    file://0121-scsi-sd-release-special-payload-on-setup-error.patch \
    file://0122-scsi-pair-eh-runtime-pm-using-one-snapshot.patch \
    file://0123-nexthop-protect-ipv6-replace-list-lifetimes.patch \
    file://0124-wifi-ibss-own-bss-reference-in-joined-event.patch \
    file://0125-f2fs-wait-for-checkpoint-before-reading-nat-flags.patch \
    file://0126-kvm-gmem-use-unsigned-binding-offset-and-size.patch \
    file://0127-net-sched-reject-qdisc-redirect-verdicts.patch \
"

# 2026-10-14 reviewed kernel follow-up; preserve the accepted board configuration.
SRC_URI += " \
    file://0200-bound-allocated-btf-object-walks.patch \
    file://0201-preserve-fastcall-patterns-with-incoming-jumps.patch \
    file://0202-keep-borrowed-refcount-acquire-nullable.patch \
    file://0203-reject-large-return-reading-trampolines.patch \
    file://0204-propagate-precision-for-null-helper-arguments.patch \
    file://0205-account-classifier-filter-allocations.patch \
    file://0220-serial-allocate-before-console-publication.patch \
    file://0221-pci-copy-dynamic-id-under-lock.patch \
    file://0222-iomap-release-pins-on-atomic-size-rejection.patch \
    file://0223-f2fs-use-folio-owner-for-atomic-cow-read.patch \
    file://0224-fbdev-serialize-user-mode-updates.patch \
    file://0225-thermal-remove-shared-hwmon-with-parent.patch \
    file://0226-ipv6-publish-multicast-lists-with-rcu.patch \
    file://0227-ip6mr-drop-dst-before-report-and-unresolved-queue.patch \
    file://0228-nfs-return-unrecorded-delegation-grants.patch \
    file://0229-net-validate-and-pull-gso-before-transmit.patch \
    file://0230-wifi-use-wiphy-work-for-owner-autodisconnect.patch \
    file://0231-kvm-vgic-serialize-lpi-release-and-reregistration.patch \
    file://0232-nvme-pci-close-dma-and-p2p-tracking-leaks.patch \
    file://0240-ext4-check-reserved-inodes-before-lazy-zeroing.patch \
"

# 2026-10-14 reviewed kernel follow-up; preserve the accepted board configuration.
SRC_URI += " \
    file://0320-io-uring-zcrx-retain-queue-until-providers-release.patch \
    file://0321-block-validate-direct-io-memory-alignment.patch \
    file://0340-nvme-initialize-fdp-before-head-publication.patch \
    file://0360-tracing-own-read-page-size-across-subbuffer-resize.patch \
"

# 2026-10-14 reviewed arena/NVMe boundary follow-up.
SRC_URI += " \
    file://0400-bpf-arena-protect-mapped-vma-lifetimes.patch \
    file://0401-nvme-bound-fdp-response-parsing.patch \
"

# Policy package installs nf_tables: fix its newly reachable expression paths.
SRC_URI += " \
    file://0420-nftables-borrow-default-set-expressions.patch \
    file://0421-nft-dynset-mark-serialized-expression-lists.patch \
"

# Bound catch-up work in the installed fq_codel module.
SRC_URI += "file://0430-codel-bound-dequeue-drop-work.patch"
