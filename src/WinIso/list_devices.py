#!/usr/bin/env python3
"""
Block device discovery for WinIso-NG.

The whole device tree is read at once with ``lsblk -J`` instead of one call per
device, and every physical disk that backs a mounted system filesystem (/,
/boot, /boot/efi, /home or swap) is filtered out before the list reaches the
user interface.  That filter is deliberately independent from the "List USB
Hard Drives" option: the disk running the live system can never be selected.
"""

import json
import os
import re
import subprocess

LSBLK_FIELDS = ["NAME", "KNAME", "PATH", "SIZE", "TYPE", "TRAN", "RM", "MOUNTPOINT", "MODEL"]

LSBLK_COMMAND = ["lsblk", "-J", "-o", ",".join(LSBLK_FIELDS)]

#: Mountpoints that must never be reachable as a write target.
SYSTEM_MOUNTPOINTS = ("/", "/boot", "/boot/efi", "/home", "[SWAP]")

#: Pseudo devices that can never be a real installation target.
IGNORED_TYPES = ("loop", "rom", "ram", "zram", "dm", "md", "nbd", "rbd")


# ---------------------------------------------------------------------------
# lsblk plumbing
# ---------------------------------------------------------------------------
def run_lsblk():
    """Return the parsed ``lsblk -J`` output, or an empty tree when it fails."""
    try:
        completed = subprocess.run(LSBLK_COMMAND, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, check=False)
    except OSError:
        return {"blockdevices": []}

    try:
        return json.loads(completed.stdout.decode("utf-8", "replace") or "{}")
    except json.JSONDecodeError:
        return {"blockdevices": []}


def block_devices(data=None):
    """Return the list of top level block devices from an lsblk JSON tree."""
    if data is None:
        data = run_lsblk()
    if not isinstance(data, dict):
        return []
    devices = data.get("blockdevices") or []
    return [device for device in devices if isinstance(device, dict)]


def iter_nodes(node):
    """Yield ``node`` and every descendant of it."""
    yield node
    for child in node.get("children") or []:
        if isinstance(child, dict):
            yield from iter_nodes(child)


def node_path(node):
    """The /dev path of a node, falling back to its NAME."""
    return node.get("path") or ("/dev/" + str(node.get("name") or node.get("kname") or ""))


def node_mountpoints(node):
    """Every non empty mountpoint of a node and its children."""
    for item in iter_nodes(node):
        mountpoint = (item.get("mountpoint") or "").strip()
        if mountpoint:
            yield mountpoint


def normalize_mountpoint(mountpoint):
    """Normalise a mountpoint for comparisons (/boot/efi/ == /boot/efi)."""
    mountpoint = (mountpoint or "").strip()
    if not mountpoint:
        return ""
    if mountpoint.startswith("[") and mountpoint.endswith("]"):
        return mountpoint.upper()
    return mountpoint.rstrip("/") or "/"


def is_system_mountpoint(mountpoint):
    """True when the mountpoint belongs to the running host system."""
    normalized = normalize_mountpoint(mountpoint)
    return normalized in {normalize_mountpoint(item) for item in SYSTEM_MOUNTPOINTS}


def system_mountpoints_of(node):
    """The host system mountpoints found anywhere below ``node``."""
    return [mountpoint for mountpoint in node_mountpoints(node) if is_system_mountpoint(mountpoint)]


# ---------------------------------------------------------------------------
# host disk protection
# ---------------------------------------------------------------------------
def _disk_name_of(source):
    """Map a partition device (sda2, nvme0n1p2, mmcblk0p1) to its disk name."""
    name = os.path.basename(source or "")
    match = re.match(r"^(nvme\d+n\d+|mmcblk\d+|mmcblk\d+boot\d+|loop\d+|md\d+)(?:p\d+)?$", name)
    if match:
        return match.group(1)
    return re.sub(r"\d+$", "", name)


def mounted_system_sources():
    """Device names backing the host system, read from /proc/mounts.

    This is only a safety net for setups where lsblk cannot report a real
    mountpoint (btrfs subvolumes, bind mounts, container overlays).
    """
    wanted = {normalize_mountpoint(item) for item in SYSTEM_MOUNTPOINTS}
    sources = set()

    try:
        with open("/proc/mounts", "r", encoding="utf-8", errors="replace") as mounts:
            for line in mounts:
                fields = line.split()
                if len(fields) < 2:
                    continue
                source, mountpoint = fields[0], fields[1].replace("\\040", " ")
                if normalize_mountpoint(mountpoint) in wanted and source.startswith("/dev/"):
                    sources.add(_disk_name_of(source))
    except OSError:
        return sources

    return sources


def as_device_list(devices):
    """Accept either an lsblk JSON tree or a plain list of device dictionaries."""
    if isinstance(devices, dict):
        return block_devices(devices)
    if devices is None:
        return []
    return [device for device in devices if isinstance(device, dict)]


def protected_disk_names(devices, extra_sources=None):
    """Names of the physical disks that hold the running system."""
    protected = set()

    for device in as_device_list(devices):
        if system_mountpoints_of(device):
            protected.add(str(device.get("name") or ""))
            protected.add(str(device.get("kname") or ""))

    for source in (mounted_system_sources() if extra_sources is None else extra_sources):
        protected.add(_disk_name_of(source))
        protected.add(source)

    protected.discard("")
    return protected


def protected_disks(devices, extra_sources=None):
    """Paths (/dev/sda) of the physical disks that hold the running system."""
    names = protected_disk_names(devices, extra_sources)
    paths = set()
    for device in as_device_list(devices):
        candidates = {str(device.get("name") or ""), str(device.get("kname") or "")}
        if candidates & names:
            paths.add(node_path(device))
    return paths


def is_protected(node, protected_names):
    """True when ``node`` is one of the protected disks."""
    return bool({str(node.get("name") or ""), str(node.get("kname") or "")} & protected_names)


def is_removable(node):
    """True for devices the kernel reports as removable or attached over USB."""
    return bool(node.get("rm")) or str(node.get("tran") or "").lower() == "usb"


def is_candidate_disk(node):
    """Only whole, writable, non virtual disks can be an installation target."""
    device_type = str(node.get("type") or "").lower()
    name = str(node.get("name") or "")

    if device_type != "disk":
        return False
    if device_type in IGNORED_TYPES:
        return False

    # eMMC boot partitions (mmcblk0boot0) are not usable targets either
    if re.match(r"^mmcblk\d+boot\d+$", name):
        return False

    return True


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------
def describe_device(node):
    """Human readable label such as ``/dev/sdb (SanDisk Cruzer, 14.5G)``."""
    path = node_path(node)
    model = (node.get("model") or "").strip()
    size = (node.get("size") or "").strip()
    details = ", ".join(part for part in (model, size) if part)
    return path + (" (" + details + ")" if details else "")


def available_devices(show_all=False, data=None):
    """Return the list of usable disks as dictionaries."""
    devices = block_devices(data)
    protected = protected_disk_names(devices)
    selected = []

    for node in devices:
        if not is_candidate_disk(node):
            continue
        if is_protected(node, protected):
            continue
        if not show_all and not is_removable(node):
            continue
        selected.append(node)

    return selected


def usb_drive(show_all=False):
    """Return ``[[path, description], ...]`` for the device dropdown."""
    return [[node_path(node), describe_device(node)]
            for node in available_devices(show_all)]


def hidden_system_disks(data=None):
    """Descriptions of the disks that were hidden because they host the system."""
    devices = block_devices(data=data)
    protected = protected_disk_names(devices)
    return [describe_device(node) + " -> " + ", ".join(sorted(set(system_mountpoints_of(node))))
            for node in devices
            if is_candidate_disk(node) and is_protected(node, protected)]


def device_details(path, data=None):
    """Return model, size, path and mountpoints for one device path."""
    devices = block_devices(data=data)
    for node in devices:
        if node_path(node) == path:
            return {
                "path": path,
                "model": (node.get("model") or "").strip(),
                "size": (node.get("size") or "").strip(),
                "transport": (node.get("tran") or "").strip(),
                "removable": is_removable(node),
                "mountpoints": sorted(set(node_mountpoints(node))),
            }

    return {"path": path, "model": "", "size": "", "transport": "", "removable": False, "mountpoints": []}


def dvd_drive():
    """Return the installed optical drives as ``[[path, description], ...]``."""
    devices_list = []
    find = subprocess.run(["find", "/sys/block",
                           "-maxdepth", "1",
                           "-mindepth", "1"], stdout=subprocess.PIPE).stdout.decode("utf-8").split()
    devices = []
    for device in find:
        tmp = re.findall("sr[0-9]", device)

        if tmp == []:
            continue

        devices.append([device, tmp[0]])

    for device in devices:
        optical_disk_drive_devfs_path = "/dev/" + device[1]

        try:
            with open(device[0] + "/device/model", "r") as model:
                model_content = model.read().strip()
        except OSError:
            model_content = ""

        devices_list.append([optical_disk_drive_devfs_path, optical_disk_drive_devfs_path + " - " + model_content])

    return devices_list


if __name__ == "__main__":
    for line in hidden_system_disks():
        print("hidden:", line)
    for path, description in usb_drive(show_all=True):
        print(description)
