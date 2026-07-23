from __future__ import annotations

import os
from pathlib import Path
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    return subprocess.run(
        args,
        cwd=REPO_ROOT,
        env=merged,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
