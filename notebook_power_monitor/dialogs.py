"""Native data-source diagnostics dialog (no HWiNFO dependency)."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from .models import Snapshot
from .ui_theme import (
    AMBER,
    BG,
    BORDER,
    CARD,
    CARD_ALT,
    CYAN,
    DIM,
    GREEN,
    MUTED,
    TEXT,
    TEXT_SOFT,
    FlatButton,
    Theme,
)
from .util import (
    APP_NAME,
    APP_VERSION,
    app_data_dir,
    fmt_age,
    fmt_clock,
    fmt_pct,
    fmt_power,
    fmt_runtime,
    short_name,
)


def _truncate(text: str, limit: int = 82) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


class SourceDialog:
    def __init__(self, app: Any, root: tk.Tk, theme: Theme, snap: Snapshot):
        self.app = app
        self.root = root
        self.theme = theme
        self.snap = snap
        self.win = tk.Toplevel(root)
        self.win.title("数据源与诊断 · 电量哨兵")
        self.win.configure(bg=BG)
        self.win.transient(root)
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        icon = app.icon_path
        if icon:
            try:
                self.win.iconbitmap(default=str(icon))
            except Exception:
                pass
        width = theme.s(860)
        height = theme.s(620)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        width = min(width, sw - theme.s(40))
        height = min(height, sh - theme.s(80))
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 2 - theme.s(14))
        self.win.geometry(f"{width}x{height}+{x}+{y}")
        self.win.minsize(theme.s(760), theme.s(540))
        self._build()
        self.update_snapshot(snap)
        self.win.after(150, self.win.focus_force)

    # -- construction --------------------------------------------------
    def _build(self) -> None:
        theme = self.theme
        outer = tk.Frame(self.win, bg=BG)
        outer.pack(fill="both", expand=True, padx=theme.s(18), pady=theme.s(14))

        header = tk.Frame(outer, bg=BG)
        header.pack(fill="x")
        title_box = tk.Frame(header, bg=BG)
        title_box.pack(side="left")
        tk.Label(
            title_box,
            text="数据源与诊断",
            bg=BG,
            fg=TEXT,
            font=theme.font(16, weight="bold"),
        ).pack(anchor="w")
        tk.Label(
            title_box,
            text="原生传感器版本：不读取 HWiNFO，只使用 Windows RAPL / NVIDIA NVML / WMI 电池。",
            bg=BG,
            fg=MUTED,
            font=theme.font(8.5),
        ).pack(anchor="w", pady=(theme.s(2), 0))
        close = tk.Button(
            header,
            text="×",
            command=self.close,
            bg=BG,
            fg=MUTED,
            activebackground=CARD,
            activeforeground=TEXT,
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=theme.font(16),
            cursor="hand2",
            takefocus=False,
        )
        close.pack(side="right", padx=(theme.s(4), 0))
        FlatButton(
            header,
            theme,
            "关闭",
            command=self.close,
            style="ghost",
            font_px=9,
            pad_x=14,
            pad_y=4,
        ).pack(side="right")

        total_card = tk.Frame(
            outer,
            bg=CARD,
            highlightthickness=theme.s(1),
            highlightbackground=BORDER,
        )
        total_card.pack(fill="x", pady=(theme.s(12), theme.s(10)))
        total_inner = tk.Frame(total_card, bg=CARD)
        total_inner.pack(fill="x", padx=theme.s(14), pady=theme.s(11))
        row = tk.Frame(total_inner, bg=CARD)
        row.pack(fill="x")
        tk.Label(
            row,
            text="总功耗来源",
            bg=CARD,
            fg=TEXT_SOFT,
            font=theme.font(10.5, weight="bold"),
        ).pack(side="left")
        self.total_badge = tk.Label(
            row,
            text="不可用",
            bg=CARD_ALT,
            fg=MUTED,
            font=theme.font(8),
            padx=theme.s(7),
            pady=theme.s(2),
            bd=0,
        )
        self.total_badge.pack(side="right")
        value_row = tk.Frame(total_inner, bg=CARD)
        value_row.pack(fill="x", pady=(theme.s(4), 0))
        self.total_value = tk.Label(
            value_row,
            text="—",
            bg=CARD,
            fg=TEXT,
            font=theme.num(26),
            anchor="w",
        )
        self.total_value.pack(side="left")
        self.total_unit = tk.Label(
            value_row,
            text="W",
            bg=CARD,
            fg=MUTED,
            font=theme.num(12, weight="normal"),
            anchor="w",
        )
        self.total_unit.pack(side="left", padx=(theme.s(4), 0), pady=(0, theme.s(3)), anchor="s")
        self.total_source = tk.Label(
            value_row,
            text="",
            bg=CARD,
            fg=CYAN,
            font=theme.font(8.5),
            anchor="w",
        )
        self.total_source.pack(side="left", padx=(theme.s(14), 0), pady=(0, theme.s(3)), anchor="s")
        self.total_detail = tk.Label(
            total_inner,
            text="",
            bg=CARD,
            fg=MUTED,
            font=theme.font(8.4),
            justify="left",
            anchor="w",
            wraplength=theme.s(790),
            height=2,
        )
        self.total_detail.pack(fill="x", pady=(theme.s(4), 0))

        mini_row = tk.Frame(outer, bg=BG)
        mini_row.pack(fill="x", pady=(0, theme.s(10)))
        for i in range(4):
            mini_row.grid_columnconfigure(i, weight=1, uniform="mini")
        self.nv_card, self.nv_title, self.nv_value, self.nv_detail = self._mini_card(
            mini_row, 0, "NVIDIA NVML", CYAN
        )
        self.rapl_card, self.rapl_title, self.rapl_value, self.rapl_detail = self._mini_card(
            mini_row, 1, "Windows RAPL", "#9EB8FF"
        )
        self.bat_card, self.bat_title, self.bat_value, self.bat_detail = self._mini_card(
            mini_row, 2, "ACPI 电池", GREEN
        )
        self.proc_card, self.proc_title, self.proc_value, self.proc_detail = self._mini_card(
            mini_row, 3, "进程采样", AMBER
        )

        diag_card = tk.Frame(
            outer,
            bg=CARD,
            highlightthickness=theme.s(1),
            highlightbackground=BORDER,
        )
        diag_card.pack(fill="both", expand=True)
        diag_head = tk.Frame(diag_card, bg=CARD)
        diag_head.pack(fill="x", padx=theme.s(14), pady=(theme.s(8), theme.s(2)))
        tk.Label(
            diag_head,
            text="诊断信息",
            bg=CARD,
            fg=TEXT_SOFT,
            font=theme.font(9.5, weight="bold"),
        ).pack(side="left")
        FlatButton(
            diag_head,
            theme,
            "复制诊断",
            command=self.copy_diag,
            style="ghost",
            font_px=8,
            pad_x=8,
            pad_y=2,
        ).pack(side="right")
        text_frame = tk.Frame(diag_card, bg=CARD)
        text_frame.pack(fill="both", expand=True, padx=theme.s(12), pady=(0, theme.s(8)))
        self.diag_text = tk.Text(
            text_frame,
            bg=CARD_ALT,
            fg=TEXT_SOFT,
            insertbackground=TEXT,
            selectbackground="#23415A",
            font=theme.font(8, family=theme.mono_family),
            relief="flat",
            bd=0,
            highlightthickness=0,
            wrap="word",
            height=6,
            padx=theme.s(8),
            pady=theme.s(5),
        )
        scroll = ttk.Scrollbar(
            text_frame,
            orient="vertical",
            command=self.diag_text.yview,
            style="Dark.Vertical.TScrollbar",
        )
        try:
            style = ttk.Style(self.win)
            style.theme_use("clam")
            style.configure(
                "Dark.Vertical.TScrollbar",
                background=BORDER,
                troughcolor=CARD_ALT,
                bordercolor=CARD_ALT,
                arrowcolor=MUTED,
                darkcolor=BORDER,
                lightcolor=BORDER,
            )
        except Exception:
            pass
        self.diag_text.configure(yscrollcommand=scroll.set)
        self.diag_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        footer = tk.Frame(outer, bg=BG)
        footer.pack(fill="x", pady=(theme.s(9), 0))
        self.log_label = tk.Label(
            footer,
            text=f"日志：{app_data_dir().name}\\monitor.log",
            bg=BG,
            fg=DIM,
            font=theme.font(7.3, family=theme.mono_family),
            anchor="w",
        )
        self.log_label.pack(side="left")
        FlatButton(
            footer,
            theme,
            "打开日志目录",
            command=self.open_logs,
            style="ghost",
            font_px=8,
            pad_x=8,
            pad_y=2,
        ).pack(side="right")
        tk.Label(
            footer,
            text=f"{APP_NAME} {APP_VERSION}",
            bg=BG,
            fg=DIM,
            font=theme.font(7.5),
        ).pack(side="right", padx=(0, theme.s(10)))

    def _mini_card(self, parent, column, title, accent):
        theme = self.theme
        card = tk.Frame(
            parent,
            bg=CARD,
            highlightthickness=theme.s(1),
            highlightbackground=BORDER,
        )
        card.grid(
            row=0,
            column=column,
            sticky="nsew",
            padx=(0 if column == 0 else theme.s(8), 0),
        )
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill="both", expand=True, padx=theme.s(11), pady=theme.s(9))
        title_lbl = tk.Label(
            inner,
            text=title,
            bg=CARD,
            fg=accent,
            font=theme.font(8.5, weight="bold"),
            anchor="w",
        )
        title_lbl.pack(fill="x")
        value = tk.Label(
            inner,
            text="—",
            bg=CARD,
            fg=TEXT_SOFT,
            font=theme.font(9.5, weight="bold"),
            anchor="w",
        )
        value.pack(fill="x", pady=(theme.s(3), 0))
        detail = tk.Label(
            inner,
            text="",
            bg=CARD,
            fg=MUTED,
            font=theme.font(7.5),
            anchor="w",
            justify="left",
            wraplength=theme.s(210),
            height=2,
        )
        detail.pack(fill="x", pady=(theme.s(1), 0))
        return card, title_lbl, value, detail

    # -- actions -------------------------------------------------------
    def open_logs(self) -> None:
        try:
            os.startfile(str(app_data_dir()))
        except Exception as exc:
            messagebox.showwarning("无法打开目录", str(exc), parent=self.win)

    def build_diag(self) -> str:
        s = self.snap
        total_state = "可用" if s.total_w is not None else "不可用"
        kind_label = {
            "computed": "CPU+GPU 计算值",
            "battery": "电池放电实测",
            "meter": "Power Meter 实测",
        }.get(s.total_kind, "—")
        lines = [
            f"{APP_NAME} {APP_VERSION} · {fmt_clock(s.timestamp)}",
            "数据模式: 原生传感器（已移除 HWiNFO 连接）",
            f"总功耗: {total_state} · 来源={s.total_source or '—'} · 类型={kind_label}",
            f"  详情: {s.total_reason or s.total_label or '—'}",
            f"CPU: {fmt_power(s.cpu.power_w)} W · 来源={s.cpu.power_source or '不可用'}",
            "  CPU 温度: 原生来源不提供",
            f"NVIDIA: {s.nvml.state.upper()} · {s.nvml.summary}",
            f"  详情: {s.nvml.detail or '—'}",
            f"  采样年龄: {fmt_age(s.nvml.extra.get('age'))}",
            f"Windows RAPL: {s.rapl.state.upper()} · {s.rapl.summary}",
            f"  详情: {s.rapl.detail or '—'}",
            f"Windows Power Meter: {s.power_meter.state.upper()} · {s.power_meter.summary}",
            f"  详情: {s.power_meter.detail or '—'}",
            f"电池: {s.battery_source.state.upper()} · {s.battery_source.summary}",
            f"  详情: {s.battery_source.detail or '—'}",
            f"进程: {s.background.active_pct if s.background.active_pct is not None else '—'}% 活动, "
            f"{s.background.background_pct if s.background.background_pct is not None else '—'}% 后台, "
            f"前台={s.background.foreground_name or '无'}, 采样 {s.background.sampled_processes} 个",
            f"日志: {app_data_dir() / 'monitor.log'}",
        ]
        return "\n".join(lines)

    def copy_diag(self) -> None:
        try:
            self.win.clipboard_clear()
            self.win.clipboard_append(self.build_diag())
        except tk.TclError:
            pass

    def close(self) -> None:
        self.app.on_source_dialog_closed(self)
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    # -- refresh -------------------------------------------------------
    def update_snapshot(self, snap: Snapshot) -> None:
        self.snap = snap
        s = snap
        if s.total_w is None:
            self.total_value.configure(text="—", fg=DIM)
            self.total_unit.configure(fg=DIM)
            self.total_source.configure(text="无可用功耗来源", fg=AMBER)
            self.total_badge.configure(text="不可用", fg=AMBER, bg="#392B18")
            self.total_detail.configure(
                text=s.total_reason or "当前没有可用的功耗来源。",
                fg=MUTED,
            )
        else:
            self.total_value.configure(text=f"{fmt_power(s.total_w)}", fg=TEXT)
            self.total_unit.configure(fg=MUTED)
            if s.total_kind == "computed":
                self.total_source.configure(text="CPU+GPU 双烤合计", fg=AMBER)
                self.total_badge.configure(text="计算值", fg=AMBER, bg="#392B18")
                self.total_detail.configure(
                    text=s.total_reason or "CPU + GPU 合计，不含屏幕、内存、硬盘、风扇和供电损耗。",
                    fg=MUTED,
                )
            else:
                self.total_source.configure(text=s.total_source or "原生实测", fg=CYAN)
                self.total_badge.configure(text="实测", fg=GREEN, bg="#16352C")
                self.total_detail.configure(
                    text=(
                        "电池放电实测 · 电池端直流功率"
                        if s.total_kind == "battery"
                        else "Windows Power Meter 硬件计数器 · 非 CPU+GPU 求和"
                    ),
                    fg=MUTED,
                )

        nv = s.nvml
        self.nv_title.configure(fg=GREEN if nv.state == "ok" else AMBER)
        nv_name = (
            (nv.extra.get("name") or nv.summary).replace("NVIDIA ", "").replace("GeForce ", "")
        )
        self.nv_value.configure(text=short_name(nv_name, 28) or "—")
        if s.gpu.power_w is not None:
            self.nv_detail.configure(
                text=f"GPU {fmt_power(s.gpu.power_w)} W · 来源 NVIDIA NVML",
                fg=MUTED,
            )
        else:
            self.nv_detail.configure(text=s.gpu.reason or nv.detail or "不可用", fg=AMBER)

        rapl = s.rapl
        self.rapl_title.configure(fg=GREEN if rapl.state == "ok" else AMBER)
        self.rapl_value.configure(
            text=f"{fmt_power(s.cpu.power_w)} W" if s.cpu.power_w is not None else "—"
        )
        self.rapl_detail.configure(
            text=(
                "CPU 封装功耗 · Windows 硬件能量计数器"
                if s.cpu.power_w is not None
                else rapl.detail or "RAPL 不可用"
            ),
            fg=MUTED,
        )

        bat = s.battery
        self.bat_title.configure(fg=GREEN if s.battery_source.state == "ok" else AMBER)
        if bat.percent is not None:
            self.bat_value.configure(
                text=f"{bat.percent:.0f}% · "
                + (f"{bat.remaining_wh:.1f} Wh" if bat.remaining_wh else "容量未知")
            )
        else:
            self.bat_value.configure(text="—")
        bits = []
        if bat.power_w is not None:
            bits.append(
                f"{'放电' if bat.discharging else ('充电' if bat.charging else '功率')} {bat.power_w:.1f} W"
            )
        if bat.runtime_seconds:
            bits.append("续航 " + fmt_runtime(bat.runtime_seconds))
        if not bits:
            bits.append(bat.reason or s.battery_source.detail or "无功率数据")
        self.bat_detail.configure(text=" · ".join(bits), fg=MUTED)

        bg = s.background
        self.proc_title.configure(fg=GREEN if bg.active_pct is not None else AMBER)
        if bg.active_pct is not None:
            self.proc_value.configure(
                text=f"{fmt_pct(bg.active_pct, 1)} 活动 · {fmt_pct(bg.background_pct, 1)} 后台"
            )
        else:
            self.proc_value.configure(text="正在采样")
        self.proc_detail.configure(
            text=f"前台 {short_name(bg.foreground_name, 18) or '无'} · 已排除 Idle · {bg.sampled_processes} 进程",
            fg=MUTED,
        )

        try:
            self.diag_text.configure(state="normal")
            self.diag_text.delete("1.0", "end")
            self.diag_text.insert("1.0", self.build_diag())
            self.diag_text.configure(state="disabled")
        except tk.TclError:
            pass

    def focus(self) -> None:
        try:
            self.win.deiconify()
            self.win.lift()
            self.win.focus_force()
        except tk.TclError:
            pass
