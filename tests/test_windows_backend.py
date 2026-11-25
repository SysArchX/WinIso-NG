#!/usr/bin/env python3
"""Tests for the Windows backend (disk filtering, command builders, plan, dry run).

They do not touch a real disk: only the generated scripts, the plan and the
filtering logic are checked, so they run on Linux and Windows alike. The dry run
is exercised with ``subprocess`` disabled, which proves that it writes nothing.
"""

import os
import sys
import tempfile
import unittest
import unittest.mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import WinIso.windows_backend as backend  # noqa: E402


def disk(number, name="SanDisk Cruzer", size=32 * 1024 ** 3, bus="USB", system=False, boot=False):
    return {
        "Number": number,
        "FriendlyName": name,
        "Size": size,
        "BusType": bus,
        "IsSystem": system,
        "IsBoot": boot,
        "PartitionStyle": "MBR",
    }


class DiskFilterTests(unittest.TestCase):
    def setUp(self):
        self.disks = [
            disk(0, "Samsung 980", 1 * 1024 ** 4, bus="NVMe", system=True, boot=True),
            disk(1, "Internal HDD", 2 * 1024 ** 4, bus="SATA"),
            disk(2, "SanDisk Cruzer", 32 * 1024 ** 3, bus="USB"),
            disk(3, "Kingston DataTraveler", 16 * 1024 ** 3, bus="USB", boot=True),
        ]

    def test_system_and_boot_disks_are_filtered(self):
        numbers = [item["Number"] for item in backend.select_disks(self.disks)]
        self.assertEqual(numbers, [2])

    def test_non_removable_bus_is_filtered(self):
        self.assertFalse(backend.is_candidate_disk(self.disks[1]))

    def test_description_contains_disk_number_and_size(self):
        self.assertEqual(backend.describe_disk(self.disks[2]), "Disk 2 - SanDisk Cruzer (32.0 GB)")

    def test_token_is_the_disk_number(self):
        self.assertEqual(backend.disk_token(self.disks[2]), "2")

    def test_human_size_units(self):
        self.assertEqual(backend.human_size(512), "512 B")
        self.assertEqual(backend.human_size(2048), "2 KB")
        self.assertEqual(backend.human_size(5 * 1024 ** 3), "5.0 GB")


class CommandBuilderTests(unittest.TestCase):
    def test_diskpart_script_ntfs(self):
        script = backend.diskpart_script(3, "NTFS", "WINISO", "W")
        self.assertIn("select disk 3", script)
        self.assertIn("clean", script)
        self.assertIn("create partition primary", script)
        self.assertIn('format fs=ntfs quick label="WINISO"', script)
        self.assertIn("assign letter=W", script)

    def test_diskpart_script_fat32(self):
        script = backend.diskpart_script(1, "FAT", "MY USB", "X")
        self.assertIn('format fs=fat32 quick label="MYUSB"', script)
        self.assertIn("assign letter=X", script)

    def test_diskpart_script_exfat(self):
        self.assertIn("format fs=exfat", backend.diskpart_script(0, "EXFAT"))

    def test_diskpart_script_converts_the_partition_scheme(self):
        self.assertIn("convert mbr", backend.diskpart_script(2, "NTFS", "WINISO", "W"))
        self.assertIn("convert gpt", backend.diskpart_script(
            2, "NTFS", "WINISO", "W", partition_scheme="GPT", target_system="UEFI"))

    def test_diskpart_marks_the_partition_active_only_for_bios_mbr(self):
        self.assertIn("\nactive\n", backend.diskpart_script(2, "NTFS", "WINISO", "W"))
        self.assertNotIn("active", backend.diskpart_script(
            2, "NTFS", "WINISO", "W", partition_scheme="GPT", target_system="UEFI"))
        self.assertNotIn("active", backend.diskpart_script(
            2, "NTFS", "WINISO", "W", target_system="UEFI"))

    def test_diskpart_full_format_omits_quick(self):
        script = backend.diskpart_script(2, "NTFS", "WINISO", "W", quick_format=False)
        self.assertIn('format fs=ntfs label="WINISO"', script)
        self.assertNotIn("quick", script)

    def test_robocopy_copies_everything(self):
        command = backend.robocopy_command("E:\\", "W:\\")
        self.assertEqual(command[0], "robocopy")
        self.assertIn("E:\\", command)
        self.assertIn("W:\\", command)
        self.assertIn("/E", command)
        self.assertNotIn("/XF", command)

    def test_robocopy_skips_install_wim_when_splitting(self):
        command = backend.robocopy_command("E:\\", "W:\\", skip_install_wim=True)
        self.assertIn("/XF", command)
        self.assertIn("install.wim", command)

    def test_mount_iso_command_escapes_quotes(self):
        command = backend.mount_iso_command("D:\\isos\\win 11.iso")
        self.assertIn("Mount-DiskImage", command)
        self.assertIn("win 11.iso", command)

    def test_mount_iso_command_escapes_single_quotes(self):
        command = backend.mount_iso_command("D:\\bob's iso.iso")
        self.assertIn("bob''s iso.iso", command)

    def test_bootsect_command(self):
        self.assertEqual(backend.bootsect_command("W"), ["bootsect", "/nt60", "W:", "/mbr"])


class DriveLetterTests(unittest.TestCase):
    def test_prefers_w_when_free(self):
        self.assertEqual(backend.free_drive_letter(["C", "D"]), "W")

    def test_skips_used_letters(self):
        self.assertEqual(backend.free_drive_letter(["C", "D", "W", "X"]), "Y")

    def test_returns_none_when_every_letter_is_used(self):
        self.assertIsNone(backend.free_drive_letter(list(backend.PREFERRED_LETTERS)))


class PlanTests(unittest.TestCase):
    def setUp(self):
        handle, self.image = tempfile.mkstemp(suffix=".iso")
        os.write(handle, b"fake iso")
        os.close(handle)

    def tearDown(self):
        if os.path.exists(self.image):
            os.remove(self.image)

    def make_plan(self, **options):
        options.setdefault("disk", disk(2))
        options.setdefault("used_letters", ["C", "D", "W"])
        options.setdefault("has_wimlib", True)
        options.setdefault("has_bootsect", True)
        options.setdefault("image_exists", True)
        return backend.build_plan(self.image, 2, **options)

    def test_valid_plan_is_ok_and_ordered(self):
        plan = self.make_plan(filesystem="FAT")
        self.assertTrue(plan.ok)
        keys = [step.key for step in plan.steps]
        self.assertEqual(keys, ["mount", "format", "split", "copy", "bootsect", "verify", "dismount"])

    def test_ntfs_plan_has_no_split_step(self):
        keys = [step.key for step in self.make_plan(filesystem="NTFS").steps]
        self.assertNotIn("split", keys)

    def test_fat_plan_offers_the_split_and_the_skipping_copy(self):
        plan = self.make_plan(filesystem="FAT")
        self.assertIn("wimlib-imagex split", " ".join(plan.step("split").commands))
        copy = " ".join(plan.step("copy").commands)
        self.assertIn("/XF install.wim", copy)

    def test_plan_picks_a_free_drive_letter(self):
        self.assertEqual(self.make_plan().letter, "X")

    def test_plan_refuses_the_system_disk(self):
        plan = self.make_plan(disk=disk(0, bus="NVMe", system=True, boot=True))
        self.assertFalse(plan.ok)
        self.assertTrue(any("system" in error.lower() for error in plan.errors))

    def test_plan_refuses_a_non_removable_disk(self):
        plan = self.make_plan(disk=disk(1, bus="SATA"))
        self.assertFalse(plan.ok)
        self.assertTrue(any("not a removable" in error for error in plan.errors))

    def test_plan_refuses_a_missing_image(self):
        plan = self.make_plan(image_exists=False)
        self.assertFalse(plan.ok)
        self.assertTrue(any("Image not found" in error for error in plan.errors))

    def test_gpt_with_bios_warns(self):
        plan = self.make_plan(partition_scheme="GPT", target_system="BIOS")
        self.assertTrue(plan.ok)
        self.assertTrue(any("GPT" in warning for warning in plan.warnings))

    def test_cluster_size_warns_about_being_ignored(self):
        plan = self.make_plan(cluster_size="4096")
        self.assertTrue(any("Cluster size" in warning for warning in plan.warnings))

    def test_fat_without_wimlib_warns(self):
        plan = self.make_plan(filesystem="FAT", has_wimlib=False)
        self.assertTrue(any("wimlib-imagex was not found" in warning for warning in plan.warnings))

    def test_bios_without_bootsect_warns(self):
        plan = self.make_plan(has_bootsect=False)
        self.assertTrue(any("bootsect was not found" in warning for warning in plan.warnings))

    def test_win11_bypass_adds_a_step(self):
        keys = [step.key for step in self.make_plan(win11_bypass=True).steps]
        self.assertIn("bypass", keys)

    def test_render_contains_the_generated_commands(self):
        rendered = self.make_plan(filesystem="FAT").render()
        self.assertIn("select disk 2", rendered)
        self.assertIn("robocopy", rendered)
        self.assertIn("2 - SanDisk Cruzer", rendered)
        self.assertIn("X:", rendered)
        self.assertIn("<ISO>", rendered)
        self.assertIn("<TARGET>", rendered)


class DryRunTests(unittest.TestCase):
    def setUp(self):
        handle, self.image = tempfile.mkstemp(suffix=".iso")
        os.write(handle, b"fake iso")
        os.close(handle)
        self.messages = []

    def tearDown(self):
        if os.path.exists(self.image):
            os.remove(self.image)

    def log(self, message):
        self.messages.append(str(message))

    def test_dry_run_never_runs_a_command(self):
        original = backend._run

        def explode(*args, **kwargs):
            raise AssertionError("the dry run executed a command")

        backend._run = explode
        try:
            result = backend.write_iso(self.image, 2, log=self.log, dry_run=True,
                                       disk=disk(2), letter="X", filesystem="FAT")
        finally:
            backend._run = original

        output = "\n".join(self.messages)
        self.assertEqual(result, 0)
        self.assertIn("Dry run: the plan above is valid", output)
        self.assertIn("select disk 2", output)
        self.assertIn("robocopy", output)

    def test_dry_run_reports_errors_and_fails(self):
        result = backend.write_iso("/nonexistent/windows.iso", 2, log=self.log, dry_run=True,
                                   disk=disk(2), letter="X")
        self.assertEqual(result, 1)
        self.assertIn("Image not found", "\n".join(self.messages))
        self.assertIn("Nothing was written", "\n".join(self.messages))

    def test_windows_job_dry_run_finishes_without_error(self):
        job = backend.WindowsJob(self.image, 2, "FAT", "WINISO", dry_run=True, letter="X")
        job.log_sink = self.log
        job.start()
        job.join(10)

        self.assertTrue(job.finished)
        self.assertEqual(job.error, "")
        self.assertIn("Dry run", "\n".join(self.messages))

    def test_dry_run_reports_the_system_disk(self):
        result = backend.write_iso(self.image, 0, log=self.log, dry_run=True,
                                   disk=disk(0, bus="USB", system=True), letter="X")
        self.assertEqual(result, 1)
        self.assertIn("hosts Windows", "\n".join(self.messages))


class ExecutionFlowTests(unittest.TestCase):
    """Run the real execution path with the Windows tools replaced by fakes."""

    def setUp(self):
        handle, self.image = tempfile.mkstemp(suffix=".iso")
        os.write(handle, b"fake iso")
        os.close(handle)
        self.calls = []
        self.copied = {}

    def tearDown(self):
        if os.path.exists(self.image):
            os.remove(self.image)

    def plan(self, filesystem="FAT"):
        return backend.build_plan(self.image, 2, filesystem=filesystem, disk=disk(2),
                                  used_letters=["C", "D"], has_wimlib=True,
                                  has_bootsect=True, image_exists=True)

    def run_plan(self, plan, copy_error=None):
        def fake_run(command, **kwargs):
            name = command[0] if isinstance(command, list) else str(command).split()[0]
            self.calls.append(os.path.basename(name))
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()

        def fake_copy(source, target, skip_install_wim=False, log=None):
            self.calls.append("copy")
            self.copied["skip"] = skip_install_wim
            if copy_error:
                raise copy_error

        with unittest.mock.patch.object(backend, "mount_iso",
                                        lambda path, log=None: self.calls.append("mount") or "E"), \
                unittest.mock.patch.object(backend, "dismount_iso",
                                           lambda path, log=None: self.calls.append("dismount")), \
                unittest.mock.patch.object(backend, "_run_diskpart",
                                           lambda script, log=None: self.calls.append("diskpart")), \
                unittest.mock.patch.object(backend, "wait_for_volume", lambda *a, **k: {}), \
                unittest.mock.patch.object(backend, "_needs_wim_split", lambda root: "install.wim"), \
                unittest.mock.patch.object(backend, "copy_files", fake_copy), \
                unittest.mock.patch.object(backend, "_run", fake_run), \
                unittest.mock.patch.object(backend.shutil, "which", lambda name: "/usr/bin/" + name), \
                unittest.mock.patch.object(backend.os.path, "isdir", lambda path: True), \
                unittest.mock.patch.object(backend.os.path, "isfile", lambda path: True), \
                unittest.mock.patch.object(backend.os, "makedirs", lambda *a, **k: None), \
                unittest.mock.patch.object(backend.glob, "glob", lambda pattern: []):
            return backend._execute(plan, lambda line: None)

    def test_execution_follows_the_plan_and_splits_for_fat(self):
        result = self.run_plan(self.plan("FAT"))

        self.assertEqual(result, 0)
        self.assertEqual(self.calls, ["mount", "diskpart", "wimlib-imagex", "copy",
                                      "bootsect", "dismount"])
        self.assertTrue(self.copied["skip"])

    def test_execution_skips_the_split_for_ntfs(self):
        result = self.run_plan(self.plan("NTFS"))

        self.assertEqual(result, 0)
        self.assertNotIn("wimlib-imagex", self.calls)
        self.assertFalse(self.copied["skip"])

    def test_failure_still_dismounts_the_image(self):
        result = self.run_plan(self.plan("FAT"), copy_error=RuntimeError("copy failed"))

        self.assertEqual(result, 1)
        self.assertIn("dismount", self.calls)


class WriteGuardTests(unittest.TestCase):
    def test_write_iso_refuses_non_windows(self):
        result = backend.write_iso("C:\\image.iso", 2, log=lambda line: None)
        self.assertEqual(result, 1)

    def test_available_matches_platform(self):
        self.assertEqual(backend.available(), sys.platform.startswith("win"))


if __name__ == "__main__":
    unittest.main()
