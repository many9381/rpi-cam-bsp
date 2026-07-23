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
LEGACY_FRAGMENTS = (
    "python3 -m venv",
    ".venv/bin/activate",
    "pip install",
    "uv pip install",
)
DIRECT_TOOL = re.compile(
    r"(^\s*|(?:&&|\|\||;|\||\$\()\s*)(?:python3?|kas)(?=\s)"
)
INDIRECT_KAS_FRAGMENTS = (
    "run_logged kas ",
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


class UvDocsContractTest(unittest.TestCase):
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
        self.assertIn("uv run --locked kas for-all-repos", text)
        self.assertIn("uv run --locked python \"$helper\" validate", text)


if __name__ == "__main__":
    unittest.main()
