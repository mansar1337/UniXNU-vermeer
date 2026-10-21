#!/usr/bin/env python3
"""Create a separate vermeerProbePkg from the working Silicium vermeer port."""

import argparse
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uefi", required=True, type=Path)
    args = parser.parse_args()
    root = args.uefi.resolve()
    source = root / "Platforms/Xiaomi/vermeerPkg"
    destination = root / "Platforms/Xiaomi/vermeerProbePkg"
    if destination.exists():
        parser.error("vermeerProbePkg already exists; inspect it before replacing")
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__"))
    for file in destination.rglob("*"):
        if file.suffix in (".dsc", ".fdf", ".inf", ".dec", ".py", ".inc"):
            text = file.read_text().replace("vermeerPkg", "vermeerProbePkg")
            if file.name == "DeviceBuild.py":
                text = text.replace('"ACTIVE_PLATFORM", "vermeerProbePkg/vermeer.dsc"',
                                    '"ACTIVE_PLATFORM", "vermeerProbePkg/vermeerProbe.dsc"')
                text = text.replace('("vermeerProbePkg/vermeer.dsc", {})', '("vermeerProbePkg/vermeerProbe.dsc", {})')
            file.write_text(text)
    dsc = destination / "vermeer.dsc"
    text = dsc.read_text().replace("PLATFORM_NAME                  = vermeer", "PLATFORM_NAME                  = vermeerProbe")
    text = text.replace("vermeerProbePkg/vermeer.fdf", "vermeerProbePkg/vermeerProbe.fdf")
    text += "\n[LibraryClasses]\n  PlatformBootOptionsLib|vermeerProbePkg/Probe/ProbeBootOptions.inf\n\n[Components]\n  vermeerProbePkg/Probe/VermeerProbe.inf\n"
    (destination / "vermeerProbe.dsc").write_text(text)
    dsc.unlink()
    fdf = destination / "vermeer.fdf"
    text = fdf.read_text()
    text = text.replace("  !include Include/RAW.inc", "  !include Include/RAW.inc\n\n  INF vermeerProbePkg/Probe/VermeerProbe.inf")
    (destination / "vermeerProbe.fdf").write_text(text)
    fdf.unlink()
    probe = destination / "Probe"
    shutil.copytree(Path(__file__).resolve().parents[1] / "uefi-probe", probe)
    (probe / "ProbeBootOptions.inf").write_text('''[Defines]
  INF_VERSION = 0x00010005
  BASE_NAME = ProbeBootOptions
  FILE_GUID = F4368684-A7B4-470B-B208-9C90EFD35B35
  MODULE_TYPE = DXE_DRIVER
  LIBRARY_CLASS = PlatformBootOptionsLib|DXE_DRIVER
[Sources]
  ProbeBootOptions.c
[Packages]
  MdePkg/MdePkg.dec
  SiliciumPkg/SiliciumPkg.dec
[LibraryClasses]
  MemoryAllocationLib
''')
    (probe / "ProbeBootOptions.c").write_text('''#include <Uefi.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/PlatformBootOptionsLib.h>
STATIC EFI_GUID mProbeGuid = {0x4E746B99, 0x462F, 0x4C10, {0x8A,0x77,0xC3,0xF8,0x3E,0x5D,0x4F,0x72}};
VOID GetPlatformBootOptions (EFI_PLATFORM_BOOT_OPTION **Options, UINT8 *Count) {
  *Options = AllocateZeroPool (sizeof (**Options));
  *Count = 0;
  if (*Options == NULL) { return; }
  (*Options)[0].AppName = L"Vermeer hardware probe";
  (*Options)[0].AppGuid = &mProbeGuid;
  (*Options)[0].LoadAttribute = LOAD_OPTION_ACTIVE;
  *Count = 1;
}
''')
    config = root / "Resources/Configs/vermeerProbe.toml"
    dtb = root / "Resources/DTBs/vermeerProbe.dtb"
    if config.exists() or dtb.exists():
        parser.error("Probe config/DTB already exists; inspect before replacing")
    shutil.copy2(root / "Resources/Configs/vermeer.toml", config)
    shutil.copy2(root / "Resources/DTBs/vermeer.dtb", dtb)
    print(f"Prepared separate probe package: {destination}")
    print(f"Build: cd {root} && python3 build_uefi.py -d vermeerProbe -r DEBUG -m 0")


if __name__ == "__main__":
    main()
