<div align="center">
<h1>WinIso-NG</h1>
<img src=".github/winiso-logo.png" alt="WinIso-NG" width="24%" />
</div>

_Create bootable Windows (and Linux) USB installers from the Linux desktop — with a Rufus-style form and a dark neon interface._

WinIso-NG is a fork of [WoeUSB-ng](https://github.com/WoeUSB/WoeUSB-ng). It writes an ISO/IMG image to a USB storage device and makes it bootable, with the same workflow and options you know from Rufus: pick the device, pick the image, choose MBR/GPT, filesystem and options, then press **START**.

## Features

**Drive properties**

* Device selector listing removable USB drives, plus **List USB Hard Drives** to reveal USB disks/SSDs
* Boot selection: **Disk or ISO image**, or **Non bootable** (format the drive as plain storage)
* **Image option**: *Standard (copy files)* or *DD image mode (raw write)*
* **SELECT** to choose the image and **CHECKSUM** for MD5 / SHA-1 / SHA-256 / SHA-512

**Format options**

* Partition scheme: **MBR** or **GPT** (picking GPT sets *UEFI (non CSM)* automatically, like Rufus)
* Target system: **BIOS (or UEFI-CSM)** or **UEFI (non CSM)**
* File systems: **FAT32**, **NTFS**, **exFAT**, **UDF** (only the ones whose tools are installed are offered)
* **Cluster size** selection, **Volume label**
* **Quick format** and **Check device for bad blocks** (destructive, one pass)

**During the job**

* Inline status line, neon progress bar, **Cancel**
* Live log window (Options → Show log)
* Automatic NTFS switch when `install.wim` exceeds the FAT32 4 GiB limit, UEFI:NTFS support partition, Windows 7 UEFI workaround, legacy GRUB bootloader for BIOS targets

## Install

### Debian / Ubuntu / Linux Mint (.deb)

```shell
sudo apt install ./winiso-ng_0.2.0_all.deb
```

Build it yourself:

```shell
git clone https://github.com/SysArchX/WinIso-NG.git
cd WinIso-NG
./packaging/build_deb.sh          # writes dist/winiso-ng_<version>_all.deb
sudo apt install ./dist/winiso-ng_0.2.0_all.deb
```

The package installs the `winiso` and `winisogui` commands, the menu entry, the polkit policy and the bundled Orbitron/Rajdhani fonts.

### From source

```shell
sudo apt install git p7zip-full python3-pip python3-wxgtk4.0 grub2-common grub-pc-bin parted dosfstools ntfs-3g exfatprogs udftools
sudo pip3 install .
```

### Arch

```shell
sudo pacman -S --needed p7zip python-pip python-wxpython parted dosfstools ntfs-3g exfatprogs udftools
git clone https://github.com/SysArchX/WinIso-NG.git && cd WinIso-NG && sudo pip3 install .
```

## Usage

```shell
sudo winisogui                                   # graphical interface
sudo winiso --device image.iso /dev/sdX          # copy mode + legacy GRUB
sudo winiso --device image.iso /dev/sdX --image-mode DD --target-filesystem NTFS
sudo winiso --device image.iso /dev/sdX --partition-scheme GPT --target-system UEFI
sudo winiso --device image.iso /dev/sdX --bad-blocks --cluster-size 4096
```

Run `winiso --help` for the complete option list.

## Rufus features that are not implemented

These Rufus options have no portable Linux equivalent and are deliberately absent:

* Windows To Go, Windows VHD and Windows 11 "TPM/Secure Boot bypass"
* Rufus MBR, Syslinux/GRUB4DOS/ReactOS bootloader installation
* Persistence partition for Ubuntu/Debian live images
* Built-in ISO download, update check and USB → VHD image dumping
* FreeDOS / MS-DOS boot media creation

Everything else in the form above is implemented natively in Python; no Rufus code was used.

## Credits

* [WoeUSB-ng](https://github.com/WoeUSB/WoeUSB-ng) by WaxyMocha, Lin-Buo-Ren, slacka and contributors — the engine this fork started from
* [WoeUSB](https://github.com/slacka/WoeUSB) by slacka et al.
* [WinUSB](https://github.com/congelli) by Colin GILLE / congelli501
* Interface layout inspired by [Rufus](https://rufus.ie) by Pete Batard (no code shared)
* Fonts: [Orbitron](https://github.com/theleagueof/orbitron) and [Rajdhani](https://github.com/itfoundry/rajdhani), SIL Open Font License 1.1

## License

GPLv3 or later — see [COPYING](COPYING).
