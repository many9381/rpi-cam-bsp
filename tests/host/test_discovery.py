from __future__ import annotations

import os
from pathlib import Path
import stat
import tempfile
import time
import unittest

from support import REPO_ROOT, run


class DiscoveryTest(unittest.TestCase):
    def make_command(self, directory: Path, name: str, body: str) -> None:
        path = directory / name
        path.write_text(
            "#!/usr/bin/env bash\nset -euo pipefail\n" + body,
            encoding="utf-8",
        )
        path.chmod(0o755)

    def test_mdns_candidate_requires_ssh_and_is_cached(self) -> None:
        """Catches accepting mDNS data without checking the requested SSH port."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            calls = root / "calls.log"
            state = root / "last-rpi5-ip"
            self.make_command(
                fake_bin,
                "avahi-resolve-host-name",
                "printf 'rpi5-minimal.local\\t192.0.2.10\\n'\n",
            )
            self.make_command(
                fake_bin,
                "ssh-keyscan",
                "printf '%s\\n' \"$*\" >> \"$DISCOVERY_CALLS\"\n"
                "[[ \" $* \" == *\" -p 2222 \"* ]]\n"
                "[[ \"${!#}\" == \"192.0.2.10\" ]]\n"
                "printf '192.0.2.10 ssh-ed25519 AAAATEST\\n'\n",
            )
            result = run(
                "bash",
                "scripts/discover-rpi5.sh",
                "--hostname",
                "rpi5-minimal",
                "--timeout",
                "1",
                "--port",
                "2222",
                "--state-file",
                str(state),
                env={
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "DISCOVERY_CALLS": str(calls),
                    "RPI5_DISCOVERY_POLL_SECONDS": "0.01",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "192.0.2.10\n")
            self.assertEqual(state.read_text(encoding="utf-8"), "192.0.2.10\n")
            self.assertIn("-p 2222", calls.read_text(encoding="utf-8"))
            self.assertIn("Probing 192.0.2.10:2222", result.stderr)

    def test_candidates_follow_mdns_previous_cache_then_lease_order(self) -> None:
        """Catches skipping or reordering the bounded discovery sources."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            calls = root / "calls.log"
            state = root / "last-rpi5-ip"
            state.write_text("192.0.2.30\n", encoding="utf-8")
            leases = root / "dnsmasq.leases"
            leases.write_text(
                "2147483647 dc:a6:32:00:00:99 198.51.100.99 other-host *\n"
                "2147483647 dc:a6:32:00:00:01 198.51.100.23 rpi5-minimal *\n",
                encoding="utf-8",
            )
            self.make_command(
                fake_bin,
                "avahi-resolve-host-name",
                "printf 'rpi5-minimal.local\\t192.0.2.10\\n'\n",
            )
            self.make_command(
                fake_bin,
                "ssh-keyscan",
                "candidate=\"${!#}\"\n"
                "printf '%s\\n' \"$candidate\" >> \"$DISCOVERY_CALLS\"\n"
                "[[ \"$candidate\" == \"198.51.100.23\" ]] || exit 1\n"
                "printf '%s ssh-ed25519 AAAATEST\\n' \"$candidate\"\n",
            )
            result = run(
                "bash",
                "scripts/discover-rpi5.sh",
                "--hostname",
                "rpi5-minimal",
                "--previous-ip",
                "192.0.2.20",
                "--lease-file",
                str(leases),
                "--timeout",
                "2",
                "--state-file",
                str(state),
                env={
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "DISCOVERY_CALLS": str(calls),
                    "RPI5_DISCOVERY_POLL_SECONDS": "0.01",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "198.51.100.23\n")
            self.assertEqual(
                calls.read_text(encoding="utf-8").splitlines(),
                ["192.0.2.10", "192.0.2.20", "192.0.2.30", "198.51.100.23"],
            )
            self.assertEqual(state.read_text(encoding="utf-8"), "198.51.100.23\n")

    def test_retries_candidates_until_ssh_becomes_reachable(self) -> None:
        """Catches treating an early SSH miss as a final discovery failure."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            attempts = root / "attempts"
            state = root / "last-rpi5-ip"
            self.make_command(
                fake_bin,
                "avahi-resolve-host-name",
                "printf 'rpi5-minimal.local\\t203.0.113.12\\n'\n",
            )
            self.make_command(
                fake_bin,
                "ssh-keyscan",
                "count=0\n"
                "[[ ! -f \"$DISCOVERY_ATTEMPTS\" ]] || "
                "count=\"$(<\"$DISCOVERY_ATTEMPTS\")\"\n"
                "count=$((count + 1))\n"
                "printf '%s\\n' \"$count\" > \"$DISCOVERY_ATTEMPTS\"\n"
                "(( count >= 2 )) || exit 1\n"
                "printf '203.0.113.12 ssh-ed25519 AAAATEST\\n'\n",
            )
            result = run(
                "bash",
                "scripts/discover-rpi5.sh",
                "--hostname",
                "rpi5-minimal",
                "--timeout",
                "2",
                "--state-file",
                str(state),
                env={
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "DISCOVERY_ATTEMPTS": str(attempts),
                    "RPI5_DISCOVERY_POLL_SECONDS": "0.01",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "203.0.113.12\n")
            self.assertEqual(attempts.read_text(encoding="utf-8"), "2\n")

    def test_matching_mac_selects_lease_when_hostname_does_not_match(self) -> None:
        """Catches depending on a DHCP hostname when a MAC hint was supplied."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            state = root / "last-rpi5-ip"
            leases = root / "dnsmasq.leases"
            leases.write_text(
                "2147483647 dc:a6:32:00:00:98 198.51.100.98 unknown *\n"
                "2147483647 dc:a6:32:00:00:45 198.51.100.45 * *\n",
                encoding="utf-8",
            )
            self.make_command(fake_bin, "avahi-resolve-host-name", "exit 1\n")
            self.make_command(
                fake_bin,
                "ssh-keyscan",
                "[[ \"${!#}\" == \"198.51.100.45\" ]] || exit 1\n"
                "printf '198.51.100.45 ssh-ed25519 AAAATEST\\n'\n",
            )
            result = run(
                "bash",
                "scripts/discover-rpi5.sh",
                "--hostname",
                "rpi5-minimal",
                "--lease-file",
                str(leases),
                "--mac",
                "DC:A6:32:00:00:45",
                "--timeout",
                "1",
                "--state-file",
                str(state),
                env={
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "RPI5_DISCOVERY_POLL_SECONDS": "0.01",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "198.51.100.45\n")
            self.assertEqual(state.read_text(encoding="utf-8"), "198.51.100.45\n")

    def test_hanging_mdns_cannot_exceed_the_discovery_deadline(self) -> None:
        """Catches an mDNS command that can outlive the overall timeout."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            self.make_command(
                fake_bin,
                "avahi-resolve-host-name",
                "sleep 2\nexit 1\n",
            )
            self.make_command(fake_bin, "ssh-keyscan", "exit 1\n")
            started = time.monotonic()
            result = run(
                "bash",
                "scripts/discover-rpi5.sh",
                "--timeout",
                "1",
                "--state-file",
                str(root / "state"),
                env={
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "RPI5_DISCOVERY_POLL_SECONDS": "0.01",
                },
            )
            elapsed = time.monotonic() - started

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertLess(elapsed, 1.8, result.stderr)
            self.assertIn("within 1s", result.stderr)

    def test_hanging_ssh_probe_cannot_exceed_the_discovery_deadline(self) -> None:
        """Catches an SSH probe that can outlive the overall timeout."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            self.make_command(
                fake_bin,
                "avahi-resolve-host-name",
                "printf 'rpi5-minimal.local\\t203.0.113.50\\n'\n",
            )
            self.make_command(fake_bin, "ssh-keyscan", "sleep 2\nexit 1\n")
            started = time.monotonic()
            result = run(
                "bash",
                "scripts/discover-rpi5.sh",
                "--timeout",
                "1",
                "--state-file",
                str(root / "state"),
                env={
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "RPI5_DISCOVERY_POLL_SECONDS": "0.01",
                },
            )
            elapsed = time.monotonic() - started

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertLess(elapsed, 1.8, result.stderr)
            self.assertIn("within 1s", result.stderr)

    def test_truncated_value_options_print_usage_without_nounset_errors(self) -> None:
        """Catches value-bearing options reading an absent positional argument."""
        for option in (
            "--hostname",
            "--timeout",
            "--previous-ip",
            "--lease-file",
            "--mac",
            "--port",
            "--state-file",
        ):
            with self.subTest(option=option):
                result = run("bash", "scripts/discover-rpi5.sh", option)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("Usage:", result.stderr)
                self.assertNotIn("unbound variable", result.stderr)

    def test_invalid_inputs_fail_before_any_network_command(self) -> None:
        """Catches malformed discovery hints reaching network commands."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            network_used = root / "network-used"
            self.make_command(
                fake_bin,
                "avahi-resolve-host-name",
                "touch \"$DISCOVERY_NETWORK_USED\"\nexit 1\n",
            )
            self.make_command(
                fake_bin,
                "ssh-keyscan",
                "touch \"$DISCOVERY_NETWORK_USED\"\nexit 1\n",
            )
            cases = (
                (("--timeout", "0"), "timeout must be a positive integer"),
                (("--port", "65536"), "invalid SSH port"),
                (("--hostname", "bad/name"), "invalid hostname"),
                (("--previous-ip", "999.2.3.4"), "invalid previous IP"),
                (("--mac", "not-a-mac"), "invalid MAC address"),
                (
                    ("--lease-file", str(root / "missing.leases")),
                    "lease file is not a readable regular file",
                ),
            )
            for arguments, expected_error in cases:
                with self.subTest(arguments=arguments):
                    network_used.unlink(missing_ok=True)
                    result = run(
                        "bash",
                        "scripts/discover-rpi5.sh",
                        "--timeout",
                        "1",
                        *arguments,
                        "--state-file",
                        str(root / "state"),
                        env={
                            "PATH": f"{fake_bin}:{os.environ['PATH']}",
                            "DISCOVERY_NETWORK_USED": str(network_used),
                            "RPI5_DISCOVERY_POLL_SECONDS": "0.01",
                        },
                    )
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(expected_error, result.stderr)
                    self.assertFalse(network_used.exists(), result.stderr)

    def test_invalid_poll_interval_fails_before_any_network_command(self) -> None:
        """Catches an invalid poll interval causing a busy discovery loop."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            network_used = root / "network-used"
            for command in ("avahi-resolve-host-name", "ssh-keyscan"):
                self.make_command(
                    fake_bin,
                    command,
                    "touch \"$DISCOVERY_NETWORK_USED\"\nexit 1\n",
                )
            result = run(
                "bash",
                "scripts/discover-rpi5.sh",
                "--timeout",
                "1",
                "--state-file",
                str(root / "state"),
                env={
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "DISCOVERY_NETWORK_USED": str(network_used),
                    "RPI5_DISCOVERY_POLL_SECONDS": "not-a-number",
                },
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("poll interval must be a positive number", result.stderr)
            self.assertFalse(network_used.exists(), result.stderr)

    def test_non_regular_lease_file_fails_before_network_commands(self) -> None:
        """Catches a lease FIFO blocking beyond the discovery deadline."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            network_used = root / "network-used"
            lease_fifo = root / "dnsmasq.leases"
            os.mkfifo(lease_fifo)
            for command in ("avahi-resolve-host-name", "ssh-keyscan", "awk"):
                self.make_command(
                    fake_bin,
                    command,
                    "touch \"$DISCOVERY_NETWORK_USED\"\nexit 1\n",
                )
            result = run(
                "bash",
                "scripts/discover-rpi5.sh",
                "--lease-file",
                str(lease_fifo),
                "--timeout",
                "1",
                "--state-file",
                str(root / "state"),
                env={
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "DISCOVERY_NETWORK_USED": str(network_used),
                    "RPI5_DISCOVERY_POLL_SECONDS": "0.01",
                },
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("lease file is not a readable regular file", result.stderr)
            self.assertFalse(network_used.exists(), result.stderr)

    def test_non_regular_state_file_is_never_read(self) -> None:
        """Catches a cached-address FIFO blocking beyond the deadline."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            state_read = root / "state-read"
            state_fifo = root / "last-rpi5-ip"
            os.mkfifo(state_fifo)
            self.make_command(fake_bin, "avahi-resolve-host-name", "exit 1\n")
            self.make_command(fake_bin, "ssh-keyscan", "exit 1\n")
            self.make_command(
                fake_bin,
                "head",
                "touch \"$DISCOVERY_STATE_READ\"\n"
                "printf '192.0.2.88\\n'\n",
            )
            result = run(
                "bash",
                "scripts/discover-rpi5.sh",
                "--timeout",
                "1",
                "--state-file",
                str(state_fifo),
                env={
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "DISCOVERY_STATE_READ": str(state_read),
                    "RPI5_DISCOVERY_POLL_SECONDS": "0.01",
                },
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("within 1s", result.stderr)
            self.assertFalse(state_read.exists(), result.stderr)

    def test_help_is_non_destructive(self) -> None:
        """Catches help output performing discovery or creating state."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            network_used = root / "network-used"
            for command in ("avahi-resolve-host-name", "ssh-keyscan"):
                self.make_command(
                    fake_bin,
                    command,
                    "touch \"$DISCOVERY_NETWORK_USED\"\nexit 99\n",
                )
            result = run(
                "bash",
                "scripts/discover-rpi5.sh",
                "--help",
                env={
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "DISCOVERY_NETWORK_USED": str(network_used),
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("Usage:", result.stdout)
            self.assertEqual(result.stderr, "")
            self.assertFalse(network_used.exists())

    def test_cache_update_replaces_symlink_without_touching_its_target(self) -> None:
        """Catches state writes that follow a pre-existing symbolic link."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            protected = root / "protected"
            protected.write_text("keep-me\n", encoding="utf-8")
            state = root / "last-rpi5-ip"
            state.symlink_to(protected)
            self.make_command(
                fake_bin,
                "avahi-resolve-host-name",
                "printf 'rpi5-minimal.local\\t192.0.2.77\\n'\n",
            )
            self.make_command(
                fake_bin,
                "ssh-keyscan",
                "printf '192.0.2.77 ssh-ed25519 AAAATEST\\n'\n",
            )
            result = run(
                "bash",
                "scripts/discover-rpi5.sh",
                "--timeout",
                "1",
                "--state-file",
                str(state),
                env={
                    "PATH": f"{fake_bin}:{os.environ['PATH']}",
                    "RPI5_DISCOVERY_POLL_SECONDS": "0.01",
                },
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(protected.read_text(encoding="utf-8"), "keep-me\n")
            self.assertFalse(state.is_symlink())
            self.assertEqual(state.read_text(encoding="utf-8"), "192.0.2.77\n")
            self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o600)

    def test_entrypoint_is_directly_executable(self) -> None:
        """Catches losing the executable mode required by operator runbooks."""
        script = REPO_ROOT / "scripts/discover-rpi5.sh"
        self.assertTrue(os.access(script, os.X_OK), script)

    def test_script_is_valid_bash(self) -> None:
        """Catches syntax errors before discovery touches the network."""
        result = run("bash", "-n", "scripts/discover-rpi5.sh")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
