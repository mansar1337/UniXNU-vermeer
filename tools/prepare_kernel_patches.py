#!/usr/bin/env python3
"""Prepare a local copy of the pinned patches, with the display probe guard."""

import hashlib
from pathlib import Path
import shutil

PATCH = "offline-component-load-probes.patch"
UPSTREAM_SHA256 = "1f228c5c6d8387b13cd8e0964ddeb56c858a5dae16478f3ed2baae8a2e4da1e9"
GUARD = "+#if defined(XNU_NATIVE_LEGACY_DISPLAY) && XNU_NATIVE_LEGACY_DISPLAY\n"
BLOCK = (
    "+\tint legacy_register = 0;\n"
    "+\tif (native_mobile_graphics_load_status == 0 &&\n"
    "+\t    PE_parse_boot_argn(\"offline-legacy-register\", &legacy_register, sizeof(legacy_register)) && legacy_register) {\n"
    "+\t\textern void native_legacy_display_probe(void);\n"
    "+\t\tnative_legacy_display_probe();\n"
    "+\t}\n"
)


def guarded_patch(data):
    if hashlib.sha256(data).hexdigest() != UPSTREAM_SHA256:
        raise ValueError("Unexpected upstream display-probe patch; inspect before updating its guard")
    text = data.decode()
    header = "@@ -478,5 +478,88 @@"
    if text.count(BLOCK) != 1 or text.count(header) != 1:
        raise ValueError("Unexpected display-probe patch context")
    text = text.replace(BLOCK, GUARD + BLOCK + "+#endif\n")
    return text.replace(header, "@@ -478,5 +478,90 @@").encode()


def prepare(upstream, tree):
    source = upstream / "patches/xnu"
    patched = guarded_patch((source / PATCH).read_bytes())
    local = tree / ".cache/vermeer-xnu-patches"
    local.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.glob("*.patch")):
        shutil.copy2(path, local / path.name)
    (local / PATCH).write_bytes(patched)
    link = tree / "patches/xnu"
    if not link.is_symlink():
        raise ValueError("Expected the upstream patch-directory symlink")
    link.unlink()
    link.symlink_to(local.resolve())
    return {"patch": PATCH, "upstream_sha256": UPSTREAM_SHA256,
            "effective_sha256": hashlib.sha256(patched).hexdigest(),
            "change": "guard optional legacy registration with XNU_NATIVE_LEGACY_DISPLAY"}
