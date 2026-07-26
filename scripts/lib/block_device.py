#!/usr/bin/env python3
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class Device:
    path: str
    kname: str
    type: str
    tran: str | None
    size: int
    model: str
    serial: str
    mountpoints: tuple[str, ...]
    parent: str | None


def parse_topology(payload: dict) -> dict[str, Device]:
    nodes: dict[str, Device] = {}

    def visit(raw: dict, parent: str | None) -> None:
        path = str(raw.get("path") or raw.get("name"))
        mountpoints = tuple(
            value for value in (raw.get("mountpoints") or []) if value
        )
        node = Device(
            path=path,
            kname=str(raw.get("kname") or Path(path).name),
            type=str(raw.get("type") or ""),
            tran=raw.get("tran"),
            size=int(raw.get("size") or 0),
            model=str(raw.get("model") or "").strip(),
            serial=str(raw.get("serial") or "").strip(),
            mountpoints=mountpoints,
            parent=parent,
        )
        if path in nodes:
            raise ValueError(f"duplicate block-device path: {path}")
        nodes[path] = node
        for child in raw.get("children") or []:
            visit(child, path)

    for root in payload.get("blockdevices") or []:
        visit(root, None)
    return nodes


def lookup(nodes: dict[str, Device], name: str) -> Device:
    candidates = [
        node
        for node in nodes.values()
        if name in {node.path, f"/dev/{node.kname}"}
    ]
    if len(candidates) != 1:
        raise ValueError(f"block device does not resolve uniquely: {name}")
    return candidates[0]


def root_disk(nodes: dict[str, Device], name: str) -> Device:
    node = lookup(nodes, name)
    while node.parent is not None:
        node = nodes[node.parent]
    return node


def descendants(nodes: dict[str, Device], root_path: str) -> list[Device]:
    result: list[Device] = []
    pending = [root_path]
    while pending:
        parent = pending.pop()
        children = [
            node for node in nodes.values() if node.parent == parent
        ]
        result.extend(children)
        pending.extend(node.path for node in children)
    return result


def mounted_paths(nodes: dict[str, Device], target: str) -> list[str]:
    root = lookup(nodes, target)
    mounted: list[str] = []
    for node in [root, *descendants(nodes, root.path)]:
        if node.mountpoints:
            mounted.append(node.path)
    return mounted


def validate_target(
    nodes: dict[str, Device],
    target: str,
    image_bytes: int,
    protected_sources: list[str],
    allow_mounted: bool,
) -> dict:
    if image_bytes <= 0:
        raise ValueError("image size must be positive")
    node = lookup(nodes, target)
    if node.type != "disk":
        raise ValueError(f"target is not a whole disk: {target}")
    if node.tran != "usb":
        raise ValueError(f"target transport is not USB: {node.tran}")
    if node.size < image_bytes:
        raise ValueError(
            f"target is smaller than image: {node.size} < {image_bytes}"
        )

    target_root = root_disk(nodes, node.path)
    for source in protected_sources:
        if not source.startswith("/dev/"):
            continue
        protected_root = root_disk(nodes, source)
        if protected_root.path == target_root.path:
            raise ValueError(
                f"target backs a protected filesystem: {source}"
            )

    mounted = mounted_paths(nodes, node.path)
    if mounted and not allow_mounted:
        raise ValueError(f"target or child is mounted: {', '.join(mounted)}")

    result = asdict(node)
    result["mounted"] = mounted
    return result


def partition_path(device: str, number: int) -> str:
    if number < 1:
        raise ValueError("partition number must be positive")
    separator = "p" if re.search(r"[0-9]$", device) else ""
    return f"{device}{separator}{number}"


def bmap_image_size(path: Path) -> int:
    root = ET.parse(path).getroot()
    for element in root.iter():
        if (
            element.tag.rsplit("}", 1)[-1] == "ImageSize"
            and element.text
        ):
            image_bytes = int(element.text.strip())
            if image_bytes <= 0:
                raise ValueError("ImageSize must be positive")
            return image_bytes
    raise ValueError("ImageSize missing from bmap")


def load_nodes(path: Path) -> dict[str, Device]:
    return parse_topology(json.loads(path.read_text(encoding="utf-8")))


def main() -> int:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("--topology", type=Path, required=True)
    validate.add_argument("--target", required=True)
    validate.add_argument("--image-bytes", type=int, required=True)
    validate.add_argument("--protected", action="append", default=[])
    validate.add_argument("--allow-mounted", action="store_true")

    mounts = commands.add_parser("mounts")
    mounts.add_argument("--topology", type=Path, required=True)
    mounts.add_argument("--target", required=True)

    partition = commands.add_parser("partition")
    partition.add_argument("--device", required=True)
    partition.add_argument("--number", type=int, required=True)

    bmap_size = commands.add_parser("bmap-size")
    bmap_size.add_argument("--bmap", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "validate":
        result = validate_target(
            load_nodes(args.topology),
            args.target,
            args.image_bytes,
            args.protected,
            args.allow_mounted,
        )
        print(json.dumps(result, sort_keys=True))
    elif args.command == "mounts":
        for path in mounted_paths(load_nodes(args.topology), args.target):
            print(path)
    elif args.command == "partition":
        print(partition_path(args.device, args.number))
    elif args.command == "bmap-size":
        print(bmap_image_size(args.bmap))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
