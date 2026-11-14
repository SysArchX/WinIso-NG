#!/usr/bin/env bash
#
# Builds a self-contained .deb for WinIso-NG without needing debhelper.
# Usage: packaging/build_deb.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

VERSION="$(python3 - <<'PY'
import re
print(re.search(r'__version__\s*=\s*"([^"]+)"', open("src/WinIso/miscellaneous.py").read()).group(1))
PY
)"

PKG="winiso-ng"
ARCH="all"
STAGE="$ROOT/build/deb/${PKG}_${VERSION}_${ARCH}"
DIST="$ROOT/dist"

echo ">> WinIso-NG ${VERSION}"

rm -rf "$STAGE"
mkdir -p "$STAGE/DEBIAN" \
         "$STAGE/usr/bin" \
         "$STAGE/usr/lib/python3/dist-packages" \
         "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/scalable/apps" \
         "$STAGE/usr/share/polkit-1/actions" \
         "$STAGE/usr/share/fonts/truetype/winiso-ng" \
         "$STAGE/usr/share/doc/$PKG/fonts"

# ---------------------------------------------------------------- python package
cp -r src/WinIso "$STAGE/usr/lib/python3/dist-packages/"
find "$STAGE/usr/lib/python3/dist-packages" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$STAGE/usr/lib/python3/dist-packages" -name '*.pyc' -delete

# ---------------------------------------------------------------- launchers
install -m 0755 packaging/launchers/winiso "$STAGE/usr/bin/winiso"
install -m 0755 packaging/launchers/winisogui "$STAGE/usr/bin/winisogui"

# ---------------------------------------------------------------- data files
install -m 0644 miscellaneous/WinIso-NG.desktop "$STAGE/usr/share/applications/"
install -m 0644 src/WinIso/data/winiso-logo.png "$STAGE/usr/share/icons/hicolor/scalable/apps/"

# The policy shipped in a system package points at /usr/bin, not /usr/local/bin
sed 's#/usr/local/bin/winisogui#/usr/bin/winisogui#' \
    miscellaneous/com.github.winiso.winiso-ng.policy \
    > "$STAGE/usr/share/polkit-1/actions/com.github.winiso.winiso-ng.policy"
chmod 0644 "$STAGE/usr/share/polkit-1/actions/com.github.winiso.winiso-ng.policy"

install -m 0644 src/WinIso/data/fonts/Orbitron.ttf "$STAGE/usr/share/fonts/truetype/winiso-ng/"
install -m 0644 src/WinIso/data/fonts/Rajdhani-Bold.ttf "$STAGE/usr/share/fonts/truetype/winiso-ng/"
cat src/WinIso/data/fonts/OFL-Orbitron.txt src/WinIso/data/fonts/OFL-Rajdhani.txt \
    > "$STAGE/usr/share/doc/$PKG/fonts/OFL.txt"

# ---------------------------------------------------------------- docs
cp packaging/debian/copyright "$STAGE/usr/share/doc/$PKG/copyright"
cp COPYING "$STAGE/usr/share/doc/$PKG/"

cat > "$STAGE/usr/share/doc/$PKG/changelog" <<EOF
winiso-ng (${VERSION}) unstable; urgency=medium

  * Rufus-style interface with the WinIso-NG neon theme.
  * Windows 11 compatibility bypass (TPM, Secure Boot, RAM and local account)
    through a generated autounattend.xml.
  * Automatic splitting of install.wim into .swm parts with wimlib-imagex, so
    strictly FAT32 targets work with modern Windows images.
  * Host disk protection: disks backing /, /boot, /boot/efi, /home or swap are
    always hidden, even with "List USB Hard Drives" enabled.
  * Target confirmation dialog showing model, size and device path.
  * Adds DD image mode, non-bootable format mode, GPT partition tables,
    exFAT/UDF filesystems, cluster size selection, bad blocks check and
    MD5/SHA-1/SHA-256/SHA-512 image checksums.
  * Fixes mountpoint creation, missing partition nodes, automounted targets,
    FAT32 oversize images, nvme/mmcblk partition naming and the UEFI:NTFS
    image download.

 -- SysArchX <354081608+SysArchX@users.noreply.github.com>  $(date -R)
EOF
gzip -9n -f "$STAGE/usr/share/doc/$PKG/changelog"

# ---------------------------------------------------------------- metadata
sed "s/@VERSION@/${VERSION}/" packaging/debian/control.in > "$STAGE/DEBIAN/control"
install -m 0644 packaging/debian/copyright "$STAGE/DEBIAN/copyright"
install -m 0755 packaging/debian/postinst "$STAGE/DEBIAN/postinst"
install -m 0755 packaging/debian/postrm "$STAGE/DEBIAN/postrm"

INSTALLED_SIZE="$(du -sk --exclude=DEBIAN "$STAGE" | cut -f1)"
printf 'Installed-Size: %s\n' "$INSTALLED_SIZE" >> "$STAGE/DEBIAN/control"

# ---------------------------------------------------------------- build
mkdir -p "$DIST"
OUTPUT="$DIST/${PKG}_${VERSION}_${ARCH}.deb"

fakeroot dpkg-deb --build --root-owner-group "$STAGE" "$OUTPUT" >/dev/null

echo ">> built $OUTPUT"
dpkg-deb --info "$OUTPUT" | sed -n '1,20p'
echo ">> contents:"
dpkg-deb --contents "$OUTPUT" | awk '{print $6}' | sed -n '1,40p'
