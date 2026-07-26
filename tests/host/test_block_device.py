import json
from pathlib import Path
import sys
import tempfile
import unittest

from support import REPO_ROOT


sys.path.insert(0, str(REPO_ROOT / "scripts/lib"))
import block_device  # noqa: E402


TOPOLOGY = {
    "blockdevices": [
        {
            "name": "/dev/nvme0n1",
            "kname": "nvme0n1",
            "path": "/dev/nvme0n1",
            "type": "disk",
            "tran": "nvme",
            "size": 1000000000000,
            "model": "SYSTEM",
            "serial": "SYS1",
            "mountpoints": [None],
            "children": [
                {
                    "name": "/dev/nvme0n1p2",
                    "kname": "nvme0n1p2",
                    "path": "/dev/nvme0n1p2",
                    "type": "part",
                    "tran": None,
                    "size": 900000000000,
                    "model": None,
                    "serial": None,
                    "mountpoints": ["/"],
                }
            ],
        },
        {
            "name": "/dev/sdb",
            "kname": "sdb",
            "path": "/dev/sdb",
            "type": "disk",
            "tran": "usb",
            "size": 500000000000,
            "model": "USB SSD",
            "serial": "USB1",
            "mountpoints": [None],
            "children": [
                {
                    "name": "/dev/sdb1",
                    "kname": "sdb1",
                    "path": "/dev/sdb1",
                    "type": "part",
                    "tran": None,
                    "size": 268435456,
                    "model": None,
                    "serial": None,
                    "mountpoints": [None],
                },
                {
                    "name": "/dev/sdb2",
                    "kname": "sdb2",
                    "path": "/dev/sdb2",
                    "type": "part",
                    "tran": None,
                    "size": 499000000000,
                    "model": None,
                    "serial": None,
                    "mountpoints": [None],
                },
            ],
        },
    ]
}


class BlockDeviceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.nodes = block_device.parse_topology(TOPOLOGY)

    def test_accepts_unmounted_usb_whole_disk(self) -> None:
        result = block_device.validate_target(
            self.nodes,
            "/dev/sdb",
            4000000000,
            ["/dev/nvme0n1p2"],
            False,
        )
        self.assertEqual(result["serial"], "USB1")

    def test_rejects_partition_non_usb_small_and_system_disk(self) -> None:
        cases = (
            ("/dev/sdb1", 1, []),
            ("/dev/nvme0n1", 1, []),
            ("/dev/sdb", 600000000000, []),
            ("/dev/nvme0n1", 1, ["/dev/nvme0n1p2"]),
        )
        for target, size, protected in cases:
            with self.subTest(target=target, size=size, protected=protected):
                with self.assertRaises(ValueError):
                    block_device.validate_target(
                        self.nodes,
                        target,
                        size,
                        protected,
                        False,
                    )

    def test_rejects_mounted_target_child(self) -> None:
        topology = json.loads(json.dumps(TOPOLOGY))
        topology["blockdevices"][1]["children"][0]["mountpoints"] = [
            "/media/ssd"
        ]
        nodes = block_device.parse_topology(topology)
        with self.assertRaisesRegex(ValueError, "mounted"):
            block_device.validate_target(nodes, "/dev/sdb", 1, [], False)

    def test_partition_paths_cover_sd_and_nvme_names(self) -> None:
        self.assertEqual(block_device.partition_path("/dev/sdb", 2), "/dev/sdb2")
        self.assertEqual(
            block_device.partition_path("/dev/nvme1n1", 2),
            "/dev/nvme1n1p2",
        )

    def test_reads_image_size_from_bmap(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.wic.bmap"
            path.write_text(
                '<?xml version="1.0"?><bmap version="2.0">'
                "<ImageSize>4294967296</ImageSize></bmap>",
                encoding="utf-8",
            )
            self.assertEqual(block_device.bmap_image_size(path), 4294967296)

    def test_rejects_non_positive_image_size(self) -> None:
        with self.assertRaisesRegex(ValueError, "positive"):
            block_device.validate_target(
                self.nodes,
                "/dev/sdb",
                0,
                [],
                False,
            )

    def test_rejects_non_positive_bmap_image_size(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "image.wic.bmap"
            path.write_text(
                '<?xml version="1.0"?><bmap version="2.0">'
                "<ImageSize>0</ImageSize></bmap>",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "positive"):
                block_device.bmap_image_size(path)


if __name__ == "__main__":
    unittest.main()
