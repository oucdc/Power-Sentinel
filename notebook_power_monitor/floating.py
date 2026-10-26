"""Borderless always-on-top floating bar."""

from __future__ import annotations

import ctypes
import tkinter as tk
from typing import Any

from .models import Snapshot
from .ui_theme import (
    AMBER,
    BORDER,
    CARD,
    CARD_ALT,
    CARD_HOVER,
    CYAN,
    DIM,
    GREEN,
    MUTED,
    PURPLE,
    RED,
    TEXT,
    TEXT_SOFT,
    Theme,
)
from .util import fmt_power, fmt_short_runtime

GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020


class FloatingBar:
    BASE_W = 816
    BASE_H = 78

    def __init__(self, app: Any, root: tk.Tk, theme: Theme) -> None:
        self.app = app
        self.root = root
        self.theme = theme
        self.visible = False
        self._drag: tuple[int, int] | None = None
        self._built = False

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.title("电量哨兵 · 悬浮条")
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-alpha", 0.985)
        except tk.TclError:
            pass
        w = theme.s(self.BASE_W)
        h = theme.s(self.BASE_H)
        self.win.geometry(f"{w}x{h}")
        self.win.configure(bg=CARD)

        self.outer = tk.Frame(
            self.win,
            bg=CARD,
            highlightthickness=theme.s(1),
            highlightbackground=BORDER,
            bd=0,
        )
        self.outer.pack(fill="both", expand=True)
        accent = tk.Frame(self.outer, bg=CYAN, width=theme.s(3))
        accent.pack(side="left", fill="y")

        brand = tk.Frame(self.outer, bg=CARD, width=theme.s(150))
        brand.pack(side="left", fill="y", padx=(theme.s(11), 0))
        brand.pack_propagate(False)
        title = tk.Label(
            brand,
            text="电量哨兵",
            bg=CARD,
            fg=TEXT,
            font=theme.font(11.2, weight="bold"),
            anchor="w",
        )
        title.pack(anchor="w", pady=(theme.s(10), 0))
        sub = tk.Label(
            brand,
            text="TOP MONITOR  ·  置顶",
            bg=CARD,
            fg=DIM,
            font=theme.font(7.0, family=theme.mono_family),
            anchor="w",
        )
        sub.pack(anchor="w", pady=(0, 0))
        status = tk.Label(
            brand,
            text="● 拖动移动 · 双击主界面",
            bg=CARD,
            fg=MUTED,
            font=theme.font(7.1),
            anchor="w",
        )
        status.pack(anchor="w", pady=(theme.s(3), 0))

        sep1 = tk.Frame(self.outer, bg=BORDER, width=theme.s(1))
        sep1.pack(side="left", fill="y", pady=theme.s(12), padx=(0, theme.s(4)))

        metrics = tk.Frame(self.outer, bg=CARD)
        metrics.pack(side="left", fill="both", expand=True, padx=(theme.s(3), 0))
        for col in range(5):
            metrics.grid_columnconfigure(col, weight=1, uniform="metric")
        self.metric_labels = []
        for col, (caption, color) in enumerate(
            (
                ("整机", CYAN),
                ("CPU", GREEN),
                ("GPU", PURPLE),
                ("电量", GREEN),
                ("续航", AMBER),
            )
        ):
            frame = tk.Frame(metrics, bg=CARD)
            frame.grid(row=0, column=col, sticky="nsew", pady=theme.s(11))
            cap = tk.Label(
                frame,
                text=caption,
                bg=CARD,
                fg=MUTED,
                font=theme.font(7.8),
                anchor="w",
            )
            cap.pack(anchor="w")
            value = tk.Label(
                frame,
                text="—",
                bg=CARD,
                fg=color,
                font=theme.num(14.5),
                anchor="w",
            )
            value.pack(anchor="w", pady=(theme.s(1), 0))
            self.metric_labels.append((cap, value, color))

        controls = tk.Frame(self.outer, bg=CARD, width=theme.s(54))
        controls.pack(side="right", fill="y")
        controls.pack_propagate(False)
        close = tk.Button(
            controls,
            text="×",
            command=self.hide,
            bg=CARD,
            fg=MUTED,
            activebackground=RED,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=theme.font(13, weight="normal"),
            cursor="hand2",
            padx=theme.s(6),
            pady=0,
            takefocus=False,
        )
        close.place(x=theme.s(26), y=theme.s(5), width=theme.s(22), height=theme.s(22))
        more = tk.Button(
            controls,
            text="⋯",
            command=self._popup_menu,
            bg=CARD,
            fg=MUTED,
            activebackground=CARD_ALT,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=theme.font(10, weight="bold"),
            cursor="hand2",
            padx=0,
            pady=0,
            takefocus=False,
        )
        more.place(x=theme.s(26), y=theme.s(31), width=theme.s(22), height=theme.s(22))
        self._controls = (close, more)

        self.menu = tk.Menu(
            self.win,
            tearoff=0,
            bg=CARD_ALT,
            fg=TEXT_SOFT,
            activebackground=CARD_HOVER,
            activeforeground=TEXT,
            bd=0,
            font=theme.font(9),
        )
        self.menu.add_command(label="显示主窗口", command=self.app.show_main)
        self.menu.add_command(label="数据源与诊断", command=self.app.show_sources)
        self.menu.add_separator()
        self.menu.add_command(label="隐藏悬浮条", command=self.hide)
        self.menu.add_command(label="退出电量哨兵", command=self.app.quit_app)

        self._bind_drag(self.outer)
        for child in self._walk(self.outer):
            if isinstance(child, tk.Button):
                continue
            child.bind("<Button-3>", self._popup_menu, add="+")

        self.win.update_idletasks()
        self._apply_native_style()

    def _walk(self, widget):
        for child in widget.winfo_children():
            yield child
            yield from self._walk(child)

    def _apply_native_style(self) -> None:
        try:
            hwnd = int(self.win.winfo_id())
            parent = ctypes.windll.user32.GetParent(hwnd)
            target = parent or hwnd
            user32 = ctypes.windll.user32
            get_long = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_long = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            get_long.restype = ctypes.c_ssize_t
            get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
            set_long.restype = ctypes.c_ssize_t
            set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            style = int(get_long(target, GWL_EXSTYLE))
            style = (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            set_long(target, GWL_EXSTYLE, style)
            user32.SetWindowPos(
                target,
                0,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
            )
            w = self.win.winfo_width()
            h = self.win.winfo_height()
            radius = self.theme.s(15)
            region = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, radius, radius)
            if region:
                ctypes.windll.user32.SetWindowRgn(target, region, True)
        except Exception:
            pass

    def _bind_drag(self, widget: tk.Widget) -> None:
        if not isinstance(widget, tk.Button):
            widget.bind("<ButtonPress-1>", self._start_drag, add="+")
            widget.bind("<B1-Motion>", self._drag_move, add="+")
            widget.bind("<ButtonRelease-1>", self._end_drag, add="+")
            widget.bind("<Double-Button-1>", lambda _e: self.app.show_main(), add="+")
        for child in widget.winfo_children():
            self._bind_drag(child)

    def _start_drag(self, event) -> None:
        try:
            self._drag = (event.x_root - self.win.winfo_x(), event.y_root - self.win.winfo_y())
        except tk.TclError:
            self._drag = None

    def _drag_move(self, event) -> None:
        if not self._drag:
            return
        x = event.x_root - self._drag[0]
        y = event.y_root - self._drag[1]
        self.win.geometry(f"+{x}+{y}")

    def _end_drag(self, _event) -> None:
        if not self._drag:
            return
        self._drag = None
        self._save_position()

    def _save_position(self) -> None:
        try:
            x, y = self.win.winfo_x(), self.win.winfo_y()
            self.app.config.set("floating_x", x)
            self.app.config.set("floating_y", y)
            self.app.config.save()
        except Exception:
            pass

    def _default_position(self) -> tuple[int, int]:
        sw = self.win.winfo_screenwidth()
        w = self.theme.s(self.BASE_W)
        x = max(0, (sw - w) // 2)
        y = self.theme.s(18)
        return x, y

    def _clamp_position(self, x: int, y: int) -> tuple[int, int]:
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        w = self.theme.s(self.BASE_W)
        h = self.theme.s(self.BASE_H)
        x = max(0, min(x, sw - w))
        y = max(0, min(y, sh - h - self.theme.s(40)))
        return x, y

    def _popup_menu(self, event=None) -> None:
        if event is not None:
            try:
                self.menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.menu.grab_release()
        else:
            try:
                x = self.win.winfo_x() + self.win.winfo_width() // 2
                y = self.win.winfo_y() + self.win.winfo_height()
                self.menu.tk_popup(x, y)
            finally:
                self.menu.grab_release()

    def show(self) -> None:
        cfg_x = self.app.config.get("floating_x")
        cfg_y = self.app.config.get("floating_y")
        if cfg_x is None or cfg_y is None:
            x, y = self._default_position()
        else:
            try:
                x, y = self._clamp_position(int(cfg_x), int(cfg_y))
            except (TypeError, ValueError):
                x, y = self._default_position()
        self.win.geometry(f"+{x}+{y}")
        self.win.deiconify()
        self.win.attributes("-topmost", True)
        self.win.lift()
        self.visible = True
        self.app.config.set("floating_visible", True)
        self.app.config.save()
        self.app.on_floating_visibility(True)
        self._apply_native_style()

    def hide(self) -> None:
        self.win.withdraw()
        self.visible = False
        self.app.config.set("floating_visible", False)
        self.app.config.save()
        self.app.on_floating_visibility(False)

    def toggle(self) -> None:
        if self.visible:
            self.hide()
        else:
            self.show()

    def destroy(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    def update(self, snap: Snapshot, stale: bool = False) -> None:
        labels = self.metric_labels
        if stale:
            for index, (cap, value, _color) in enumerate(labels):
                cap.configure(
                    text=("总功耗", "CPU", "GPU", "电量", "续航")[index] + " · 中断", fg=RED
                )
                value.configure(text="—", fg=DIM)
            return
        total_caption = "双烤" if snap.total_kind == "computed" else "整机"
        total_text = "—" if snap.total_w is None else f"{fmt_power(snap.total_w, 1)} W"
        labels[0][0].configure(
            text=total_caption + ("" if snap.total_w is not None else " · 不可用"),
            fg=MUTED if snap.total_w is not None else AMBER,
        )
        labels[0][1].configure(text=total_text, fg=CYAN if snap.total_w is not None else DIM)

        cpu_text = "—" if snap.cpu.power_w is None else f"{fmt_power(snap.cpu.power_w, 1)} W"
        labels[1][0].configure(
            text="CPU" + ("" if snap.cpu.power_w is not None else " · 不可用"),
            fg=MUTED if snap.cpu.power_w is not None else AMBER,
        )
        labels[1][1].configure(text=cpu_text, fg=GREEN if snap.cpu.power_w is not None else DIM)

        gpu_available = snap.gpu.power_w is not None
        if gpu_available:
            gpu_caption = "GPU"
            gpu_text = f"{fmt_power(snap.gpu.power_w, 1)} W"
        else:
            reason = snap.gpu.reason or ""
            if "休眠" in reason or "断电" in reason:
                gpu_caption = "GPU · 休眠"
            else:
                gpu_caption = "GPU · 不可用"
            gpu_text = "—"
        labels[2][0].configure(text=gpu_caption, fg=MUTED if gpu_available else AMBER)
        labels[2][1].configure(text=gpu_text, fg=PURPLE if gpu_available else DIM)

        bat = snap.battery
        if bat.percent is not None:
            bat_caption = "电量 · " + (
                "充电中" if bat.charging else ("放电" if bat.discharging else "接通")
            )
            bat_text = f"{bat.percent:.0f}%"
            bat_color = GREEN if bat.percent > 50 else (AMBER if bat.percent > 20 else RED)
        else:
            bat_caption = "电量 · 不可用"
            bat_text = "—"
            bat_color = DIM
        labels[3][0].configure(text=bat_caption, fg=MUTED if bat.percent is not None else AMBER)
        labels[3][1].configure(text=bat_text, fg=bat_color)

        if bat.direction == "discharging" and bat.runtime_seconds is not None:
            runtime_caption = "续航"
            runtime_text = fmt_short_runtime(bat.runtime_seconds)
            runtime_color = TEXT
        elif bat.direction == "charging" and bat.time_to_full_seconds is not None:
            runtime_caption = "充满"
            runtime_text = fmt_short_runtime(bat.time_to_full_seconds)
            runtime_color = CYAN
        elif bat.ac_online:
            runtime_caption = "接通电源"
            runtime_text = "AC"
            runtime_color = GREEN
        else:
            runtime_caption = "续航"
            runtime_text = "—"
            runtime_color = DIM
        labels[4][0].configure(text=runtime_caption, fg=MUTED)
        labels[4][1].configure(text=runtime_text, fg=runtime_color)

        if snap.demo:
            labels[0][0].configure(text="整机 · 演示", fg=AMBER)
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
