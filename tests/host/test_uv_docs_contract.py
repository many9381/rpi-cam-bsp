import re
import unittest

from support import read


DESIGN_DOCUMENT = (
    "docs/superpowers/specs/"
    "2026-07-22-rpi5-yocto-build-validation-design.md"
)
IMPLEMENTATION_PLAN = (
    "docs/superpowers/plans/"
    "2026-07-22-rpi5-yocto-firmware-implementation.md"
)
UV_IMPLEMENTATION_PLAN = (
    "docs/superpowers/plans/"
    "2026-07-23-uv-python-environment-implementation.md"
)
UV_DESIGN = (
    "docs/superpowers/specs/"
    "2026-07-23-uv-python-environment-design.md"
)
UV_RELEASE_URL = (
    "https://releases.astral.sh/github/uv/releases/download/0.11.31/"
    "uv-x86_64-unknown-linux-gnu.tar.gz"
)
UV_RELEASE_SHA256 = (
    "8cc1cd82d434ec565376f98bd938d4b715b5791a80ff2d3aa"
    "78821cf85091b4b"
)
UV_RELEASE_PAGE = "https://github.com/astral-sh/uv/releases/tag/0.11.31"
LEGACY_FRAGMENTS = (
    "python3 -m venv",
    ".venv/bin/activate",
    "pip install",
    "uv pip install",
)
DIRECT_TOOL = re.compile(
    r"(^\s*|(?:&&|\|\||;|\||\$\(|`)\s*)"
    r"(?:(?:[A-Za-z_][A-Za-z0-9_]*="
    r"(?:[^\s;&|]+|'[^']*'|\"[^\"]*\"))\s+|"
    r"(?:(?:sudo|env|exec|time|setsid)\s+))*"
    r"(?:python3?|kas)(?=\s|$)"
)
DIRECT_TOOL_NEGATIVE_FIXTURES = (
    "sudo python scripts/check.py",
    "env kas dump kas/rpi5-minimal.yml",
    "exec python -m unittest",
    "time kas --version",
    "FOO=bar python scripts/check.py",
    "setsid kas shell kas/qemuarm64-minimal.yml",
)
UV_PLAN_BOOTSTRAP_DIRECT_TOOL_FIXTURES = (
    "python3 --version",
    "python3 -m unittest discover -s tests/host -p 'test_*.py' -v",
    "python3 -m unittest discover -s tests/host "
    "-p 'test_repository_contract.py' -v",
    "python3 -m unittest discover -s tests/host "
    "-p 'test_uv_environment_contract.py' -v",
    "python3 -m unittest discover -s tests/host "
    "-p 'test_repository_contract.py' -v",
    "python3 -m unittest discover -s tests/host "
    "-p 'test_uv_environment_contract.py' -v",
)
INDIRECT_KAS_FRAGMENTS = (
    "run_logged kas ",
    "setsid kas ",
    "rpi5_require_cmd kas",
    'rpi5_require_cmd "kas"',
    "command -v kas",
)


def shell_lines(markdown: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    in_shell_fence = False
    for line_number, line in enumerate(markdown.splitlines(), start=1):
        stripped = line.strip()
        if stripped in ("```bash", "```sh", "```shell"):
            in_shell_fence = True
            continue
        if stripped.startswith("```"):
            in_shell_fence = False
            continue
        if in_shell_fence:
            lines.append((line_number, line))
        elif stripped.startswith("Run: `") and stripped.endswith("`"):
            lines.append((line_number, stripped.removeprefix("Run: `")[:-1]))
    return lines


def embedded_shell(markdown: str, marker: str) -> str:
    _, separator, remainder = markdown.partition(marker)
    if not separator:
        raise AssertionError(f"missing embedded shell marker: {marker}")
    return remainder.partition("```")[0]


class UvDocsContractTest(unittest.TestCase):
    def assert_exact_embedded_environment_contracts(
        self,
        text: str,
        expected_copies: int,
    ) -> None:
        expected = read(
            "tests/host/test_uv_environment_contract.py"
        ).rstrip("\n")
        actual = [
            match.group(1)
            for match in re.finditer(r"```python\n(.*?)\n```", text, re.S)
            if "class UvEnvironmentContractTest" in match.group(1)
        ]
        self.assertEqual(len(actual), expected_copies)
        self.assertEqual(actual, [expected] * expected_copies)

    def assert_authenticated_privileged_uv_flow(self, text: str) -> None:
        self.assertNotIn("UV_BIN", text)
        for fragment in (
            UV_RELEASE_URL,
            UV_RELEASE_SHA256,
            UV_RELEASE_PAGE,
            'uv_archive="${UV_ARCHIVE:-}"',
            '[[ "$uv_archive" = /* && -f "$uv_archive" && ! -L "$uv_archive" ]]',
            "mktemp -d /var/tmp/rpi5-flash-uv.",
            '[[ -d "$uv_private_dir" && ! -L "$uv_private_dir" ]]',
            '[[ "$(stat -c %u "$uv_private_dir")" == "0" ]]',
            'install -m 0600 -- "$uv_archive" "$uv_archive_copy"',
            '[[ -f "$uv_archive_copy" && ! -L "$uv_archive_copy" ]]',
            '[[ "$(stat -c %u "$uv_archive_copy")" == "$EUID" ]]',
            "sha256sum --check --strict",
            "--gzip",
            "--no-same-owner",
            "--no-same-permissions",
            'uv_bin="$uv_extract_dir/uv-x86_64-unknown-linux-gnu/uv"',
            '[[ -f "$uv_bin" && ! -L "$uv_bin" ]]',
            'chmod 0700 "$uv_bin"',
            '[[ "$(stat -c %u "$uv_bin")" == "$EUID"',
            'find "$uv_private_dir" -xdev -depth -delete',
            'sudo UV_ARCHIVE="$UV_ARCHIVE" ./scripts/flash-ssd.sh',
            "test_spoofed_uv_executable_is_rejected",
            "SPOOF_EXECUTED",
            "printf 'uv 0.11.31",
            'self.assertFalse(marker.exists(), "spoofed executable was run")',
        ):
            self.assertIn(fragment, text)

    def assert_physical_venv_gates(self, text: str) -> None:
        for fragment in (
            'test -z "${UV_PROJECT_ENVIRONMENT:-}"',
            "test -d .venv",
            "test ! -L .venv",
            'test "$(realpath .venv)" = "$(pwd -P)/.venv"',
            "assert pathlib.Path(sys.prefix).resolve() == expected",
            "assert sys.version_info[:2] == (3, 12)",
        ):
            self.assertGreaterEqual(text.count(fragment), 4, fragment)

    def assert_strengthened_environment_plan(
        self,
        text: str,
        expected_copies: int = 1,
    ) -> None:
        for environment_contract in (
            "def validate_lock(lock: dict)",
            "test_running_environment_is_physical_checkout_local_venv",
            "test_environment_contract_rejects_external_override",
            "test_environment_contract_rejects_symlinked_venv",
            "test_lock_validator_rejects_structural_corruption",
            'self.lock["requires-python"], "==3.12.*"',
            '"version": "0.0.0"',
            '"source": {"virtual": "."}',
            '"registry": "https://pypi.org/simple"',
            "kas registry source must be exact",
            "duplicate package names",
            "missing dependency",
            "registry closure mismatch",
            "invalid sdist hash",
            "missing wheels",
            "invalid wheel hash",
        ):
            self.assertGreaterEqual(
                text.count(environment_contract),
                expected_copies,
                environment_contract,
            )

    def assert_locked_uv_document(self, relative: str) -> str:
        text = read(relative)
        for fragment in LEGACY_FRAGMENTS:
            self.assertNotIn(fragment, text, f"{relative}: {fragment}")
        offenders = [
            f"{line_number}: {line}"
            for line_number, line in shell_lines(text)
            if DIRECT_TOOL.search(line)
        ]
        self.assertEqual(offenders, [], relative)
        return text

    def assert_secure_flash_script_order(self, text: str) -> None:
        script = embedded_shell(text, "# scripts/flash-ssd.sh\n")
        for forbidden in ("UV_BIN", "curl ", "wget ", "sudo -E"):
            self.assertNotIn(forbidden, script)
        ordered = (
            'install -m 0600 -- "$uv_archive" "$uv_archive_copy"',
            "sha256sum --check --strict",
            "tar --extract",
            '"$uv_bin" --version',
            '"$uv_bin" run --locked',
        )
        positions = [script.index(fragment) for fragment in ordered]
        self.assertEqual(positions, sorted(positions))
        first_block_operation = min(
            script.index(fragment)
            for fragment in ("findmnt ", "lsblk ", "bmaptool ")
        )
        self.assertLess(script.index('"$uv_bin" --version'), first_block_operation)

    def test_direct_tool_detector_rejects_wrappers_and_assignments(self) -> None:
        for command in DIRECT_TOOL_NEGATIVE_FIXTURES:
            with self.subTest(command=command):
                self.assertIsNotNone(DIRECT_TOOL.search(command))

    def test_direct_tool_detector_allows_locked_uv_under_setsid(self) -> None:
        command = (
            "setsid uv run --locked kas shell "
            "kas/qemuarm64-minimal.yml -c runqemu"
        )
        self.assertIsNone(DIRECT_TOOL.search(command))

    def test_build_design_uses_locked_uv_commands(self) -> None:
        text = self.assert_locked_uv_document(DESIGN_DOCUMENT)
        self.assertNotIn("requirements-build.txt", text)
        self.assertIn("uv lock --check", text)
        self.assertIn("uv sync --locked", text)
        self.assertGreaterEqual(text.count("uv run --locked kas"), 8)

    def test_firmware_plan_uses_locked_uv_commands(self) -> None:
        text = self.assert_locked_uv_document(IMPLEMENTATION_PLAN)
        for fragment in INDIRECT_KAS_FRAGMENTS:
            self.assertNotIn(fragment, text)
        self.assertNotIn("- Create: `requirements-build.txt`", text)
        self.assertNotIn("# requirements-build.txt", text)
        self.assertNotRegex(text, r"git add [^\n]*requirements-build\.txt")
        self.assertIn(
            'self.assertFalse((REPO_ROOT / "requirements-build.txt").exists())',
            text,
        )
        self.assertIn("| `pyproject.toml` |", text)
        self.assertIn("| `uv.lock` |", text)
        self.assertIn("| `.python-version` |", text)
        self.assertIn("required-version = \"==0.11.31\"", text)
        self.assertIn("python-preference = \"only-system\"", text)
        self.assertGreaterEqual(text.count("uv run --locked python"), 25)
        self.assertGreaterEqual(text.count("uv run --locked kas"), 15)
        self.assertIn("run_logged uv run --locked kas", text)
        self.assertIn("setsid uv run --locked kas shell", text)
        self.assertIn("uv run --locked kas for-all-repos", text)
        self.assertIn(
            '"$uv_bin" run --locked python "$helper" validate',
            text,
        )
        self.assertNotIn("sudo ./scripts/flash-ssd.sh", text)
        self.assert_authenticated_privileged_uv_flow(text)
        self.assert_secure_flash_script_order(text)
        self.assert_physical_venv_gates(text)
        self.assert_strengthened_environment_plan(text)
        self.assert_exact_embedded_environment_contracts(text, 1)
        self.assertIn(
            'repo_root="$(rpi5_repo_root)"\ncd "$repo_root"\nuv_archive=',
            text,
        )
        self.assertIn(
            'repo_root="$(rpi5_repo_root)"\ncd "$repo_root"\nhostname=',
            text,
        )
        self.assertGreaterEqual(
            text.count(
                'git commit -m "chore: add uv-managed Yocto workspace guardrails"'
            ),
            2,
        )

    def test_uv_migration_plan_matches_final_secure_flow(self) -> None:
        text = read(UV_IMPLEMENTATION_PLAN)
        direct_tools = [
            line
            for _, line in shell_lines(text)
            if DIRECT_TOOL.search(line)
        ]
        self.assertEqual(
            direct_tools,
            list(UV_PLAN_BOOTSTRAP_DIRECT_TOOL_FIXTURES),
        )
        self.assert_authenticated_privileged_uv_flow(text)
        self.assert_physical_venv_gates(text)
        self.assertNotIn(
            'validate --topology "$topology" \\\n    --device "$target_device"',
            text,
        )
        for helper_call in (
            '"$uv_bin" run --locked python "$helper" bmap-size',
            '"$uv_bin" run --locked python "$helper" validate',
            '"$uv_bin" run --locked python "$helper" mounts',
            '"$uv_bin" run --locked python "$helper" partition',
        ):
            self.assertIn(helper_call, text)
        self.assertIn("--target \"$device\"", text)
        self.assertIn("setsid uv run --locked kas shell", text)
        self.assertIn(
            'self.assertIn("setsid uv run --locked kas shell", script)',
            text,
        )
        self.assert_strengthened_environment_plan(text, expected_copies=2)
        self.assert_exact_embedded_environment_contracts(text, 2)
        self.assertGreaterEqual(
            text.count('repo_root="$(rpi5_repo_root)"\ncd "$repo_root"'),
            4,
        )
        for deletion_guard in (
            'legacy_venv="/home/many/yocto-rpi5-cam-firmware/'
            '.worktrees/yocto-implementation/.venv"',
            '[[ -d "$legacy_venv" && ! -L "$legacy_venv" ]]',
            "grep -Fqx 'home = /usr/bin'",
            "grep -Fqx 'include-system-site-packages = false'",
            "grep -Fqx 'version = 3.12.3'",
            "grep -Fqx 'executable = /usr/bin/python3.12'",
            "grep -Fqx 'command = /usr/bin/python3 -m venv --without-pip "
            "/home/many/yocto-rpi5-cam-firmware/.worktrees/"
            "yocto-implementation/.venv'",
            'find "$legacy_venv" -xdev ! -user "$(id -un)"',
            '[[ "$mount_target" == "$legacy_venv" || '
            '"$mount_target" == "$legacy_venv/"* ]]',
            'rm -r --one-file-system -- "$legacy_venv"',
        ):
            self.assertIn(deletion_guard, text)

    def test_uv_design_defines_authenticated_archive_trust_boundary(self) -> None:
        text = read(UV_DESIGN)
        for fragment in (
            UV_RELEASE_URL,
            UV_RELEASE_SHA256,
            UV_RELEASE_PAGE,
            "UV_ARCHIVE",
            "root-owned",
            "spoofed executable",
            "UV_PROJECT_ENVIRONMENT",
        ):
            self.assertIn(fragment, text)


if __name__ == "__main__":
    unittest.main()
