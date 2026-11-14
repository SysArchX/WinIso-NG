#!/usr/bin/env python3
"""Tests for the automatic install.wim splitting used on FAT32 targets."""

import os
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import WinIso.core as core  # noqa: E402


class WimSplitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.source = os.path.join(self.temp.name, "source")
        self.target = os.path.join(self.temp.name, "target")
        os.makedirs(os.path.join(self.source, "sources"))
        os.makedirs(self.target)

        self.wim = os.path.join(self.source, "sources", "install.wim")
        with open(self.wim, "wb") as handle:
            handle.write(b"WIM" * 4096)

        # A stand-in for wimlib-imagex: copies the first argument to the second one.
        self.fake_tool = os.path.join(self.temp.name, "wimlib-imagex")
        with open(self.fake_tool, "w", encoding="utf-8") as handle:
            handle.write('#!/bin/sh\ncp "$1" "$2"\n')
        os.chmod(self.fake_tool, os.stat(self.fake_tool).st_mode | stat.S_IEXEC)

    def tearDown(self):
        self.temp.cleanup()

    def test_small_wim_is_not_split(self):
        self.assertFalse(core.needs_wim_split(self.source))
        self.assertEqual(core.split_install_wim(self.source, self.target), 0)
        self.assertFalse(os.path.exists(os.path.join(self.target, "sources", "install.swm")))

    def test_oversized_wim_is_split_into_swm_parts(self):
        with mock.patch.object(core, "FAT32_MAX_FILE_SIZE", 1024), \
                mock.patch.object(core, "find_wim_split_command", return_value=[self.fake_tool]):
            self.assertTrue(core.needs_wim_split(self.source))
            self.assertEqual(core.split_install_wim(self.source, self.target), 0)

        swm = os.path.join(self.target, "sources", "install.swm")
        self.assertTrue(os.path.isfile(swm))
        with open(swm, "rb") as handle:
            self.assertEqual(handle.read(3), b"WIM")

    def test_missing_wimlib_fails_with_a_clear_error(self):
        with mock.patch.object(core, "FAT32_MAX_FILE_SIZE", 1024), \
                mock.patch.object(core, "find_wim_split_command", return_value=None):
            self.assertEqual(core.split_install_wim(self.source, self.target), 1)

    def test_oversized_esd_is_reported(self):
        os.remove(self.wim)
        esd = os.path.join(self.source, "sources", "install.esd")
        with open(esd, "wb") as handle:
            handle.write(b"ESD" * 4096)

        with mock.patch.object(core, "FAT32_MAX_FILE_SIZE", 1024):
            self.assertEqual(core.split_install_wim(self.source, self.target), 1)

    def test_install_wim_is_skipped_during_the_copy(self):
        with open(os.path.join(self.source, "sources", "boot.wim"), "wb") as handle:
            handle.write(b"BOOT")

        with mock.patch.object(core.utils, "check_kill_signal", return_value=None), \
                mock.patch.object(core, "FAT32_MAX_FILE_SIZE", 1024):
            core.copy_filesystem_files(self.source, self.target, skip_oversized_wim=True)

        self.assertFalse(os.path.exists(os.path.join(self.target, "sources", "install.wim")))
        self.assertTrue(os.path.isfile(os.path.join(self.target, "sources", "boot.wim")))

    def test_oversized_helper_only_matches_install_wim(self):
        with mock.patch.object(core, "FAT32_MAX_FILE_SIZE", 1024):
            self.assertTrue(core.is_oversized_install_wim(self.wim))
            self.assertFalse(core.is_oversized_install_wim(
                os.path.join(self.source, "sources", "boot.wim")))


if __name__ == "__main__":
    unittest.main()
