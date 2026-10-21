"""Check Apple DT encoding against the concrete ArmCpu/ArmDTPlatform ABI."""

from pathlib import Path
import struct
import sys
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from make_vermeer_adt import generate


def decode(data):
    def read(offset):
        count, children = struct.unpack_from("<II", data, offset)
        offset += 8
        props = {}
        for _ in range(count):
            name, length = struct.unpack_from("<32sI", data, offset)
            offset += 36
            name = name.split(b"\0", 1)[0].decode()
            assert name not in props and offset + length <= len(data)
            props[name] = data[offset:offset + length]
            offset += (length + 3) & ~3
        nodes = {}
        for _ in range(children):
            child, offset = read(offset)
            nodes[child["props"]["name"].rstrip(b"\0").decode()] = child
        return {"props": props, "children": nodes}, offset
    tree, end = read(0)
    assert end == len(data)
    return tree


class AdtTests(unittest.TestCase):
    def test_platform_driver_abi_and_single_observed_cpu(self):
        tree = decode(generate(0x100000000, 0x300, 19200000, 0x20000000))
        nodes = tree["children"]
        self.assertTrue({"chosen", "cpus", "arm-io", "defaults", "options"} <= nodes.keys())
        self.assertNotIn("psci", nodes)
        self.assertEqual(set(nodes["cpus"]["children"]), {"cpu0"})
        self.assertEqual(struct.unpack("<I", nodes["cpus"]["children"]["cpu0"]["props"]["reg"])[0], 0x300)
        bus = nodes["arm-io"]
        self.assertEqual(set(bus["children"]), {"intc"})
        gic = bus["children"]["intc"]["props"]
        child_base, physical_base, length = struct.unpack("<3Q", bus["props"]["ranges"])
        regions = struct.unpack("<4Q", gic["reg"])
        self.assertEqual((physical_base + regions[0] - child_base, physical_base + regions[2] - child_base),
                         (0x17100000, 0x17180000))
        self.assertLessEqual(regions[2] + regions[3], length)
        self.assertEqual(struct.unpack("<Q", gic["redistributor-stride"])[0], 0x40000)
        chosen = nodes["chosen"]["props"]
        self.assertEqual(len(chosen["random-seed"]), 64)
        bank = chosen["nvram-proxy-data"]
        self.assertEqual(struct.unpack_from("<I", bank, 16)[0], zlib.adler32(bank[20:]))
        self.assertEqual(nodes["chosen"]["children"]["memory-map"]["props"], {"name": b"memory-map\0"})

    def test_invalid_runtime_facts_are_rejected(self):
        for args in [(0, 0, 19200000, 0x20000000), (0x100000000, 1, 19200000, 0x20000000),
                     (0x100000000, 0, 24000000, 0x20000000), (0x100000000, 0, 19200000, 0x11001000)]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                generate(*args)
