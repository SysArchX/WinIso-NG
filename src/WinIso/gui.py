#!/usr/bin/env python3

import os
import threading
import time

import wx
import wx.adv


import WinIso.core as core
import WinIso.list_devices as list_devices
import WinIso.miscellaneous as miscellaneous
import WinIso.theme as theme
import WinIso.utils as utils
import WinIso.windows_backend as windows_backend

data_directory = os.path.dirname(__file__) + "/data/"

app = wx.App()

theme.register_fonts(data_directory)

_ = miscellaneous.i18n

LABEL_WIDTH = 120

BOOT_NONE = _("Non bootable")
BOOT_IMAGE = _("Disk or ISO image (Please select)")

IMAGE_STANDARD = _("Standard (copy files)")
IMAGE_DD = _("DD image mode (raw write)")

CHECKSUM_ALGORITHMS = ["MD5", "SHA-1", "SHA-256", "SHA-512"]
CLUSTER_SIZES = ["Default", "512", "1024", "2048", "4096", "8192", "16384", "32768", "65536"]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
class Hairline(wx.Panel):
    """Thin neon separator between form sections."""

    def __init__(self, parent):
        super(Hairline, self).__init__(parent, wx.ID_ANY, size=(-1, 2))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetMinSize((-1, 2))
        self.Bind(wx.EVT_PAINT, self.on_paint)

    def on_paint(self, __=None):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(theme.SURFACE))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        width = self.GetClientSize().width
        gc.SetPen(wx.Pen(theme.BORDER, 1))
        gc.StrokeLine(0, 1, width, 1)


def section_label(parent, text, colour=theme.MUTED):
    label = wx.StaticText(parent, wx.ID_ANY, text.upper())
    font = theme.ui_font("heading", parent)
    label.SetFont(font)
    label.SetForegroundColour(colour)
    return label


def form_label(parent, text):
    label = wx.StaticText(parent, wx.ID_ANY, text)
    label.SetFont(theme.ui_font("body", parent))
    label.SetForegroundColour(theme.MUTED)
    label.SetMinSize((LABEL_WIDTH, -1))
    return label


def make_choice(parent, items, value=None, height=29):
    choice = wx.ComboBox(parent, wx.ID_ANY, choices=items, style=wx.CB_READONLY)
    choice.SetBackgroundColour(theme.SURFACE)
    choice.SetForegroundColour(theme.TEXT)
    choice.SetFont(theme.ui_font("body", parent))
    choice.SetMinSize((-1, height))
    if value is not None and value in items:
        choice.SetStringSelection(value)
    return choice


def make_checkbox(parent, label, value=False):
    checkbox = wx.CheckBox(parent, wx.ID_ANY, label)
    checkbox.SetValue(value)
    checkbox.SetForegroundColour(theme.TEXT)
    checkbox.SetBackgroundColour(theme.SURFACE)
    checkbox.SetFont(theme.ui_font("body", parent))
    return checkbox


class LabelField(wx.Panel):
    """Borderless-looking text input built on the themed field frame."""

    def __init__(self, parent, value=""):
        super(LabelField, self).__init__(parent, wx.ID_ANY)
        self.SetBackgroundColour(theme.BG_BOTTOM)

        self.frame = theme.FieldFrame(self, accent=theme.BORDER, background=theme.BG_BOTTOM, min_height=34)
        sizer_inner = wx.BoxSizer(wx.HORIZONTAL)

        self.text = wx.TextCtrl(self.frame, wx.ID_ANY, value, style=wx.BORDER_NONE)
        self.text.SetBackgroundColour(theme.SURFACE_ALT)
        self.text.SetForegroundColour(theme.TEXT)
        self.text.SetFont(theme.ui_font("body", self))
        sizer_inner.Add(self.text, 1, wx.EXPAND | wx.ALL, 6)
        self.frame.SetSizer(sizer_inner)

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(self.frame, 1, wx.EXPAND)
        self.SetSizer(sizer)

    def GetValue(self):
        return self.text.GetValue()

    def SetValue(self, value):
        self.text.SetValue(value)

    def Enable(self, enable=True):
        self.text.Enable(enable)
        self.frame.Enable(enable)


def make_form_grid():
    grid = wx.FlexGridSizer(cols=4, vgap=5, hgap=8)
    grid.AddGrowableCol(1)
    return grid


def add_grid_row(grid, parent, label_text, control, extra_controls=None):
    grid.Add(form_label(parent, label_text), 0, wx.ALIGN_CENTER_VERTICAL)
    grid.Add(control, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL)

    extras = list(extra_controls or [])
    for index in range(2):
        if index < len(extras):
            grid.Add(extras[index], 0, wx.ALIGN_CENTER_VERTICAL)
        else:
            grid.Add((0, 0))


def add_grid_control(grid, control):
    grid.Add((0, 0))
    grid.Add(control, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL)
    grid.Add((0, 0))
    grid.Add((0, 0))


# ---------------------------------------------------------------------------
# dialogs
# ---------------------------------------------------------------------------
class ChecksumDialog(wx.Dialog):
    """Rufus-style image checksum window (MD5, SHA-1, SHA-256, SHA-512)."""

    def __init__(self, parent, image_path):
        super(ChecksumDialog, self).__init__(parent, wx.ID_ANY, _("Image checksum"),
                                             style=wx.DEFAULT_DIALOG_STYLE)
        self.SetBackgroundColour(theme.CARD)
        self.image_path = image_path
        self.SetIcon(wx.Icon(data_directory + "icon.ico"))

        outer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(self, wx.ID_ANY, _("CHECKSUM"))
        if theme.FONTS["label"] is not None:
            title.SetFont(theme.FONTS["label"])
        title.SetForegroundColour(theme.CYAN)
        outer.Add(title, 0, wx.ALL, 16)

        info = wx.StaticText(self, wx.ID_ANY, os.path.basename(image_path))
        info.SetForegroundColour(theme.MUTED)
        outer.Add(info, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)

        row = wx.BoxSizer(wx.HORIZONTAL)
        self.algorithm = make_choice(self, CHECKSUM_ALGORITHMS, "SHA-256")
        row.Add(self.algorithm, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)
        self.compute_button = theme.NeonButton(self, label=_("Compute"), accent=theme.CYAN,
                                               min_size=(120, 34), background=theme.CARD)
        row.Add(self.compute_button, 0, wx.ALIGN_CENTER_VERTICAL)
        outer.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 16)

        self.result = wx.TextCtrl(self, wx.ID_ANY, "", style=wx.TE_READONLY)
        self.result.SetBackgroundColour(theme.BG_TOP)
        self.result.SetForegroundColour(theme.CYAN)
        if theme.FONTS["body"] is not None:
            self.result.SetFont(theme.FONTS["body"])
        self.result.SetMinSize((-1, 34))
        outer.Add(self.result, 0, wx.EXPAND | wx.ALL, 16)

        self.progress = theme.NeonProgressBar(self, background=theme.CARD)
        outer.Add(self.progress, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 16)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.AddStretchSpacer(1)
        self.copy_button = theme.NeonButton(self, label=_("Copy"), accent=theme.VIOLET,
                                            min_size=(110, 36), background=theme.CARD)
        buttons.Add(self.copy_button, 0, wx.RIGHT, 8)
        close_button = theme.NeonButton(self, label=_("Close"), accent=theme.MAGENTA,
                                        min_size=(110, 36), background=theme.CARD)
        buttons.Add(close_button, 0)
        outer.Add(buttons, 0, wx.EXPAND | wx.ALL, 16)

        self.SetSizer(outer)
        self.SetClientSize((560, 300))

        self.compute_button.Bind(wx.EVT_BUTTON, self.on_compute)
        self.copy_button.Bind(wx.EVT_BUTTON, self.on_copy)
        close_button.Bind(wx.EVT_BUTTON, lambda event: self.Close())

        self.CentreOnParent()

    def on_compute(self, __):
        algorithm = self.algorithm.GetValue().lower().replace("-", "")
        self.result.SetValue(_("Computing..."))
        self.compute_button.Enable(False)

        def worker():
            try:
                digest = utils.calculate_checksum(
                    self.image_path, algorithm,
                    progress_callback=lambda p, done, total: wx.CallAfter(self.progress.SetValue, p))
                wx.CallAfter(self.result.SetValue, digest)
            except Exception as error:
                wx.CallAfter(self.result.SetValue, str(error))
            finally:
                wx.CallAfter(self.compute_button.Enable, True)

        threading.Thread(target=worker, daemon=True).start()

    def on_copy(self, __):
        value = self.result.GetValue()
        if value and not wx.TheClipboard.Open():
            return
        if value:
            wx.TheClipboard.SetData(wx.TextDataObject(value))
            wx.TheClipboard.Close()


class LogFrame(wx.Frame):
    """Live application log."""

    def __init__(self, parent):
        super(LogFrame, self).__init__(parent, wx.ID_ANY, "WinIso-NG - " + _("Log"),
                                       size=wx.Size(680, 380))
        self.SetBackgroundColour(theme.BG)
        self.SetIcon(wx.Icon(data_directory + "icon.ico"))

        panel = theme.TechBackground(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.text = wx.TextCtrl(panel, wx.ID_ANY, "", style=wx.TE_MULTILINE | wx.TE_READONLY)
        self.text.SetBackgroundColour(theme.BG_TOP)
        self.text.SetForegroundColour(theme.MUTED)
        if theme.FONTS["body"] is not None:
            self.text.SetFont(theme.FONTS["body"])
        sizer.Add(self.text, 1, wx.EXPAND | wx.ALL, 12)

        panel.SetSizer(sizer)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(outer)
        self.CentreOnParent()

    def append(self, message):
        self.text.AppendText(str(message).rstrip() + "\n")


class DialogAbout(wx.Dialog):
    def __init__(self, parent, ID=wx.ID_ANY, title=_("About"), size=wx.Size(650, 590),
                 style=wx.DEFAULT_DIALOG_STYLE):
        super(DialogAbout, self).__init__(parent, ID, title, wx.DefaultPosition, size, style)

        self.SetSizeHints(wx.DefaultSize, wx.DefaultSize)
        self.SetBackgroundColour(theme.CARD)
        self.SetIcon(wx.Icon(data_directory + "icon.ico"))

        sizer_all = wx.BoxSizer(wx.VERTICAL)
        sizer_img = wx.BoxSizer(wx.HORIZONTAL)

        img = wx.Image(data_directory + "icon.ico", wx.BITMAP_TYPE_ICO).Scale(52, 52, wx.IMAGE_QUALITY_BILINEAR)
        sizer_img.Add(wx.StaticBitmap(self, wx.ID_ANY, wx.Bitmap(img)), 0, wx.ALL, 8)

        sizer_text = wx.BoxSizer(wx.VERTICAL)

        title_label = wx.StaticText(self, wx.ID_ANY, "WinIso-NG")
        if theme.FONTS["title"] is not None:
            title_label.SetFont(theme.FONTS["title"])
        title_label.SetForegroundColour(theme.CYAN)
        sizer_text.Add(title_label, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 4)

        version_label = wx.StaticText(self, wx.ID_ANY, miscellaneous.__version__)
        if theme.FONTS["body"] is not None:
            version_label.SetFont(theme.FONTS["body"])
        version_label.SetForegroundColour(theme.MAGENTA)
        sizer_text.Add(version_label, 0, wx.LEFT, 4)
        sizer_img.Add(sizer_text, 0, 0, 5)
        sizer_all.Add(sizer_img, 0, wx.EXPAND, 8)

        notebook = wx.Notebook(self, wx.ID_ANY)
        notebook.SetBackgroundColour(theme.CARD)
        notebook.SetForegroundColour(theme.TEXT)

        notebook.AddPage(PanelNoteBookAutors(notebook, wx.ID_ANY,
                                             "slacka \nLin-Buo-Ren\nWaxyMocha",
                                             data_directory + "winiso-logo.png",
                                             "github.com/WoeUSB/WoeUSB-ng"), _("Authors"), True)
        notebook.AddPage(PanelNoteBookAutors(notebook, wx.ID_ANY, "Colin GILLE / Congelli501",
                                             data_directory + "c501-logo.png",
                                             "www.congelli.eu"), _("Original WinUSB Developer"), False)

        licence_str = _('''
            This file is part of WinIso-NG.

            WinIso-NG is free software: you can redistribute it and/or modify
            it under the terms of the GNU General Public License as published by
            the Free Software Foundation, either version 3 of the License, or
            (at your option) any later version.

            WinIso-NG is distributed in the hope that it will be useful,
            but WITHOUT ANY WARRANTY; without even the implied warranty of
            MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
            GNU General Public License for more details.

            You should have received a copy of the GNU General Public License
            along with WinIso-NG.  If not, see <http://www.gnu.org/licenses/>.
        ''')

        licence_txt = wx.TextCtrl(notebook, wx.ID_ANY, licence_str, wx.DefaultPosition,
                                  wx.DefaultSize, wx.TE_MULTILINE | wx.TE_READONLY)
        licence_txt.SetBackgroundColour(theme.BG_TOP)
        licence_txt.SetForegroundColour(theme.MUTED)
        if theme.FONTS["body"] is not None:
            licence_txt.SetFont(theme.FONTS["body"])

        notebook.AddPage(licence_txt, _("License"))
        sizer_all.Add(notebook, 1, wx.EXPAND | wx.ALL, 8)

        buttons = wx.BoxSizer(wx.HORIZONTAL)
        buttons.AddStretchSpacer(1)
        ok_button = theme.NeonButton(self, label="OK", accent=theme.CYAN, filled=True,
                                     min_size=(120, 40), background=theme.CARD)
        buttons.Add(ok_button, 0)
        sizer_all.Add(buttons, 0, wx.EXPAND | wx.BOTTOM | wx.RIGHT, 10)

        self.SetSizer(sizer_all)
        self.Layout()

        ok_button.Bind(wx.EVT_BUTTON, lambda event: self.EndModal(wx.ID_OK))


class PanelNoteBookAutors(wx.Panel):
    def __init__(self, parent, ID=wx.ID_ANY, autherName="", imgName="", siteLink="", pos=wx.DefaultPosition,
                 size=wx.DefaultSize, style=wx.TAB_TRAVERSAL):
        super(PanelNoteBookAutors, self).__init__(parent, ID, pos, size, style)

        self.SetBackgroundColour(theme.CARD)

        sizer_note_book_autors = wx.BoxSizer(wx.VERTICAL)

        auteur_static_text = wx.StaticText(self, wx.ID_ANY, autherName)
        if theme.FONTS["body"] is not None:
            auteur_static_text.SetFont(theme.FONTS["body"])
        auteur_static_text.SetForegroundColour(theme.TEXT)
        sizer_note_book_autors.Add(auteur_static_text, 0, wx.ALL, 8)

        if siteLink != "":
            autor_link = wx.adv.HyperlinkCtrl(self, wx.ID_ANY, siteLink, siteLink)
            autor_link.SetForegroundColour(theme.CYAN)
            sizer_note_book_autors.Add(autor_link, 0, wx.LEFT | wx.BOTTOM, 8)

        if imgName != "" and os.path.isfile(imgName):
            img = wx.Image(imgName, wx.BITMAP_TYPE_PNG)
            if img.GetWidth() > 320:
                ratio = 320.0 / img.GetWidth()
                img = img.Scale(320, int(img.GetHeight() * ratio), wx.IMAGE_QUALITY_HIGH)
            sizer_note_book_autors.Add(wx.StaticBitmap(self, wx.ID_ANY, wx.Bitmap(img)), 0, wx.LEFT | wx.BOTTOM, 8)

        self.SetSizer(sizer_note_book_autors)


# ---------------------------------------------------------------------------
# worker
# ---------------------------------------------------------------------------
class WinIso_handler(threading.Thread):
    """
    Runs the writing job in the background and reports progress to the window.
    """
    progress = False
    state = ""
    error = ""
    kill = False
    finished = False
    log_sink = None

    def append_log(self, text):
        if self.log_sink is not None:
            self.log_sink(text)

    def __init__(self, source, target, filesystem, label, partition_scheme, target_system,
                 image_mode, cluster_size, quick_format, bad_blocks_check, skip_legacy_bootloader,
                 win11_bypass=False):
        threading.Thread.__init__(self)
        self.daemon = True

        core.gui = self
        self.source = source
        self.target = target
        self.filesystem = filesystem
        self.label = label
        self.partition_scheme = partition_scheme
        self.target_system = target_system
        self.image_mode = image_mode
        self.cluster_size = cluster_size
        self.quick_format = quick_format
        self.bad_blocks_check = bad_blocks_check
        self.skip_legacy_bootloader = skip_legacy_bootloader
        self.win11_bypass = win11_bypass

    def run(self):
        source_fs_mountpoint = target_fs_mountpoint = temp_directory = None

        try:
            result = core.init(from_cli=False,
                               install_mode="device",
                               source_media=self.source,
                               target_media=self.target,
                               target_filesystem_type=self.filesystem,
                               filesystem_label=self.label,
                               partition_scheme=self.partition_scheme,
                               target_system=self.target_system,
                               image_mode=self.image_mode,
                               cluster_size=self.cluster_size,
                               quick_format=self.quick_format,
                               bad_blocks_check=self.bad_blocks_check,
                               skip_legacy_bootloader=self.skip_legacy_bootloader,
                               win11_bypass=self.win11_bypass)

            (source_fs_mountpoint, target_fs_mountpoint, temp_directory, install_mode, source_media, target_media,
             workaround_bios_boot_flag, skip_legacy_bootloader, target_filesystem_type, filesystem_label, verbose,
             debug, parser, partition_scheme, target_system, image_mode, cluster_size, quick_format,
             bad_blocks_check, win11_bypass) = result

            core.main(source_fs_mountpoint, target_fs_mountpoint, source_media, target_media, install_mode,
                      temp_directory, target_filesystem_type, workaround_bios_boot_flag, None,
                      skip_legacy_bootloader,
                      partition_scheme=partition_scheme, target_system=target_system, image_mode=image_mode,
                      filesystem_label=filesystem_label, cluster_size=cluster_size, quick_format=quick_format,
                      bad_blocks_check=bad_blocks_check, win11_bypass=win11_bypass)
        except SystemExit:
            pass
        except Exception as error:
            self.error = str(error)
        finally:
            if temp_directory is not None:
                try:
                    core.cleanup(source_fs_mountpoint, target_fs_mountpoint, temp_directory, self.target)
                except Exception as error:
                    self.error = str(error)

            self.finished = True


# ---------------------------------------------------------------------------
# main window
# ---------------------------------------------------------------------------
class MainFrame(wx.Frame):
    def __init__(self, title, pos, size, style=wx.DEFAULT_FRAME_STYLE):
        super(MainFrame, self).__init__(None, -1, title, pos, size, style)

        self.SetBackgroundColour(theme.BG)
        self.SetIcon(wx.Icon(data_directory + "icon.ico"))

        file_menu = wx.Menu()
        self.__menuItemShowAll = wx.MenuItem(file_menu, wx.ID_ANY, _("Show all drives") + " \tCtrl+A",
                                             _("Show all drives, even those not detected as USB stick."),
                                             wx.ITEM_CHECK)
        file_menu.Append(self.__menuItemShowAll)
        file_menu.AppendSeparator()
        refresh_item = file_menu.Append(wx.ID_REFRESH)
        file_menu.AppendSeparator()
        exit_item = file_menu.Append(wx.ID_EXIT)

        options_menu = wx.Menu()
        self.options_skip_grub = wx.MenuItem(options_menu, wx.ID_ANY, _("Skip legacy grub bootloader"),
                                             _("No legacy grub bootloader will be created. NOTE: It will only boot on system with UEFI support."),
                                             wx.ITEM_CHECK)
        options_menu.Append(self.options_skip_grub)
        log_item = options_menu.Append(wx.ID_ANY, _("Show log") + "\tCtrl+L")

        help_menu = wx.Menu()
        help_item = help_menu.Append(wx.ID_ABOUT)

        menu_bar = wx.MenuBar()
        menu_bar.Append(file_menu, _("&File"))
        menu_bar.Append(options_menu, _("&Options"))
        menu_bar.Append(help_menu, _("&Help"))
        self.SetMenuBar(menu_bar)

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Scrolling keeps every option reachable on small screens
        self.scroller = wx.ScrolledWindow(self, wx.ID_ANY, style=wx.VSCROLL)
        self.scroller.SetBackgroundColour(theme.BG)
        self.scroller.SetScrollRate(0, 14)

        self.panel = MainPanel(self.scroller, wx.ID_ANY, frame=self)
        panel_sizer = wx.BoxSizer(wx.VERTICAL)
        panel_sizer.Add(self.panel, 1, wx.EXPAND)
        self.scroller.SetSizer(panel_sizer)

        main_sizer.Add(self.scroller, 1, wx.EXPAND)
        self.SetSizer(main_sizer)

        self.scroller.FitInside()

        self.Bind(wx.EVT_MENU, self.panel.on_show_all_drive, self.__menuItemShowAll)
        self.Bind(wx.EVT_MENU, lambda event: self.panel.refresh_devices(), refresh_item)
        self.Bind(wx.EVT_MENU, self.panel.show_log, log_item)
        self.Bind(wx.EVT_MENU, self.on_about, help_item)
        self.Bind(wx.EVT_MENU, lambda event: self.Close(True), exit_item)

    def on_about(self, __):
        dialog = DialogAbout(self)
        dialog.ShowModal()
        dialog.Destroy()

    def is_show_all_checked(self):
        return self.__menuItemShowAll.IsChecked()


class MainPanel(theme.TechBackground):
    def __init__(self, parent, ID, frame=None):
        super(MainPanel, self).__init__(parent, ID)

        self.__parent = frame if frame is not None else parent.GetParent()
        self.image_path = ""
        self.image_info = None
        self.handler = None
        self.log_frame = None
        self.log_buffer = []
        self.installing = False
        self.dry_run = None

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ------------------------------------------------------------- header
        header = wx.BoxSizer(wx.HORIZONTAL)

        logo_path = data_directory + "winiso-logo.png"
        if os.path.isfile(logo_path):
            image = wx.Image(logo_path, wx.BITMAP_TYPE_PNG).Scale(50, 50, wx.IMAGE_QUALITY_HIGH)
            header.Add(wx.StaticBitmap(self, wx.ID_ANY, wx.Bitmap(image)), 0,
                       wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 12)

        titles = wx.BoxSizer(wx.VERTICAL)
        title = wx.StaticText(self, wx.ID_ANY, "WinIso-NG")
        title.SetFont(theme.ui_font("title", self))
        title.SetForegroundColour(theme.TEXT)
        titles.Add(title, 0)

        subtitle = wx.StaticText(self, wx.ID_ANY, _("Create a bootable Windows USB installer"))
        subtitle.SetFont(theme.ui_font("body", self))
        subtitle.SetForegroundColour(theme.MUTED)
        titles.Add(subtitle, 0, wx.TOP, 1)

        header.Add(titles, 1, wx.ALIGN_CENTER_VERTICAL)
        main_sizer.Add(header, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 20)
        main_sizer.AddSpacer(10)
        main_sizer.Add(Hairline(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)

        # ------------------------------------------------------------- device
        main_sizer.Add(section_label(self, _("Device")), 0, wx.LEFT | wx.RIGHT | wx.TOP, 20)
        main_sizer.AddSpacer(2)

        device_grid = make_form_grid()
        self.device_choice = make_choice(self, [""])
        self.device_devices = []
        add_grid_row(device_grid, self, _("Device"), self.device_choice)

        self.list_hard_drives = make_checkbox(self, _("List USB Hard Drives"))
        self.list_hard_drives.SetToolTip(_("Show USB hard drives and SSDs, which are hidden by default."))
        self.list_hard_drives.Bind(wx.EVT_CHECKBOX, lambda event: self.refresh_devices())
        add_grid_control(device_grid, self.list_hard_drives)

        main_sizer.Add(device_grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)
        main_sizer.Add(Hairline(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        # ------------------------------------------------------------- boot selection
        main_sizer.Add(section_label(self, _("Boot selection")), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, 10)
        main_sizer.AddSpacer(2)

        boot_grid = make_form_grid()
        self.boot_choice = make_choice(self, [BOOT_NONE, BOOT_IMAGE], BOOT_IMAGE)
        self.select_button = theme.NeonButton(self, label=_("Select"), accent=theme.CYAN,
                                              min_size=(96, 29), background=theme.BG_BOTTOM)
        self.checksum_button = theme.NeonButton(self, label=_("Checksum"), accent=theme.VIOLET,
                                                min_size=(112, 29), background=theme.BG_BOTTOM)
        add_grid_row(boot_grid, self, _("Boot selection"), self.boot_choice,
                     [self.select_button, self.checksum_button])

        self.image_mode_choice = make_choice(self, [IMAGE_STANDARD, IMAGE_DD], IMAGE_STANDARD)
        add_grid_row(boot_grid, self, _("Image option"), self.image_mode_choice)

        main_sizer.Add(boot_grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)
        main_sizer.Add(Hairline(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        # ------------------------------------------------------------- format options
        main_sizer.Add(section_label(self, _("Format options")), 0,
                       wx.LEFT | wx.RIGHT | wx.TOP, 10)
        main_sizer.AddSpacer(2)

        format_grid = make_form_grid()

        self.scheme_choice = make_choice(self, ["MBR", "GPT"], "MBR")
        add_grid_row(format_grid, self, _("Partition scheme"), self.scheme_choice)

        self.target_system_choice = make_choice(
            self, [_("BIOS (or UEFI-CSM)"), _("UEFI (non CSM)")], _("BIOS (or UEFI-CSM)"))
        add_grid_row(format_grid, self, _("Target system"), self.target_system_choice)

        if windows_backend.available():
            filesystems = ["FAT", "NTFS", "EXFAT"]
            self.missing_filesystems = []
        else:
            available = utils.supported_filesystems()
            filesystems = [name for name in ("FAT", "NTFS", "EXFAT", "UDF") if available.get(name)]
            self.missing_filesystems = [name for name in ("FAT", "NTFS", "EXFAT", "UDF")
                                        if not available.get(name)]

        self.filesystem_choice = make_choice(self, filesystems,
                                             "NTFS" if "NTFS" in filesystems else filesystems[0])
        add_grid_row(format_grid, self, _("File system"), self.filesystem_choice)

        self.cluster_choice = make_choice(self, CLUSTER_SIZES, "Default")
        add_grid_row(format_grid, self, _("Cluster size"), self.cluster_choice)

        self.label_field = LabelField(self, "WINISO")
        add_grid_row(format_grid, self, _("Volume label"), self.label_field)

        self.quick_format = make_checkbox(self, _("Quick format"), True)
        self.bad_blocks = make_checkbox(self, _("Check device for bad blocks"), False)
        format_checks = wx.BoxSizer(wx.HORIZONTAL)
        format_checks.Add(self.quick_format, 0, wx.RIGHT, 18)
        format_checks.Add(self.bad_blocks, 0)
        format_grid.Add((0, 0))
        format_grid.Add(format_checks, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL)
        format_grid.Add((0, 0))
        format_grid.Add((0, 0))

        self.win11_bypass = make_checkbox(
            self, _("Windows 11 Compatibility Bypass (TPM / Secure Boot / Local Account)"), False)
        self.win11_bypass.SetToolTip(_(
            "Writes an autounattend.xml to the installer root that skips the TPM, Secure Boot and RAM "
            "checks and lets you finish setup with a local account, without a network connection."))

        main_sizer.Add(format_grid, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)

        # Kept outside the grid so this long label cannot widen the whole form
        bypass_sizer = wx.BoxSizer(wx.HORIZONTAL)
        bypass_sizer.Add((LABEL_WIDTH - 10, 0))
        bypass_sizer.Add(self.win11_bypass, 1, wx.EXPAND)
        main_sizer.Add(bypass_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 20)

        # Windows only: every write is preceded by a reviewable plan
        if windows_backend.available():
            self.dry_run = make_checkbox(
                self, _("Dry run (show every command, write nothing)"), False)
            self.dry_run.SetToolTip(_(
                "Prints the validated plan (diskpart script, robocopy command and checks) "
                "without mounting anything, formatting the disk or copying files."))

            dry_sizer = wx.BoxSizer(wx.HORIZONTAL)
            dry_sizer.Add((LABEL_WIDTH - 10, 0))
            dry_sizer.Add(self.dry_run, 1, wx.EXPAND)
            main_sizer.Add(dry_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 20)

        main_sizer.Add(Hairline(self), 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        # ------------------------------------------------------------- status
        main_sizer.AddSpacer(6)

        status_sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.start_button = theme.NeonButton(self, label=_("Start"), accent=theme.MAGENTA, filled=True,
                                             min_size=(190, 36))
        status_sizer.Add(self.start_button, 0, wx.RIGHT, 10)

        self.cancel_button = theme.NeonButton(self, label=_("Cancel"), accent=theme.VIOLET,
                                              min_size=(110, 36))
        self.cancel_button.Enable(False)
        status_sizer.Add(self.cancel_button, 0)

        main_sizer.Add(status_sizer, 0, wx.ALIGN_RIGHT | wx.LEFT | wx.RIGHT, 18)
        main_sizer.AddSpacer(4)

        self.status_label = wx.StaticText(self, wx.ID_ANY, _("Ready"))
        self.status_label.SetFont(theme.ui_font("small", self))
        self.status_label.SetForegroundColour(theme.MUTED)
        main_sizer.Add(self.status_label, 0, wx.LEFT | wx.RIGHT, 20)
        main_sizer.AddSpacer(5)

        self.progress_bar = theme.NeonProgressBar(self, background=theme.BG_BOTTOM)
        main_sizer.Add(self.progress_bar, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.SetSizer(main_sizer)

        # ------------------------------------------------------------- events
        self.start_button.Bind(wx.EVT_BUTTON, self.on_start)
        self.cancel_button.Bind(wx.EVT_BUTTON, self.on_cancel)
        self.select_button.Bind(wx.EVT_BUTTON, self.on_select_image)
        self.checksum_button.Bind(wx.EVT_BUTTON, self.on_checksum)
        self.boot_choice.Bind(wx.EVT_COMBOBOX, self.on_boot_choice_changed)
        self.scheme_choice.Bind(wx.EVT_COMBOBOX, self.on_scheme_changed)
        self.filesystem_choice.Bind(wx.EVT_COMBOBOX, self.on_filesystem_changed)

        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)

        self.refresh_devices()
        self.on_boot_choice_changed(None)

        if self.missing_filesystems:
            self.append_log(_("Note: not offered because the tool is missing: {0}").format(
                ", ".join(self.missing_filesystems)))

    # ------------------------------------------------------------- device list
    def refresh_devices(self):
        show_all = self.__parent.is_show_all_checked()

        self.device_devices = []
        previous = self.device_choice.GetValue()

        self.device_choice.Clear()

        if windows_backend.available():
            entries = windows_backend.list_removable_disks()
        else:
            entries = list_devices.usb_drive(show_all)

        for device, description in entries:
            self.device_devices.append(device)
            self.device_choice.Append(description)

        if self.device_devices:
            if previous in [self.device_choice.GetString(index) for index in range(self.device_choice.GetCount())]:
                self.device_choice.SetStringSelection(previous)
            else:
                self.device_choice.SetSelection(0)
        else:
            self.device_choice.Append(_("No USB device found"))
            self.device_choice.SetSelection(0)

        self.update_start_state()

    def selected_device(self):
        index = self.device_choice.GetSelection()
        if index == wx.NOT_FOUND or index >= len(self.device_devices):
            return None
        return self.device_devices[index]

    # ------------------------------------------------------------- boot selection
    def on_boot_choice_changed(self, __):
        is_image = self.boot_choice.GetValue() == BOOT_IMAGE

        self.image_mode_choice.Enable(is_image)
        self.select_button.Enable(is_image)
        self.checksum_button.Enable(is_image and os.path.isfile(self.image_path))

        if not is_image:
            self.filesystem_choice.Enable(True)

        self.update_start_state()

    def on_select_image(self, __):
        dialog = wx.FileDialog(self, _("Please select a disk image"), wildcard=
                               "Disk images (*.iso;*.img;*.vhd;*.gz;*.xz;*.zip)|*.iso;*.img;*.vhd;*.gz;*.xz;*.zip"
                               "|Iso images (*.iso)|*.iso;*.ISO|All files|*",
                               style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)

        if dialog.ShowModal() != wx.ID_OK:
            dialog.Destroy()
            return

        self.image_path = dialog.GetPath()
        dialog.Destroy()

        self.boot_choice.SetStringSelection(BOOT_IMAGE)
        self.checksum_button.Enable(True)
        self.set_status(_("Analyzing image..."))
        self.append_log(_("Selected image: {0}").format(self.image_path))

        def analyze():
            info = core.inspect_image(self.image_path)
            wx.CallAfter(self.apply_image_info, info)

        threading.Thread(target=analyze, daemon=True).start()
        self.on_boot_choice_changed(None)

    def apply_image_info(self, info):
        self.image_info = info

        label = os.path.splitext(os.path.basename(self.image_path))[0]
        label = "".join(character for character in label.upper() if character.isalnum())[:11]
        if label:
            self.label_field.SetValue(label)

        if info.get("is_windows"):
            filesystems = [self.filesystem_choice.GetString(index)
                           for index in range(self.filesystem_choice.GetCount())]

            if info.get("install_wim_size", 0) > (2 ** 32) - 1:
                if "NTFS" in filesystems:
                    self.filesystem_choice.SetStringSelection("NTFS")
                    self.append_log(_("The image contains a file larger than 4 GiB, NTFS selected."))

                self.append_log(_("FAT32 is still supported: install.wim will be split into .swm parts."))
            elif "FAT" in filesystems:
                self.filesystem_choice.SetStringSelection("FAT")

            self.append_log(_("Detected a Windows image."))

            if not info.get("has_efi_boot"):
                self.append_log(_("Warning: no UEFI bootloader found inside the image."))
        else:
            self.append_log(_("Detected a non-Windows image, DD image mode is usually the safe choice."))

        self.set_status(_("READY"))
        self.update_start_state()

    def on_checksum(self, __):
        if not os.path.isfile(self.image_path):
            wx.MessageBox(_("Select an image first."), "WinIso-NG", wx.OK | wx.ICON_INFORMATION, self)
            return

        dialog = ChecksumDialog(self, self.image_path)
        dialog.ShowModal()
        dialog.Destroy()

    # ------------------------------------------------------------- format options
    def on_scheme_changed(self, __):
        # Rufus pairs GPT with UEFI and MBR with BIOS by default
        if self.scheme_choice.GetValue() == "GPT":
            self.target_system_choice.SetStringSelection(_("UEFI (non CSM)"))
        else:
            self.target_system_choice.SetStringSelection(_("BIOS (or UEFI-CSM)"))

    def on_filesystem_changed(self, __):
        filesystem = self.filesystem_choice.GetValue()

        if filesystem == "FAT" and self.image_info and self.image_info.get("install_wim_size", 0) > (2 ** 32) - 1:
            self.append_log(_("install.wim is larger than 4 GiB: it will be split with wimlib-imagex for FAT32."))

        if filesystem == "FAT":
            self.cluster_choice.SetItems(["Default", "512", "1024", "2048", "4096", "8192", "16384", "32768"])
            self.cluster_choice.SetStringSelection("Default")
        else:
            self.cluster_choice.SetItems(CLUSTER_SIZES)
            self.cluster_choice.SetStringSelection("Default")

    def update_start_state(self):
        can_start = True

        if self.selected_device() is None:
            can_start = False

        if self.boot_choice.GetValue() == BOOT_IMAGE and not os.path.isfile(self.image_path):
            can_start = False

        if self.installing:
            can_start = False

        self.start_button.Enable(can_start)

    # ------------------------------------------------------------- status / log
    def set_status(self, text):
        wx.CallAfter(self.status_label.SetLabel, text)

    def append_log(self, text):
        if self.log_frame is not None and self.log_frame:
            wx.CallAfter(self.log_frame.append, text)
        else:
            self.log_buffer.append(str(text))

    def show_log(self, __=None):
        if self.log_frame is None or not self.log_frame:
            self.log_frame = LogFrame(self.__parent)
            for line in self.log_buffer:
                self.log_frame.append(line)
            self.log_buffer = []
            self.log_frame.Show()
        else:
            self.log_frame.Show()
            self.log_frame.Raise()

    def on_show_all_drive(self, __):
        self.refresh_devices()

    # ------------------------------------------------------------- install
    def target_summary(self, device):
        """Model, size and path of the selected device, on any platform."""
        if windows_backend.available():
            details = windows_backend.disk_details(device)
            return _("Target device: Disk {0}\nModel: {1}\nSize: {2}\nPath: {3}").format(
                device,
                details.get("model") or _("unknown model"),
                details.get("size") or _("unknown size"),
                details.get("path") or _("unknown path"))

        details = list_devices.device_details(device)
        return _("Target device: {0}\nModel: {1}\nSize: {2}").format(
            device,
            details.get("model") or _("unknown model"),
            details.get("size") or _("unknown size"))

    def on_start(self, __):
        dry_run = bool(windows_backend.available() and self.dry_run is not None
                       and self.dry_run.GetValue())

        if windows_backend.available():
            if not dry_run and not windows_backend.is_admin():
                wx.MessageBox(_("WinIso-NG must run as administrator to write to a disk."), "WinIso-NG",
                              wx.OK | wx.ICON_ERROR, self)
                return
        elif os.getuid() != 0:
            wx.MessageBox(_("WinIso-NG must run as root to write to a storage device."), "WinIso-NG",
                          wx.OK | wx.ICON_ERROR, self)
            return

        device = self.selected_device()

        image_mode = "ISO"
        boot_choice = self.boot_choice.GetValue()

        if boot_choice == BOOT_NONE:
            image_mode = "NONE"
        elif self.image_mode_choice.GetValue() == IMAGE_DD:
            image_mode = "DD"

        if image_mode != "NONE" and not os.path.isfile(self.image_path):
            wx.MessageBox(_("Select an image first."), "WinIso-NG", wx.OK | wx.ICON_INFORMATION, self)
            return

        message = _("Are you sure? This will delete all your files and wipe out the selected device.")
        message = self.target_summary(device) + "\n\n" + message

        if dry_run:
            message = self.target_summary(device) + "\n\n" + _(
                "Dry run: the whole plan is listed in the log and nothing is written.")

        if not dry_run and self.win11_bypass.GetValue() and image_mode != "NONE":
            message += "\n\n" + _("An autounattend.xml with the Windows 11 bypass will be written to the target.")

        if self.bad_blocks.GetValue() and not dry_run:
            message += "\n\n" + _("The bad blocks check also destroys all data on the device.")

        if wx.MessageBox(message, _("Confirm target device"),
                         wx.YES_NO | wx.ICON_WARNING | wx.NO_DEFAULT, self) != wx.YES:
            return

        filesystem = self.filesystem_choice.GetValue()

        if windows_backend.available():
            if image_mode == "DD":
                wx.MessageBox(_("DD image mode is only available on Linux. Choose Standard (copy files)."),
                              "WinIso-NG", wx.OK | wx.ICON_INFORMATION, self)
                return

            self.handler = windows_backend.WindowsJob(
                image_path=self.image_path,
                disk_number=int(device),
                filesystem=filesystem,
                label=self.label_field.GetValue(),
                win11_bypass=self.win11_bypass.GetValue(),
                dry_run=dry_run,
                partition_scheme=self.scheme_choice.GetValue(),
                target_system="UEFI" if self.target_system_choice.GetValue() == _("UEFI (non CSM)") else "BIOS",
                quick_format=self.quick_format.GetValue(),
                cluster_size=self.cluster_choice.GetValue())
        else:
            self.handler = WinIso_handler(
                source=self.image_path,
                target=device,
                filesystem=filesystem,
                label=self.label_field.GetValue(),
                partition_scheme=self.scheme_choice.GetValue(),
                target_system="UEFI" if self.target_system_choice.GetValue() == _("UEFI (non CSM)") else "BIOS",
                image_mode=image_mode,
                cluster_size=self.cluster_choice.GetValue(),
                quick_format=self.quick_format.GetValue(),
                bad_blocks_check=self.bad_blocks.GetValue(),
                skip_legacy_bootloader=self.__parent.options_skip_grub.IsChecked(),
                win11_bypass=self.win11_bypass.GetValue())

        self.handler.log_sink = self.append_log

        self.installing = True
        self.set_installing(True)
        self.append_log("=" * 46)
        self.append_log(_("Starting on {0}").format(device))

        self.handler.start()
        self.timer.Start(120)

    def on_cancel(self, __):
        if self.handler is not None and self.installing:
            self.handler.kill = True
            self.set_status(_("Cancel requested..."))

    def set_installing(self, installing):
        self.installing = installing

        controls = [self.device_choice, self.boot_choice, self.image_mode_choice, self.select_button,
                    self.checksum_button, self.scheme_choice, self.target_system_choice,
                    self.filesystem_choice, self.cluster_choice, self.label_field,
                    self.quick_format, self.bad_blocks, self.list_hard_drives,
                    self.win11_bypass]

        if self.dry_run is not None:
            controls.append(self.dry_run)

        for control in controls:
            control.Enable(not installing)

        if not installing:
            self.on_boot_choice_changed(None)

        self.cancel_button.Enable(installing)
        self.update_start_state()

    def on_timer(self, __):
        if self.handler is None:
            return

        if self.handler.state:
            self.status_label.SetLabel(str(self.handler.state)[:110])

        if self.handler.progress:
            self.progress_bar.SetValue(int(self.handler.progress))
        elif self.handler.progress is not False:
            self.progress_bar.Pulse()

        if not self.handler.finished:
            return

        self.timer.Stop()
        self.progress_bar.SetValue(0)
        self.set_installing(False)

        if self.handler.error:
            self.status_label.SetLabel(_("FAILED"))
            self.append_log(_("Error: {0}").format(self.handler.error))
            wx.MessageBox(_("Installation failed!") + "\n" + str(self.handler.error), _("Installation"),
                          wx.OK | wx.ICON_ERROR, self)
        elif self.handler.kill:
            self.status_label.SetLabel(_("CANCELLED"))
        elif getattr(self.handler, "dry_run", False):
            self.status_label.SetLabel(_("DRY RUN DONE"))
            self.append_log(_("Dry run finished: nothing was written."))
            wx.MessageBox(_("Dry run finished: nothing was written. The plan is in the log."),
                          _("Dry run"), wx.OK | wx.ICON_INFORMATION, self)
        else:
            self.status_label.SetLabel(_("DONE"))
            self.append_log(_("Installation succeeded!"))
            wx.MessageBox(_("Installation succeeded!"), _("Installation"), wx.OK | wx.ICON_INFORMATION, self)

        self.refresh_devices()
        self.handler = None


def run():
    frame = MainFrame("WinIso-NG", wx.DefaultPosition, wx.Size(780, 726))
    frame.SetMinSize(wx.Size(680, 520))

    frame.Show(True)
    frame.scroller.FitInside()
    app.MainLoop()


if __name__ == "__main__":
    run()
