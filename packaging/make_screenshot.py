#!/usr/bin/env python3
"""Render the WinIso-NG window and save a screenshot of it.

Usage (from the repository root, inside a graphical session):

    PYTHONPATH=src python3 packaging/make_screenshot.py [doc/screenshot.png]

The window is shown for two seconds, captured with a screen blit (so no
external screenshot tool is needed) and then closed.
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import wx  # noqa: E402

import WinIso.gui as gui  # noqa: E402

OUTPUT = sys.argv[1] if len(sys.argv) > 1 else "doc/screenshot.png"


def main():
    frame = gui.MainFrame("WinIso-NG", wx.DefaultPosition, wx.Size(780, 726))
    frame.SetMinSize(wx.Size(680, 520))
    frame.Show(True)
    frame.scroller.FitInside()

    def capture():
        frame.Raise()
        wx.Yield()
        time.sleep(0.5)

        rect = frame.GetScreenRect()
        bitmap = wx.Bitmap(rect.width, rect.height)
        memory = wx.MemoryDC(bitmap)
        screen = wx.ScreenDC()
        memory.Blit(0, 0, rect.width, rect.height, screen, rect.x, rect.y)
        memory.SelectObject(wx.NullBitmap)
        bitmap.SaveFile(OUTPUT, wx.BITMAP_TYPE_PNG)
        print("saved", OUTPUT, rect.width, "x", rect.height)

        frame.Hide()
        gui.app.ExitMainLoop()

    wx.CallLater(2000, capture)
    gui.app.MainLoop()


if __name__ == "__main__":
    main()
