#!/usr/bin/env python3
"""Build the source XNU milestone using a pinned, unmodified UniXNU build driver.

Unlike `unixnu build kernel`, this deliberately stops before prelinking Apple
kernelcache components. It does not build a firmware or phone boot image.
"""

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import tomllib

UNIXNU_COMMIT = "b6ae99c17194e6a18fd819d3148e69fe405e91fc"
XNU_COMMIT = "d8b80295118ef25ac3a784134bcf95cd8e88109f"
KERNEL = "build/xnu/ios-obj/DEVELOPMENT_ARM64_BCM2837/mach.development.bcm2837.unstripped.noctf"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], text=True).strip()


def verify_source(root):
    revision = git(root, "rev-parse", "HEAD")
    if revision != UNIXNU_COMMIT:
        raise ValueError(f"Unexpected UniXNU revision: {revision}; expected {UNIXNU_COMMIT}")
    if git(root, "status", "--porcelain", "--untracked-files=no"):
        raise ValueError("Use an unchanged UniXNU reference checkout")
    feeds = tomllib.loads((root / "feeds.toml").read_text())
    xnu = next(item for item in feeds["source"] if item["name"] == "xnu")
    if xnu["commit"] != XNU_COMMIT:
        raise ValueError("The pinned XNU reference changed")
    return feeds


def verify_kernel(path):
    data = path.read_bytes()
    if len(data) < 32:
        raise ValueError("Truncated kernel")
    magic, cpu, subtype, kind, ncmds, cmdbytes, flags, reserved = struct.unpack_from("<8I", data)
    if (magic, cpu, subtype, kind) != (0xFEEDFACF, 0x0100000C, 0, 2):
        raise ValueError("Expected ordinary ARM64 MH_EXECUTE (not ARM64e)")
    end = 32 + cmdbytes
    if end > len(data):
        raise ValueError("Truncated load-command table")
    offset = 32
    build_version = None
    entry_command = False
    for _ in range(ncmds):
        if offset + 8 > end:
            raise ValueError("Truncated load command")
        cmd, length = struct.unpack_from("<II", data, offset)
        if length < 8 or offset + length > end:
            raise ValueError("Invalid load command")
        if cmd == 0x32:
            if length < 24:
                raise ValueError("Truncated LC_BUILD_VERSION")
            target, minimum, sdk, ntools = struct.unpack_from("<4I", data, offset + 8)
            build_version = {"platform": target, "minimum": minimum, "sdk": sdk}
        if cmd in (0x5, 0x80000028):
            entry_command = True
        offset += length
    if offset != end or not entry_command:
        raise ValueError("Kernel must have valid commands and an entry command")
    if not build_version or build_version["platform"] != 2 or build_version["minimum"] != 0x110000:
        raise ValueError(f"Expected iOS 17 build version: {build_version}")
    return {"cpu": "ARM64", "filetype": "MH_EXECUTE", "bytes": len(data),
            "sha256": sha256(path), "build_version": build_version}


def preflight():
    if platform.system() != "Darwin":
        raise ValueError("This source build uses macOS/Xcode. Run the macos-15 workflow; Linux Mach-O smoke tests are separate.")
    required = ("git", "make", "clang", "cmake", "ninja", "unifdef", "xcrun", "xcodebuild", "ditto", "plutil")
    missing = [name for name in required if not shutil.which(name)]
    if missing:
        raise ValueError("Missing host tools: " + ", ".join(missing))
    subprocess.run(["xcodebuild", "-version"], check=True)
    for tool in ("clang", "mig", "iig"):
        subprocess.run(["xcrun", "--sdk", "iphoneos", "--find", tool], check=True)
    subprocess.run(["xcrun", "--sdk", "iphoneos", "--show-sdk-path"], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unixnu", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("out"))
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument("--check", action="store_true", help="Check source/configuration only; works on Linux")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    root = args.unixnu.resolve()
    device = Path(__file__).resolve().parents[1]
    verify_source(root)
    sys.path.insert(0, str(root / "scripts"))
    cli = importlib.import_module("unixnu.cli")
    config = importlib.import_module("unixnu.config")
    kernel = importlib.import_module("unixnu.kernel")
    parsed = config.parse_config((device / "configs/vermeer_build_defconfig").read_text())
    archives = tomllib.loads((device / "board.toml").read_text())["kernel"]["archives"]
    for builder in archives:
        if not (root / "scripts" / builder.split()[0]).is_file():
            raise ValueError(f"Unknown archive builder: {builder}")
    if not parsed["XNU_SOURCE_CORECRYPTO14"] or not parsed["XNU_SOURCE_PTHREAD"]:
        raise ValueError("Source crypto and pthread are required by this baseline")
    if parsed["XNU_CRYPTO_BOOTSTRAP"] != "source":
        raise ValueError("This milestone must not depend on prelinked Apple crypto")
    for name, value in parsed.items():
        if value is True and name not in {"XNU_SOURCE_CORECRYPTO14", "XNU_SOURCE_PTHREAD", "XNU_NATIVE_ARCH_TIMER"}:
            raise ValueError(f"Unexpected feature in build-only baseline: {name}")
    print(f"Verified UniXNU {UNIXNU_COMMIT}, XNU {XNU_COMMIT}, source-build configuration", flush=True)
    if args.check:
        return 0
    preflight()
    out = args.out.resolve()
    # Use the real upstream parser/context so configuration and module resolution
    # have the same semantics as its CLI. Only the final prelink step is omitted.
    options = cli.parser().parse_args([
        "build", "kernel", "-D", str(device), "--out", str(out), "-j", str(args.jobs),
    ])
    ctx = config.Context(options)
    ctx.work.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(device / "configs/vermeer_build_defconfig", ctx.config_path)
    ctx.config = parsed
    modules = cli.prepare(ctx, ["kernel"])
    kernel.build(ctx, modules)
    source_kernel = ctx.tree / KERNEL
    report = verify_kernel(source_kernel)
    destination = ctx.work / "kernel"
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / "kernel.development.vermeer-build.macho"
    shutil.copy2(source_kernel, output)
    symbols = destination / "symbols.txt"
    with symbols.open("w") as stream:
        subprocess.run(["xcrun", "nm", "-n", str(output)], stdout=stream, check=True)
    symbol_names = symbols.read_text()
    for required in ("_source_corecrypto14_bootstrap", "_source_pthread_bootstrap"):
        if required not in symbol_names:
            raise ValueError(f"Kernel is missing {required}")
    seal = source_kernel.with_suffix(source_kernel.suffix + ".crypto-hmac.json")
    if not seal.is_file():
        raise ValueError("Source crypto POST HMAC report is missing")
    seal_report = json.loads(seal.read_text())
    if seal_report["kernel_sha256"] != report["sha256"]:
        raise ValueError("Source crypto HMAC report belongs to another kernel")
    shutil.copy2(seal, destination / "crypto-hmac.json")
    revisions = {f"{kind}:{name}": {"commit": m.commit or (m.source or {}).get("commit"),
                                    "origin": m.origin}
                 for (kind, name), m in modules.items()}
    # Include the gitlink pins for modules obtained as UniXNU submodules.
    submodules = git(root, "submodule", "status", "--recursive")
    report.update({
        "unixnu_commit": UNIXNU_COMMIT, "xnu_commit": XNU_COMMIT,
        "modules": revisions, "submodules": submodules,
        "configuration": parsed, "board": "vermeer", "soc": "SM8550",
        "build_configuration_sha256": {
            name: sha256(device / name)
            for name in ("board.toml", "configs/vermeer_build_defconfig", "tools/build_source_kernel.py")
        },
        "machine_configuration": "BCM2837", "page_bytes": 4096,
        "prelinked": False, "bootable_phone_image": False,
        "hardware_boot_tested": False, "vermeer_platform_cpu_drivers_linked": False,
        "source_crypto_runtime_selftests_executed": False,
    })
    (destination / "build-report.json").write_text(json.dumps(report, indent=2) + "\n")
    (destination / "SHA256SUMS").write_text(f"{sha256(output)}  {output.name}\n")
    print(f"Source kernel built: {output}\nThis is a build baseline; vermeer phone boot is not implemented.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error)) from None
