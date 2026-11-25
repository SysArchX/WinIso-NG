#!/usr/bin/env python3
"""Windows backend for WinIso-NG.

The Linux engine in :mod:`WinIso.core` relies on mount, parted, mkfs and GRUB.
On Windows the same job is done with native tools instead:

* PowerShell ``Get-Disk`` to list removable disks (system and boot disks are
  filtered out);
* ``diskpart`` to clean the disk, create one partition and format it;
* ``Mount-DiskImage`` to mount the ISO without extracting it;
* ``robocopy`` to copy the installation files;
* ``wimlib-imagex`` (optional) to split ``install.wim`` for FAT32 targets;
* ``bootsect`` (optional, Windows ADK) to make the drive bootable on BIOS.

Every run is described by a :class:`Plan`. The same plan object is rendered by
``--dry-run`` and executed by a real write, so what the user previews is exactly
what would run. Preconditions (image exists, disk is not the system disk, the
target is removable, a drive letter is free) are checked before anything is
mounted or wiped.

Only whole physical disks can be selected, the system/boot disk is refused even
if it reaches this module, and every destructive step is logged.
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

FAT32_MAX_FILE_SIZE = (2 ** 32) - 1

REMOVABLE_BUS_TYPES = ("USB", "SD", "MMC", "1394")

POWERSHELL = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command"]

PREFERRED_LETTERS = ("W", "X", "Y", "Z", "V", "U", "T", "R", "Q", "P", "O", "N")

FAT_FILESYSTEMS = ("FAT", "VFAT", "FAT32")


def available():
    """True when the app is running on Windows."""
    return sys.platform.startswith("win")


def is_admin():
    """True when the process has administrator rights (required by diskpart)."""
    if not available():
        return False

    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# disk discovery
# ---------------------------------------------------------------------------
def list_disks_data():
    """Return ``Get-Disk`` output as a list of dictionaries."""
    command = (
        "Get-Disk | Select-Object Number,FriendlyName,Size,BusType,IsSystem,IsBoot,PartitionStyle "
        "| ConvertTo-Json -Compress"
    )

    try:
        completed = subprocess.run(POWERSHELL + [command], capture_output=True, text=True)
    except OSError:
        return []

    payload = (completed.stdout or "").strip()
    if not payload:
        return []

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []

    if isinstance(data, dict):
        data = [data]

    return [disk for disk in data if isinstance(disk, dict)]


def used_drive_letters():
    """Drive letters currently in use (empty list off Windows)."""
    if not available():
        return []

    command = (
        "Get-Volume | Where-Object { $_.DriveLetter } "
        "| Select-Object -ExpandProperty DriveLetter | ConvertTo-Json -Compress"
    )

    try:
        completed = subprocess.run(POWERSHELL + [command], capture_output=True, text=True)
    except OSError:
        return []

    payload = (completed.stdout or "").strip()
    if not payload:
        return []

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []

    if isinstance(data, str):
        data = [data]

    return [str(letter).strip().rstrip(":") for letter in data if str(letter).strip()]


def free_drive_letter(used=(), preferred="W"):
    """First free drive letter, preferring ``preferred`` (``None`` if all taken)."""
    taken = set(str(letter).strip().rstrip(":").upper() for letter in used)
    candidates = [preferred] + [letter for letter in PREFERRED_LETTERS if letter != preferred]

    for letter in candidates:
        if letter.upper() not in taken:
            return letter.upper()

    return None


def is_candidate_disk(disk):
    """Whole removable disks that are not the running system."""
    if str(disk.get("BusType") or "").upper() not in REMOVABLE_BUS_TYPES:
        return False
    if disk.get("IsSystem") or disk.get("IsBoot"):
        return False
    return True


def select_disks(disks):
    """Filter a ``Get-Disk`` list down to safe targets."""
    return [disk for disk in disks if is_candidate_disk(disk)]


def human_size(size):
    """Format a byte count the way Windows does (GB with one decimal)."""
    try:
        value = float(size)
    except (TypeError, ValueError):
        return "?"

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return ("{0:.0f} {1}" if unit in ("B", "KB") else "{0:.1f} {1}").format(value, unit)
        value /= 1024.0

    return "?"


def describe_disk(disk):
    """Label shown in the device dropdown."""
    name = (disk.get("FriendlyName") or "Disk").strip()
    return "Disk {0} - {1} ({2})".format(disk.get("Number"), name, human_size(disk.get("Size")))


def disk_token(disk):
    """Stable identifier used by the GUI (the physical disk number)."""
    return str(disk.get("Number"))


def list_removable_disks():
    """Return ``[[token, description], ...]`` for the GUI."""
    return [[disk_token(disk), describe_disk(disk)] for disk in select_disks(list_disks_data())]


def disk_details(number):
    """Return the model, size and physical path of a disk number."""
    for disk in list_disks_data():
        if str(disk.get("Number")) == str(number):
            return {
                "number": disk.get("Number"),
                "model": (disk.get("FriendlyName") or "").strip(),
                "size": human_size(disk.get("Size")),
                "bytes": disk.get("Size"),
                "bus": (disk.get("BusType") or "").strip(),
                "path": "\\\\.\\PhysicalDrive{0}".format(disk.get("Number")),
                "system": bool(disk.get("IsSystem") or disk.get("IsBoot")),
                "found": True,
            }

    return {"number": number, "model": "", "size": "", "bytes": None, "bus": "",
            "path": "", "system": False, "found": False}


# ---------------------------------------------------------------------------
# command builders (pure, unit tested)
# ---------------------------------------------------------------------------
def diskpart_script(disk_number, filesystem="NTFS", label="WINISO", letter="W",
                    partition_scheme="MBR", target_system="BIOS", quick_format=True):
    """Build the diskpart script that wipes and formats the target disk.

    The script also converts the disk to the requested partition scheme: after
    ``clean`` a disk keeps its old style, so ``create partition primary`` on a
    GPT disk would silently produce a GPT volume even when MBR was selected.
    """
    filesystem = (filesystem or "NTFS").upper()
    if filesystem in FAT_FILESYSTEMS:
        format_fs = "fat32"
    elif filesystem == "EXFAT":
        format_fs = "exfat"
    else:
        format_fs = "ntfs"

    scheme = "gpt" if str(partition_scheme).upper() == "GPT" else "mbr"
    uefi = str(target_system).upper() == "UEFI"

    safe_label = "".join(character for character in (label or "WINISO")[:11] if character.isalnum()) or "WINISO"

    format_line = 'format fs={0} {1}label="{2}"'.format(
        format_fs, "quick " if quick_format else "", safe_label)

    lines = [
        "select disk {0}".format(int(disk_number)),
        "clean",
        "convert {0}".format(scheme),
        "create partition primary",
        "select partition 1",
        format_line,
    ]

    # Only MBR disks boot through the legacy BIOS chain
    if scheme == "mbr" and not uefi:
        lines.append("active")

    lines.extend(["assign letter={0}".format(letter), "exit", ""])

    return "\n".join(lines)


def robocopy_command(source, target, skip_install_wim=False):
    """Build the robocopy command used to copy the ISO contents."""
    command = [
        "robocopy", source, target,
        "/E",            # include empty directories
        "/COPY:DAT",     # data, attributes, timestamps
        "/DCOPY:DAT",    # same for directories
        "/NFL", "/NDL",  # no per-file / per-directory lists
        "/NJH", "/NJS",  # no job header/summary
        "/NP",           # no progress percentage spam
        "/R:1", "/W:1",  # one retry, one second
        "/XJ",           # skip junction points
    ]

    if skip_install_wim:
        command.append("/XF")
        command.append("install.wim")

    return command


def mount_iso_command(image_path):
    """PowerShell one-liner that mounts an ISO and prints its drive letter."""
    return (
        "$m = Mount-DiskImage -ImagePath '{0}' -PassThru; "
        "$v = $m | Get-Volume; "
        "Write-Output $v.DriveLetter"
    ).format(image_path.replace("'", "''"))


def dismount_iso_command(image_path):
    return "Dismount-DiskImage -ImagePath '{0}'".format(image_path.replace("'", "''"))


def bootsect_command(letter):
    """Make the partition bootable on legacy BIOS (needs the Windows ADK)."""
    return ["bootsect", "/nt60", "{0}:".format(letter), "/mbr"]


def _is_fat(filesystem):
    return str(filesystem or "").upper() in FAT_FILESYSTEMS


def _expected_filesystem(filesystem):
    if _is_fat(filesystem):
        return "FAT32"
    return str(filesystem or "NTFS").upper()


def wim_split_command():
    """``wimlib-imagex split`` argv prefix, or ``None`` when it is not installed."""
    tool = shutil.which("wimlib-imagex")
    if tool is None:
        return None
    return [tool, "split"]


# ---------------------------------------------------------------------------
# the plan: one description used by both the dry run and the real write
# ---------------------------------------------------------------------------
class PlanStep(object):
    """One step of a write, with the commands it would run."""

    def __init__(self, key, title, commands=(), payload=None, description=""):
        self.key = key
        self.title = title
        self.commands = list(commands)
        self.payload = payload or {}
        self.description = description


class Plan(object):
    """A complete, reviewable description of a Windows write."""

    def __init__(self, image_path, disk_number, filesystem, label, letter,
                 partition_scheme, target_system, steps, warnings, errors, disk=None):
        self.image_path = image_path
        self.disk_number = disk_number
        self.filesystem = filesystem
        self.label = label
        self.letter = letter
        self.partition_scheme = partition_scheme
        self.target_system = target_system
        self.steps = steps
        self.warnings = warnings
        self.errors = errors
        self.disk = disk or {}

    @property
    def ok(self):
        return not self.errors

    def step(self, key):
        for step in self.steps:
            if step.key == key:
                return step
        return None

    def render(self):
        """Human readable plan, with ``<ISO>``/``<TARGET>`` placeholders."""
        model = (self.disk.get("model") or self.disk.get("FriendlyName") or "").strip()
        size = self.disk.get("size") or human_size(self.disk.get("Size"))

        lines = [
            "",
            "WinIso-NG Windows plan",
            "=" * 23,
            "Image:        {0}".format(self.image_path),
            "Disk:         {0} - {1} ({2})".format(self.disk_number, model or "unknown", size or "unknown"),
            "Filesystem:   {0}, label {1}".format(self.filesystem, self.label),
            "Partitions:   {0}, target {1}".format(self.partition_scheme, self.target_system),
            "Drive letter: {0}:".format(self.letter),
        ]

        lines.extend([
            "",
            "<ISO> is the mounted image and <TARGET> the {0}: drive.".format(self.letter),
        ])

        if self.errors:
            lines.append("")
            lines.append("Errors (nothing will be written):")
            lines.extend("  - " + error for error in self.errors)

        if self.warnings:
            lines.append("")
            lines.append("Warnings:")
            lines.extend("  - " + warning for warning in self.warnings)

        lines.append("")
        lines.append("Steps:")

        for index, step in enumerate(self.steps, 1):
            lines.append("{0}. {1}".format(index, step.title))
            if step.description:
                lines.append("   " + step.description)
            for command in step.commands:
                for line in str(command).replace("%ISO%", "<ISO>").replace("%TARGET%", "<TARGET>").splitlines():
                    lines.append("     " + line)
            lines.append("")

        return "\n".join(lines)


def build_plan(image_path, disk_number, filesystem="NTFS", label="WINISO",
               win11_bypass=False, partition_scheme="MBR", target_system="BIOS",
               quick_format=True, cluster_size="Default", letter=None,
               disk=None, used_letters=None, has_wimlib=None, has_bootsect=None,
               image_exists=None):
    """Describe (and validate) a write without touching the disk.

    Every parameter that would normally be probed from the system can be
    injected, which is what the tests do. Off Windows the probes return nothing,
    so the plan is still rendered and only the disk checks are skipped.
    """
    errors = []
    warnings = []

    if image_exists is None:
        image_exists = os.path.isfile(image_path)
    if not image_exists:
        errors.append("Image not found: {0}".format(image_path))
    elif os.path.splitext(str(image_path))[1].lower() not in (".iso", ".img"):
        warnings.append("The image does not have an .iso/.img extension; make sure it is a Windows image.")

    info = dict(disk) if disk is not None else disk_details(disk_number)
    found = bool(info.get("found", True))

    if not found:
        message = "Disk {0} was not found.".format(disk_number)
        if available():
            errors.append(message)
        else:
            warnings.append(message + " Disk checks are skipped because this is not Windows.")

    system = bool(info.get("system") or info.get("IsSystem") or info.get("IsBoot"))
    if system:
        errors.append("Disk {0} hosts Windows (system/boot disk); refusing to use it.".format(disk_number))

    bus = str(info.get("bus") or info.get("BusType") or "").upper()
    if bus and bus not in REMOVABLE_BUS_TYPES:
        errors.append("Disk {0} is a {1} disk, not a removable USB/SD device.".format(disk_number, bus))

    if cluster_size and str(cluster_size) != "Default":
        warnings.append(
            "Cluster size {0} is not applied on Windows: diskpart formats with the default "
            "cluster size.".format(cluster_size))

    fat = _is_fat(filesystem)

    if str(partition_scheme).upper() == "GPT" and str(target_system).upper() != "UEFI":
        warnings.append("A GPT disk only boots on most firmware with UEFI; choose MBR for BIOS.")
    if str(partition_scheme).upper() == "MBR" and str(target_system).upper() == "UEFI":
        warnings.append("UEFI boot from an MBR disk only works on firmware with CSM enabled.")

    if has_wimlib is None:
        has_wimlib = wim_split_command() is not None
    if has_bootsect is None:
        has_bootsect = shutil.which("bootsect") is not None

    if fat and not has_wimlib:
        warnings.append(
            "wimlib-imagex was not found: if sources\\install.wim is larger than 4 GiB the FAT32 "
            "write will stop before copying. Install wimlib or use NTFS/exFAT.")
    if str(target_system).upper() != "UEFI" and not has_bootsect:
        warnings.append(
            "bootsect was not found (Windows ADK): the BIOS boot code will not be written, so the "
            "drive will only boot on UEFI systems.")

    if used_letters is None:
        used_letters = used_drive_letters()
    if letter is None:
        letter = free_drive_letter(used_letters)
    if letter is None:
        errors.append("Every preferred drive letter is in use; free one of W-X-Y-Z-V-U-T-R-Q-P.")

    letter = letter or "W"
    steps = []

    steps.append(PlanStep(
        "mount",
        "Mount the image",
        [" ".join(POWERSHELL + [mount_iso_command(image_path)])],
        {"image": image_path},
    ))

    script = diskpart_script(disk_number, filesystem, label, letter,
                             partition_scheme=partition_scheme,
                             target_system=target_system,
                             quick_format=quick_format)
    steps.append(PlanStep(
        "format",
        "Wipe disk {0} and format it as {1}".format(disk_number, _expected_filesystem(filesystem)),
        ["diskpart /s <temporary script>", script],
        {"script": script, "disk_number": disk_number, "letter": letter,
         "filesystem": filesystem},
        description="Everything on the disk is destroyed at this step.",
    ))

    if fat:
        steps.append(PlanStep(
            "split",
            "Split install.wim for FAT32 (only when it is larger than 4 GiB)",
            ["wimlib-imagex split %ISO%sources\\install.wim %TARGET%sources\\install.swm 3800"],
            {},
            description="Skipped automatically when install.wim fits, or when the image ships "
                        "install.esd (which cannot be split).",
        ))

    copy_commands = [" ".join(robocopy_command("%ISO%", "%TARGET%"))]
    if fat:
        copy_commands.append(" ".join(robocopy_command("%ISO%", "%TARGET%", skip_install_wim=True)))

    steps.append(PlanStep(
        "copy",
        "Copy the installation files",
        copy_commands,
        {"fat": fat},
        description=("The second form, with /XF install.wim, is used only when the split ran."
                     if fat else ""),
    ))

    if win11_bypass:
        steps.append(PlanStep(
            "bypass",
            "Write autounattend.xml (Windows 11 bypass)",
            ["write %TARGET%autounattend.xml"],
        ))

    steps.append(PlanStep(
        "bootsect",
        "Write the legacy BIOS boot code (bootsect)",
        [" ".join(bootsect_command(letter))],
        {"letter": letter},
        description="Uses the Windows ADK bootsect; skipped when it is not installed.",
    ))

    steps.append(PlanStep(
        "verify",
        "Verify the copy",
        [
            "Test-Path %TARGET%sources\\boot.wim",
            "Test-Path %TARGET%sources\\install.wim (or install*.swm)",
            "Test-Path %TARGET%bootmgr (or efi\\boot\\bootx64.efi)",
        ],
    ))

    steps.append(PlanStep(
        "dismount",
        "Dismount the image",
        [" ".join(POWERSHELL + [dismount_iso_command(image_path)])],
        {"image": image_path},
    ))

    return Plan(image_path, disk_number, filesystem, label, letter,
                partition_scheme, target_system, steps, warnings, errors, disk=info)


# ---------------------------------------------------------------------------
# execution
# ---------------------------------------------------------------------------
def _run(command, log=None, check=False, echo=True):
    if log is not None and echo:
        log("> " + (command if isinstance(command, str) else " ".join(command)))

    completed = subprocess.run(command, capture_output=True, text=True)
    output = ((completed.stdout or "") + (completed.stderr or "")).strip()

    if output and log is not None:
        for line in output.splitlines():
            log(line)

    if check and completed.returncode != 0:
        raise RuntimeError("command failed ({0}): {1}".format(completed.returncode, output[:400]))

    return completed


def mount_iso(image_path, log=None):
    """Mount an ISO and return its drive letter (without the colon)."""
    completed = _run(POWERSHELL + [mount_iso_command(image_path)], log=log, check=True)
    letter = (completed.stdout or "").strip().splitlines()[-1].strip().rstrip(":")

    if len(letter) != 1:
        raise RuntimeError("could not determine the mounted ISO drive letter")

    return letter


def dismount_iso(image_path, log=None):
    try:
        _run(POWERSHELL + [dismount_iso_command(image_path)], log=log)
    except OSError:
        pass


def _run_diskpart(script, log=None):
    handle, path = tempfile.mkstemp(prefix="winiso-", suffix=".txt")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as script_file:
            script_file.write(script)

        _run(["diskpart", "/s", path], log=log, check=True, echo=False)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def format_disk(disk_number, filesystem="NTFS", label="WINISO", letter="W", log=None,
                partition_scheme="MBR", target_system="BIOS", quick_format=True, script=None):
    """Run diskpart with the generated script."""
    script = script or diskpart_script(disk_number, filesystem, label, letter,
                                       partition_scheme=partition_scheme,
                                       target_system=target_system,
                                       quick_format=quick_format)
    _run_diskpart(script, log=log)


def volume_info(letter):
    """``Get-Volume`` details for a letter, or ``None`` when the volume is not there."""
    if not available():
        return None

    command = (
        "Get-Volume -DriveLetter {0} -ErrorAction SilentlyContinue "
        "| Select-Object DriveLetter,FileSystem,FileSystemLabel | ConvertTo-Json -Compress"
    ).format(letter)

    try:
        completed = subprocess.run(POWERSHELL + [command], capture_output=True, text=True)
    except OSError:
        return None

    payload = (completed.stdout or "").strip()
    if not payload:
        return None

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None

    return data if isinstance(data, dict) else None


def wait_for_volume(letter, filesystem, attempts=15, delay=2):
    """Wait until diskpart's new volume is mounted, and check its filesystem."""
    expected = _expected_filesystem(filesystem).lower()

    for _ in range(attempts):
        info = volume_info(letter)
        if info:
            actual = str(info.get("FileSystem") or "").lower()
            if actual and actual != expected and not actual.startswith(expected):
                raise RuntimeError(
                    "drive {0}: was formatted as {1}, not {2}".format(letter, actual, expected))
            return info
        time.sleep(delay)

    raise RuntimeError("drive {0}: did not appear after formatting".format(letter))


def copy_files(source_root, target_root, skip_install_wim=False, log=None):
    """Copy the mounted ISO contents to the freshly formatted partition."""
    completed = _run(robocopy_command(source_root, target_root, skip_install_wim), log=log)

    # robocopy uses exit codes 0-7 for success (8 and above are failures)
    if completed.returncode >= 8:
        raise RuntimeError("robocopy failed with exit code {0}".format(completed.returncode))


def _needs_wim_split(source_root):
    for name in ("install.wim", "install.esd"):
        path = os.path.join(source_root, "sources", name)
        try:
            if os.path.isfile(path) and os.path.getsize(path) > FAT32_MAX_FILE_SIZE:
                return name
        except OSError:
            continue

    return None


def _execute(plan, emit):
    context = {"iso_root": None, "target_root": None, "mounted": False,
               "skip_install_wim": False}

    try:
        for step in plan.steps:
            if step.key == "dismount":
                continue

            emit("")
            emit(step.title)

            iso_root = context.get("iso_root") or "<ISO>"
            target_root = context.get("target_root") or "<TARGET>"
            for command in step.commands:
                for line in str(command).replace("%ISO%", iso_root).replace("%TARGET%", target_root).splitlines():
                    emit("  " + line)

            handler = _STEP_HANDLERS.get(step.key)
            if handler is not None:
                handler(step, context, emit)

        return 0
    except Exception as error:  # noqa: BLE001 - surfaced to the user
        emit("Error: {0}".format(error))
        return 1
    finally:
        if context.get("mounted"):
            emit("")
            emit("Dismount the image")
            dismount_iso(plan.image_path, log=emit)


def _step_mount(step, context, emit):
    letter = mount_iso(step.payload["image"], log=emit)
    context["iso_root"] = letter + ":\\"
    context["mounted"] = True

    if not os.path.isdir(os.path.join(context["iso_root"], "sources")):
        raise RuntimeError("the image has no sources folder; it does not look like a Windows ISO")
    emit("Mounted as {0}".format(context["iso_root"]))


def _step_format(step, context, emit):
    _run_diskpart(step.payload["script"], log=emit)
    context["target_root"] = step.payload["letter"] + ":\\"
    wait_for_volume(step.payload["letter"], step.payload["filesystem"])


def _step_split(step, context, emit):
    source_root = context["iso_root"]
    oversized = _needs_wim_split(source_root)

    if oversized is None:
        emit("install.wim fits into FAT32; no split is required.")
        return

    if oversized == "install.esd":
        raise RuntimeError(
            "the image ships an install.esd larger than 4 GiB, which cannot be split; "
            "use NTFS or exFAT as the target filesystem")

    command = wim_split_command()
    if command is None:
        raise RuntimeError(
            "install.wim is larger than 4 GiB and wimlib-imagex was not found; install wimlib "
            "or use NTFS/exFAT as the target filesystem")

    directory = os.path.join(context["target_root"], "sources")
    os.makedirs(directory, exist_ok=True)

    _run(command + [os.path.join(source_root, "sources", "install.wim"),
                    os.path.join(directory, "install.swm"), "3800"], log=emit, check=True)

    if not os.path.isfile(os.path.join(directory, "install.swm")):
        raise RuntimeError("wimlib-imagex did not create install.swm")

    context["skip_install_wim"] = True
    emit("install.wim was split into install*.swm.")


def _step_copy(step, context, emit):
    copy_files(context["iso_root"], context["target_root"],
               skip_install_wim=context.get("skip_install_wim", False), log=emit)


def _step_bypass(step, context, emit):
    from WinIso import core

    if core.write_autounattend(context["target_root"]) != 0:
        raise RuntimeError("could not write autounattend.xml")


def _step_bootsect(step, context, emit):
    if shutil.which("bootsect") is None:
        emit("bootsect was not found (Windows ADK); the drive boots on UEFI only.")
        return

    _run(bootsect_command(step.payload["letter"]), log=emit, check=True)


def _step_verify(step, context, emit):
    target = context["target_root"]

    required = [
        (os.path.join(target, "sources", "boot.wim"), "sources\\boot.wim"),
    ]

    has_install = os.path.isfile(os.path.join(target, "sources", "install.wim"))
    has_split = bool(glob.glob(os.path.join(target, "sources", "install*.swm")))
    if not (has_install or has_split):
        required.append((None, "sources\\install.wim or sources\\install*.swm"))

    has_boot = (os.path.isfile(os.path.join(target, "bootmgr")) or
                os.path.isfile(os.path.join(target, "efi", "boot", "bootx64.efi")))
    if not has_boot:
        required.append((None, "bootmgr or efi\\boot\\bootx64.efi"))

    missing = [label for path, label in required if path is None or not os.path.isfile(path)]

    if missing:
        raise RuntimeError("the copy is incomplete; missing: " + ", ".join(missing))

    emit("Required files are present on {0}".format(target))


_STEP_HANDLERS = {
    "mount": _step_mount,
    "format": _step_format,
    "split": _step_split,
    "copy": _step_copy,
    "bypass": _step_bypass,
    "bootsect": _step_bootsect,
    "verify": _step_verify,
}


def write_iso(image_path, disk_number, filesystem="NTFS", label="WINISO",
              win11_bypass=False, log=None, dry_run=False, partition_scheme="MBR",
              target_system="BIOS", quick_format=True, cluster_size="Default",
              disk=None, letter=None):
    """Create a bootable Windows USB drive from an ISO on Windows.

    ``dry_run`` prints the validated plan and returns without touching anything,
    so it can also be run on Linux to review what Windows would do.

    :return: 0 on success, 1 on failure
    """
    def emit(message):
        if log is not None:
            log(str(message))

    if not dry_run and not available():
        emit("The Windows backend can only write on Windows (use dry_run=True to preview).")
        return 1

    plan = build_plan(image_path, disk_number, filesystem=filesystem, label=label,
                      win11_bypass=win11_bypass, partition_scheme=partition_scheme,
                      target_system=target_system, quick_format=quick_format,
                      cluster_size=cluster_size, disk=disk, letter=letter)

    emit(plan.render())

    if not plan.ok:
        emit("Nothing was written.")
        return 1

    if dry_run:
        emit("Dry run: the plan above is valid. Nothing was written.")
        return 0

    if not is_admin():
        emit("WinIso-NG must run as administrator to write to a disk.")
        return 1

    return _execute(plan, emit)


# ---------------------------------------------------------------------------
# GUI job
# ---------------------------------------------------------------------------
class WindowsJob(threading.Thread):
    """Background writer used by the GUI on Windows."""

    def __init__(self, image_path, disk_number, filesystem, label, win11_bypass=False,
                 dry_run=False, partition_scheme="MBR", target_system="BIOS",
                 quick_format=True, cluster_size="Default", letter=None):
        super(WindowsJob, self).__init__(daemon=True)
        self.image_path = image_path
        self.disk_number = disk_number
        self.filesystem = filesystem
        self.label = label
        self.win11_bypass = win11_bypass
        self.dry_run = dry_run
        self.partition_scheme = partition_scheme
        self.target_system = target_system
        self.quick_format = quick_format
        self.cluster_size = cluster_size
        self.letter = letter

        self.progress = False
        self.state = ""
        self.error = ""
        self.kill = False
        self.finished = False
        self.log_sink = None

    def append_log(self, text):
        self.state = str(text)[:110]
        if self.log_sink is not None:
            self.log_sink(text)

    def run(self):
        try:
            result = write_iso(self.image_path, self.disk_number, self.filesystem, self.label,
                               self.win11_bypass, log=self.append_log, dry_run=self.dry_run,
                               partition_scheme=self.partition_scheme,
                               target_system=self.target_system,
                               quick_format=self.quick_format,
                               cluster_size=self.cluster_size,
                               letter=self.letter)
            if result != 0 and not self.error:
                self.error = "the operation did not complete"
        except Exception as error:  # noqa: BLE001
            self.error = str(error)
        finally:
            self.finished = True


# ---------------------------------------------------------------------------
# command line (dry run is the default)
# ---------------------------------------------------------------------------
def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="WinIso.windows_backend",
        description="Preview (default) or run the Windows write plan.")
    parser.add_argument("--list", action="store_true", help="list removable disks")
    parser.add_argument("--image", help="Windows ISO or IMG file")
    parser.add_argument("--disk", type=int, help="physical disk number")
    parser.add_argument("--fs", default="NTFS", help="FAT32, NTFS or EXFAT (default: NTFS)")
    parser.add_argument("--label", default="WINISO", help="volume label")
    parser.add_argument("--scheme", default="MBR", choices=["MBR", "GPT"])
    parser.add_argument("--target", default="BIOS", choices=["BIOS", "UEFI"])
    parser.add_argument("--bypass", action="store_true", help="write the Windows 11 bypass")
    parser.add_argument("--no-quick-format", action="store_true")
    parser.add_argument("--letter", help="drive letter to use (default: first free one)")
    parser.add_argument("--dry-run", action="store_true",
                        help="only print the plan (this is also the default)")
    parser.add_argument("--write", action="store_true",
                        help="actually write; without it nothing is changed")
    args = parser.parse_args(argv)

    if args.list:
        for token, description in list_removable_disks():
            print("{0}\t{1}".format(token, description))
        return 0

    if not args.image or args.disk is None:
        parser.error("--image and --disk are required unless --list is used")

    dry_run = not args.write

    return write_iso(args.image, args.disk, filesystem=args.fs, label=args.label,
                     win11_bypass=args.bypass, log=print, dry_run=dry_run,
                     partition_scheme=args.scheme, target_system=args.target,
                     quick_format=not args.no_quick_format, letter=args.letter)


if __name__ == "__main__":
    sys.exit(main())
