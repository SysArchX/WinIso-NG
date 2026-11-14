#!/usr/bin/env python3
"""Unit tests for the lsblk based device filter."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import WinIso.list_devices as devices  # noqa: E402


def disk(name, size="16G", tran="usb", rm=True, model="SanDisk Cruzer", children=None):
    return {
        "name": name,
        "kname": name,
        "path": "/dev/" + name,
        "size": size,
        "type": "disk",
        "tran": tran,
        "rm": rm,
        "mountpoint": None,
        "model": model,
        "children": children or [],
    }


def part(name, mountpoint, size="512M"):
    return {
        "name": name,
        "kname": name,
        "path": "/dev/" + name,
        "size": size,
        "type": "part",
        "tran": None,
        "rm": False,
        "mountpoint": mountpoint,
        "model": None,
    }


def fake_lsblk():
    return {"blockdevices": [
        disk("sda", size="465.8G", tran="sata", rm=False, model="TOSHIBA MQ01ABF050", children=[
            part("sda1", "/boot/efi"),
            part("sda2", "/"),
        ]),
        disk("sdb", size="14.5G", tran="usb", rm=True, model="SanDisk Cruzer Blade"),
        disk("sdc", size="1.8T", tran="sata", rm=False, model="Backup HDD"),
        disk("sdd", size="8G", tran="usb", rm=True, model="SwapStick", children=[
            part("sdd1", "[SWAP]"),
        ]),
        disk("sde", size="32G", tran="usb", rm=True, model="HomeStick", children=[
            part("sde1", "/home"),
        ]),
        {
            "name": "loop0", "kname": "loop0", "path": "/dev/loop0", "size": "4G",
            "type": "loop", "tran": None, "rm": False, "mountpoint": "/mnt/lfs", "model": None,
        },
    ]}


class DeviceFilterTests(unittest.TestCase):
    def setUp(self):
        self.data = fake_lsblk()

    def paths(self, show_all):
        return [node["path"] for node in devices.available_devices(show_all, data=self.data)]

    def test_root_disk_is_always_blocked(self):
        self.assertNotIn("/dev/sda", self.paths(show_all=False))
        self.assertNotIn("/dev/sda", self.paths(show_all=True))

    def test_removable_device_is_accepted(self):
        self.assertIn("/dev/sdb", self.paths(show_all=False))

    def test_internal_disk_only_with_show_all(self):
        self.assertNotIn("/dev/sdc", self.paths(show_all=False))
        self.assertIn("/dev/sdc", self.paths(show_all=True))

    def test_swap_and_home_disks_are_blocked(self):
        for show_all in (False, True):
            selected = self.paths(show_all)
            self.assertNotIn("/dev/sdd", selected)
            self.assertNotIn("/dev/sde", selected)

    def test_loop_devices_are_ignored(self):
        self.assertNotIn("/dev/loop0", self.paths(show_all=True))

    def test_protected_disks_reports_the_root_disk(self):
        self.assertIn("/dev/sda", devices.protected_disks(self.data, extra_sources=set()))

    def test_hidden_system_disks_lists_the_root_disk(self):
        hidden = devices.hidden_system_disks(data=self.data)
        self.assertTrue(any("/dev/sda" in line and "/" in line for line in hidden))

    def test_description_contains_model_and_size(self):
        node = [item for item in devices.available_devices(show_all=True, data=self.data)
                if item["path"] == "/dev/sdb"][0]
        self.assertEqual(devices.describe_device(node), "/dev/sdb (SanDisk Cruzer Blade, 14.5G)")

    def test_usb_drive_returns_path_and_description(self):
        drives = devices.usb_drive(show_all=False)
        self.assertTrue(all(isinstance(path, str) and isinstance(text, str) for path, text in drives))

    def test_device_details_returns_model_size_and_path(self):
        details = devices.device_details("/dev/sdb", data=self.data)
        self.assertEqual(details["path"], "/dev/sdb")
        self.assertEqual(details["model"], "SanDisk Cruzer Blade")
        self.assertEqual(details["size"], "14.5G")

    def test_system_mountpoint_normalisation(self):
        self.assertTrue(devices.is_system_mountpoint("/"))
        self.assertTrue(devices.is_system_mountpoint("/boot/efi/"))
        self.assertTrue(devices.is_system_mountpoint("[swap]"))
        self.assertFalse(devices.is_system_mountpoint("/media/user/USB"))
        self.assertFalse(devices.is_system_mountpoint("/boot_extra"))


if __name__ == "__main__":
    unittest.main()
