<div align="center">
<h1>WinIso-NG</h1>
<img src=".github/winiso-logo.png" alt="brand" width="28%" />
</div>

_A Linux program to create a Windows USB stick installer from a real Windows DVD or image._

This package contains two programs:

* **winiso**: A command-line utility that enables you to create your own bootable Windows installation USB storage device from an existing Windows Installation disc or disk image
* **winisogui**: Graphic version of winiso

Supported images:

Windows Vista, Windows 7, Window 8.x, Windows 10. All languages and any version (home, pro...) and Windows PE are supported.

Supported bootmodes:

* Legacy/MBR-style/IBM PC compatible bootmode
* Native UEFI booting is supported for Windows 7 and later images (limited to the FAT filesystem as the target)

This project rewrite of original [WinIso](https://github.com/WinIso/WinIso-NG) 

## Installation

### Arch
```shell
yay -S winiso-ng
```

### For other distributions

### 1. Install WinIso-NG's Dependencies
#### Ubuntu

```shell
sudo apt install git p7zip-full python3-pip python3-wxgtk4.0 grub2-common grub-pc-bin parted dosfstools ntfs-3g
```

#### Fedora (tested on: Fedora Workstation 33)
```shell
sudo dnf install git p7zip p7zip-plugins python3-pip python3-wxpython4
```

### 2. Install WinIso-NG
```shell
sudo pip3 install WinIso-NG
```

## Installation from source code

### 1. Install WinIso-NG's Build Dependencies
#### Ubuntu
```shell
sudo apt install git p7zip-full python3-pip python3-wxgtk4.0 grub2-common grub-pc-bin parted dosfstools ntfs-3g
```
#### Arch
```shell
sudo pacman -Suy p7zip python-pip python-wxpython
```
#### Fedora (tested on: Fedora Workstation 33) 
```shell
sudo dnf install git p7zip p7zip-plugins python3-pip python3-wxpython4
```
### 2. Install WinIso-NG
```shell
git clone https://github.com/SysArchX/WinIso-NG.git
cd WinIso-NG
sudo pip3 install .
```

## Installation from source code locally or in virtual environment 
```shell
git clone https://github.com/SysArchX/WinIso-NG.git
cd WinIso-NG
git apply development.patch
sudo pip3 install -e .
```
Please note that this will not create menu shortcut and you may need to run gui twice as it may want to adjust policy. 

## Uninstalling

To remove WinIso-NG completely run (needed only when using installation from source code):
```shell
sudo pip3 uninstall WinIso-NG
sudo rm /usr/share/icons/WinIso-NG/icon.ico \
    /usr/share/applications/WinIso-NG.desktop \
    /usr/local/bin/winisogui
sudo rmdir /usr/share/icons/WinIso-NG/
```

## License
WinIso-NG is distributed under the [GPL license](https://github.com/SysArchX/WinIso-NG/blob/master/COPYING).
