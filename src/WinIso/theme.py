"""Futuristic dark/neon theme for the WinIso-NG GUI.

Provides the colour palette, bundled font loading and the custom-drawn
widgets used by the interface (background, cards, buttons, radio buttons,
progress bar and the installation progress dialog).
"""

import os

import wx

# --------------------------------------------------------------------------
# Palette
# --------------------------------------------------------------------------
BG_TOP = wx.Colour(8, 12, 24)
BG_BOTTOM = wx.Colour(17, 23, 42)
CARD = wx.Colour(12, 18, 33)
CARD_TOP = wx.Colour(17, 25, 45)
CYAN = wx.Colour(0, 229, 255)
MAGENTA = wx.Colour(255, 45, 149)
VIOLET = wx.Colour(124, 77, 255)
TEXT = wx.Colour(232, 240, 255)
MUTED = wx.Colour(118, 140, 178)
DIM = wx.Colour(72, 90, 120)
BORDER = wx.Colour(38, 58, 92)

FONTS = {"title": None, "label": None, "body": None, "small": None}


def register_fonts(data_directory):
    """Register the bundled fonts (when the platform allows it) and build the UI fonts."""
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

    def resolve_face(preferred, fallback="DejaVu Sans"):
        """Use the preferred family when the system can provide it, otherwise fall back."""
        probe = wx.Font(wx.FontInfo(12).FaceName(preferred))
        if probe.GetFaceName() == preferred:
            return preferred
        return fallback

    title_face = resolve_face("Orbitron")
    body_face = resolve_face("Rajdhani")

    def build(face, size, weight=wx.FONTWEIGHT_NORMAL):
        font = wx.Font(wx.FontInfo(size).FaceName(face))
        font.SetWeight(weight)
        return font

    FONTS["title"] = build(title_face, 20, wx.FONTWEIGHT_BOLD)
    FONTS["label"] = build(body_face, 11, wx.FONTWEIGHT_BOLD)
    FONTS["body"] = build(body_face, 11)
    FONTS["small"] = build(body_face, 9)
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


# --------------------------------------------------------------------------
# Background
# --------------------------------------------------------------------------
class TechBackground(wx.Panel):
    """Panel painting the dark gradient, tech grid and neon top border."""

    def __init__(self, parent, id=wx.ID_ANY, **kwargs):
        super(TechBackground, self).__init__(parent, id, **kwargs)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, lambda event: (self.Refresh(), event.Skip()))

    def on_paint(self, __=None):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(BG_BOTTOM))
        dc.Clear()

        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return

        width, height = self.GetClientSize()

        brush = gc.CreateLinearGradientBrush(0, 0, 0, height, BG_TOP, BG_BOTTOM)
        gc.SetBrush(brush)
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.DrawRectangle(0, 0, width, height)

        # tech grid
        gc.SetPen(wx.Pen(wx.Colour(96, 160, 230, 16), 1))
        step = 34
        for x in range(0, width, step):
            gc.StrokeLine(x, 0, x, height)
        for y in range(0, height, step):
            gc.StrokeLine(0, y, width, y)

        # neon hairline at the very top
        gc.SetPen(wx.Pen(CYAN, 2))
        gc.StrokeLine(0, 1, width * 0.55, 1)
        gc.SetPen(wx.Pen(MAGENTA, 2))
        gc.StrokeLine(width * 0.55, 1, width, 1)


class Card(wx.Panel):
    """Rounded translucent card with a neon corner accent."""

    def __init__(self, parent, id=wx.ID_ANY, accent=CYAN, **kwargs):
        super(Card, self).__init__(parent, id, **kwargs)
        self.accent = accent
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_SIZE, lambda event: (self.Refresh(), event.Skip()))

    def on_paint(self, __=None):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(BG_BOTTOM))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return

        width, height = self.GetClientSize()
        radius = 10

        gc.SetBrush(wx.Brush(CARD))
        gc.SetPen(wx.Pen(wx.Colour(120, 200, 255, 40), 1))
        gc.DrawRoundedRectangle(1, 1, width - 2, height - 2, radius)

        # faint inner highlight along the top edge
        gc.SetPen(wx.Pen(wx.Colour(self.accent.Red(), self.accent.Green(), self.accent.Blue(), 45), 1))
        gc.StrokeLine(12, 2, width - 12, 2)

        # accent bar on the left edge
        gc.SetPen(wx.Pen(self.accent, 3))
        gc.StrokeLine(1, 12, 1, height - 12)


# --------------------------------------------------------------------------
# Controls
# --------------------------------------------------------------------------
class FieldFrame(wx.Panel):
    """Inset text field frame with a neon hairline border."""

    def __init__(self, parent, id=wx.ID_ANY, accent=BORDER, background=CARD, min_height=40):
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
        gc.SetBrush(wx.Brush(BG_TOP))
        gc.SetPen(wx.Pen(wx.Colour(self.accent.Red(), self.accent.Green(), self.accent.Blue(), 160), 1))
        gc.DrawRoundedRectangle(0.5, 0.5, width - 1, height - 1, 5)


class NeonButton(wx.Control):
    """Custom drawn futuristic button."""

    def __init__(self, parent, id=wx.ID_ANY, label="", accent=CYAN, filled=False,
                 min_size=(120, 40), background=BG_BOTTOM):
        super(NeonButton, self).__init__(parent, id, size=min_size,
                                         style=wx.BORDER_NONE)
        self.label = label.upper()
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
        self.label = label.upper()
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
        accent = self.accent if enabled else DIM
        radius = 6

        # outer glow
        if enabled and self.hover:
            for offset, alpha in ((4, 26), (2, 46)):
                gc.SetPen(wx.Pen(wx.Colour(accent.Red(), accent.Green(), accent.Blue(), alpha), 2))
                gc.SetBrush(wx.TRANSPARENT_BRUSH)
                gc.DrawRoundedRectangle(offset, offset, width - offset * 2, height - offset * 2, radius)

        # body
        if self.filled and enabled:
            brush = gc.CreateLinearGradientBrush(0, 0, width, height,
                                                 lerp_colour(accent, wx.BLACK, 0.15),
                                                 lerp_colour(accent, wx.BLACK, 0.55))
        elif self.hover and enabled:
            brush = gc.CreateLinearGradientBrush(0, 0, 0, height,
                                                 wx.Colour(accent.Red(), accent.Green(), accent.Blue(), 60), CARD)
        else:
            brush = gc.CreateLinearGradientBrush(0, 0, 0, height, CARD_TOP, CARD)
        gc.SetBrush(brush)
        gc.SetPen(wx.Pen(accent if enabled else BORDER, 2))
        gc.DrawRoundedRectangle(1, 1, width - 2, height - 2, radius)

        # label
        font = wx.Font(FONTS["label"]) if FONTS["label"] else self.GetFont()
        font.SetPointSize(11)
        gc.SetFont(font, wx.WHITE if self.filled and enabled else (TEXT if enabled else DIM))
        text_width, text_height = gc.GetTextExtent(self.label)
        gc.DrawText(self.label, (width - text_width) / 2, (height - text_height) / 2)


class NeonRadio(wx.Control):
    """Custom drawn neon radio button (mutual exclusion handled by the owner)."""

    def __init__(self, parent, id=wx.ID_ANY, label="", accent=CYAN, background=CARD):
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
        accent = self.accent if enabled else DIM
        radius = 7

        # outer ring
        pen_width = 2 if not self.selected else 3
        gc.SetPen(wx.Pen(accent, pen_width))
        gc.SetBrush(wx.Brush(wx.Colour(accent.Red(), accent.Green(), accent.Blue(), 40) if self.selected
                             else CARD))
        gc.DrawEllipse(4, centre_y - radius, radius * 2, radius * 2)

        if self.selected:
            glow = wx.Colour(accent.Red(), accent.Green(), accent.Blue(), 90)
            gc.SetBrush(wx.Brush(glow))
            gc.SetPen(wx.TRANSPARENT_PEN)
            gc.DrawEllipse(8, centre_y - radius + 4, (radius - 4) * 2, (radius - 4) * 2)

        font = wx.Font(FONTS["label"]) if FONTS["label"] else self.GetFont()
        gc.SetFont(font, TEXT if enabled else DIM)
        text_width, text_height = gc.GetTextExtent(self.label)
        gc.DrawText(self.label, 30, centre_y - text_height / 2.0)


class NeonProgressBar(wx.Control):
    """Slim neon progress bar with pulse mode."""

    def __init__(self, parent, id=wx.ID_ANY, accent=CYAN, background=CARD):
        super(NeonProgressBar, self).__init__(parent, id, size=(-1, 10), style=wx.BORDER_NONE)
        self.value = 0
        self.pulse_position = 0
        self.accent = accent
        self.background = background
        self.SetMinSize((-1, 10))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self.on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda event: None)

    def SetValue(self, value):
        self.value = max(0, min(100, int(value)))
        self.Refresh()

    def Pulse(self):
        self.pulse_position = (self.pulse_position + 7) % 140
        self.Refresh()

    def on_paint(self, __=None):
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.background))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return

        width, height = self.GetClientSize()

        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(255, 255, 255, 18)))
        gc.DrawRoundedRectangle(0, 1, width, height - 2, height / 2.0)

        if self.value > 0:
            filled = max(height, width * self.value / 100.0)
            gc.SetBrush(gc.CreateLinearGradientBrush(0, 0, filled, 0, CYAN, MAGENTA))
            gc.DrawRoundedRectangle(0, 1, filled, height - 2, height / 2.0)
        else:
            # indeterminate sweep
            sweep = width / 3.0
            x = (width + sweep) * self.pulse_position / 140.0 - sweep
            gc.SetBrush(gc.CreateLinearGradientBrush(x, 0, x + sweep, 0,
                                                     wx.Colour(0, 229, 255, 0), CYAN))
            gc.DrawRoundedRectangle(max(0, x), 1, min(sweep, width - max(0, x)), height - 2, height / 2.0)


# --------------------------------------------------------------------------
# Installation progress dialog
# --------------------------------------------------------------------------
class InstallProgressDialog(wx.Dialog):
    """Dark neon replacement for wx.ProgressDialog."""

    def __init__(self, parent, title, message, maximum=101):
        style = wx.DEFAULT_DIALOG_STYLE & ~wx.CLOSE_BOX & ~wx.MAXIMIZE_BOX
        super(InstallProgressDialog, self).__init__(parent, wx.ID_ANY, title, style=style)
        self.SetBackgroundColour(CARD)
        self.maximum = maximum
        self.cancelled = False

        panel = Card(self, accent=CYAN)
        panel.SetBackgroundColour(CARD)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.title_label = wx.StaticText(panel, wx.ID_ANY, title.upper())
        self.title_label.SetFont(FONTS["title"] or self.GetFont())
        self.title_label.SetForegroundColour(CYAN)
        sizer.Add(self.title_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 18)

        self.status_label = wx.StaticText(panel, wx.ID_ANY, message)
        self.status_label.SetFont(FONTS["body"] or self.GetFont())
        self.status_label.SetForegroundColour(TEXT)
        sizer.Add(self.status_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 18)

        self.progress = NeonProgressBar(panel)
        sizer.Add(self.progress, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 18)

        button_sizer = wx.BoxSizer(wx.HORIZONTAL)
        button_sizer.AddStretchSpacer(1)
        self.cancel_button = NeonButton(panel, label="Cancel", accent=MAGENTA, min_size=(110, 36),
                                        background=CARD)
        button_sizer.Add(self.cancel_button, 0, wx.ALL, 18)
        sizer.Add(button_sizer, 0, wx.EXPAND)

        panel.SetSizer(sizer)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(outer)
        self.SetClientSize((520, 210))

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
