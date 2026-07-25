from __future__ import annotations

import argparse
import os
from pathlib import Path
import signal
import socket
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ready", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    arguments = parser.parse_args()

    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 2222))
    listener.listen()
    arguments.runtime.write_text(str(Path(sys.prefix)), encoding="utf-8")
    arguments.ready.touch()
    while True:
        time.sleep(1)


if __name__ == "__main__":
    raise SystemExit(main())
