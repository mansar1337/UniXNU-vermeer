#!/usr/bin/env python3
"""Generate a single-CPU Apple DT from stock vermeer facts and runtime inputs."""

import argparse
import os
from pathlib import Path
import struct
import zlib

DRAM_BASE = 0x80000000
ARMIO_BASE = 0x17000000
GIC_DIST = 0x17100000
GIC_REDIST = 0x17180000
TIMEBASE = 19200000  # stock vermeer.dts /soc/timer clock-frequency


def node(name, properties=(), children=()):
    properties = [("name", name.encode() + b"\0"), *properties]
    if len({key for key, _ in properties}) != len(properties):
        raise ValueError("Duplicate ADT property")
    result = struct.pack("<II", len(properties), len(children))
    for key, data in properties:
        if len(key.encode()) >= 32:
            raise ValueError("ADT property name exceeds 31 bytes")
        result += struct.pack("<32sI", key.encode(), len(data))
        result += data + bytes(-len(data) % 4)
    return result + b"".join(children)


def nvram_proxy():
    # Volatile CHRP bank layout used by upstream IODTNVRAM. No flash backing.
    def header(name, size):
        raw = bytearray(struct.pack("<BBH12s", 0x70, 0, size // 16, name))
        checksum = sum(raw)
        while checksum > 255:
            checksum = (checksum & 255) + (checksum >> 8)
        raw[1] = checksum
        return raw

    image = bytearray(8192)
    image[:16] = header(b"nvram", 32)
    image[32:48] = header(b"common", 16 + 2048)
    free_at = 32 + 16 + 2048
    image[free_at:free_at + 16] = header(b"free", len(image) - free_at)
    struct.pack_into("<I", image, 16, zlib.adler32(image[20:]))
    return [("nvram-bank-size", struct.pack("<I", len(image))),
            ("nvram-bank-count", struct.pack("<I", 1)),
            ("nvram-current-bank", struct.pack("<I", 0)),
            ("nvram-proxy-data", bytes(image))]


def generate(dram_size, boot_mpidr, counter_hz, owned_memory_size):
    if not 0 < dram_size < 1 << 64 or dram_size % 0x1000:
        raise ValueError("Observed DRAM size must be positive and page aligned")
    if boot_mpidr not in range(0, 0x800, 0x100):
        raise ValueError("Boot MPIDR must match stock vermeer CPU affinities 0x0..0x700")
    if counter_hz != TIMEBASE:
        raise ValueError("Runtime CNTFRQ differs from the stock 19.2 MHz timer; inspect before boot")
    if not 0x10000000 <= owned_memory_size <= 0x200000000 or owned_memory_size % 0x200000:
        raise ValueError("DarwinBoot window must be 256 MiB..8 GiB in 2 MiB steps")
    if owned_memory_size > dram_size:
        raise ValueError("DarwinBoot window exceeds observed DRAM size")
    return node("device-tree", [
        ("model", b"Redmi K70\0"), ("compatible", b"xiaomi,vermeer\0qcom,sm8550\0"),
        ("#address-cells", struct.pack("<I", 2)), ("#size-cells", struct.pack("<I", 2)),
    ], [
        node("chosen", [("random-seed", os.urandom(64)), ("osenvironment", b"main\0"),
                        ("dram-base", struct.pack("<Q", DRAM_BASE)),
                        ("dram-size", struct.pack("<Q", dram_size)),
                        ("darwinboot-memory-size", struct.pack("<Q", owned_memory_size)),
                        *nvram_proxy()], [node("memory-map")]),
        node("cpus", children=[node("cpu0", [
            ("state", b"running\0"), ("reg", struct.pack("<I", boot_mpidr)),
            ("device_type", b"cpu\0"), ("compatible", b"qcom,kryo\0"),
            ("timebase-frequency", struct.pack("<I", counter_hz)),
        ])]),
        node("arm-io", [("device_type", b"arm-io\0"), ("#address-cells", struct.pack("<I", 2)),
                        ("#size-cells", struct.pack("<I", 2)),
                        ("ranges", struct.pack("<QQQ", 0, ARMIO_BASE, 0x02000000))], [
            node("intc", [("compatible", b"arm,gic-v3\0"),
                          ("reg", struct.pack("<4Q", GIC_DIST - ARMIO_BASE, 0x10000,
                                              GIC_REDIST - ARMIO_BASE, 0x200000)),
                          ("redistributor-stride", struct.pack("<Q", 0x40000))]),
        ]),
        node("defaults", [("sleep-disabled", struct.pack("<I", 1))]),
        node("options"), node("product", [("product-name", b"Redmi K70\0"), ("model", b"xiaomi,vermeer\0")]),
    ])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--dram-size", required=True, type=lambda s: int(s, 0), help="Observed physical DRAM span from base 0x80000000")
    parser.add_argument("--boot-mpidr", required=True, type=lambda s: int(s, 0), help="Observed MPIDR affinity bits (not the full register)")
    parser.add_argument("--counter-hz", required=True, type=lambda s: int(s, 0), help="Observed CNTFRQ_EL0")
    parser.add_argument("--owned-memory-size", required=True, type=lambda s: int(s, 0), help="Window proven available in the UEFI map")
    args = parser.parse_args()
    try:
        data = generate(args.dram_size, args.boot_mpidr, args.counter_hz, args.owned_memory_size)
    except ValueError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(data)
    print(f"vermeer single-CPU ADT: {len(data)} bytes; runtime inputs supplied by caller")


if __name__ == "__main__":
    main()
