"""Exercise the actual acceptance awk filters with old and new sshd output."""
from pathlib import Path
import re
import subprocess
import unittest

from support import REPO_ROOT


class SshdPolicyTest(unittest.TestCase):
    scripts = ("test-rpi5.sh", "test-qemu-guest.sh")
    settings = (
        ("PasswordAuthentication", "no"),
        ("KbdInteractiveAuthentication", "no"),
        ("PermitRootLogin", "no"),
        ("AuthenticationMethods", "publickey"),
        ("AllowUsers", "rpiadmin"),
    )

    def filters(self, script):
        text = (REPO_ROOT / "scripts" / script).read_text()
        text = text.replace("\\\n", "").replace('\\"', '"').replace("\\$", "$")
        filters = re.findall(r"sudo -n /usr/sbin/sshd -T \| awk\s*'(.*?)'", text, re.S)
        self.assertEqual(len(filters), len(self.settings), script)
        return filters

    def check_dump(self, mixed_case):
        dump = "LogLevel INFO\n" + "".join(
            f"{name if mixed_case else name.lower()} {value}\n"
            for name, value in self.settings
        )
        for script in self.scripts:
            for predicate, (_, expected) in zip(self.filters(script), self.settings):
                with self.subTest(script=script, expected=expected, predicate=predicate):
                    result = subprocess.run(["awk", predicate], input=dump, text=True, capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout, expected + "\n")

    def test_legacy_lowercase_dump(self):
        self.check_dump(False)

    def test_new_mixed_case_dump(self):
        self.check_dump(True)

    def test_authentication_methods_fail_closed_for_missing_or_duplicate_lines(self):
        for script in self.scripts:
            predicate = self.filters(script)[3]
            for dump in ("", "AuthenticationMethods\n",
                         "AuthenticationMethods publickey\nauthenticationmethods password\n"):
                with self.subTest(script=script, dump=dump):
                    result = subprocess.run(["awk", predicate], input=dump, text=True, capture_output=True)
                    self.assertNotEqual(result.returncode, 0)

    def test_authentication_method_values_remain_exact(self):
        for script in self.scripts:
            predicate = self.filters(script)[3]
            for value in ("publickey password", "PublicKey", "publickey,password"):
                with self.subTest(script=script, value=value):
                    result = subprocess.run(["awk", predicate], input=f"AuthenticationMethods {value}\n",
                                            text=True, capture_output=True)
                    self.assertEqual(result.stdout.strip(), value)
                    self.assertNotEqual(result.stdout.strip(), "publickey")
