#!/usr/bin/env python3
"""Tests for the generated autounattend.xml used by the Windows 11 bypass."""

import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import WinIso.core as core  # noqa: E402

NS = {"u": "urn:schemas-microsoft-com:unattend"}


class AutounattendTests(unittest.TestCase):
    def setUp(self):
        self.xml = core.build_autounattend_xml()

    def test_xml_is_well_formed(self):
        root = ElementTree.fromstring(self.xml)
        self.assertEqual(root.tag, "{urn:schemas-microsoft-com:unattend}unattend")

    def test_labconfig_keys_are_present(self):
        for value in ("BypassTPMCheck", "BypassSecureBootCheck", "BypassRAMCheck"):
            self.assertIn("LabConfig", self.xml)
            self.assertIn("/v {0} /t REG_DWORD /d 1 /f".format(value), self.xml)

    def test_bypass_nro_is_present(self):
        self.assertIn("BypassNRO", self.xml)
        self.assertIn("/v BypassNRO /t REG_DWORD /d 1 /f", self.xml)

    def test_oobe_registry_path_is_used(self):
        self.assertIn(r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\OOBE", self.xml)

    def test_both_settings_passes_exist(self):
        passes = [node.get("pass") for node in ElementTree.fromstring(self.xml).findall("u:settings", NS)]
        self.assertIn("windowsPE", passes)
        self.assertIn("specialize", passes)

    def test_write_autounattend_creates_the_file_on_the_target_root(self):
        with tempfile.TemporaryDirectory() as target:
            self.assertEqual(core.write_autounattend(target), 0)

            path = os.path.join(target, core.AUTOUNATTEND_FILENAME)
            self.assertTrue(os.path.isfile(path))

            with open(path, "r", encoding="utf-8") as handle:
                written = handle.read()

            ElementTree.fromstring(written)
            self.assertIn("BypassTPMCheck", written)
            self.assertIn("BypassNRO", written)


if __name__ == "__main__":
    unittest.main()
