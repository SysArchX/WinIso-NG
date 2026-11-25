"""Professional light theme for the WinIso-NG GUI.

A neutral, high-contrast palette with a single blue accent, system UI fonts and
flat controls, so the application looks like a modern desktop utility instead of
a custom-drawn neon skin.
"""

import os

import wx

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------
BG = wx.Colour(0xF4, 0xF5, 0xF7)          # window background
SURFACE = wx.Colour(0xFF, 0xFF, 0xFF)      # cards, panels, inputs
SURFACE_ALT = wx.Colour(0xF9, 0xFA, 0xFB)  # subtle fills, hover states
BORDER = wx.Colour(0xE1, 0xE5, 0xEA)       # 1px hairlines
BORDER_STRONG = wx.Colour(0xD1, 0xD5, 0xDB)

TEXT = wx.Colour(0x11, 0x18, 0x27)
MUTED = wx.Colour(0x6B, 0x72, 0x80)
DIM = wx.Colour(0x9C, 0xA3, 0xAF)

ACCENT = wx.Colour(0x25, 0x63, 0xEB)
ACCENT_HOVER = wx.Colour(0x1D, 0x4E, 0xD8)
ACCENT_SOFT = wx.Colour(0xEF, 0xF6, 0xFF)
SUCCESS = wx.Colour(0x05, 0x96, 0x69)
WARNING = wx.Colour(0xB4, 0x53, 0x09)
DANGER = wx.Colour(0xDC, 0x26, 0x26)

# Names kept for the existing call sites; they now map to the neutral palette.
BG_TOP = SURFACE
BG_BOTTOM = SURFACE
CARD = SURFACE
CARD_TOP = SURFACE_ALT
CYAN = ACCENT
MAGENTA = ACCENT
VIOLET = BORDER_STRONG

FONTS = {"title": None, "heading": None, "label": None, "body": None, "small": None}

_UI_FACES = ("Segoe UI", "Inter", "Cantarell", "Ubuntu", "Noto Sans", "DejaVu Sans")


def register_fonts(data_directory):
    """Build the interface fonts from the system UI face (bundled fonts optional)."""
    font_directory = os.path.join(data_directory, "fonts")

    add_private_font = getattr(wx.FontEnumerator, "AddPrivateFont", None)
    if add_private_font is not None:
        enumerator = wx.FontEnumerator()
        for filename in ("Orbitron.ttf", "Rajdhani-Bold.ttf"):
            path = os.path.join(font_directory, filename)
            if os.path.isfile(path):
                try:
                    enumerator.AddPrivateFont(path)
                except Exception:
                    pass

    def resolve_face():
        for face in _UI_FACES:
            probe = wx.Font(wx.FontInfo(11).FaceName(face))
            if probe.GetFaceName() == face:
                return face
        return ""

    face = resolve_face()

    def build(size, weight=wx.FONTWEIGHT_NORMAL):
        font = wx.Font(wx.FontInfo(size))
        if face:
            font.SetFaceName(face)
        font.SetWeight(weight)
        return font

    FONTS["title"] = build(17, wx.FONTWEIGHT_BOLD)
    FONTS["heading"] = build(9, wx.FONTWEIGHT_BOLD)
    FONTS["label"] = build(10)
    FONTS["body"] = build(10)
    FONTS["small"] = build(9)
    return FONTS


def lerp_colour(first, second, ratio):
    ratio = max(0.0, min(1.0, ratio))
    return wx.Colour(
        int(first.Red() + (second.Red() - first.Red()) * ratio),
        int(first.Green() + (second.Green() - first.Green()) * ratio),
        int(first.Blue() + (second.Blue() - first.Blue()) * ratio),
    )


def accent_gradient(gc, rect, first, second):
    return gc.CreateLinearGradientBrush(rect.x, rect.y, rect.x + rect.width, rect.y, first, second)


def ui_font(kind, fallback_widget=None):
    """Return one of the registered fonts, falling back to the widget font."""
    font = FONTS.get(kind)
    if font is not None:
        return wx.Font(font)
    return wx.Font(fallback_widget.GetFont()) if fallback_widget is not None else wx.Font(wx.FontInfo(10))


# --------------------------------------------------------------------------
# Surfaces
# --------------------------------------------------------------------------
class TechBackground(wx.Panel):
    """Plain application surface (kept name for compatibility)."""

    def __init__(self, parent, id=wx.ID_ANY, **kwargs):
        super(TechBackground, self).__init__(parent, id, **kwargs)
        self.SetBackgroundColour(SURFACE)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: None)


class Card(wx.Panel):
    """White rounded card with a 1px border."""

    def __init__(self, parent, id=wx.ID_ANY, accent=ACCENT, **kwargs):
        super(Card, self).__init__(parent, id, **kwargs)
        self.accent = accent
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, lambda event: (self.Refresh(), event.Skip()))

    def on_paint(self, __=None):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(BG))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return

        width, height = self.GetClientSize()
        gc.SetBrush(wx.Brush(SURFACE))
        gc.SetPen(wx.Pen(BORDER, 1))
        gc.DrawRoundedRectangle(0.5, 0.5, width - 1, height - 1, 8)


# --------------------------------------------------------------------------
# Controls
# --------------------------------------------------------------------------
class FieldFrame(wx.Panel):
    """Rounded 1px border around a text field."""

    def __init__(self, parent, id=wx.ID_ANY, accent=BORDER, background=SURFACE, min_height=34):
        super(FieldFrame, self).__init__(parent, id)
        self.accent = accent
        self.background = background
        self.SetMinSize((-1, min_height))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, lambda event: (self.Refresh(), event.Skip()))

    def on_paint(self, __=None):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.background))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return

        width, height = self.GetClientSize()
        gc.SetBrush(wx.Brush(SURFACE_ALT))
        gc.SetPen(wx.Pen(BORDER_STRONG if self.IsEnabled() else BORDER, 1))
        gc.DrawRoundedRectangle(0.5, 0.5, width - 1, height - 1, 6)


class NeonButton(wx.Control):
    """Flat button: filled = primary action, outlined = secondary."""

    def __init__(self, parent, id=wx.ID_ANY, label="", accent=ACCENT, filled=False,
                 min_size=(120, 34), background=SURFACE):
        super(NeonButton, self).__init__(parent, id, size=min_size, style=wx.BORDER_NONE)
        self.label = label
        self.accent = accent
        self.filled = filled
        self.background = background
        self.hover = False
        self.SetMinSize(min_size)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: None)
        self.Bind(wx.EVT_ENTER_WINDOW, self.on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self.on_leave)
        self.Bind(wx.EVT_LEFT_DOWN, lambda event: self.SetFocus())
        self.Bind(wx.EVT_LEFT_UP, self.on_click)
        self.Bind(wx.EVT_KEY_UP, self.on_key)

    def on_enter(self, event):
        self.hover = True
        self.SetCursor(wx.Cursor(wx.CURSOR_HAND))
        self.Refresh()

    def on_leave(self, event):
        self.hover = False
        self.Refresh()

    def on_key(self, event):
        if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_SPACE):
            self.on_click(event)
        else:
            event.Skip()

    def on_click(self, __):
        if not self.IsEnabled():
            return
        event = wx.CommandEvent(wx.EVT_BUTTON.typeId, self.GetId())
        event.SetEventObject(self)
        self.GetEventHandler().ProcessEvent(event)

    def SetLabel(self, label):
        self.label = label
        self.Refresh()

    def GetLabel(self):
        return self.label

    def Enable(self, enable=True):
        super(NeonButton, self).Enable(enable)
        self.Refresh()

    def on_paint(self, __=None):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.background))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return

        width, height = self.GetClientSize()
        enabled = self.IsEnabled()
        radius = 6

        if not enabled:
            fill, border, text = SURFACE_ALT, BORDER, DIM
        elif self.filled:
            fill = ACCENT_HOVER if self.hover else ACCENT
            border, text = fill, wx.WHITE
        else:
            fill = SURFACE_ALT if self.hover else SURFACE
            border, text = BORDER_STRONG, TEXT

        gc.SetBrush(wx.Brush(fill))
        gc.SetPen(wx.Pen(border, 1))
        gc.DrawRoundedRectangle(0.5, 0.5, width - 1, height - 1, radius)

        font = ui_font("label", self)
        font.SetWeight(wx.FONTWEIGHT_BOLD if self.filled else wx.FONTWEIGHT_NORMAL)
        gc.SetFont(font, text)
        text_width, text_height = gc.GetTextExtent(self.label)
        gc.DrawText(self.label, (width - text_width) / 2, (height - text_height) / 2)


class NeonRadio(wx.Control):
    """Minimal radio button (mutual exclusion handled by the owner)."""

    def __init__(self, parent, id=wx.ID_ANY, label="", accent=ACCENT, background=SURFACE):
        super(NeonRadio, self).__init__(parent, id, size=(-1, 26), style=wx.BORDER_NONE)
        self.label = label
        self.accent = accent
        self.background = background
        self.selected = False
        self.hover = False
        self.SetMinSize((-1, 26))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: None)
        self.Bind(wx.EVT_ENTER_WINDOW, lambda event: (setattr(self, "hover", True),
                                                      self.SetCursor(wx.Cursor(wx.CURSOR_HAND)),
                                                      self.Refresh()))
        self.Bind(wx.EVT_LEAVE_WINDOW, lambda event: (setattr(self, "hover", False), self.Refresh()))
        self.Bind(wx.EVT_LEFT_UP, self.on_click)
        self.Bind(wx.EVT_KEY_UP, self.on_key)

    def on_click(self, __):
        if self.IsEnabled() and not self.selected:
            self.SetValue(True)
            event = wx.CommandEvent(wx.EVT_RADIOBUTTON.typeId, self.GetId())
            event.SetEventObject(self)
            self.GetEventHandler().ProcessEvent(event)

    def on_key(self, event):
        if event.GetKeyCode() in (wx.WXK_RETURN, wx.WXK_SPACE):
            self.on_click(event)
        else:
            event.Skip()

    def SetValue(self, value):
        self.selected = bool(value)
        self.Refresh()

    def GetValue(self):
        return self.selected

    def Enable(self, enable=True):
        super(NeonRadio, self).Enable(enable)
        self.Refresh()

    def on_paint(self, __=None):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.background))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return

        height = self.GetClientSize().height
        centre_y = height / 2.0
        enabled = self.IsEnabled()
        radius = 7

        gc.SetBrush(wx.Brush(SURFACE))
        gc.SetPen(wx.Pen(ACCENT if self.selected and enabled else BORDER_STRONG, 1))
        gc.DrawEllipse(4, centre_y - radius, radius * 2, radius * 2)

        if self.selected:
            gc.SetBrush(wx.Brush(ACCENT if enabled else DIM))
            gc.SetPen(wx.TRANSPARENT_PEN)
            gc.DrawEllipse(8, centre_y - radius + 4, (radius - 4) * 2, (radius - 4) * 2)

        gc.SetFont(ui_font("body", self), TEXT if enabled else DIM)
        text_width, text_height = gc.GetTextExtent(self.label)
        gc.DrawText(self.label, 30, centre_y - text_height / 2.0)


class NeonProgressBar(wx.Control):
    """Slim progress bar with an indeterminate sweep."""

    def __init__(self, parent, id=wx.ID_ANY, accent=ACCENT, background=SURFACE):
        super(NeonProgressBar, self).__init__(parent, id, size=(-1, 6), style=wx.BORDER_NONE)
        self.value = 0
        self.pulse_position = 0
        self.idle = True
        self.accent = accent
        self.background = background
        self.SetMinSize((-1, 6))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: None)

    def SetValue(self, value):
        self.value = max(0, min(100, int(value)))
        self.idle = self.value == 0
        self.Refresh()

    def Pulse(self):
        self.pulse_position = (self.pulse_position + 7) % 140
        self.idle = False
        self.Refresh()

    def on_paint(self, __=None):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.background))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return

        width, height = self.GetClientSize()
        radius = height / 2.0

        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(BORDER))
        gc.DrawRoundedRectangle(0, 0, width, height, radius)

        if self.value > 0:
            filled = max(height, width * self.value / 100.0)
            gc.SetBrush(wx.Brush(ACCENT))
            gc.DrawRoundedRectangle(0, 0, filled, height, radius)
        elif not self.idle:
            sweep = width / 3.0
            x = (width + sweep) * self.pulse_position / 140.0 - sweep
            gc.SetBrush(wx.Brush(ACCENT_SOFT))
            gc.DrawRoundedRectangle(max(0, x), 0, min(sweep, width - max(0, x)), height, radius)


# --------------------------------------------------------------------------
# Installation progress dialog
# --------------------------------------------------------------------------
class InstallProgressDialog(wx.Dialog):
    """Clean modal progress dialog used by the CLI-style flows."""

    def __init__(self, parent, title, message, maximum=101):
        style = wx.DEFAULT_DIALOG_STYLE & ~wx.CLOSE_BOX & ~wx.MAXIMIZE_BOX
        super(InstallProgressDialog, self).__init__(parent, wx.ID_ANY, title, style=style)
        self.SetBackgroundColour(SURFACE)
        self.maximum = maximum
        self.cancelled = False

        sizer = wx.BoxSizer(wx.VERTICAL)

        self.title_label = wx.StaticText(self, wx.ID_ANY, title)
        self.title_label.SetFont(ui_font("title", self))
        self.title_label.SetForegroundColour(TEXT)
        sizer.Add(self.title_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 20)

        self.status_label = wx.StaticText(self, wx.ID_ANY, message)
        self.status_label.SetFont(ui_font("body", self))
        self.status_label.SetForegroundColour(MUTED)
        sizer.Add(self.status_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 20)

        self.progress = NeonProgressBar(self, background=SURFACE)
        sizer.Add(self.progress, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 20)

        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.AddStretchSpacer(1)
        self.cancel_button = NeonButton(self, label="Cancel", min_size=(100, 32), background=SURFACE)
        button_sizer.Add(self.cancel_button, 0, wx.ALL, 20)
        sizer.Add(button_sizer, 0, wx.EXPAND)

        self.SetSizer(sizer)
        self.SetClientSize((520, 200))

        self.cancel_button.Bind(wx.EVT_BUTTON, self.on_cancel)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        self.CentreOnParent()

    def on_cancel(self, __):
        self.cancelled = True
        self.status_label.SetLabel("Cancelling...")
        self.Layout()

    def on_close(self, __):
        self.cancelled = True

    def Show(self, show=True):
        if show:
            super(InstallProgressDialog, self).Show()
            wx.Yield()
            return True
        return super(InstallProgressDialog, self).Show(show)

    def Pulse(self, message=None):
        if message is not None:
            self.status_label.SetLabel(str(message))
        self.progress.Pulse()
        wx.Yield()
        return (not self.cancelled,)

    def Update(self, value, message=None):
        if message is not None:
            self.status_label.SetLabel(str(message))
        self.progress.SetValue(min(100, int(value * 100 / max(1, self.maximum - 1))))
        wx.Yield()
        return (not self.cancelled,)

    def Resume(self):
        """Undo a cancel request when the user chooses to keep installing."""
        self.cancelled = False
        return True
