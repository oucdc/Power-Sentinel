"""Visual language and small reusable Canvas widgets."""

from __future__ import annotations

import math
import tkinter as tk
import tkinter.font as tkfont
from collections.abc import Callable, Sequence

# Palette
BG = "#080D16"
BG_SOFT = "#0B1220"
CARD = "#101827"
CARD_ALT = "#0C1422"
CARD_HOVER = "#142034"
BORDER = "#1D2B42"
BORDER_SOFT = "#17243A"
TEXT = "#F2F7FF"
TEXT_SOFT = "#C8D5E8"
MUTED = "#8393A9"
DIM = "#586A82"
CYAN = "#4DD8FF"
CYAN_DIM = "#173B4D"
GREEN = "#5BE0A0"
GREEN_DIM = "#16352C"
AMBER = "#FFB454"
AMBER_DIM = "#392B18"
RED = "#FF7089"
RED_DIM = "#3A1D28"
PURPLE = "#A78BFA"
PURPLE_DIM = "#2A2342"
BLUE = "#6AA8FF"

STATE_COLORS = {
    "ok": GREEN,
    "warn": AMBER,
    "error": RED,
    "off": DIM,
}


class Theme:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.scale = 1.0
        dpi = float(root.winfo_fpixels("1i"))
        dpi_scale = dpi / 96.0
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        fit_w = max(0.1, (screen_w - 72) / 1180.0)
        fit_h = max(0.1, (screen_h - 132) / 800.0)
        # Fit the base 1180x800 dashboard on screen while respecting DPI.  On a
        # large desktop, upscale slightly so 9-10 px labels stay comfortable.
        self.scale = max(0.76, min(max(dpi_scale, 1.20), fit_w, fit_h))
        families = set(tkfont.families(root))
        self.family = (
            "Microsoft YaHei UI"
            if "Microsoft YaHei UI" in families
            else ("Microsoft YaHei" if "Microsoft YaHei" in families else "Segoe UI")
        )
        self.display_family = (
            "Bahnschrift"
            if "Bahnschrift" in families
            else (
                "Segoe UI Variable Display"
                if "Segoe UI Variable Display" in families
                else "Segoe UI"
            )
        )
        self.mono_family = (
            "Cascadia Mono"
            if "Cascadia Mono" in families
            else ("Consolas" if "Consolas" in families else self.family)
        )
        self._fonts: dict[tuple, tkfont.Font] = {}

    def s(self, px: float) -> int:
        return max(1, int(round(px * self.scale)))

    def font(
        self,
        px: float,
        weight: str = "normal",
        family: str | None = None,
        slant: str = "roman",
    ) -> tkfont.Font:
        size = -max(7, int(round(px * self.scale)))
        key = (size, weight, family or self.family, slant)
        if key not in self._fonts:
            self._fonts[key] = tkfont.Font(
                root=self.root,
                family=key[2],
                size=size,
                weight=weight,
                slant=slant,
            )
        return self._fonts[key]

    def num(self, px: float, weight: str = "bold") -> tkfont.Font:
        return self.font(px, weight=weight, family=self.display_family)

    def set_icon(self, path: str | None) -> None:
        if path:
            try:
                self.root.iconbitmap(default=path)
            except Exception:
                pass


def rounded_rect(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    radius: float,
    fill: str,
    outline: str = "",
    width: float = 1.0,
    tags: str | tuple = "",
) -> int:
    radius = max(0.0, min(radius, (x2 - x1) / 2.0, (y2 - y1) / 2.0))
    points = [
        x1 + radius,
        y1,
        x2 - radius,
        y1,
        x2,
        y1,
        x2,
        y1 + radius,
        x2,
        y2 - radius,
        x2,
        y2,
        x2 - radius,
        y2,
        x1 + radius,
        y2,
        x1,
        y2,
        x1,
        y2 - radius,
        x1,
        y1 + radius,
        x1,
        y1,
    ]
    return canvas.create_polygon(
        points,
        smooth=True,
        splinesteps=18,
        fill=fill,
        outline=outline,
        width=width,
        tags=tags,
    )


class Card(tk.Frame):
    def __init__(self, parent: tk.Widget, theme: Theme, height: int, **kwargs) -> None:
        super().__init__(
            parent,
            bg=CARD,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=theme.s(1),
            bd=0,
            **kwargs,
        )
        self.theme = theme
        self.configure(height=theme.s(height))
        self.pack_propagate(False)
        self.grid_propagate(False)

    def pad(self) -> tuple[int, int]:
        return self.theme.s(16), self.theme.s(14)


class FlatButton(tk.Button):
    def __init__(
        self,
        parent: tk.Widget,
        theme: Theme,
        text: str,
        command: Callable | None = None,
        style: str = "ghost",
        font_px: float = 10,
        pad_x: int = 12,
        pad_y: int = 5,
        **kwargs,
    ) -> None:
        self.theme = theme
        self.style = style
        if style == "primary":
            bg, fg, border, active_fg = CYAN_DIM, CYAN, "#24536A", "#DFF8FF"
        elif style == "danger":
            bg, fg, border, active_fg = RED_DIM, RED, "#582C3A", "#FFE0E6"
        else:
            bg, fg, border, active_fg = BG_SOFT, MUTED, BORDER, TEXT
        self._bg = bg
        self._fg = fg
        self._border = border
        self._active_fg = active_fg
        super().__init__(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=CARD_HOVER,
            activeforeground=active_fg,
            relief="flat",
            bd=0,
            highlightthickness=theme.s(1),
            highlightbackground=border,
            highlightcolor=border,
            font=theme.font(font_px, weight="normal"),
            cursor="hand2",
            padx=theme.s(pad_x),
            pady=theme.s(pad_y),
            takefocus=True,
            **kwargs,
        )
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")

    def _on_enter(self, _event=None) -> None:
        try:
            if str(self["state"]) == "disabled":
                return
            self.configure(bg=CARD_HOVER, highlightbackground=self._fg, fg=self._active_fg)
        except tk.TclError:
            pass

    def _on_leave(self, _event=None) -> None:
        try:
            self.configure(bg=self._bg, highlightbackground=self._border, fg=self._fg)
        except tk.TclError:
            pass


class StatePill(tk.Frame):
    def __init__(self, parent: tk.Widget, theme: Theme, text: str, state: str = "off"):
        super().__init__(
            parent,
            bg=CARD_ALT,
            highlightthickness=theme.s(1),
            highlightbackground=BORDER_SOFT,
            bd=0,
        )
        self.theme = theme
        self.dot = tk.Canvas(
            self,
            width=theme.s(8),
            height=theme.s(8),
            bg=CARD_ALT,
            highlightthickness=0,
            bd=0,
        )
        self.dot.pack(side="left", padx=(theme.s(8), theme.s(5)), pady=theme.s(6))
        self._dot_id = self.dot.create_oval(1, 1, theme.s(7), theme.s(7), fill=DIM, outline="")
        self.label = tk.Label(
            self,
            text=text,
            bg=CARD_ALT,
            fg=MUTED,
            font=theme.font(9, weight="normal"),
            bd=0,
        )
        self.label.pack(side="left", padx=(0, theme.s(9)), pady=theme.s(3))
        self.set_state(state)

    def set_state(self, state: str, text: str | None = None) -> None:
        color = STATE_COLORS.get(state, DIM)
        try:
            self.dot.itemconfigure(self._dot_id, fill=color)
            self.label.configure(fg=TEXT_SOFT if state == "ok" else MUTED)
            if text is not None:
                self.label.configure(text=text)
            self.configure(highlightbackground=color if state in ("warn", "error") else BORDER_SOFT)
        except tk.TclError:
            pass


class BatteryBar(tk.Canvas):
    def __init__(self, parent: tk.Widget, theme: Theme, height: int = 11):
        super().__init__(
            parent,
            height=theme.s(height),
            bg=CARD,
            highlightthickness=0,
            bd=0,
        )
        self.theme = theme
        self._percent: float | None = None
        self._charging = False
        self.bind("<Configure>", lambda _e: self.redraw())

    def set(self, percent: float | None, charging: bool = False) -> None:
        self._percent = percent
        self._charging = charging
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        w = max(10, self.winfo_width())
        h = max(6, self.winfo_height())
        r = h / 2
        rounded_rect(self, 0, 0, w, h, r, fill="#182337", outline="")
        if self._percent is None:
            return
        p = max(0.0, min(100.0, self._percent))
        if self._charging:
            color = CYAN
        elif p <= 20:
            color = RED
        elif p <= 50:
            color = AMBER
        else:
            color = GREEN
        fill_w = (w - 2) * p / 100.0
        if fill_w > 0:
            rounded_rect(self, 1, 1, max(1 + h - 2, fill_w), h - 1, (h - 2) / 2, fill=color)
        # subtle 25/50/75 ticks
        for tick in (25, 50, 75):
            x = 1 + (w - 2) * tick / 100.0
            self.create_line(x, 2, x, h - 2, fill=CARD, width=1)
        if p < 100 and fill_w > 0:
            self.create_oval(
                max(1, fill_w - h + 1),
                1,
                max(1, fill_w),
                h - 1,
                fill=color,
                outline="",
            )


class Sparkline(tk.Canvas):
    def __init__(self, parent: tk.Widget, theme: Theme, height: int = 48, color: str = CYAN):
        super().__init__(
            parent,
            height=theme.s(height),
            bg=CARD,
            highlightthickness=0,
            bd=0,
        )
        self.theme = theme
        self.color = color
        self.values: list[float | None] = []
        self.bind("<Configure>", lambda _e: self.redraw())

    def set_values(self, values: Sequence[float | None]) -> None:
        self.values = list(values)[-60:]
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        w = max(20, self.winfo_width())
        h = max(12, self.winfo_height())
        values = self.values
        if not values:
            return
        vals = [v for v in values if v is not None]
        if not vals:
            self.create_text(
                w / 2,
                h / 2,
                text="等待读数",
                fill=DIM,
                font=self.theme.font(8),
            )
            return
        vmin = min(vals)
        vmax = max(vals)
        span = max(1.0, vmax - vmin)
        # keep the sparkline readable even for a mostly flat signal
        y_low = vmin - span * 0.25
        y_high = vmax + span * 0.20
        if y_high - y_low < 4:
            mid = (y_high + y_low) / 2
            y_low, y_high = mid - 2, mid + 2
        n = max(2, len(values) - 1)
        points: list[tuple[float, float]] = []
        segments: list[list[tuple[float, float]]] = []
        current: list[tuple[float, float]] = []
        for i, value in enumerate(values):
            x = 2 + (w - 4) * i / n
            if value is None:
                if len(current) >= 2:
                    segments.append(current)
                current = []
                continue
            y = h - 4 - (value - y_low) / (y_high - y_low) * (h - 8)
            point = (x, y)
            points.append(point)
            current.append(point)
        if len(current) >= 2:
            segments.append(current)
        for seg in segments:
            poly = list(seg) + [(seg[-1][0], h - 1), (seg[0][0], h - 1)]
            self.create_polygon(poly, fill="#102D3C", outline="")
            self.create_line(
                [c for point in seg for c in point],
                fill=self.color,
                width=max(1.5, 1.7 * self.theme.scale),
                smooth=True,
                splinesteps=12,
            )
        if points:
            lx, ly = points[-1]
            r = max(2.0, 2.4 * self.theme.scale)
            self.create_oval(lx - r, ly - r, lx + r, ly + r, fill=self.color, outline=CARD)


class MiniMeter(tk.Canvas):
    def __init__(self, parent: tk.Widget, theme: Theme, color: str, height: int = 5):
        super().__init__(
            parent,
            height=theme.s(height),
            bg=CARD,
            highlightthickness=0,
            bd=0,
        )
        self.theme = theme
        self.color = color
        self.value: float | None = None
        self.bind("<Configure>", lambda _e: self.redraw())

    def set(self, value: float | None) -> None:
        self.value = value
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        w = max(10, self.winfo_width())
        h = max(3, self.winfo_height())
        r = h / 2
        rounded_rect(self, 0, 0, w, h, r, fill="#182337", outline="")
        if self.value is None:
            return
        p = max(0.0, min(100.0, self.value))
        if p > 0:
            rounded_rect(self, 0, 0, max(h, w * p / 100.0), h, r, fill=self.color)


def format_delta(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}"


def nice_ceiling(value: float) -> int:
    if value <= 5:
        return 5
    if value <= 20:
        return int(math.ceil(value / 5.0) * 5)
    if value <= 100:
        return int(math.ceil(value / 10.0) * 10)
    return int(math.ceil(value / 25.0) * 25)
