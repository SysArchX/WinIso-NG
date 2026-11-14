from setuptools import setup

setup(
    data_files=[
        ("share/applications", ["miscellaneous/WinIso-NG.desktop"]),
        ("share/polkit-1/actions", ["miscellaneous/com.github.winiso.winiso-ng.policy"]),
        ("share/icons/hicolor/scalable/apps", ["src/WinIso/data/winiso-logo.png"]),
        ("share/fonts/truetype/winiso-ng", ["src/WinIso/data/fonts/Orbitron.ttf",
                                            "src/WinIso/data/fonts/Rajdhani-Bold.ttf"]),
    ],
    install_requires=[
        'termcolor',
        'wxPython',
    ]
)
