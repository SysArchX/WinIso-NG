import os
import pathlib
import re
import shutil
import subprocess
import sys
import time
from xml.dom.minidom import parseString

import WinIso.miscellaneous as miscellaneous

_ = miscellaneous.i18n

#: Disable message coloring when set to True, set by --no-color
no_color = False

# External tools
try:
    import termcolor
except ImportError:
    print("Module termcolor is not installed, text coloring disabled")
    no_color = True

gui = None
verbose = False


def check_runtime_dependencies(application_name):
    """
    :param application_name:
    :return:
    """
    result = "success"

    system_commands = ["mount", "umount", "wipefs", "lsblk", "blockdev", "df", "parted", "7z"]
    for command in system_commands:
        if shutil.which(command) is None:
            print_with_color(
                _("Error: {0} requires {1} command in the executable search path, but it is not found.").format(
                    application_name, command),
                "red")
            result = "failed"

    fat = ["mkdosfs", "mkfs.msdos", "mkfs.vfat", "mkfs.fat"]
    for command in fat:
        if shutil.which(command) is not None:
            fat = command
            break

    if isinstance(fat, list):
        print_with_color(_("Error: mkdosfs/mkfs.msdos/mkfs.vfat/mkfs.fat command not found!"), "red")
        print_with_color(_("Error: Please make sure that dosfstools is properly installed!"), "red")
        result = "failed"

    ntfs = "mkntfs"
    if shutil.which("mkntfs") is None:
        print_with_color(_("Error: mkntfs command not found!"), "red")
        print_with_color(_("Error: Please make sure that ntfs-3g is properly installed!"), "red")
        result = "failed"

    grub = ["grub-install", "grub2-install"]
    for command in grub:
        if shutil.which(command) is not None:
            grub = command
            break

    if isinstance(grub, list):
        print_with_color(_("Error: grub-install or grub2-install command not found!"), "red")
        print_with_color(_("Error: Please make sure that GNU GRUB is properly installed!"), "red")
        result = "failed"

    if result != "success":
        raise RuntimeError("Dependencies are not met")
    else:
        return [fat, ntfs, grub]


def check_runtime_parameters(install_mode, source_media, target_media):
    """
    :param install_mode:
    :param source_media:
    :param target_media:
    :return:
    """
    if not os.path.isfile(source_media) and not pathlib.Path(source_media).is_block_device():
        print_with_color(
            _("Error: Source media \"{0}\" not found or not a regular file or a block device file!").format(
                source_media),
            "red")
        return 1

    if not pathlib.Path(target_media).is_block_device():
        print_with_color(_("Error: Target media \"{0}\" is not a block device file!").format(target_media), "red")
        return 1

    if install_mode == "device" and target_media[-1].isdigit():
        print_with_color(_("Error: Target media \"{0}\" is not an entire storage device!").format(target_media), "red")
        return 1

    if install_mode == "partition" and not target_media[-1].isdigit():
        print_with_color(_("Error: Target media \"{0}\" is not an partition!").format(target_media), "red")
        return 1
    return 0


def partition_node(device, number):
    """
    Build the partition device node for a storage device.

    Devices whose name ends with a digit (nvme0n1, mmcblk0, loop0) use the `p` separator,
    so naively appending the number produced paths like /dev/nvme0n11 that never exist.

    :param device: The whole storage device, for example /dev/sda or /dev/nvme0n1
    :param number: The partition number
    :return: The partition device node
    """
    if device and device[-1].isdigit():
        return device + "p" + str(number)
    return device + str(number)


def wait_for_block_device(path, timeout=15, interval=0.2):
    """
    Wait until a block device node appears in /dev.

    After repartitioning, udev and the kernel may need a moment to create the partition node,
    which made the mount step fail with "/dev/sdX1: Can't lookup blockdev".

    :param path: Device node to wait for
    :param timeout: Maximum time to wait in seconds
    :return: 0 - the node exists; 1 - timed out
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        if os.path.exists(path):
            return 0
        time.sleep(interval)

    print_with_color(
        _("Warning: The partition device {0} did not appear after {1} seconds, trying anyway...").format(
            path, timeout), "yellow")
    return 1


def get_filesystem_type(device):
    """
    :param device: Partition device node
    :return: Filesystem type reported by lsblk, for example vfat or ntfs
    """
    return subprocess.run(["lsblk",
                           "--output", "FSTYPE",
                           "--noheadings",
                           device], stdout=subprocess.PIPE).stdout.decode("utf-8").strip()


def determine_target_parameters(install_mode, target_media):
    """
    :param install_mode:
    :param target_media:
    :return:
    """
    if install_mode == "partition":
        target_partition = target_media

        while target_media[-1].isdigit():
            target_media = target_media[:-1]
        target_device = target_media
    else:
        target_device = target_media
        target_partition = partition_node(target_media, 1)

    if verbose:
        print_with_color(_("Info: Target device is {0}").format(target_device))
        print_with_color(_("Info: Target partition is {0}").format(target_partition))

    return [target_device, target_partition]


def get_mountpoints(device):
    """
    :param device: A storage device or partition device node
    :return: List of mountpoints currently using the device
    """
    result = subprocess.run(["findmnt", "--noheadings", "--output", "TARGET", "--source", device],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    if result.returncode != 0:
        return []

    return [line.strip() for line in result.stdout.decode("utf-8").splitlines() if line.strip()]


def check_is_target_device_busy(device):
    """
    Unmount every filesystem that is still mounted on the device.

    Automounted partitions were the reason behind the frequent
    "Refusing to make a filesystem here!" and "volume is already exclusively opened" failures.

    :param device:
    :return: 0 - not busy; 1 - a filesystem could not be unmounted
    """
    mountpoints = get_mountpoints(device)

    if mountpoints == []:
        return 0

    print_with_color(_("Warning: The following partitions will be unmounted: {0}").format(mountpoints), "yellow")

    for mountpoint in mountpoints:
        if subprocess.run(["umount", mountpoint]).returncode:
            print_with_color(
                _("Error: Unable to unmount {0}. Please unmount it manually and try again.").format(mountpoint),
                "red")
            return 1

    if get_mountpoints(device) != []:
        print_with_color(
            _("Error: {0} is still mounted by another program. Please unmount it manually and try again.").format(device),
            "red")
        return 1

    return 0


def check_source_and_target_not_busy(install_mode, source_media, target_device, target_partition):
    """
    :param install_mode:
    :param source_media:
    :param target_device:
    :param target_partition:
    :return:
    """
    if check_is_target_device_busy(source_media):
        print_with_color(_("Error: Source media is currently mounted, unmount the partition then try again"), "red")
        return 1

    if install_mode == "partition":
        if check_is_target_device_busy(target_partition):
            print_with_color(_("Error: Target partition is currently mounted, unmount the partition then try again"),
                             "red")
            return 1
    else:
        if check_is_target_device_busy(target_device):
            print_with_color(
                _(
                    "Error: Target device is currently busy, unmount all mounted partitions in target device then try again"),
                "red")
            return 1


def check_fat32_filesize_limitation(source_fs_mountpoint, quiet=False):
    """
    :param source_fs_mountpoint:
    :param quiet: Do not print the warning, only report the result
    :return: 1 if a file exceeds the FAT32 4GiB single file size limit
    """
    for dirpath, dirnames, filenames in os.walk(source_fs_mountpoint):
        for file in filenames:
            path = os.path.join(dirpath, file)
            if os.path.getsize(path) > (2 ** 32) - 1:  # Max fat32 file size
                if not quiet:
                    print_with_color(
                        _(
                            "Warning: File {0} in source image has exceed the FAT32 Filesystem 4GiB Single File Size Limitation, switching to NTFS filesystem.").format(
                            path),
                        "yellow")
                    print_with_color(
                        _(
                            "Refer: https://github.com/WoeUSB/WoeUSB-ng/wiki/Limitations#fat32-filesystem-4gib-single-file-size-limitation for more info."),
                        "yellow")
                return 1
    return 0


def check_target_partition(target_partition, target_device):
    """
    Check target partition for potential problems before mounting them for --partition creation mode as we don't know about the existing partition

    :param target_partition: The target partition to check
    :param target_device: The parent device of the target partition, this is passed in to check UEFI:NTFS filesystem's existence on check_uefi_ntfs_support_partition
    :return:
    """
    target_filesystem = get_filesystem_type(target_partition)

    if target_filesystem == "vfat":
        pass  # supported
    elif target_filesystem == "ntfs":
        check_uefi_ntfs_support_partition(target_device)
    else:
        print_with_color(_("Error: Target filesystem not supported, currently supported filesystem: FAT, NTFS."), "red")
        return 1

    return 0


def check_uefi_ntfs_support_partition(target_device):
    """
    Check if the UEFI:NTFS support partition exists
    Currently it depends on the fact that this partition has a label of "UEFI_NTFS"

    :param target_device: The UEFI:NTFS partition residing entier device file
    :return:
    """
    lsblk = subprocess.run(["lsblk",
                            "--output", "LABEL",
                            "--noheadings",
                            target_device], stdout=subprocess.PIPE).stdout.decode("utf-8").strip()

    if re.findall("UEFI_NTFS", lsblk) != []:
        print_with_color(
            _("Warning: Your device doesn't seems to have an UEFI:NTFS partition, "
              "UEFI booting will fail if the motherboard firmware itself doesn't support NTFS filesystem!"))
        print_with_color(
            _("Info: You may recreate disk with an UEFI:NTFS partition by using the --device creation method"))


def check_target_filesystem_free_space(target_fs_mountpoint, source_fs_mountpoint, target_partition):
    """
    :param target_fs_mountpoint:
    :param source_fs_mountpoint:
    :param target_partition:
    :return:
    """
    df = subprocess.run(["df",
                         "--block-size=1",
                         target_fs_mountpoint], stdout=subprocess.PIPE).stdout
    # free_space = int(df.strip().split()[4])

    awk = subprocess.Popen(["awk", "{print $4}"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    free_space = awk.communicate(input=df)[0]
    free_space = free_space.decode("utf-8").strip()
    free_space = re.sub("[^0-9]", "", free_space)
    free_space = int(free_space)

    needed_space = 0
    for dirpath, dirnames, filenames in os.walk(source_fs_mountpoint):
        for file in filenames:
            path = os.path.join(dirpath, file)
            needed_space += os.path.getsize(path)

    additional_space_required_for_grub_installation = 1000 * 1000 * 10  # 10MiB

    needed_space += additional_space_required_for_grub_installation

    if needed_space > free_space:
        print_with_color(_("Error: Not enough free space on target partition!"))
        print_with_color(
            _("Error: We required {0}({1} bytes) but '{2}' only has {3}({4} bytes).")
            .format(
                str(get_size(str(needed_space))),
                str(needed_space),
                target_partition,
                str(free_space),
                str(free_space)))
        return 1


def print_with_color(text, color=""):
    """
    Print function
    This function takes into account no_color flag
    Also if used by gui, sends information to it, rather than putting it into standard output

    :param text: Text to be printed
    :param color: Color of the text
    """
    if gui is not None:
        gui.state = text
        if hasattr(gui, "append_log"):
            try:
                gui.append_log(text)
            except Exception:
                pass
        if color == "red":
            gui.error = text
            sys.exit()
    else:
        if no_color or color == "":
            sys.stdout.write(text + "\n")
        else:
            termcolor.cprint(text, color)


def convert_to_human_readable_format(num, suffix='B'):
    for unit in ['', 'Ki', 'Mi', 'Gi']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Ti', suffix)


def get_size(path):
    total_size = 0
    for dirpath, __, filenames in os.walk(path):
        for file in filenames:
            path = os.path.join(dirpath, file)
            total_size += os.path.getsize(path)
    return total_size


def check_kill_signal():
    """
    Ok, you may asking yourself, what the f**k is this, and why is it called everywhere. Let me explain
    In python you can't just stop or kill thread, it must end its execution,
    or recognize moment where you want it to stop and politely perform euthanasia on itself.
    So, here, if gui is set, we throw exception which is going to be (hopefully) catch by GUI,
    simultaneously ending whatever script was doing meantime!
    Everyone goes to home happy and user is left with wrecked pendrive (just joking, next thing called by gui is cleanup)
    """
    if gui is not None:
        if gui.kill:
            raise sys.exit()


# noinspection DuplicatedCode
def update_policy_to_allow_for_running_gui_as_root(path):
    dom = parseString(
        "<?xml version=\"1.0\" ?>"
        "<!DOCTYPE policyconfig  PUBLIC '-//freedesktop//DTD polkit Policy Configuration 1.0//EN'  "
        "'http://www.freedesktop.org/software/polkit/policyconfig-1.dtd'><!-- \n"
        "DOC: https://www.freedesktop.org/software/polkit/docs/latest/polkit.8.html\n"
        "--><policyconfig>\n"
        "	<vendor>The WinIso Project</vendor>\n"
        "	<vendor_url>https://github.com/WinIso/WinIso-NG</vendor_url>\n"
        "	<icon_name>winiso-icon</icon_name>\n"
        "\n"
        "	<action id=\"com.github.winiso.winiso-ng.run-gui-using-pkexec\">\n"
        "		<description>Run `winiso` as SuperUser</description>\n"
        "		<description xml:lang=\"zh_TW\">以超級使用者(SuperUser)身份執行 `winiso`</description>\n"
        "		<description xml:lang=\"pl_PL\">Uruchom `winiso` jako root</description>\n"
        "		\n"
        "		<message>Authentication is required to run `winiso` as SuperUser.</message>\n"
        "		<message xml:lang=\"zh_TW\">以超級使用者(SuperUser)身份執行 `winiso` 需要通過身份驗證。</message>\n"
        "		<message xml:lang=\"pl_PL\">Wymagana jest autoryzacja do uruchomienia `winiso` jako root</message>\n"
        "		\n"
        "		<defaults>\n"
        "			<allow_any>auth_admin</allow_any>\n"
        "			<allow_inactive>auth_admin</allow_inactive>\n"
        "			<allow_active>auth_admin_keep</allow_active>\n"
        "		</defaults>\n"
        "		\n"
        "		<annotate key=\"org.freedesktop.policykit.exec.path\">/usr/local/bin/winisogui</annotate>\n"
        "   		<annotate key=\"org.freedesktop.policykit.exec.allow_gui\">true</annotate>\n"
        "	</action>\n"
        "	<action id=\"com.github.winiso.winiso-ng.run-gui-using-pkexec-local\">\n"
        "		<description>Run `winiso` as SuperUser</description>\n"
        "		<description xml:lang=\"zh_TW\">以超級使用者(SuperUser)身份執行 `winiso`</description>\n"
        "		<description xml:lang=\"pl_PL\">Uruchom `winiso` jako root</description>\n"
        "\n"
        "		<message>Authentication is required to run `winiso` as SuperUser.</message>\n"
        "		<message xml:lang=\"zh_TW\">以超級使用者(SuperUser)身份執行 `winiso` 需要通過身份驗證。</message>\n"
        "		<message xml:lang=\"pl_PL\">Wymagana jest autoryzacja do uruchomienia `winiso` jako root</message>\n"
        "\n"
        "		<defaults>\n"
        "			<allow_any>auth_admin</allow_any>\n"
        "			<allow_inactive>auth_admin</allow_inactive>\n"
        "			<allow_active>auth_admin_keep</allow_active>\n"
        "		</defaults>\n"
        "\n"
        "		<annotate key=\"org.freedesktop.policykit.exec.path\">/usr/local/bin/winisogui</annotate>\n"
        "   		<annotate key=\"org.freedesktop.policykit.exec.allow_gui\">true</annotate>\n"
        "	</action>\n"
        "</policyconfig>"
    )
    for action in dom.getElementsByTagName('action'):
        if action.getAttribute('id') == "com.github.winiso.winiso-ng.run-gui-using-pkexec":
            for annotate in action.getElementsByTagName('annotate'):
                if annotate.getAttribute('key') == "org.freedesktop.policykit.exec.path":
                    annotate.childNodes[0].nodeValue = path

    with open("/usr/share/polkit-1/actions/com.github.winiso.winiso-ng.policy", "w") as file:
        file.write(dom.toxml())


def extract_percentage(text):
    """
    Pull a trailing percentage out of a progress line printed by badblocks/dd.

    :param text: A line such as "Checking for bad blocks (read-write test):  42.51% done"
    :return: Integer percentage or None
    """
    match = re.search(r"([0-9]{1,3}(?:\.[0-9]+)?)\s*%", text)
    if match is None:
        return None

    try:
        return min(100, int(float(match.group(1))))
    except ValueError:
        return None


def find_filesystem_tool(filesystem_type):
    """
    Locate the mkfs utility for a filesystem.

    :param filesystem_type: FAT, NTFS, EXFAT or UDF
    :return: Path of the formatting utility, or None when it is not installed
    """
    candidates = {
        "FAT": ["mkdosfs", "mkfs.fat", "mkfs.vfat", "mkfs.msdos"],
        "NTFS": ["mkntfs"],
        "EXFAT": ["mkexfatfs", "mkfs.exfat"],
        "UDF": ["mkudffs"],
    }

    for command in candidates.get(filesystem_type.upper(), []):
        path = shutil.which(command)
        if path is not None:
            return path

    return None


def supported_filesystems():
    """
    :return: Dict of the filesystems that can be created on this system and their utility
    """
    return {name: find_filesystem_tool(name) for name in ("FAT", "NTFS", "EXFAT", "UDF")}


def get_media_size(path):
    """
    :param path: A regular file or a block device
    :return: Size in bytes (0 when it cannot be determined)
    """
    try:
        if os.path.isfile(path):
            return os.path.getsize(path)

        result = subprocess.run(["blockdev", "--getsize64", path], stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        if result.returncode == 0:
            return int(result.stdout.decode("utf-8").strip() or 0)
    except (OSError, ValueError):
        pass

    return 0


def calculate_checksum(path, algorithm="sha256", progress_callback=None):
    """
    Compute the checksum of an image without loading it into memory.

    :param path: File to hash
    :param algorithm: Any algorithm supported by hashlib (md5, sha1, sha256, sha512)
    :param progress_callback: Optional callable(percentage, hashed_bytes, total_bytes)
    :return: Hexadecimal digest
    """
    import hashlib

    digest = hashlib.new(algorithm)
    total = get_media_size(path)
    processed = 0

    with open(path, "rb") as image:
        while True:
            chunk = image.read(4 * 1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
            processed += len(chunk)
            if progress_callback is not None and total:
                progress_callback(int(processed * 100 / total), processed, total)

    return digest.hexdigest()
