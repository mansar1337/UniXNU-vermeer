#!/usr/bin/env python3
"""Reject the timer/provider mismatch found in Actions run 39614669422."""

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("source_build", ROOT / "tools/build_source_kernel.py")
BUILD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD)


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.baseline = {
            "XNU_SOURCE_CORECRYPTO14": True,
            "XNU_SOURCE_PTHREAD": True,
            "XNU_CRYPTO_BOOTSTRAP": "source",
            "XNU_NATIVE_ARCH_TIMER": False,
            "XNU_ARMCPU": False,
        }

    def test_source_build_without_interrupt_provider_is_accepted(self):
        BUILD.verify_configuration(self.baseline)

    def test_first_actions_configuration_is_rejected_early(self):
        self.baseline["XNU_NATIVE_ARCH_TIMER"] = True
        with self.assertRaisesRegex(ValueError, "XNU_NATIVE_ARCH_TIMER requires XNU_ARMCPU"):
            BUILD.verify_configuration(self.baseline)

    def test_source_build_cannot_enable_ufs(self):
        self.baseline["XNU_NATIVE_UFS"] = True
        with self.assertRaisesRegex(ValueError, "Unexpected feature.*XNU_NATIVE_UFS"):
            BUILD.verify_configuration(self.baseline)


if __name__ == "__main__":
    unittest.main()
