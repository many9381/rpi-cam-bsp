#!/usr/bin/env python3
"""Exercise the shipped policy in a disposable network namespace/container.

Requires root/CAP_NET_ADMIN and CAP_NET_RAW, nft, ip, and systemd-sysctl.
Refuses a namespace with non-loopback interfaces. Never run on a live device.
Usage: verify_kernel_policy_network.py FIREWALL SYSCTL
"""
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import sys
import tempfile
import unittest


def run(*args, check=True):
    return subprocess.run(args, check=check, text=True, capture_output=True)


def checksum(data):
    data += b"\0" * (len(data) % 2)
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    while total >> 16:
        total = (total & 65535) + (total >> 16)
    return (~total) & 65535


class PolicyNetworkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.nft = os.environ.get("POLICY_NFT", "nft")
        cls.firewall, cls.sysctl = map(Path, sys.argv[1:3])
        links = json.loads(run("ip", "-j", "link").stdout)
        if {x["ifname"] for x in links} != {"lo"}:
            raise RuntimeError("A disposable namespace containing only lo is required")
        run("ip", "link", "set", "lo", "up")
        run(cls.nft, "add", "table", "ip", "test_foreign_policy")
        run(cls.nft, "-f", str(cls.firewall))
        cls.apply_sysctl()

    @classmethod
    def apply_sysctl(cls):
        run("/usr/lib/systemd/systemd-sysctl", "--prefix=/net/ipv6", str(cls.sysctl))

    def counter(self, chain):
        result = run(self.nft, "-j", "list", "table", "ip", "rpi5_security", check=False)
        if result.returncode:
            return 0
        return sum(e["counter"]["packets"]
                   for item in json.loads(result.stdout)["nftables"]
                   if (r := item.get("rule")) and r["chain"] == chain
                   for e in r["expr"] if "counter" in e)

    def icmp(self, kind, expected_kind):
        payload = struct.pack("!BBHHHIII", kind, 0, 0, 0x5173, 1, 0, 0, 0)
        payload = payload[:2] + struct.pack("!H", checksum(payload)) + payload[4:]
        with socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP) as s:
            s.settimeout(0.3)
            try:
                s.sendto(payload, ("127.0.0.1", 0))
            except PermissionError:
                # An OUTPUT drop can reject sendto itself. The caller also
                # requires the exact output-rule counter to advance.
                if kind == 14:
                    return False
                raise
            try:
                while True:
                    packet = s.recv(4096)
                    pos = (packet[0] & 15) * 4
                    if packet[pos] == expected_kind and packet[pos + 4:pos + 6] == b"Qs":
                        return True
            except socket.timeout:
                return False

    def test_timestamp_request_is_dropped_before_reply(self):
        before = self.counter("input")
        self.assertFalse(self.icmp(13, 14))
        self.assertEqual(self.counter("input"), before + 1)

    def test_timestamp_reply_cannot_leave_local_stack(self):
        before = self.counter("output")
        self.assertFalse(self.icmp(14, 14))
        self.assertEqual(self.counter("output"), before + 1)

    def test_normal_echo_remains_available(self):
        self.assertTrue(self.icmp(8, 0))

    def test_tcp_and_udp_application_traffic_remains_available(self):
        for kind in (socket.SOCK_STREAM, socket.SOCK_DGRAM):
            with socket.socket(socket.AF_INET, kind) as server:
                server.bind(("127.0.0.1", 0))
                server.settimeout(1)
                if kind == socket.SOCK_STREAM:
                    server.listen(1)
                with socket.socket(socket.AF_INET, kind) as client:
                    client.settimeout(1)
                    client.connect(server.getsockname())
                    client.send(b"camera-policy-control")
                    if kind == socket.SOCK_STREAM:
                        conn, _ = server.accept()
                        with conn:
                            self.assertEqual(conn.recv(99), b"camera-policy-control")
                    else:
                        self.assertEqual(server.recv(99), b"camera-policy-control")

    def test_reload_is_idempotent_and_preserves_foreign_table(self):
        for _ in range(3):
            run(self.nft, "-f", str(self.firewall))
        run(self.nft, "list", "table", "ip", "test_foreign_policy")
        rows = json.loads(run(self.nft, "-j", "list", "table", "ip", "rpi5_security").stdout)
        self.assertEqual(sum("rule" in row for row in rows["nftables"]), 2)

    def test_invalid_reload_preserves_active_rules(self):
        before = run(self.nft, "-j", "list", "table", "ip", "rpi5_security").stdout
        with tempfile.NamedTemporaryFile(mode="w", suffix=".nft") as bad:
            bad.write(self.firewall.read_text() + "\nthis is invalid nft syntax\n")
            bad.flush()
            self.assertNotEqual(run(self.nft, "-f", bad.name, check=False).returncode, 0)
        self.assertEqual(run(self.nft, "-j", "list", "table", "ip", "rpi5_security").stdout, before)

    def test_existing_and_hotplug_dotted_interface_get_policy(self):
        run("ip", "link", "add", "kp.late", "type", "dummy")
        key = Path("/proc/sys/net/ipv6/conf/kp.late/drop_unicast_in_l2_multicast")
        try:
            key.write_text("0")
            run("/usr/lib/systemd/systemd-sysctl", "--prefix=/net/ipv6/conf/kp.late", str(self.sysctl))
            self.assertEqual(key.read_text().strip(), "1")
            key.write_text("0")
            self.apply_sysctl()
            self.assertEqual(key.read_text().strip(), "1")
        finally:
            run("ip", "link", "delete", "kp.late")

    def ipv6_packet(self, multicast_mac, multicast_ip=False, broadcast=False):
        run("ip", "link", "add", "kp-tx", "type", "veth", "peer", "name", "kp-rx")
        try:
            for dev, address in (("kp-tx", "fd73::1"), ("kp-rx", "fd73::2")):
                run("ip", "link", "set", dev, "up")
                run("ip", "-6", "addr", "add", address + "/64", "dev", dev, "nodad")
            # Test the installed default on an interface created after sysctl ran.
            inherited = Path("/proc/sys/net/ipv6/conf/kp-rx/drop_unicast_in_l2_multicast").read_text().strip()
            target = "ff02::114" if multicast_ip else "fd73::2"
            with socket.socket(socket.AF_INET6, socket.SOCK_DGRAM) as receiver:
                receiver.settimeout(0.3)
                receiver.bind(("::", 0))
                if multicast_ip:
                    receiver.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP,
                                        socket.inet_pton(socket.AF_INET6, target) +
                                        struct.pack("@I", socket.if_nametoindex("kp-rx")))
                src = socket.inet_pton(socket.AF_INET6, "fd73::1")
                dst = socket.inet_pton(socket.AF_INET6, target)
                payload = b"ipv6-policy-control"
                udp = struct.pack("!HHHH", 54000, receiver.getsockname()[1], 8 + len(payload), 0) + payload
                pseudo = src + dst + struct.pack("!I3xB", len(udp), socket.IPPROTO_UDP)
                udp = udp[:6] + struct.pack("!H", checksum(pseudo + udp) or 65535) + udp[8:]
                ipv6 = struct.pack("!IHBB", 6 << 28, len(udp), socket.IPPROTO_UDP, 64) + src + dst
                smac = bytes.fromhex(Path("/sys/class/net/kp-tx/address").read_text().strip().replace(":", ""))
                dmac = (bytes.fromhex("333300000114" if multicast_ip else "333300000099")
                        if multicast_mac else bytes.fromhex(Path("/sys/class/net/kp-rx/address").read_text().strip().replace(":", "")))
                if broadcast:
                    dmac = b"\xff" * 6
                with socket.socket(socket.AF_PACKET, socket.SOCK_RAW) as sender:
                    sender.bind(("kp-tx", 0))
                    sender.send(dmac + smac + b"\x86\xdd" + ipv6 + udp)
                try:
                    received = receiver.recv(99) == payload
                except socket.timeout:
                    received = False
                return inherited, received
        finally:
            run("ip", "link", "delete", "kp-tx")

    def test_new_interface_rejects_unicast_ip_in_multicast_frame(self):
        inherited, received = self.ipv6_packet(True)
        self.assertEqual(inherited, "1")
        self.assertFalse(received)

    def test_unicast_ip_in_broadcast_frame_is_dropped(self):
        _, received = self.ipv6_packet(True, broadcast=True)
        self.assertFalse(received)

    def test_normal_ipv6_unicast_remains_available(self):
        _, received = self.ipv6_packet(False)
        self.assertTrue(received)

    def test_valid_ipv6_multicast_remains_available(self):
        _, received = self.ipv6_packet(True, True)
        self.assertTrue(received)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]], verbosity=2)
