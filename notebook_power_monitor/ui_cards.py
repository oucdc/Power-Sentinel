"""Dashboard cards.  Every card distinguishes a real reading from unavailable."""

from __future__ import annotations

import math
import tkinter as tk
from collections.abc import Callable, Sequence

from .models import BatteryInfo, CpuInfo, GpuInfo, Snapshot, SourceStatus
from .ui_theme import (
    AMBER,
    AMBER_DIM,
    BG,
    BORDER_SOFT,
    CARD,
    CARD_ALT,
    CYAN,
    CYAN_DIM,
    DIM,
    GREEN,
    GREEN_DIM,
    MUTED,
    PURPLE,
    PURPLE_DIM,
    RED,
    RED_DIM,
    TEXT,
    TEXT_SOFT,
    BatteryBar,
    Card,
    FlatButton,
    MiniMeter,
    Sparkline,
    StatePill,
    Theme,
    rounded_rect,
)
from .util import (
    clamp,
    fmt_clock,
    fmt_pct,
    fmt_power,
    fmt_runtime,
    short_name,
)

TONE_BG = {
    "cyan": CYAN_DIM,
    "green": GREEN_DIM,
    "amber": AMBER_DIM,
    "red": RED_DIM,
    "purple": PURPLE_DIM,
    "muted": CARD_ALT,
}
TONE_FG = {
    "cyan": CYAN,
    "green": GREEN,
    "amber": AMBER,
    "red": RED,
    "purple": PURPLE,
    "muted": MUTED,
}
TONE_BORDER = {
    "cyan": "#205069",
    "green": "#1F4A3A",
    "amber": "#4E3B20",
    "red": "#512532",
    "purple": "#3A305C",
    "muted": BORDER_SOFT,
}


class Badge(tk.Label):
    def __init__(
        self,
        parent: tk.Widget,
        theme: Theme,
        text: str,
        tone: str = "muted",
        font_px: float = 8,
    ) -> None:
        self.theme = theme
        self._tone = tone
        self._font_px = font_px
        super().__init__(
            parent,
            text=text,
            bg=TONE_BG.get(tone, CARD_ALT),
            fg=TONE_FG.get(tone, MUTED),
            font=theme.font(font_px, weight="normal"),
            padx=theme.s(7),
            pady=theme.s(2),
            bd=0,
            highlightthickness=theme.s(1),
            highlightbackground=TONE_BORDER.get(tone, BORDER_SOFT),
        )
        self._font = theme.font(font_px, weight="normal")

    def set(self, text: str | None = None, tone: str | None = None) -> None:
        if text is not None:
            self.configure(text=text)
        if tone is not None:
            self._tone = tone
        try:
            self.configure(
                bg=TONE_BG.get(self._tone, CARD_ALT),
                fg=TONE_FG.get(self._tone, MUTED),
                highlightbackground=TONE_BORDER.get(self._tone, BORDER_SOFT),
            )
        except tk.TclError:
            pass


def source_state(status: SourceStatus) -> str:
    return status.state if status.state in ("ok", "warn", "error", "off") else "off"


class HeaderBar(tk.Frame):
    def __init__(
        self,
        parent: tk.Widget,
        theme: Theme,
        on_sources: Callable,
        on_floating: Callable,
    ) -> None:
        super().__init__(parent, bg=BG, height=theme.s(54))
        self.theme = theme
        self.pack_propagate(False)
        self.grid_propagate(False)
        self._floating_visible = False

        logo = tk.Canvas(
            self,
            width=theme.s(36),
            height=theme.s(36),
            bg=BG,
            highlightthickness=0,
            bd=0,
        )
        logo.pack(side="left", pady=(0, theme.s(2)))
        rounded_rect(
            logo,
            1,
            1,
            theme.s(35),
            theme.s(35),
            theme.s(10),
            fill="#0E2634",
            outline="#1E4A5D",
            width=theme.s(1),
        )
        logo.create_polygon(
            theme.s(21),
            theme.s(5),
            theme.s(11),
            theme.s(20),
            theme.s(17),
            theme.s(20),
            theme.s(14),
            theme.s(31),
            theme.s(26),
            theme.s(15),
            theme.s(19),
            theme.s(15),
            fill=CYAN,
            outline="",
        )

        text_frame = tk.Frame(self, bg=BG)
        text_frame.pack(side="left", padx=(theme.s(10), 0))
        title_row = tk.Frame(text_frame, bg=BG)
        title_row.pack(anchor="w")
        tk.Label(
            title_row,
            text="电量哨兵",
            bg=BG,
            fg=TEXT,
            font=theme.font(18, weight="bold"),
            bd=0,
        ).pack(side="left")
        self.live_label = tk.Label(
            title_row,
            text="● LIVE",
            bg=BG,
            fg=GREEN,
            font=theme.font(8, weight="bold", family=theme.mono_family),
            bd=0,
        )
        self.live_label.pack(side="left", padx=(theme.s(9), 0), pady=(theme.s(2), 0))
        tk.Label(
            text_frame,
            text="NOTEBOOK POWER MONITOR",
            bg=BG,
            fg=DIM,
            font=theme.font(7.5, weight="normal", family=theme.mono_family),
            bd=0,
        ).pack(anchor="w", pady=(theme.s(1), 0))

        right = tk.Frame(self, bg=BG)
        right.pack(side="right", fill="y")
        buttons = tk.Frame(right, bg=BG)
        buttons.pack(side="right", pady=theme.s(8))
        self.floating_button = FlatButton(
            buttons,
            theme,
            "顶部悬浮条",
            command=on_floating,
            style="primary",
            font_px=9.5,
            pad_x=12,
            pad_y=5,
        )
        self.floating_button.pack(side="right", padx=(theme.s(8), 0))
        self.source_button = FlatButton(
            buttons,
            theme,
            "数据源",
            command=on_sources,
            style="ghost",
            font_px=9.5,
            pad_x=12,
            pad_y=5,
        )
        self.source_button.pack(side="right")

        pills = tk.Frame(right, bg=BG)
        pills.pack(side="right", padx=(0, theme.s(16)), pady=theme.s(11))
        self.pill_rapl = StatePill(pills, theme, "RAPL")
        self.pill_rapl.pack(side="left", padx=(0, theme.s(5)))
        self.pill_nv = StatePill(pills, theme, "NVIDIA")
        self.pill_nv.pack(side="left", padx=(0, theme.s(5)))
        self.pill_bat = StatePill(pills, theme, "电池")
        self.pill_bat.pack(side="left")

    def update_status(self, snap: Snapshot, stale: bool = False) -> None:
        if stale:
            self.live_label.configure(text="● 中断", fg=RED)
        elif snap.demo:
            self.live_label.configure(text="● DEMO", fg=AMBER)
        else:
            self.live_label.configure(text="● LIVE", fg=GREEN)
        self.pill_rapl.set_state(source_state(snap.rapl))
        self.pill_nv.set_state(source_state(snap.nvml))
        self.pill_bat.set_state(source_state(snap.battery_source))
        self.set_floating_visible(self._floating_visible)

    def set_floating_visible(self, visible: bool) -> None:
        self._floating_visible = visible
        try:
            self.floating_button.configure(text="收起悬浮条" if visible else "顶部悬浮条")
        except tk.TclError:
            pass


class TotalCard(Card):
    def __init__(self, parent: tk.Widget, theme: Theme, height: int = 236) -> None:
        super().__init__(parent, theme, height)
        self.theme = theme
        inner = tk.Frame(self, bg=CARD)
        inner.pack(fill="both", expand=True, padx=theme.s(16), pady=theme.s(13))

        title_row = tk.Frame(inner, bg=CARD)
        title_row.pack(fill="x")
        self.title_label = tk.Label(
            title_row,
            text="整机功耗",
            bg=CARD,
            fg=TEXT_SOFT,
            font=theme.font(12, weight="bold"),
        )
        self.title_label.pack(side="left")
        self.mode_badge = Badge(title_row, theme, "仅实测", tone="muted")
        self.mode_badge.pack(side="right")
        tk.Label(
            title_row,
            text="WALL / DC",
            bg=CARD,
            fg=DIM,
            font=theme.font(7, family=theme.mono_family),
        ).pack(side="right", padx=(0, theme.s(7)))

        value_row = tk.Frame(inner, bg=CARD)
        value_row.pack(fill="x", pady=(theme.s(3), theme.s(1)))
        self.value_label = tk.Label(
            value_row,
            text="—",
            bg=CARD,
            fg=TEXT,
            font=theme.num(52),
            bd=0,
            anchor="w",
        )
        self.value_label.pack(side="left")
        self.unit_label = tk.Label(
            value_row,
            text="W",
            bg=CARD,
            fg=MUTED,
            font=theme.num(17, weight="normal"),
            bd=0,
        )
        self.unit_label.pack(side="left", padx=(theme.s(5), 0), pady=(0, theme.s(9)), anchor="s")

        badge_row = tk.Frame(inner, bg=CARD)
        badge_row.pack(fill="x", pady=(0, theme.s(4)))
        self.source_badge = Badge(badge_row, theme, "不可用", tone="muted")
        self.source_badge.pack(side="left")
        self.limit_label = tk.Label(
            badge_row,
            text="",
            bg=CARD,
            fg=DIM,
            font=theme.font(8),
        )
        self.limit_label.pack(side="left", padx=(theme.s(8), 0))

        self.reason_label = tk.Label(
            inner,
            text="正在连接传感器…",
            bg=CARD,
            fg=MUTED,
            font=theme.font(8.8),
            justify="left",
            anchor="nw",
            wraplength=theme.s(345),
            height=3,
        )
        self.reason_label.pack(fill="x", pady=(0, theme.s(3)))

        self.spark = Sparkline(inner, theme, height=40, color=CYAN)
        self.spark.pack(fill="x", side="bottom")

    def update(self, snap: Snapshot, history: Sequence[float | None], stale: bool = False) -> None:
        total = None if stale else snap.total_w
        if total is None:
            self.value_label.configure(text="—", fg=DIM)
            self.unit_label.configure(fg=DIM)
        else:
            self.value_label.configure(text=fmt_power(total, 1), fg=TEXT)
            self.unit_label.configure(fg=MUTED)
        if stale:
            self.title_label.configure(text="整机功耗")
            self.mode_badge.set("数据过期", "red")
            self.source_badge.set("已隐藏", "red")
            self.reason_label.configure(
                text="采集线程暂时无响应，功耗读数已隐藏，不会显示旧值。", fg=RED
            )
            self.spark.set_values([])
            return
        if snap.demo:
            self.title_label.configure(text="整机功耗")
            self.mode_badge.set("演示", "amber")
            self.source_badge.set("演示数据", "amber")
            self.reason_label.configure(text="仅用于界面验收，此数字不是真实传感器读数。", fg=AMBER)
            self.spark.set_values(history)
            return
        if snap.total_w is None:
            self.title_label.configure(text="整机功耗")
            self.mode_badge.set("不可用", "muted")
            self.source_badge.set("无真实来源", "muted")
            self.reason_label.configure(
                text=snap.total_reason or "当前没有可用的整机功耗传感器。", fg=MUTED
            )
            self.spark.set_values([])
            return
        if snap.total_kind == "computed":
            self.title_label.configure(text="双烤功耗合计")
            self.mode_badge.set("计算值", "amber")
            self.source_badge.set("CPU+GPU 合计", "amber")
            self.reason_label.configure(
                text=snap.total_reason
                or "CPU + GPU 双烤合计，不含屏幕、内存、硬盘、风扇和供电损耗。",
                fg=MUTED,
            )
        elif snap.total_kind == "battery":
            self.title_label.configure(text="整机功耗 · 电池")
            self.mode_badge.set("实测 · 电池端", "amber")
            self.source_badge.set("电池放电实测", "amber")
            self.reason_label.configure(
                text="电池放电功率实测，属于系统直流侧读数。",
                fg=MUTED,
            )
        elif snap.total_kind == "meter":
            self.title_label.configure(text="整机功耗")
            self.mode_badge.set("真实传感器", "cyan")
            self.source_badge.set("Windows 实测", "cyan")
            label = snap.total_label or "Windows Power Meter"
            self.reason_label.configure(
                text=f"{label} · Windows EMI 硬件计数器，不是 CPU+GPU 求和",
                fg=MUTED,
            )
        else:
            self.title_label.configure(text="整机功耗")
            self.mode_badge.set("真实传感器", "cyan")
            self.source_badge.set("原生实测", "cyan")
            label = snap.total_label or "总功耗传感器"
            self.reason_label.configure(text=f"{label} · 不是 CPU+GPU 求和估算", fg=MUTED)
        self.limit_label.configure(text="")
        self.spark.set_values(history)


class MetricCard(Card):
    def __init__(
        self,
        parent: tk.Widget,
        theme: Theme,
        title: str,
        kicker: str,
        accent: str,
        height: int = 236,
    ) -> None:
        super().__init__(parent, theme, height)
        self.theme = theme
        self.accent = accent
        inner = tk.Frame(self, bg=CARD)
        inner.pack(fill="both", expand=True, padx=theme.s(15), pady=theme.s(13))

        title_row = tk.Frame(inner, bg=CARD)
        title_row.pack(fill="x")
        tk.Label(
            title_row,
            text=title,
            bg=CARD,
            fg=TEXT_SOFT,
            font=theme.font(12, weight="bold"),
        ).pack(side="left")
        self.status_dot = tk.Canvas(
            title_row,
            width=theme.s(8),
            height=theme.s(8),
            bg=CARD,
            highlightthickness=0,
            bd=0,
        )
        self.status_dot.pack(side="right", padx=(0, theme.s(4)), pady=(theme.s(4), 0))
        self._dot = self.status_dot.create_oval(1, 1, theme.s(7), theme.s(7), fill=DIM, outline="")
        tk.Label(
            title_row,
            text=kicker,
            bg=CARD,
            fg=DIM,
            font=theme.font(8.5),
        ).pack(side="right", padx=(0, theme.s(7)))

        value_row = tk.Frame(inner, bg=CARD)
        value_row.pack(fill="x", pady=(theme.s(3), 0))
        self.value_label = tk.Label(
            value_row,
            text="—",
            bg=CARD,
            fg=TEXT,
            font=theme.num(40),
            bd=0,
            anchor="w",
        )
        self.value_label.pack(side="left")
        self.unit_label = tk.Label(
            value_row,
            text="W",
            bg=CARD,
            fg=MUTED,
            font=theme.num(14, weight="normal"),
            bd=0,
        )
        self.unit_label.pack(side="left", padx=(theme.s(4), 0), pady=(0, theme.s(5)), anchor="s")

        badge_row = tk.Frame(inner, bg=CARD)
        badge_row.pack(fill="x", pady=(0, theme.s(4)))
        self.source_badge = Badge(badge_row, theme, "不可用", tone="muted")
        self.source_badge.pack(side="left")

        stats = tk.Frame(inner, bg=CARD)
        stats.pack(fill="x", pady=(0, theme.s(4)))
        stats.grid_columnconfigure(0, weight=1)
        stats.grid_columnconfigure(1, weight=1)
        self.temp_caption = tk.Label(
            stats, text="温度", bg=CARD, fg=DIM, font=theme.font(8), anchor="w"
        )
        self.temp_caption.grid(row=0, column=0, sticky="w")
        self.util_caption = tk.Label(
            stats, text="占用", bg=CARD, fg=DIM, font=theme.font(8), anchor="w"
        )
        self.util_caption.grid(row=0, column=1, sticky="w")
        self.temp_value = tk.Label(
            stats, text="—", bg=CARD, fg=TEXT_SOFT, font=theme.num(15, weight="bold"), anchor="w"
        )
        self.temp_value.grid(row=1, column=0, sticky="w")
        self.util_value = tk.Label(
            stats, text="—", bg=CARD, fg=TEXT_SOFT, font=theme.num(15, weight="bold"), anchor="w"
        )
        self.util_value.grid(row=1, column=1, sticky="w")

        self.meter = MiniMeter(inner, theme, accent, height=5)
        self.meter.pack(fill="x", pady=(0, theme.s(4)))

        self.reason_label = tk.Label(
            inner,
            text="正在连接传感器…",
            bg=CARD,
            fg=MUTED,
            font=theme.font(8.3),
            justify="left",
            anchor="nw",
            wraplength=theme.s(260),
            height=2,
        )
        self.reason_label.pack(fill="both", expand=True)

    def set_power(self, value: float | None, source: str, source_tone: str, reason: str) -> None:
        if value is None:
            self.value_label.configure(text="—", fg=DIM)
            self.unit_label.configure(fg=DIM)
            self.status_dot.itemconfigure(self._dot, fill=DIM)
        else:
            self.value_label.configure(text=fmt_power(value), fg=TEXT)
            self.unit_label.configure(fg=MUTED)
            self.status_dot.itemconfigure(self._dot, fill=self.accent)
        self.source_badge.set(source, source_tone)
        self.reason_label.configure(text=reason, fg=MUTED)

    def set_stats(self, temp: float | None, util: float | None) -> None:
        if temp is None:
            self.temp_value.configure(text="—", fg=DIM)
        else:
            color = RED if temp >= 90 else (AMBER if temp >= 80 else TEXT_SOFT)
            self.temp_value.configure(text=f"{temp:.0f} °C", fg=color)
        if util is None:
            self.util_value.configure(text="—", fg=DIM)
        else:
            self.util_value.configure(text=fmt_pct(util, 0), fg=TEXT_SOFT)
        self.meter.set(util)

    def set_unavailable(self, reason: str, source: str = "不可用") -> None:
        self.set_power(None, source, "muted", reason)
        self.set_stats(None, None)


class CpuCard(MetricCard):
    def __init__(self, parent: tk.Widget, theme: Theme) -> None:
        super().__init__(parent, theme, "CPU", "处理器封装", GREEN)

    def update(self, cpu: CpuInfo, stale: bool = False) -> None:
        if stale:
            self.set_unavailable("采集线程无响应，CPU 读数已隐藏。", "已隐藏")
            return
        if cpu.power_w is None:
            self.set_power(None, "不可用", "muted", cpu.power_reason or "CPU 功耗不可用")
        else:
            if cpu.power_source.startswith("演示"):
                src, tone = "演示", "amber"
            elif "RAPL" in cpu.power_source:
                src, tone = "Windows RAPL", "green"
            else:
                src, tone = "传感器", "green"
            detail = cpu.power_detail or "CPU 封装功耗实测"
            self.set_power(cpu.power_w, src, tone, f"{detail} · 非估算值")
        self.set_stats(cpu.temp_c, cpu.util_pct)


class GpuCard(MetricCard):
    def __init__(self, parent: tk.Widget, theme: Theme) -> None:
        super().__init__(parent, theme, "GPU", "独立显卡", PURPLE)

    def update(self, gpu: GpuInfo, stale: bool = False) -> None:
        if stale:
            self.set_unavailable("采集线程无响应，GPU 读数已隐藏。", "已隐藏")
            return
        if gpu.power_w is None:
            self.set_unavailable(gpu.reason or "独立显卡数据不可用", "不可用")
        else:
            if gpu.source.startswith("演示"):
                src, tone = "演示", "amber"
            elif "NVML" in gpu.source:
                src, tone = "NVIDIA NVML", "green"
            else:
                src, tone = "传感器", "green"
            self.set_power(gpu.power_w, src, tone, gpu.power_detail or "GPU 功耗实测")
        self.set_stats(gpu.temp_c, gpu.util_pct)


class BatteryCard(Card):
    def __init__(self, parent: tk.Widget, theme: Theme, height: int = 226) -> None:
        super().__init__(parent, theme, height)
        self.theme = theme
        inner = tk.Frame(self, bg=CARD)
        inner.pack(fill="both", expand=True, padx=theme.s(16), pady=theme.s(13))

        title_row = tk.Frame(inner, bg=CARD)
        title_row.pack(fill="x")
        tk.Label(
            title_row,
            text="电池与续航",
            bg=CARD,
            fg=TEXT_SOFT,
            font=theme.font(12, weight="bold"),
        ).pack(side="left")
        self.state_badge = Badge(title_row, theme, "正在读取", tone="muted")
        self.state_badge.pack(side="right")

        body = tk.Frame(inner, bg=CARD)
        body.pack(fill="x", pady=(theme.s(5), theme.s(2)))
        left = tk.Frame(body, bg=CARD)
        left.pack(side="left", anchor="n")
        self.percent_value = tk.Label(
            left,
            text="—",
            bg=CARD,
            fg=TEXT,
            font=theme.num(34),
            anchor="w",
        )
        self.percent_value.pack(anchor="w")
        self.percent_caption = tk.Label(left, text="当前电量", bg=CARD, fg=DIM, font=theme.font(8))
        self.percent_caption.pack(anchor="w")

        right = tk.Frame(body, bg=CARD)
        right.pack(side="right", anchor="ne")
        self.runtime_value = tk.Label(
            right,
            text="—",
            bg=CARD,
            fg=TEXT,
            font=theme.num(20),
            anchor="e",
        )
        self.runtime_value.pack(anchor="e")
        self.runtime_caption = tk.Label(
            right, text="预计剩余", bg=CARD, fg=DIM, font=theme.font(8), anchor="e"
        )
        self.runtime_caption.pack(anchor="e")

        self.bar = BatteryBar(inner, theme, height=11)
        self.bar.pack(fill="x", pady=(theme.s(3), theme.s(6)))

        self.meta_label = tk.Label(
            inner,
            text="正在读取电池数据…",
            bg=CARD,
            fg=TEXT_SOFT,
            font=theme.font(8.6),
            anchor="w",
            justify="left",
        )
        self.meta_label.pack(fill="x")
        self.sub_label = tk.Label(
            inner,
            text="",
            bg=CARD,
            fg=MUTED,
            font=theme.font(8.2),
            anchor="w",
            justify="left",
            wraplength=theme.s(400),
            height=1,
        )
        self.sub_label.pack(fill="x", pady=(theme.s(2), 0))

    def update(self, bat: BatteryInfo, stale: bool = False) -> None:
        if stale:
            self.percent_value.configure(text="—", fg=DIM)
            self.runtime_value.configure(text="—", fg=DIM)
            self.state_badge.set("数据过期", "red")
            self.meta_label.configure(text="采集线程无响应，电池读数已隐藏。", fg=RED)
            self.sub_label.configure(text="")
            self.bar.set(None)
            return
        if not bat.present:
            self.percent_value.configure(text="—", fg=DIM)
            self.runtime_value.configure(text="—", fg=DIM)
            self.state_badge.set("未检测到", "muted")
            self.meta_label.configure(text=bat.reason or "未检测到电池", fg=MUTED)
            self.sub_label.configure(text="电池无法测量插电输入功率。" if bat.ac_online else "")
            self.bar.set(None)
            return
        percent = bat.percent
        if percent is None:
            self.percent_value.configure(text="—", fg=DIM)
        else:
            color = GREEN if percent > 50 else (AMBER if percent > 20 else RED)
            self.percent_value.configure(text=f"{percent:.0f}%", fg=color)
        self.bar.set(percent, bat.charging)
        if bat.direction == "discharging":
            self.state_badge.set("电池供电", "amber")
        elif bat.direction == "charging":
            self.state_badge.set("正在充电", "cyan")
        elif bat.ac_online:
            self.state_badge.set("已接通电源", "green")
        else:
            self.state_badge.set("状态未知", "muted")

        if bat.direction == "discharging":
            self.runtime_value.configure(text=fmt_runtime(bat.runtime_seconds), fg=TEXT)
            self.runtime_caption.configure(
                text="预计剩余 · 按最近放电功率" if bat.runtime_seconds else "预计剩余不可用"
            )
        elif bat.direction == "charging":
            if bat.time_to_full_seconds:
                self.runtime_value.configure(text=fmt_runtime(bat.time_to_full_seconds), fg=TEXT)
                self.runtime_caption.configure(text="预计充满 · 按当前充电功率")
            else:
                self.runtime_value.configure(text="—", fg=DIM)
                self.runtime_caption.configure(text="预计充满")
        elif bat.ac_online:
            self.runtime_value.configure(text="已接通", fg=GREEN)
            self.runtime_caption.configure(text="电池未放电")
        else:
            self.runtime_value.configure(text="—", fg=DIM)
            self.runtime_caption.configure(text="续航不可用")

        meta_bits = []
        if bat.remaining_wh is not None:
            if bat.full_wh:
                meta_bits.append(f"{bat.remaining_wh:.1f} / {bat.full_wh:.1f} Wh")
            else:
                meta_bits.append(f"{bat.remaining_wh:.1f} Wh")
        if bat.power_w is not None:
            verb = (
                "放电"
                if bat.direction == "discharging"
                else ("充电" if bat.direction == "charging" else "功率")
            )
            meta_bits.append(f"{verb} {bat.power_w:.1f} W")
        if bat.voltage_v:
            meta_bits.append(f"{bat.voltage_v:.1f} V")
        if meta_bits:
            self.meta_label.configure(text="  ·  ".join(meta_bits), fg=TEXT_SOFT)
        else:
            self.meta_label.configure(text=bat.reason or "电池容量/功率不可用", fg=MUTED)
        extra = []
        if bat.health_pct is not None:
            extra.append(f"健康度 {bat.health_pct:.0f}%")
        if bat.cycle_count is not None:
            extra.append(f"{bat.cycle_count} 次循环")
        if bat.power_w is None and bat.direction in ("charging", "discharging"):
            extra.append("驱动未报告功率，续航不使用估算")
        extra.append("WMI 电池" if "WMI" in (bat.source or "") else "ACPI 电池")
        self.sub_label.configure(text="  ·  ".join(extra), fg=MUTED)


class ProcessCard(Card):
    ROWS = 4

    def __init__(self, parent: tk.Widget, theme: Theme, height: int = 226) -> None:
        super().__init__(parent, theme, height)
        self.theme = theme
        inner = tk.Frame(self, bg=CARD)
        inner.pack(fill="both", expand=True, padx=theme.s(16), pady=theme.s(13))

        title_row = tk.Frame(inner, bg=CARD)
        title_row.pack(fill="x")
        tk.Label(
            title_row,
            text="后台进程活动",
            bg=CARD,
            fg=TEXT_SOFT,
            font=theme.font(12, weight="bold"),
        ).pack(side="left")
        self.idle_badge = Badge(title_row, theme, "已排除 Idle", tone="green", font_px=7.5)
        self.idle_badge.pack(side="right")

        summary = tk.Frame(inner, bg=CARD)
        summary.pack(fill="x", pady=(theme.s(3), theme.s(2)))
        self.big_value = tk.Label(
            summary,
            text="—",
            bg=CARD,
            fg=GREEN,
            font=theme.num(27),
            anchor="w",
        )
        self.big_value.pack(side="left")
        self.big_caption = tk.Label(
            summary,
            text="占全机 CPU",
            bg=CARD,
            fg=MUTED,
            font=theme.font(8.3),
        )
        self.big_caption.pack(side="left", padx=(theme.s(6), 0), pady=(0, theme.s(4)), anchor="s")
        self.detail_label = tk.Label(
            summary,
            text="",
            bg=CARD,
            fg=DIM,
            font=theme.font(8.2),
            anchor="e",
        )
        self.detail_label.pack(side="right", anchor="e")

        self.active_bar = ActiveBar(inner, theme, height=9)
        self.active_bar.pack(fill="x", pady=(0, theme.s(5)))

        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x", pady=(0, theme.s(2)))
        tk.Label(
            head,
            text="后台进程",
            bg=CARD,
            fg=DIM,
            font=theme.font(7.8),
        ).pack(side="left")
        tk.Label(
            head,
            text="占全机",
            bg=CARD,
            fg=DIM,
            font=theme.font(7.8),
        ).pack(side="right")

        self.rows: list[tuple[tk.Frame, tk.Label, tk.Label]] = []
        for _ in range(self.ROWS):
            row = tk.Frame(inner, bg=CARD)
            row.pack(fill="x", pady=(0, theme.s(1)))
            dot = tk.Canvas(
                row,
                width=theme.s(6),
                height=theme.s(6),
                bg=CARD,
                highlightthickness=0,
                bd=0,
            )
            dot.pack(side="left", padx=(0, theme.s(6)))
            dot_id = dot.create_oval(0, 0, theme.s(5), theme.s(5), fill=CYAN, outline="")
            name = tk.Label(
                row,
                text="",
                bg=CARD,
                fg=TEXT_SOFT,
                font=theme.font(8.8),
                anchor="w",
            )
            name.pack(side="left")
            pct = tk.Label(
                row,
                text="",
                bg=CARD,
                fg=MUTED,
                font=theme.font(8.8, family=theme.mono_family),
                anchor="e",
            )
            pct.pack(side="right")
            self.rows.append((row, dot, dot_id, name, pct))

        self.note = tk.Label(
            inner,
            text="已排除 System Idle Process；按逻辑线程归一化。",
            bg=CARD,
            fg=DIM,
            font=theme.font(8.0),
            anchor="w",
        )
        self.note.pack(fill="x", pady=(theme.s(2), 0))

    def update(self, snap: Snapshot, stale: bool = False) -> None:
        bg = snap.background
        if stale:
            self.big_value.configure(text="—", fg=DIM)
            self.detail_label.configure(text="")
            self.active_bar.set(None, None, None)
            for _row, dot, dot_id, name, pct in self.rows:
                name.configure(text="")
                pct.configure(text="")
                dot.itemconfigure(dot_id, fill=CARD)
            self.note.configure(text="采集线程无响应，进程读数已隐藏。", fg=RED)
            return
        if bg.background_pct is None:
            self.big_value.configure(text="—", fg=DIM)
        else:
            self.big_value.configure(text=fmt_pct(bg.background_pct, 1), fg=GREEN)
        if bg.active_pct is not None and bg.background_pct is not None:
            self.detail_label.configure(
                text=f"占活动 {fmt_pct(bg.share_of_active_pct, 0)} · 全机活动 {fmt_pct(bg.active_pct, 1)}"
            )
        else:
            self.detail_label.configure(text="")
        self.active_bar.set(bg.active_pct, bg.background_pct, bg.foreground_pid)
        for index, (_row, dot, dot_id, name_lbl, pct_lbl) in enumerate(self.rows):
            if index < len(bg.top):
                item = bg.top[index]
                name_lbl.configure(text=short_name(item.name, 22))
                pct_lbl.configure(text=fmt_pct(item.cpu_pct, 1))
                dot.itemconfigure(dot_id, fill=CYAN)
            else:
                name_lbl.configure(text="")
                pct_lbl.configure(text="")
                dot.itemconfigure(dot_id, fill=CARD)
        fg = short_name(bg.foreground_name, 18) if bg.foreground_name else "无"
        self.note.configure(
            text=f"已排除 System Idle Process 与前台（{fg}）；按逻辑线程归一化。",
            fg=DIM,
        )


class ActiveBar(tk.Canvas):
    def __init__(self, parent: tk.Widget, theme: Theme, height: int = 9):
        super().__init__(
            parent,
            height=theme.s(height),
            bg=CARD,
            highlightthickness=0,
            bd=0,
        )
        self.theme = theme
        self._active: float | None = None
        self._background: float | None = None
        self._foreground_pid: int | None = None
        self.bind("<Configure>", lambda _e: self.redraw())

    def set(
        self,
        active: float | None,
        background: float | None,
        foreground_pid: int | None,
    ) -> None:
        self._active = active
        self._background = background
        self._foreground_pid = foreground_pid
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        w = max(10, self.winfo_width())
        h = max(4, self.winfo_height())
        r = h / 2
        rounded_rect(self, 0, 0, w, h, r, fill="#182337", outline="")
        if self._active is None:
            return
        active = clamp(self._active, 0, 100)
        background = clamp(self._background or 0, 0, active)
        if background > 0:
            rounded_rect(self, 0, 0, max(h, w * background / 100.0), h, r, fill=GREEN)
        fg = max(0.0, active - background)
        if fg > 0:
            x1 = w * background / 100.0
            x2 = max(x1 + 2, w * active / 100.0)
            rounded_rect(self, x1, 0, x2, h, r, fill=AMBER)
        if active > 1:
            self.create_line(
                w * active / 100.0,
                0,
                w * active / 100.0,
                h,
                fill=TEXT,
                width=1,
            )


class HistoryChart(tk.Canvas):
    def __init__(self, parent: tk.Widget, theme: Theme, height: int = 106):
        super().__init__(
            parent,
            height=theme.s(height),
            bg=CARD,
            highlightthickness=0,
            bd=0,
        )
        self.theme = theme
        self.history: list[tuple[float | None, float | None, float | None]] = []
        self.bind("<Configure>", lambda _e: self.redraw())

    def set_history(
        self, history: Sequence[tuple[float | None, float | None, float | None]]
    ) -> None:
        self.history = list(history)[-90:]
        self.redraw()

    def _segments(self, values: list[float | None], xs: list[float], ys: list[float]):
        result = []
        current = []
        for x, y, value in zip(xs, ys, values, strict=False):
            if value is None:
                if len(current) >= 2:
                    result.append(current)
                current = []
            else:
                current.append((x, y))
        if len(current) >= 2:
            result.append(current)
        return result

    def redraw(self) -> None:
        self.delete("all")
        w = max(80, self.winfo_width())
        h = max(40, self.winfo_height())
        left, right, top, bottom = (
            self.theme.s(38),
            self.theme.s(8),
            self.theme.s(8),
            self.theme.s(18),
        )
        plot_w = max(10, w - left - right)
        plot_h = max(10, h - top - bottom)
        self.create_line(left, top, left, top + plot_h, fill=BORDER_SOFT, width=1)
        all_values = [v for row in self.history for v in row if v is not None]
        if not all_values:
            self.create_text(
                left + plot_w / 2,
                top + plot_h / 2,
                text="等待真实传感器数据…",
                fill=DIM,
                font=self.theme.font(8.5),
            )
            return
        raw_max = max(10.0, max(all_values) * 1.10)
        y_max = 10.0
        step = 5.0
        for candidate in (5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
            divisions = int(math.ceil(raw_max / candidate))
            if 2 <= divisions <= 6:
                step = float(candidate)
                y_max = step * divisions
                break
        else:
            step = 1000.0
            y_max = step * max(2, int(math.ceil(raw_max / step)))
        divisions = max(2, int(round(y_max / step)))
        for i in range(divisions + 1):
            y = top + plot_h * i / divisions
            self.create_line(left, y, left + plot_w, y, fill="#162238", width=1)
            value = y_max - step * i
            self.create_text(
                left - self.theme.s(6),
                y,
                text=f"{value:.0f}",
                anchor="e",
                fill=MUTED,
                font=self.theme.font(8.0, family=self.theme.mono_family),
            )
        self.create_text(
            left - self.theme.s(6),
            top - self.theme.s(1),
            text="W",
            anchor="e",
            fill=DIM,
            font=self.theme.font(7, family=self.theme.mono_family),
        )
        n = max(2, len(self.history) - 1)
        xs = [left + plot_w * i / n for i in range(len(self.history))]
        total_vals = [row[0] for row in self.history]
        cpu_vals = [row[1] for row in self.history]
        gpu_vals = [row[2] for row in self.history]

        def ypos(v: float | None) -> float:
            if v is None:
                return top + plot_h
            return top + plot_h - clamp(v / y_max, 0, 1) * plot_h

        ys_total = [ypos(v) for v in total_vals]
        # fill under the total line segment by segment
        for seg in self._segments(total_vals, xs, ys_total):
            poly = list(seg) + [(seg[-1][0], top + plot_h), (seg[0][0], top + plot_h)]
            self.create_polygon(poly, fill="#0E2A39", outline="")
        series = [
            (total_vals, ys_total, CYAN, 2.0),
            (cpu_vals, [ypos(v) for v in cpu_vals], GREEN, 1.45),
            (gpu_vals, [ypos(v) for v in gpu_vals], PURPLE, 1.45),
        ]
        for values, ys, color, width in series:
            for seg in self._segments(values, xs, ys):
                self.create_line(
                    [coord for point in seg for coord in point],
                    fill=color,
                    width=max(1, int(round(width * self.theme.scale))),
                    smooth=True,
                    splinesteps=10,
                )
        for i, value in enumerate(total_vals):
            if value is not None and i == len(total_vals) - 1:
                r = max(2, 2.2 * self.theme.scale)
                self.create_oval(
                    xs[i] - r,
                    ys_total[i] - r,
                    xs[i] + r,
                    ys_total[i] + r,
                    fill=CYAN,
                    outline=CARD,
                )
        for i, label in enumerate(("−90s", "−60s", "−30s", "现在")):
            x = left + plot_w * i / 3
            anchor = "sw" if i == 0 else ("se" if i == 3 else "s")
            self.create_text(
                x,
                h - self.theme.s(3),
                text=label,
                anchor=anchor,
                fill=MUTED,
                font=self.theme.font(8.0, family=self.theme.mono_family),
            )


class ChartCard(Card):
    def __init__(self, parent: tk.Widget, theme: Theme, height: int = 162) -> None:
        super().__init__(parent, theme, height)
        self.theme = theme
        inner = tk.Frame(self, bg=CARD)
        inner.pack(fill="both", expand=True, padx=theme.s(16), pady=(theme.s(11), theme.s(8)))
        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x", pady=(0, theme.s(2)))
        tk.Label(
            head,
            text="功耗趋势",
            bg=CARD,
            fg=TEXT_SOFT,
            font=theme.font(11, weight="bold"),
        ).pack(side="left")
        tk.Label(
            head,
            text="最近 90 秒 · 传感器趋势",
            bg=CARD,
            fg=DIM,
            font=theme.font(8.2),
        ).pack(side="left", padx=(theme.s(8), 0), pady=(theme.s(1), 0))
        legend = tk.Frame(head, bg=CARD)
        legend.pack(side="right")
        for text, color in (("合计", CYAN), ("CPU", GREEN), ("GPU", PURPLE)):
            dot = tk.Canvas(
                legend,
                width=theme.s(7),
                height=theme.s(7),
                bg=CARD,
                highlightthickness=0,
                bd=0,
            )
            dot.pack(side="left", padx=(theme.s(8), theme.s(3)))
            dot.create_oval(1, 1, theme.s(6), theme.s(6), fill=color, outline="")
            tk.Label(
                legend,
                text=text,
                bg=CARD,
                fg=MUTED,
                font=theme.font(7.8),
            ).pack(side="left")
        self.chart = HistoryChart(inner, theme, height=110)
        self.chart.pack(fill="both", expand=True)

    def update(self, history, stale: bool = False) -> None:
        self.chart.set_history(history)


class FooterBar(tk.Frame):
    def __init__(self, parent: tk.Widget, theme: Theme) -> None:
        super().__init__(parent, bg=BG, height=theme.s(22))
        self.theme = theme
        self.pack_propagate(False)
        self.left = tk.Label(
            self,
            text="正在启动数据采集…",
            bg=BG,
            fg=MUTED,
            font=theme.font(8.2),
            anchor="w",
        )
        self.left.pack(side="left")
        self.right = tk.Label(
            self,
            text="",
            bg=BG,
            fg=MUTED,
            font=theme.font(8.2, family=theme.mono_family),
            anchor="e",
        )
        self.right.pack(side="right")

    def update(self, snap: Snapshot, stale: bool = False) -> None:
        if stale:
            self.left.configure(text="采集线程无响应 · 读数已隐藏", fg=RED)
        elif snap.demo:
            self.left.configure(text="演示模式 · 图表/数字均为界面演示，非真实传感器", fg=AMBER)
        else:
            cpu_src = "RAPL" if "RAPL" in snap.cpu.power_source else "不可用"
            nv = "NVML 正常" if snap.nvml.state == "ok" else f"NVIDIA {snap.nvml.summary}"
            bat = snap.battery_source.summary
            self.left.configure(
                text=f"CPU：{cpu_src}  ·  {nv}  ·  电池：{bat}",
                fg=DIM,
            )
        self.right.configure(
            text=f"{snap.refresh_s:.0f}s 刷新  ·  {fmt_clock(snap.timestamp)}  ·  关闭后驻留托盘"
        )
