# WinIso-NG on Android

Short answer: **this codebase cannot run on Android**, and writing an official
Windows ISO to a USB drive from an Android phone without root needs a separate
native app. This page explains why, and what the practical options are.

## Can the desktop implementation be applied here?

**No.** There is nothing in this repository that can be packaged as an APK: the
UI is wxPython, the engine shells out to Linux storage tools, and Android denies
block-device access to apps. Porting means writing a new Kotlin app with its own
USB mass-storage and filesystem code, and that app is not part of this project.

**Yes, for the no-root copy mode** — but only as that separate native app, using
the same design as the desktop engine: partition the USB drive, format it
FAT32/NTFS, copy the ISO contents, split `install.wim` into `.swm` parts.

| Question | Answer |
| --- | --- |
| Can I install this app on Android? | No, it is a desktop application (wxPython, Linux tools) |
| Can an Android app write a Windows ISO without root? | Only with a userspace USB mass-storage driver plus a FAT32/NTFS writer |
| Does raw-writing the ISO work? | No: official Windows ISOs are UDF and most firmware will not boot UDF from USB |
| Is a split of `install.wim` needed? | Yes on FAT32 (4 GiB file limit); NTFS/exFAT avoids it |
| Is that app in this repository? | No, and it cannot be built from it |

## Why this app cannot simply be ported

WinIso-NG is a desktop application:

* the interface is **wxPython**, which has no Android build;
* the engine calls Linux tools that Android does not ship: `mount`, `parted`,
  `mkfs.fat`, `mkfs.ntfs`, `grub-install` and `wipefs`;
* Android apps have no permission to open block devices such as `/dev/sda`
  or `/dev/block/sda`, not even with the storage permissions.

A phone port is therefore a new app, not a rebuild of this one.

## The two Android limits that matter

### 1. Block devices are off limits without root

Writing a "raw" ISO means writing sectors directly to the drive. Android
exposes USB drives only through the Storage Access Framework (files), so apps
that do this without root implement a **USB Mass Storage driver in user space**
over Android's USB Host API. That is how EtchDroid writes Linux images, and it
is a significant amount of native code.

### 2. Official Windows ISOs are not bootable when written raw

Microsoft's ISO uses **UDF**, and most PC firmware cannot boot UDF from a USB
drive (it is designed for DVDs). EtchDroid's own FAQ states that Windows images
"only work on DVDs" and must be converted to another filesystem first.

That is exactly why WinIso-NG, on the desktop, does not raw-write a Windows ISO
either: it copies the files to a FAT32/NTFS partition and splits `install.wim`
into `.swm` parts. Doing the same on Android requires a userspace **FAT32/NTFS
writer** on top of the USB driver, plus a way to split `install.wim`
(wimlib cross-compiled for Android).

## What works today

| Approach | Needs root | Windows ISO | Notes |
| --- | :---: | :---: | --- |
| Raw ISO write (EtchDroid and similar) | no | no | Fine for Linux/BSD installers |
| Raw `dd` from a terminal app | yes | no | Same UDF limitation |
| Ventoy-style drive (copy the ISO as a file) | no | yes | Ventoy's bootloader chain-loads the ISO; prepare the drive once on a PC |
| WinIso-NG copy mode (this project) | desktop | yes | Format + copy + split `install.wim` + `autounattend.xml` |

So the realistic Android route for a Windows 11 installer is a **Ventoy
prepared drive** (done once on a computer, then you can drop ISOs on it from the
phone with any file manager) or a small PC running WinIso-NG.

## What a native Android version would take

If this project grows an Android app, the honest scope is:

1. **Kotlin + Jetpack Compose** UI, USB Host API, foreground service.
2. **USB Mass Storage driver** (Bulk-Only Transport + SCSI) to reach the drive
   without root, with read-back verification.
3. **FAT32/NTFS writer** for copy mode, plus `install.wim` splitting through a
   wimlib build for Android (NDK).
4. **ISO reader** using `Storage Access Framework`, streaming (images are often
   5-7 GB).
5. Same safety rules as the desktop app: system disk never listed, confirmation
   with model/size/path, `autounattend.xml` generation for the Windows 11
   bypass.

Steps 2-3 are the hard part and are the reason apps in this space either stop at
Linux images or use the Ventoy trick.

## Windows and Linux, which do work

The desktop app runs on both:

* **Linux** — the original engine (parted, mkfs, GRUB, UEFI:NTFS).
* **Windows** — native `diskpart` + `robocopy` + optional `wimlib` and
  `bootsect`; see the Windows section of the README.
