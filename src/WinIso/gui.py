#!/usr/bin/env python3

import os
import time
import threading

import wx
import wx.adv


import WinIso.core as core
import WinIso.list_devices as list_devices
import WinIso.miscellaneous as miscellaneous
import WinIso.theme as theme

data_directory = os.path.dirname(__file__) + "/data/"

app = wx.App()

theme.register_fonts(data_directory)

_ = miscellaneous.i18n


def section_label(parent, text, colour=theme.CYAN):
    label = wx.StaticText(parent, wx.ID_ANY, text)
    label.SetFont(theme.FONTS["small"] or parent.GetFont())
    label.SetForegroundColour(colour)
    label.SetBackgroundColour(theme.CARD)
    return label


def body_label(parent, text, colour=theme.TEXT):
    label = wx.StaticText(parent, wx.ID_ANY, text)
    label.SetFont(theme.FONTS["body"] or parent.GetFont())
    label.SetForegroundColour(colour)
    label.SetBackgroundColour(theme.CARD)
    return label


def style_list(control):
    control.SetBackgroundColour(theme.BG_TOP)
    control.SetForegroundColour(theme.TEXT)
    if theme.FONTS["body"] is not None:
        control.SetFont(theme.FONTS["body"])


class IsoPicker(wx.Panel):
    """Dark text field plus a neon Browse button, replacing wx.FilePickerCtrl."""

    def __init__(self, parent, on_change):
        super(IsoPicker, self).__init__(parent, wx.ID_ANY)
        self.SetBackgroundColour(theme.CARD)
        self.path = ""
        self.on_change = on_change

        sizer = wx.BoxSizer(wx.HORIZONTAL)

        self.field = theme.FieldFrame(self, accent=theme.CYAN, background=theme.CARD, min_height=40)
        field_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.text = wx.TextCtrl(self.field, wx.ID_ANY, "", style=wx.TE_READONLY | wx.BORDER_NONE)
        self.text.SetBackgroundColour(theme.BG_TOP)
        self.text.SetForegroundColour(theme.MUTED)
        if theme.FONTS["body"] is not None:
            self.text.SetFont(theme.FONTS["body"])
        field_sizer.Add(self.text, 1, wx.EXPAND | wx.ALL, 9)
        self.field.SetSizer(field_sizer)
        sizer.Add(self.field, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 8)

        self.button = theme.NeonButton(self, label=_("Browse"), accent=theme.CYAN,
                                       min_size=(104, 40), background=theme.CARD)
        sizer.Add(self.button, 0, wx.ALIGN_CENTER_VERTICAL)

        self.SetSizer(sizer)
        self.button.Bind(wx.EVT_BUTTON, self.on_browse)

    def GetPath(self):
        return self.path

    def Enable(self, enable=True):
        self.text.Enable(enable)
        self.field.Enable(enable)
        self.button.Enable(enable)

    def on_browse(self, __):
        dialog = wx.FileDialog(self, _("Please select a disk image"), wildcard=
                               "Iso images (*.iso)|*.iso;*.ISO|All files|*",
                               style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST)
        if dialog.ShowModal() == wx.ID_OK:
            self.path = dialog.GetPath()
            self.text.SetValue(self.path)
            self.text.SetForegroundColour(theme.TEXT)
            self.on_change()
        dialog.Destroy()


class MainFrame(wx.Frame):
    __MainPanel = None
    __MenuBar = None

    __menuItemShowAll = None

    def __init__(self, title, pos, size, style=wx.DEFAULT_FRAME_STYLE):
        super(MainFrame, self).__init__(None, -1, title, pos, size, style)

        self.SetBackgroundColour(theme.BG_BOTTOM)
        self.SetIcon(wx.Icon(data_directory + "icon.ico"))

        file_menu = wx.Menu()
        self.__menuItemShowAll = wx.MenuItem(file_menu, wx.ID_ANY, _("Show all drives") + " \tCtrl+A",
                                             _("Show all drives, even those not detected as USB stick."),
                                             wx.ITEM_CHECK)
        file_menu.Append(self.__menuItemShowAll)

        file_menu.AppendSeparator()
        exit_item = file_menu.Append(wx.ID_EXIT)

        help_menu = wx.Menu()
        help_item = help_menu.Append(wx.ID_ABOUT)

        options_menu = wx.Menu()
        self.options_boot = wx.MenuItem(options_menu, wx.ID_ANY, _("Set boot flag"),
                                        _("Sets boot flag after process of copying."),
                                        wx.ITEM_CHECK)
        self.options_filesystem = wx.MenuItem(options_menu, wx.ID_ANY, _("Use NTFS"),
                                              _("Use NTFS instead of FAT. NOTE: NTFS seems to be slower than FAT."),
                                              wx.ITEM_CHECK)
        self.options_skip_grub = wx.MenuItem(options_menu, wx.ID_ANY, _("Skip legacy grub bootloader"),
                                              _("No legacy grub bootloader will be created. NOTE: It will only boot on system with UEFI support."),
                                              wx.ITEM_CHECK)
        options_menu.Append(self.options_boot)
        options_menu.Append(self.options_filesystem)
        options_menu.Append(self.options_skip_grub)

        self.__MenuBar = wx.MenuBar()
        self.__MenuBar.Append(file_menu, _("&File"))
        self.__MenuBar.Append(options_menu, _("&Options"))
        self.__MenuBar.Append(help_menu, _("&Help"))

        self.SetMenuBar(self.__MenuBar)

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        self.__MainPanel = MainPanel(self, wx.ID_ANY)
        main_sizer.Add(self.__MainPanel, 1, wx.EXPAND)

        self.SetSizer(main_sizer)

        self.Bind(wx.EVT_MENU, self.__MainPanel.on_show_all_drive)
        self.Bind(wx.EVT_MENU, self.on_quit, exit_item)
        self.Bind(wx.EVT_MENU, self.on_about, help_item)

    def on_quit(self, __):
        self.Close(True)

    def on_about(self, __):
        my_dialog_about = DialogAbout(self, wx.ID_ANY)
        my_dialog_about.ShowModal()
        my_dialog_about.Destroy()

    def is_show_all_checked(self):
        return self.__menuItemShowAll.IsChecked()


class MainPanel(theme.TechBackground):
    __parent = None

    __dvdDriveList = None
    __usbStickList = wx.ListBox

    __dvdDriveDevList = []
    __usbStickDevList = []

    __isoFile = None

    __parentFrame = None

    __btInstall = None
    __btRefresh = None

    __isoChoice = None
    __dvdChoice = None

    def __init__(self, parent, ID, pos=wx.DefaultPosition, size=wx.DefaultSize, style=wx.TAB_TRAVERSAL):
        super(MainPanel, self).__init__(parent, ID, pos=pos, size=size, style=style)

        self.__parent = parent

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # ---------------------------------------------------------------- header
        header_sizer = wx.BoxSizer(wx.HORIZONTAL)

        logo_path = data_directory + "winiso-logo.png"
        if os.path.isfile(logo_path):
            image = wx.Image(logo_path, wx.BITMAP_TYPE_PNG).Scale(58, 58, wx.IMAGE_QUALITY_HIGH)
            header_sizer.Add(wx.StaticBitmap(self, wx.ID_ANY, wx.Bitmap(image)), 0,
                             wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 14)

        title_sizer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(self, wx.ID_ANY, "WinIso-NG")
        if theme.FONTS["title"] is not None:
            title.SetFont(theme.FONTS["title"])
        title.SetForegroundColour(theme.CYAN)
        title_sizer.Add(title, 0, wx.BOTTOM, 2)

        subtitle = wx.StaticText(self, wx.ID_ANY, _("Create a bootable Windows USB installer"))
        if theme.FONTS["small"] is not None:
            subtitle.SetFont(theme.FONTS["small"])
        subtitle.SetForegroundColour(theme.MUTED)
        title_sizer.Add(subtitle, 0)

        header_sizer.Add(title_sizer, 1, wx.ALIGN_CENTER_VERTICAL)

        main_sizer.Add(header_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 20)
        main_sizer.AddSpacer(20)

        # ---------------------------------------------------------------- source
        source_card = theme.Card(self, accent=theme.CYAN)
        source_sizer = wx.BoxSizer(wx.VERTICAL)

        source_sizer.Add(section_label(source_card, _("Source :").rstrip(" :").upper()),
                         0, wx.LEFT | wx.RIGHT | wx.TOP, 16)
        source_sizer.AddSpacer(10)

        self.__isoChoice = theme.NeonRadio(source_card, label=_("From a disk image (iso)"),
                                          accent=theme.CYAN, background=theme.CARD)
        self.__dvdChoice = theme.NeonRadio(source_card, label=_("From a CD/DVD drive"),
                                          accent=theme.VIOLET, background=theme.CARD)

        source_sizer.Add(self.__isoChoice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 16)
        source_sizer.AddSpacer(6)
        source_sizer.Add(self.__dvdChoice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 16)
        source_sizer.AddSpacer(10)

        self.__isoFile = IsoPicker(source_card, self.on_list_or_file_modified)
        source_sizer.Add(self.__isoFile, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 16)
        source_sizer.AddSpacer(10)

        self.__dvdDriveList = wx.ListBox(source_card, wx.ID_ANY)
        style_list(self.__dvdDriveList)
        source_sizer.Add(self.__dvdDriveList, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)

        source_card.SetSizer(source_sizer)
        main_sizer.Add(source_card, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)
        main_sizer.AddSpacer(16)

        # ---------------------------------------------------------------- target
        target_card = theme.Card(self, accent=theme.MAGENTA)
        target_sizer = wx.BoxSizer(wx.VERTICAL)

        target_sizer.Add(section_label(target_card, _("Target device :").rstrip(" :").upper(),
                                       theme.MAGENTA), 0, wx.LEFT | wx.RIGHT | wx.TOP, 16)
        target_sizer.AddSpacer(10)

        self.__usbStickList = wx.ListBox(target_card, wx.ID_ANY)
        style_list(self.__usbStickList)
        target_sizer.Add(self.__usbStickList, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 16)
        target_sizer.AddSpacer(8)

        target_sizer.Add(body_label(target_card,
                                    _("All data on the selected device will be erased."),
                                    theme.MUTED), 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 16)

        target_card.SetSizer(target_sizer)
        main_sizer.Add(target_card, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)

        # ---------------------------------------------------------------- footer
        main_sizer.AddSpacer(18)

        footer_sizer = wx.BoxSizer(wx.HORIZONTAL)

        bt_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.__btRefresh = theme.NeonButton(self, label=_("Refresh"), accent=theme.VIOLET,
                                            min_size=(120, 44))
        bt_sizer.Add(self.__btRefresh, 0, wx.RIGHT, 10)
        self.__btInstall = theme.NeonButton(self, label=_("Install"), accent=theme.MAGENTA,
                                            filled=True, min_size=(150, 44))
        bt_sizer.Add(self.__btInstall, 0)

        footer_sizer.AddStretchSpacer(1)
        footer_sizer.Add(bt_sizer, 0)

        main_sizer.Add(footer_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 20)

        # ---------------------------------------------------------------- events
        self.SetSizer(main_sizer)

        self.Bind(wx.EVT_LISTBOX, self.on_list_or_file_modified, self.__usbStickList)
        self.Bind(wx.EVT_LISTBOX, self.on_list_or_file_modified, self.__dvdDriveList)

        self.Bind(wx.EVT_BUTTON, self.on_install, self.__btInstall)
        self.Bind(wx.EVT_BUTTON, self.on_refresh, self.__btRefresh)

        self.Bind(wx.EVT_RADIOBUTTON, self.on_source_option_changed, self.__isoChoice)
        self.Bind(wx.EVT_RADIOBUTTON, self.on_source_option_changed, self.__dvdChoice)

        self.refresh_list_content()
        self.on_source_option_changed(None)
        self.__btInstall.Enable(self.is_install_ok())

    def refresh_list_content(self):
        # USB
        self.__usbStickDevList = []
        self.__usbStickList.Clear()

        show_all_checked = self.__parent.is_show_all_checked()

        device_list = list_devices.usb_drive(show_all_checked)

        for device in device_list:
            self.__usbStickDevList.append(device[0])
            self.__usbStickList.Append(device[1])

        # ISO

        self.__dvdDriveDevList = []
        self.__dvdDriveList.Clear()

        drive_list = list_devices.dvd_drive()

        for drive in drive_list:
            self.__dvdDriveDevList.append(drive[0])
            self.__dvdDriveList.Append(drive[1])

        self.__btInstall.Enable(self.is_install_ok())

    def on_source_option_changed(self, event):
        sender = None
        if event is not None and hasattr(event, "GetEventObject"):
            sender = event.GetEventObject()

        if sender is self.__isoChoice:
            self.__isoChoice.SetValue(True)
            self.__dvdChoice.SetValue(False)
        elif sender is self.__dvdChoice:
            self.__dvdChoice.SetValue(True)
            self.__isoChoice.SetValue(False)

        is_iso = self.__isoChoice.GetValue()

        self.__isoFile.Enable(is_iso)
        self.__dvdDriveList.Enable(not is_iso)

        self.__btInstall.Enable(self.is_install_ok())

    def is_install_ok(self):
        is_iso = self.__isoChoice.GetValue()
        return ((is_iso and os.path.isfile(self.__isoFile.GetPath())) or (
                not is_iso and self.__dvdDriveList.GetSelection() != wx.NOT_FOUND)) and self.__usbStickList.GetSelection() != wx.NOT_FOUND

    def on_list_or_file_modified(self, event=None):
        if event is not None and hasattr(event, "GetEventType") and event.GetEventType() == wx.wxEVT_LISTBOX:
            if not event.IsSelection():
                return

        self.__btInstall.Enable(self.is_install_ok())

    def on_refresh(self, __):
        self.refresh_list_content()

    def on_install(self, __):
        global woe
        if wx.MessageBox(
            _("Are you sure? This will delete all your files and wipe out the selected partition."),
            _("Cancel"),
            wx.YES_NO | wx.ICON_QUESTION | wx.NO_DEFAULT,
            self) != wx.YES:
            return
        if self.is_install_ok():
            is_iso = self.__isoChoice.GetValue()

            device = self.__usbStickDevList[self.__usbStickList.GetSelection()]

            if is_iso:
                iso = self.__isoFile.GetPath()
            else:
                iso = self.__dvdDriveDevList[self.__dvdDriveList.GetSelection()]

            if self.__parent.options_filesystem.IsChecked():
                filesystem = "NTFS"
            else:
                filesystem = "FAT"

            woe = WinIso_handler(iso, device, boot_flag=self.__parent.options_boot.IsChecked(), filesystem=filesystem, skip_grub=self.__parent.options_skip_grub.IsChecked())
            woe.start()

            dialog = theme.InstallProgressDialog(self.GetParent(), _("Installing"), _("Please wait..."), 101)
            dialog.Show()

            while woe.is_alive():
                if not woe.progress:
                    status = dialog.Pulse(woe.state)[0]
                    time.sleep(0.06)
                else:
                    status = dialog.Update(woe.progress, woe.state)[0]

                if not status:
                    if wx.MessageBox(_("Are you sure you want to cancel the installation?"), _("Cancel"),
                                     wx.YES_NO | wx.ICON_QUESTION, self) == wx.NO:
                        dialog.Resume()
                    else:
                        woe.kill = True
                        break
            dialog.Destroy()

            if woe.error == "":
                wx.MessageBox(_("Installation succeeded!"), _("Installation"), wx.OK | wx.ICON_INFORMATION, self)
            else:
                wx.MessageBox(_("Installation failed!") + "\n" + str(woe.error), _("Installation"),
                              wx.OK | wx.ICON_ERROR,
                              self)

    def on_show_all_drive(self, __):
        self.refresh_list_content()


class DialogAbout(wx.Dialog):
    __bitmapIcone = None
    __staticTextTitre = None
    __staticTextVersion = None
    __NotebookAutorLicence = None
    __MyPanelNoteBookAutors = None
    __BtOk = None

    def __init__(self, parent, ID=wx.ID_ANY, title=_("About"), pos=wx.DefaultPosition, size=wx.Size(650, 590),
                 style=wx.DEFAULT_DIALOG_STYLE):
        super(DialogAbout, self).__init__(parent, ID, title, pos, size, style)

        self.SetSizeHints(wx.DefaultSize, wx.DefaultSize)
        self.SetBackgroundColour(theme.CARD)
        self.SetIcon(wx.Icon(data_directory + "icon.ico"))

        sizer_all = wx.BoxSizer(wx.VERTICAL)
        sizer_img = wx.BoxSizer(wx.HORIZONTAL)

        img = wx.Image(data_directory + "icon.ico", wx.BITMAP_TYPE_ICO).Scale(52, 52, wx.IMAGE_QUALITY_BILINEAR)
        self.__bitmapIcone = wx.StaticBitmap(self, wx.ID_ANY, wx.Bitmap(img), wx.DefaultPosition, wx.Size(52, 52))
        sizer_img.Add(self.__bitmapIcone, 0, wx.ALL, 8)

        sizer_text = wx.BoxSizer(wx.VERTICAL)

        self.__staticTextTitre = wx.StaticText(self, wx.ID_ANY, "WinIso-NG")
        if theme.FONTS["title"] is not None:
            self.__staticTextTitre.SetFont(theme.FONTS["title"])
        self.__staticTextTitre.SetForegroundColour(theme.CYAN)
        sizer_text.Add(self.__staticTextTitre, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 4)

        self.__staticTextVersion = wx.StaticText(self, wx.ID_ANY, miscellaneous.__version__)
        if theme.FONTS["body"] is not None:
            self.__staticTextVersion.SetFont(theme.FONTS["body"])
        self.__staticTextVersion.SetForegroundColour(theme.MAGENTA)
        sizer_text.Add(self.__staticTextVersion, 0, wx.LEFT, 4)
        sizer_img.Add(sizer_text, 0, 0, 5)
        sizer_all.Add(sizer_img, 0, wx.EXPAND, 8)

        self.__NotebookAutorLicence = wx.Notebook(self, wx.ID_ANY)
        self.__NotebookAutorLicence.SetBackgroundColour(theme.CARD)
        self.__NotebookAutorLicence.SetForegroundColour(theme.TEXT)

        self.__NotebookAutorLicence.AddPage(
            PanelNoteBookAutors(self.__NotebookAutorLicence, wx.ID_ANY, "slacka \nLin-Buo-Ren\nWaxyMocha", data_directory + "winiso-logo.png",
                                "github.com/WoeUSB/WoeUSB-ng"), _("Authors"), True)
        self.__NotebookAutorLicence.AddPage(
            PanelNoteBookAutors(self.__NotebookAutorLicence, wx.ID_ANY, "Colin GILLE / Congelli501",
                                data_directory + "c501-logo.png", "www.congelli.eu"), _("Original WinUSB Developer"), False)

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

        licence_txt = wx.TextCtrl(self.__NotebookAutorLicence, wx.ID_ANY, licence_str, wx.DefaultPosition,
                                  wx.DefaultSize, wx.TE_MULTILINE | wx.TE_READONLY)
        licence_txt.SetBackgroundColour(theme.BG_TOP)
        licence_txt.SetForegroundColour(theme.MUTED)
        if theme.FONTS["body"] is not None:
            licence_txt.SetFont(theme.FONTS["body"])

        self.__NotebookAutorLicence.AddPage(licence_txt, _("License"))

        sizer_all.Add(self.__NotebookAutorLicence, 1, wx.EXPAND | wx.ALL, 8)

        self.__BtOk = theme.NeonButton(self, label="OK", accent=theme.CYAN, filled=True,
                                       min_size=(120, 40), background=theme.CARD)
        sizer_all.Add(self.__BtOk, 0, wx.ALIGN_RIGHT | wx.BOTTOM | wx.RIGHT, 10)
        self.__BtOk.SetFocus()

        self.SetSizer(sizer_all)
        self.Layout()

        self.__BtOk.Bind(wx.EVT_BUTTON, lambda event: self.EndModal(wx.ID_OK))


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
            img_autor_logo = wx.StaticBitmap(self, wx.ID_ANY, wx.Bitmap(img))
            sizer_note_book_autors.Add(img_autor_logo, 0, wx.LEFT | wx.BOTTOM, 8)

        self.SetSizer(sizer_note_book_autors)


class WinIso_handler(threading.Thread):
    """
    Class for handling communication with winiso.
    """
    progress = False
    state = ""
    error = ""
    kill = False

    def __init__(self, source, target, boot_flag, filesystem, skip_grub=False):
        threading.Thread.__init__(self)

        core.gui = self
        self.source = source
        self.target = target
        self.boot_flag = boot_flag
        self.filesystem = filesystem
        self.skip_grub = skip_grub

    def run(self):
        source_fs_mountpoint, target_fs_mountpoint, temp_directory, target_media = core.init(
            from_cli=False,
            install_mode="device",
            source_media=self.source,
            target_media=self.target
        )
        try:
            core.main(source_fs_mountpoint, target_fs_mountpoint, self.source, self.target, "device", temp_directory,
                      self.filesystem, self.boot_flag , None, self.skip_grub)
        except SystemExit:
            pass

        core.cleanup(source_fs_mountpoint, target_fs_mountpoint, temp_directory, target_media)


def run():
    frameTitle = "WinIso-NG"

    frame = MainFrame(frameTitle, wx.DefaultPosition, wx.Size(580, 760))
    frame.SetMinSize(wx.Size(520, 700))

    frame.Show(True)
    app.MainLoop()


if __name__ == "__main__":
    run()
