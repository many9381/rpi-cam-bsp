from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path

from support import REPO_ROOT, read


DOCUMENTS = (
    "README.md",
    "docs/runbooks/build-qemu.md",
    "docs/runbooks/usb-ssd-bringup.md",
    "docs/runbooks/remote-validation.md",
    "docs/runbooks/camera-validation.md",
    "docs/runbooks/eeprom-recovery.md",
    "docs/licensing/camera-h264.md",
    "docs/evidence-schema.md",
)


class DocumentationContractTest(unittest.TestCase):
    def test_readme_declares_supported_route_and_git_policy(self) -> None:
        """Catches an entry point that omits the supported hardware or workflow."""
        text = read("README.md")
        for expected in (
            "Yocto 6.0",
            "Raspberry Pi 5",
            "Camera Module 3 Wide",
            "USB SSD",
            "two planned hands-on SSD sessions",
            "`develop`",
            "`feature/SCOPE`",
            "English",
            "Conventional Commit",
        ):
            self.assertIn(expected, text)

    def test_local_links_resolve_and_bash_blocks_parse(self) -> None:
        """Catches stale navigation and operator snippets with invalid Bash."""
        for relative in DOCUMENTS:
            with self.subTest(document=relative):
                path = REPO_ROOT / relative
                self.assertTrue(path.is_file(), relative)
                text = path.read_text(encoding="utf-8")
                for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                    if re.match(r"^[a-z]+://", target) or target.startswith("#"):
                        continue
                    local_target = target.split("#", 1)[0]
                    resolved = (path.parent / local_target).resolve()
                    self.assertTrue(resolved.exists(), f"{relative}: {target}")
                for index, block in enumerate(
                    re.findall(r"```bash\n(.*?)\n```", text, flags=re.DOTALL),
                    start=1,
                ):
                    syntax = subprocess.run(
                        ["bash", "-n"],
                        input=block,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        check=False,
                    )
                    self.assertEqual(
                        syntax.returncode,
                        0,
                        f"{relative} bash block {index}: {syntax.stderr}",
                    )

    def test_runbooks_use_the_guarded_gates_and_two_ssd_sessions(self) -> None:
        """Catches bypassing a gate or expanding routine physical handling."""
        build = read("docs/runbooks/build-qemu.md")
        storage = read("docs/runbooks/usb-ssd-bringup.md")
        remote = read("docs/runbooks/remote-validation.md")
        camera = read("docs/runbooks/camera-validation.md")
        combined = "\n".join((build, storage, remote, camera))

        for expected in (
            "./scripts/host-preflight.sh --initial",
            "./scripts/test-qemu.sh --build-id \"$BUILD_ID\"",
            "artifacts/$BUILD_ID/qemu-test/PASS",
            "--profile rpi5-minimal",
            "ERASE:$TARGET_DEVICE:$BUILD_ID",
            "./scripts/test-rpi5.sh --build-id \"$BUILD_ID\" --host \"$RPI_IP\"",
            "three reboots",
            "--profile rpi5-camera",
            "./scripts/test-camera.sh --build-id \"$BUILD_ID\" --host \"$RPI_IP\"",
            "--wide-label-confirmed",
            "IMX708",
        ):
            self.assertIn(expected, combined)
        self.assertEqual(combined.count("Hands-on SSD session 1 of 2"), 1)
        self.assertEqual(combined.count("Hands-on SSD session 2 of 2"), 1)
        self.assertNotRegex(combined, r"(?m)(?:^|\s)(?:sudo\s+)?dd\s+")

    def test_no_uart_normal_route_and_eeprom_exception_are_explicit(self) -> None:
        """Catches emergency media or UART becoming a normal dependency."""
        remote = read("docs/runbooks/remote-validation.md")
        recovery = read("docs/runbooks/eeprom-recovery.md")

        for expected in (
            "USB-to-UART is not part of this project",
            "five minutes",
            "180 seconds",
            "HDMI",
        ):
            self.assertIn(expected, remote)
        self.assertNotIn("microSD", remote)
        for expected in (
            "exception path",
            "temporary microSD",
            "BOOT_ORDER",
            "USB-MSD",
            "UAS",
            "replace the bridge",
            "Do not add a UART step",
        ):
            self.assertIn(expected, recovery)

    def test_license_and_evidence_boundaries_are_explicit(self) -> None:
        """Catches external distribution or sensitive evidence becoming implicit."""
        license_text = read("docs/licensing/camera-h264.md")
        for expected in (
            "libx264",
            "GPL",
            "internal development",
            "blocks external distribution",
            "recorded review",
        ):
            self.assertIn(expected, license_text)

        evidence = read("docs/evidence-schema.md")
        self.assertIn("artifacts/releases/BUILD_ID.json", evidence)
        self.assertIn("schema version 1", evidence.lower())
        for forbidden in (
            "private key",
            "public key",
            "IP address",
            "MAC address",
            "device serial",
            "SSH host key",
            "sample media",
            "console log",
            "raw journal",
        ):
            self.assertIn(forbidden, evidence)


if __name__ == "__main__":
    unittest.main()
