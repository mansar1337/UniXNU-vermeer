#!/usr/bin/env python3
"""The disabled display feature must not leave an external linker reference."""

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from prepare_kernel_patches import BLOCK, GUARD, guarded_patch


class DisplayGuardTests(unittest.TestCase):
    def test_unexpected_upstream_patch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Unexpected upstream"):
            guarded_patch(b"unexpected patch revision")

    @unittest.skipUnless(shutil.which("clang") and shutil.which("nm"), "requires compiler and nm")
    def test_disabled_feature_has_no_linker_reference(self):
        # Compile the actual inserted condition and call with minimal declarations.
        code = (GUARD + BLOCK + "+#endif\n").replace("\n+", "\n")[1:]
        with tempfile.TemporaryDirectory(prefix="vermeer-display-guard-") as tmp:
            root = Path(tmp)
            source = root / "probe.c"
            source.write_text(
                "extern int native_mobile_graphics_load_status;\n"
                "extern int PE_parse_boot_argn(const char *, void *, unsigned long);\n"
                "void probe(void) {\n" + code + "}\n"
            )
            for mode in (None, 0, 1):
                obj = root / f"probe-{mode}.o"
                flags = [] if mode is None else [f"-DXNU_NATIVE_LEGACY_DISPLAY={mode}"]
                subprocess.run(["clang", "-c", "-O2", *flags, str(source), "-o", str(obj)], check=True)
                names = subprocess.check_output(["nm", "-u", str(obj)], text=True)
                self.assertEqual("native_legacy_display_probe" in names, mode == 1)


if __name__ == "__main__":
    unittest.main()
