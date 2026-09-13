"""Provision local Wi-Fi secrets into an image, never a shared package."""

import json
import os
from pathlib import Path
import re
import stat
import tempfile


def _check_private_file(info):
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
        raise ValueError("Wi-Fi input must be a regular, non-symlink file with mode 0600")


def rootfs_checksums(machine, config_file, helper_file):
    """Track secret creation/removal/content in rootfs signatures, not packages."""
    if machine != "raspberrypi5":
        return ""
    for path in (config_file, helper_file):
        if not os.path.isabs(path) or any(c.isspace() or c in ":*?[]" for c in str(path)):
            raise ValueError("Wi-Fi input paths must be absolute without whitespace, colons or globs")
    try:
        _check_private_file(os.lstat(config_file))
        present = True
    except FileNotFoundError:
        present = False
    return f" {config_file}:{present} {helper_file}:True"


def _load_config(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return None
    except OSError:
        raise ValueError("Cannot safely open local Wi-Fi input") from None
    with os.fdopen(fd, "rb") as source:
        _check_private_file(os.fstat(source.fileno()))
        raw = source.read(4097)
        if len(raw) > 4096:
            raise ValueError("Wi-Fi input must be at most 4096 bytes")
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeError):
            raise ValueError("Wi-Fi input must be a small UTF-8 JSON object") from None
    if not isinstance(data, dict) or set(data) != {"ssid", "psk", "country"}:
        raise ValueError("Wi-Fi input requires exactly ssid, psk and country")
    if not all(isinstance(value, str) for value in data.values()):
        raise ValueError("Wi-Fi input fields must be strings")
    try:
        ssid = data["ssid"].encode("utf-8")
    except UnicodeError:
        raise ValueError("Wi-Fi SSID must be valid UTF-8") from None
    if not 1 <= len(ssid) <= 32:
        raise ValueError("Wi-Fi SSID must contain 1 to 32 UTF-8 bytes")
    if re.fullmatch(r"[0-9a-fA-F]{64}", data["psk"]) is None:
        raise ValueError("Wi-Fi PSK must be exactly 64 hexadecimal characters, not a passphrase")
    if re.fullmatch(r"[a-zA-Z]{2}", data["country"]) is None:
        raise ValueError("Wi-Fi country must be a two-letter country code")
    return (
        "ctrl_interface=DIR=/run/wpa_supplicant GROUP=root\n"
        "update_config=0\n"
        f"country={data['country'].upper()}\n\nnetwork={{\n"
        f"    ssid={ssid.hex()}\n"
        f"    psk={data['psk'].lower()}\n"
        "    key_mgmt=WPA-PSK\n    proto=RSN\n}\n"
    )


def install_wifi_config(config_file, rootfs, sysconfdir="/etc"):
    """Return whether an optional local config was installed; never log secrets."""
    # Check lstat first, including dangling symlinks and FIFOs; never block on input.
    try:
        _check_private_file(os.lstat(config_file))
    except FileNotFoundError:
        pass
    content = _load_config(config_file)
    relative = Path(sysconfdir.lstrip("/")) / "wpa_supplicant"
    if ".." in relative.parts:
        raise ValueError("Wi-Fi destination must remain inside the image")
    directory = Path(rootfs)
    for part in relative.parts:
        directory = directory / part
        if directory.is_symlink():
            raise ValueError("Wi-Fi destination directories must not be symlinks")
    target = directory / "wpa_supplicant-wlan0.conf"
    if content is None:
        target.unlink(missing_ok=True)
        return False
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    # mkstemp is private even with a permissive build umask. os.replace prevents
    # following an existing destination symlink or leaving a partially written PSK.
    fd, temporary = tempfile.mkstemp(prefix=".wifi-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="ascii") as destination:
            destination.write(content)
        os.replace(temporary, target)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return True
