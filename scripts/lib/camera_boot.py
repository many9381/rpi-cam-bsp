"""Repair only the registered SSD's camera boot configuration; never reflash it."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile

from block_device import partition_path
from codex_flash_auth import safe_path
from install_ssd import command, live_target_plan


def auto_config(original):
    retained = []
    automatic = []
    manual = []
    camera_parameters = False
    for line in original.splitlines(keepends=True):
        active = line.split("#", 1)[0].strip()
        key, separator, value = active.partition("=")
        key, value = key.strip(), value.strip()
        if active.startswith("[") or active.startswith("include "):
            raise ValueError("Conditional/included boot configuration needs manual review")
        if separator and key in ("cmdline", "overlay_prefix", "os_prefix", "kernel",
                                 "device_tree", "device_tree_overlay", "device_tree_param"):
            raise ValueError("Redirected/aliased boot configuration needs manual review")
        if separator and key == "dtparam" and camera_parameters:
            raise ValueError("Separate IMX708 parameters need manual review")
        if separator and key == "camera_auto_detect":
            if value not in ("0", "1"):
                raise ValueError("Unrecognized camera_auto_detect value")
            automatic.append("camera_auto_detect=" + value)
        elif separator and key == "dtoverlay" and value.split(",", 1)[0] == "imx708":
            if value not in ("imx708", "imx708,cam0"):
                raise ValueError("Custom IMX708 overlay parameters need manual review")
            manual.append(active)
            camera_parameters = True
        else:
            if separator and key == "dtoverlay":
                camera_parameters = False
            retained.append(line)
    if automatic == ["camera_auto_detect=1"] and not manual:
        return original
    result = "".join(retained)
    if result and not result.endswith("\n"):
        result += "\n"
    return result + "camera_auto_detect=1\n"


def inspect_config(boot):
    for relative in ("kernel_2712.img", "bcm2712-rpi-5-b.dtb", "overlays/imx708.dtbo",
                     "cmdline.txt", "config.txt"):
        path = safe_path(boot, relative)
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing Raspberry Pi camera boot artifact: {relative}")
    if "root=/dev/sda2" not in (boot / "cmdline.txt").read_text().split():
        raise ValueError("Boot partition is not configured for this project's USB SSD image")
    config = boot / "config.txt"
    if config.stat().st_size > 65536:
        raise ValueError("Unexpectedly large boot config")
    original = config.read_bytes()
    updated = auto_config(original.decode("utf-8")).encode("utf-8")
    return original, updated


def write_new(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def repair_config(boot):
    original, updated = inspect_config(boot)
    if original == updated:
        return False
    backup = safe_path(boot, "config.txt.before-camera-autodetect", missing=True)
    if backup.exists():
        if not backup.is_file() or backup.read_bytes() != original:
            raise ValueError("Existing camera boot backup differs; refusing to overwrite it")
    else:
        write_new(backup, original)
    temporary = safe_path(boot, ".config.txt.camera-autodetect.tmp", missing=True)
    # Exclusive creation refuses a stale temporary file from an interrupted run.
    write_new(temporary, updated)
    try:
        os.replace(temporary, boot / "config.txt")
        directory = os.open(boot, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)
    if inspect_config(boot) != (updated, updated):
        raise ValueError("Camera boot configuration verification failed")
    return True


def require_target(repo, fingerprint):
    plan = live_target_plan(repo)
    if plan["fingerprint"] != fingerprint:
        raise ValueError("Registered SSD identity changed before camera boot repair")
    return plan


def repair_ssd(repo, fingerprint, runtime_payload=None):
    if runtime_payload is not None:
        import camera_runtime_repair as runtime
        files = runtime.load(runtime_payload)
    if os.geteuid() != 0:
        raise ValueError("Camera boot repair needs administrator access to mount the SSD")
    plan = require_target(repo, fingerprint)
    for mounted in reversed(plan["target"]["mounted"]):
        command("umount", mounted)
    plan = require_target(repo, fingerprint)
    boot_partition = partition_path(plan["device"], 1)
    if command("lsblk", "-nro", "FSTYPE", boot_partition) != "vfat":
        raise ValueError("Registered SSD partition 1 must be FAT boot storage")
    temporary = Path(tempfile.mkdtemp(prefix="rpi5-camera-boot-"))
    boot = temporary / "boot"
    root = temporary / "root"
    try:
        boot.mkdir(mode=0o700)
        command("mount", "-o", "ro,nodev,nosuid,noexec", boot_partition, str(boot))
        try:
            original, updated = inspect_config(boot)
            changed = original != updated
            if changed:
                require_target(repo, fingerprint)
                command("mount", "-o", "remount,rw,nodev,nosuid,noexec", str(boot))
                if inspect_config(boot)[0] != original:
                    raise ValueError("Boot config changed between inspection and write")
                repair_config(boot)
                command("sync", "-f", str(boot))
                command("mount", "-o", "remount,ro,nodev,nosuid,noexec", str(boot))
            if inspect_config(boot) != (updated, updated):
                raise ValueError("Read-only verification of boot repair failed")
            require_target(repo, fingerprint)
            if runtime_payload is not None:
                root_partition = partition_path(plan["device"], 2)
                if command("lsblk", "-nro", "FSTYPE", root_partition) != "ext4":
                    raise ValueError("Camera root partition must be ext4")
                root.mkdir(mode=0o700)
                command("mount", "-o", "ro,noload,nodev,nosuid,noexec", root_partition, str(root))
                try:
                    runtime.inspect_target(root, files)
                finally:
                    command("umount", str(root))
                require_target(repo, fingerprint)
                command("mount", "-o", "rw,nodev,nosuid,noexec", root_partition, str(root))
                try:
                    backup = runtime.install(root, runtime_payload)
                    if backup is not None:
                        print("Previous runtime backed up on SSD: /" + str(backup.relative_to(root)))
                    command("sync", "-f", str(root))
                finally:
                    command("umount", str(root))
                command("mount", "-o", "ro,noload,nodev,nosuid,noexec", root_partition, str(root))
                try:
                    runtime.verify(root, runtime_payload)
                    require_target(repo, fingerprint)
                finally:
                    command("umount", str(root))
        finally:
            command("umount", str(boot))
    finally:
        # Never recursively remove a mount tree: an unsuccessful umount must
        # leave its files and mountpoint intact for recovery.
        if not os.path.ismount(boot):
            boot.rmdir()
        if root.exists() and not os.path.ismount(root):
            root.rmdir()
        if not os.path.ismount(boot) and not os.path.ismount(root):
            temporary.rmdir()
    if runtime_payload is None:
        print("PASS camera boot repair; camera_auto_detect=1; root filesystem preserved; safe to disconnect")
    else:
        print("PASS camera runtime repair; Raspberry Pi libcamera installed; accounts/config preserved; safe to disconnect")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "apply"))
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--runtime", action="store_true")
    args = parser.parse_args()
    try:
        payload = args.repo / ".state/camera-runtime-repair" if args.runtime else None
        if payload is not None:
            import camera_runtime_repair
            camera_runtime_repair.load(payload)
        if args.action == "plan":
            print(json.dumps(live_target_plan(args.repo)))
        else:
            if not args.expected_fingerprint:
                raise ValueError("Camera repair requires the preflight SSD fingerprint")
            repair_ssd(args.repo, args.expected_fingerprint, payload)
    except (ValueError, OSError, KeyError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
