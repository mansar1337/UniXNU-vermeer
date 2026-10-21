#!/usr/bin/env python3
# Copyright (c) 2026, UniXNU contributors. All rights reserved.
# SPDX-License-Identifier: BSD-2-Clause-Patent
# Adapted from UniXNU-sheng/scripts/build-arm-driver.py at
# 0c2046b84dbee545e7e3923eb74d7bb1ce020978; license in licenses/UniXNU-sheng.txt.
"""Build only the pinned CPU/platform drivers using XNU's recorded ABI."""

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("component", choices=("ArmDTPlatform", "ArmCpu"))
args = parser.parse_args()
component = args.component
recipe = ROOT / "build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/iokit/DEVELOPMENT/IOPlatformExpert.cpo.json"
record = json.loads(recipe.read_text().strip().rstrip(","))
source = ROOT / "drivers" / component / (component + ".cpp")
out = ROOT / "build" / {"ArmDTPlatform": "armdt-platform", "ArmCpu": "armcpu"}[component]
out.mkdir(parents=True, exist_ok=True)
destination = out / (component + ".o")
arguments = record["arguments"]
command = []
index = 0
while index < len(arguments):
    value = arguments[index]
    if value == record["file"]:
        command.append(str(source))
    elif value == "-o":
        command.extend(["-o", str(destination)])
        index += 1
    elif value == "-Xclang" and arguments[index + 1].startswith("-W"):
        index += 1
    elif not value.startswith("-W"):
        command.append(value)
    index += 1
command.extend(["-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
                "-Wno-c99-designator", "-Wno-reorder-init-list", "-Wno-deprecated-enum-enum-conversion",
                "-I", str(ROOT / ".cache/xnu-work/osfmk")])
(out / "compile-command.json").write_text(json.dumps(command, indent=2) + "\n")
result = subprocess.run(command, cwd=record["directory"], stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, text=True)
(out / "compile.log").write_text(result.stdout)
if result.returncode:
    raise SystemExit(result.stdout[-3500:])
data = destination.read_bytes()
if struct.unpack_from("<4I", data) != (0xFEEDFACF, 0x0100000C, 0, 1):
    raise SystemExit("Unexpected platform object architecture")
offset = 32
deployment = None
for _ in range(struct.unpack_from("<I", data, 16)[0]):
    cmd, length = struct.unpack_from("<II", data, offset)
    if cmd == 0x32:
        deployment = struct.unpack_from("<II", data, offset + 8)
    offset += length
if deployment != (2, 0x110000):
    raise SystemExit(f"Unexpected platform deployment {deployment}")
archive = out / ("lib" + component + ".a")
archive.unlink(missing_ok=True)
subprocess.run(["xcrun", "ar", "rcs", str(archive), str(destination)], check=True)
(out / "build-report.json").write_text(json.dumps({
    "component": component, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
    "cpu": "ARM64", "deployment": "iOS 17", "warnings_as_errors": True,
    "hardware_tested": False,
}, indent=2) + "\n")
print(f"{component}: -Werror build and ARM64/iOS 17 object audit passed")
