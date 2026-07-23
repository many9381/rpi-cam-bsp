import re
import unittest

from support import REPO_ROOT, read, run


class HostToolsTest(unittest.TestCase):
    def test_new_build_id_uses_utc_and_current_commit(self) -> None:
        result = run("bash", "scripts/new-build-id.sh")
        self.assertEqual(result.returncode, 0, result.stderr)
        build_id = result.stdout.strip()
        self.assertRegex(build_id, r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")
        sha = run("git", "rev-parse", "--short=12", "HEAD").stdout.strip()
        self.assertTrue(build_id.endswith(f"-{sha}"))

    def test_common_library_accepts_only_canonical_build_ids(self) -> None:
        good = run(
            "bash",
            "-c",
            "source scripts/lib/common.sh; "
            "rpi5_validate_build_id 20260722T120000Z-0123456789ab",
        )
        bad = run(
            "bash",
            "-c",
            "source scripts/lib/common.sh; rpi5_validate_build_id latest",
        )
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertNotEqual(bad.returncode, 0)

    def test_preflight_has_both_disk_modes_and_required_tools(self) -> None:
        script = read("scripts/host-preflight.sh")
        self.assertIn("--initial", script)
        self.assertIn("146800640", script)
        self.assertIn("--incremental", script)
        self.assertIn("20971520", script)
        for command in (
            "uv",
            "bmaptool",
            "qemu-system-aarch64",
            "avahi-resolve-host-name",
            "partprobe",
            "ffprobe",
        ):
            self.assertIn(command, script)

    def test_preflight_rejects_uv_environment_override_before_uv_commands(
        self,
    ) -> None:
        script = read("scripts/host-preflight.sh")
        override_check = script.index("UV_PROJECT_ENVIRONMENT")
        first_uv_command = min(
            script.index("uv lock --check"),
            script.index("uv run --locked"),
        )
        self.assertLess(override_check, first_uv_command)

    def test_scripts_are_valid_bash(self) -> None:
        for path in (
            "scripts/lib/common.sh",
            "scripts/new-build-id.sh",
            "scripts/host-preflight.sh",
        ):
            result = run("bash", "-n", path)
            self.assertEqual(result.returncode, 0, f"{path}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
