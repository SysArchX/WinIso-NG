# Build a standalone WinIso-NG.exe for Windows with PyInstaller.
#
# Usage (from the repository root, in PowerShell):
#     .\packaging\build_windows.ps1
#
# The executable is written to dist\WinIso-NG\WinIso-NG.exe. It must be run as
# administrator, because diskpart needs elevated rights.
#
# Preview every command before writing anything (no admin needed):
#     python -m WinIso.windows_backend --image D:\win11.iso --disk 2 --fs FAT32

$ErrorActionPreference = "Stop"

python -m pip install --upgrade pip
python -m pip install --upgrade pyinstaller wxPython termcolor

python -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "WinIso-NG" `
    --icon "src\WinIso\data\icon.ico" `
    --add-data "src\WinIso\data;WinIso\data" `
    --add-data "src\WinIso\locale;WinIso\locale" `
    --paths src `
    --hidden-import WinIso.windows_backend `
    "packaging\win_entry.py"

Write-Host ""
Write-Host "Built dist\WinIso-NG\WinIso-NG.exe"
Write-Host "Optional tools: install wimlib (for FAT32 splits) and the Windows ADK (for bootsect)."
