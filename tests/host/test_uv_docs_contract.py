import os
from pathlib import Path
import re
import tarfile
import tempfile
import unittest

from support import read, run


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
    def assert_embedded_auth_rejects_wrong_hash_spoof(
        self,
        text: str,
    ) -> None:
        script = embedded_shell(text, "# scripts/flash-ssd.sh\n")
        auth_source = script.partition(
            'readonly UV_RELEASE_SHA256="'
        )[2]
        self.assertTrue(auth_source)
        auth_source = (
            'readonly UV_RELEASE_SHA256="'
            + auth_source.partition(
                '\n\nif [[ "${BASH_SOURCE[0]}" != "$0" ]]'
            )[0]
        )
        with tempfile.TemporaryDirectory(
            prefix="uv-auth-contract-",
        ) as temporary:
            root = Path(temporary)
            archive_root = root / "archive-root"
            payload = archive_root / "uv-x86_64-unknown-linux-gnu"
            payload.mkdir(parents=True)
            spoof = payload / "uv"
            marker = root / "SPOOF_EXECUTED"
            private = root / "private"
            archive = root / "spoof.tar.gz"
            private.mkdir(mode=0o700)
            spoof.write_text(
                "#!/usr/bin/env bash\n"
                ': > "${SPOOF_MARKER:?}"\n'
                "printf 'uv 0.11.31\\n'\n",
                encoding="utf-8",
            )
            spoof.chmod(0o755)
            with tarfile.open(archive, "w:gz") as tar:
                tar.add(
                    payload,
                    arcname="uv-x86_64-unknown-linux-gnu",
                )
            command = (
                "set -euo pipefail\n"
                "rpi5_die() {\n"
                "    printf 'ERROR: %s\\n' \"$*\" >&2\n"
                "    return 1\n"
                "}\n"
                f"{auth_source}\n"
                'authenticate_uv_archive "$1" "$2" || exit 1\n'
                'uv_bin="$authenticated_uv_bin"\n'
                '"$uv_bin" --version\n'
            )
            result = run(
                "bash",
                "-c",
                command,
                "bash",
                os.fspath(archive),
                os.fspath(private),
                env={"SPOOF_MARKER": os.fspath(marker)},
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "authenticated uv archive checksum mismatch",
                result.stderr,
            )
            self.assertFalse(
                marker.exists(),
                "wrong-hash spoofed executable was run",
            )

    def assert_override_rejected_before_sync(self, text: str) -> None:
        sync_blocks = [
            block
            for block in re.findall(r"```bash\n(.*?)\n```", text, re.S)
            if "sync --locked" in block
        ]
        self.assertTrue(sync_blocks)
        for block in sync_blocks:
            with self.subTest(first_line=block.splitlines()[0]):
                check = 'test -z "${UV_PROJECT_ENVIRONMENT:-}"'
                self.assertIn(check, block)
                first_environment_use = min(
                    block.index(fragment)
                    for fragment in (
                        "uv lock",
                        '"$UV" lock',
                        "uv sync",
                        '"$UV" sync',
                        "uv run",
                        '"$UV" run',
                    )
                    if fragment in block
                )
                self.assertLess(block.index(check), first_environment_use)
                for physical_gate in (
                    "test -d .venv",
                    "test ! -L .venv",
                    'test "$(realpath .venv)" = "$(pwd -P)/.venv"',
                    "assert pathlib.Path(sys.prefix).resolve() == expected",
                    "assert sys.version_info[:2] == (3, 12)",
                ):
                    self.assertIn(physical_gate, block)

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
            '[[ ! -f "$uv_archive_copy" || -L "$uv_archive_copy" ]]',
            '[[ "$(stat -c %u "$uv_archive_copy")" != "$EUID" ]]',
            "sha256sum --check --strict",
            "--gzip",
            "--no-same-owner",
            "--no-same-permissions",
            'candidate_uv_bin="$uv_extract_dir/uv-x86_64-unknown-linux-gnu/uv"',
            '[[ ! -f "$candidate_uv_bin" || -L "$candidate_uv_bin" ]]',
            'if ! chmod 0700 "$candidate_uv_bin"',
            '[[ "$(stat -c %u "$candidate_uv_bin")" != "$EUID"',
            'authenticated_uv_bin="$candidate_uv_bin"',
            'authenticate_uv_archive "$uv_archive" "$uv_private_dir"',
            'uv_bin="$authenticated_uv_bin"',
            'find "$uv_private_dir" -xdev -depth -delete',
            'sudo UV_ARCHIVE="$UV_ARCHIVE" ./scripts/flash-ssd.sh',
            "test_spoofed_uv_executable_is_rejected",
            "SPOOF_EXECUTED",
            "printf 'uv 0.11.31",
            "spoof.chmod(0o755)",
            '"tar", "--create", "--gzip"',
            'authenticated_uv_bin=""',
            '[[ -d .venv && ! -L .venv ]]',
            '[[ "$(realpath .venv)" == "$repo_root/.venv" ]]',
            'uv_private_dir="$(mktemp -d /var/tmp/rpi5-flash-uv.XXXXXXXX)"\n'
            "trap cleanup_uv EXIT",
            'self.assertFalse(marker.exists(), "spoofed executable was run")',
        ):
            self.assertIn(fragment, text)
        self.assertNotIn('uv_bin="$(authenticate_uv_archive', text)

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
        venv_bin_offenders = [
            f"{line_number}: {line}"
            for line_number, line in shell_lines(text)
            if ".venv/bin/" in line
        ]
        self.assertEqual(venv_bin_offenders, [], relative)
        return text

    def assert_secure_flash_script_order(self, text: str) -> None:
        script = embedded_shell(text, "# scripts/flash-ssd.sh\n")
        for forbidden in ("UV_BIN", "curl ", "wget ", "sudo -E"):
            self.assertNotIn(forbidden, script)
        ordered = (
            'install -m 0600 -- "$uv_archive" "$uv_archive_copy"',
            "sha256sum --check --strict",
            "tar --extract",
            'authenticated_uv_bin="$candidate_uv_bin"',
            'uv_bin="$authenticated_uv_bin"',
            '"$uv_bin" --version',
            '"$uv_bin" run --locked',
        )
        positions = [script.index(fragment) for fragment in ordered]
        self.assertEqual(positions, sorted(positions))
        first_block_operation = min(
            script.index(fragment)
            for fragment in ("findmnt ", "lsblk ", "bmaptool ")
        )
        override_check = '[[ -z "${UV_PROJECT_ENVIRONMENT:-}" ]]'
        authentication_call = (
            'authenticate_uv_archive "$uv_archive" "$uv_private_dir" || exit 1\n'
            'uv_bin="$authenticated_uv_bin"'
        )
        self.assertIn(override_check, script)
        self.assertIn(authentication_call, script)
        authentication_body = script.partition(
            "authenticate_uv_archive() {"
        )[2].partition("\n}\n")[0]
        self.assertGreaterEqual(authentication_body.count("return 1"), 8)
        for guarded_operation in (
            "if ! install -m 0600",
            "if ! install -d -m 0700",
            "if ! tar --extract",
            "if ! chmod 0700",
        ):
            self.assertIn(guarded_operation, authentication_body)
        self.assertLess(
            script.index("trap cleanup_uv EXIT"),
            script.index('chown root:root "$uv_private_dir"'),
        )
        self.assertLess(
            script.index(override_check),
            script.index(authentication_call),
        )
        for locality_check in (
            '[[ -d .venv && ! -L .venv ]]',
            '[[ "$(realpath .venv)" == "$repo_root/.venv" ]]',
        ):
            self.assertLess(
                script.index(locality_check),
                script.index(authentication_call),
            )
        prefix_gate = '"$uv_bin" run --locked python -c'
        self.assertIn(prefix_gate, script)
        self.assertLess(
            script.index(prefix_gate),
            first_block_operation,
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
        self.assert_override_rejected_before_sync(text)
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
        self.assertIn(
            'self.assertIn("setsid uv run --locked kas shell", script)',
            text,
        )
        self.assertIn("uv run --locked kas for-all-repos", text)
        self.assertIn(
            '"$uv_bin" run --locked python "$helper" validate',
            text,
        )
        self.assertNotIn("sudo ./scripts/flash-ssd.sh", text)
        self.assert_authenticated_privileged_uv_flow(text)
        self.assert_secure_flash_script_order(text)
        self.assert_embedded_auth_rejects_wrong_hash_spoof(text)
        self.assert_override_rejected_before_sync(text)
        self.assert_physical_venv_gates(text)
        self.assert_strengthened_environment_plan(text)
        self.assert_exact_embedded_environment_contracts(text, 1)
        self.assertIn(
            'repo_root="$(rpi5_repo_root)"\n'
            'cd "$repo_root"\n'
            '[[ -d .venv && ! -L .venv ]]',
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
        self.assertEqual(
            [
                f"{line_number}: {line}"
                for line_number, line in shell_lines(text)
                if ".venv/bin/" in line
            ],
            [],
        )
        self.assert_authenticated_privileged_uv_flow(text)
        self.assert_override_rejected_before_sync(text)
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
        for final_contract in (
            "Final consolidated documentation contract",
            "assert_authenticated_privileged_uv_flow",
            "assert_secure_flash_script_order",
            "assert_override_rejected_before_sync",
            "assert_physical_venv_gates",
            "assert_exact_embedded_environment_contracts",
            "test_uv_migration_plan_matches_final_secure_flow",
            "six focused documentation-contract tests",
        ):
            self.assertIn(final_contract, text)
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
        self.assert_override_rejected_before_sync(text)
        for fragment in (
            UV_RELEASE_URL,
            UV_RELEASE_SHA256,
            UV_RELEASE_PAGE,
            "UV_ARCHIVE",
            "root-owned",
            "spoofed executable",
            "UV_PROJECT_ENVIRONMENT",
            "command substitution",
            "validated executable",
            "sys.prefix",
        ):
            self.assertIn(fragment, text)


if __name__ == "__main__":
    unittest.main()
