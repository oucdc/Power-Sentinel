# 电量哨兵 · Notebook Power Monitor

[English](README.md) | **简体中文**

[![CI](https://github.com/oucdc/Power-Sentinel/actions/workflows/ci.yml/badge.svg)](https://github.com/oucdc/Power-Sentinel/actions/workflows/ci.yml)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-0078D4)](https://www.microsoft.com/windows)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

面向 Windows 游戏本 / 高性能笔记本的实时能耗监控工具：深色中文界面、顶部悬浮条、系统托盘，双击即可运行。

CPU 功耗来自 Windows RAPL，GPU 功耗/温度来自 NVIDIA NVML，电池来自 WMI/ACPI。不插电时总功耗使用电池放电实测；插电时使用 **CPU+GPU 双烤合计**，界面明确标注为“计算值”，不冒充墙插整机输入功率。

![仪表盘](docs/images/dashboard.png)

## 功能

- **CPU 功耗**：Windows RAPL `Energy Meter(RAPL_Package0_PKG)`。
- **GPU 功耗、温度、占用率**：NVIDIA NVML，与 NVIDIA App 同源。
- **总功耗**：不插电用电池放电实测；插电用 CPU+GPU 双烤合计，界面标注“计算值”。
- **电池续航**：用当前剩余 Wh 和实测放电功率估算，不是只看百分比。
- **后台进程活动**：排除 `System Idle Process` 和前台进程，每个进程上限 100%，后台总计不超过全机活动 CPU。
- **主窗口 + 置顶悬浮条 + 托盘**。
- **90 秒功耗趋势图**、数据源状态、可复制的诊断信息。
- **混合显卡 / MUX 友好**：独显休眠或断电时 GPU 明确显示不可用，不显示旧值；CPU、电池、进程数据不受影响。
- **单实例**：再次启动会唤醒已有窗口。
- **无网络请求、无遥测、不捆绑第三方监控工具。**

## 下载

从 GitHub Releases 下载最新的 `电量哨兵-vX.Y.Z.zip`，解压后双击 `电量哨兵.exe`。

> 必须保留同目录下的 `_internal` 文件夹，不要只复制 EXE。

## 从源码运行

要求：Windows 10/11、64 位 Python 3.10+；GPU 数据需要 NVIDIA 驱动。克隆或下载仓库后，在仓库根目录运行：

```powershell
git clone https://github.com/oucdc/Power-Sentinel.git
cd Power-Sentinel
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m notebook_power_monitor
```

安装后也可以运行：

```powershell
notebook-power-monitor
```

### 构建 Windows 发布版

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\build.ps1
python .\scripts\package_release.py
```

目录版输出到 `dist\电量哨兵\`，发布 ZIP 输出到 `release\`。详见 [docs/releasing.md](docs/releasing.md)。

## 数据来源

| 指标 | 来源 | 读不到时 |
|---|---|---|
| CPU 功耗 | Windows RAPL / PDH 能量计数器 | 显示“不可用”并说明原因 |
| GPU 功耗/温度 | NVIDIA NVML | 独显休眠时整个 GPU 卡片不可用 |
| 总功耗 | 插电：CPU+GPU 双烤合计（计算值）；不插电：电池放电实测 | CPU/GPU 任一功率缺失且无 Power Meter 时显示“不可用” |
| CPU 温度 | 原生接口无可靠来源 | `—` |
| GPU 温度 | NVIDIA NVML | `—` |
| 电池 | WMI `root\wmi:BatteryStatus` + ACPI 电池信息 | 只显示百分比，不伪造功率 |
| 后台 CPU | `GetSystemTimes` / `GetProcessTimes` | 不可用时显示占位，不编造数值 |

### 总功耗怎么算？

**不插电**：使用电池放电实测（直流侧），保留原功能。

**插电**：显示 `CPU 功耗 + GPU 功耗`，标题为 **双烤功耗合计**，并标注 **计算值**。这是双烤时的部件合计，不含屏幕、内存、硬盘、风扇、VRM 和供电损耗，因此不是墙插整机输入功率，不能直接和插座功率计对比。

插电时如果 CPU 或 GPU 其中一个功率不可用，会回退到真实的 Windows Power Meter 读数；两者都没有时明确显示不可用。

CPU 温度被刻意留空。Windows 没有可靠的原生封装温度接口，程序不会显示一个看起来合理但可能错误的数值。

### 独显休眠 / MUX 切换

NVML 是 GPU 数据的“存活门控”：NVML 报错、读数为 0、或超过 3.5 秒没有新样本时，GPU 卡片显示不可用。CPU RAPL 与电池 WMI 和显卡状态独立，所以切换 MUX 或独显休眠不会导致 CPU/电池读数消失。

## 隐私

- 无网络请求、遥测或统计。
- 配置和日志位于 `%APPDATA%\NotebookPowerMonitor\`（不可写时自动回退到程序目录）。
- 只有点击“复制诊断”时才会写入剪贴板。
- 提交 Issue 前请自行隐去机器名、用户名和本地路径。

## 项目结构

```text
notebook_power_monitor/   应用包
  assets/                 运行时图标
  battery.py              WMI / ACPI 电池读取
  collector.py            原生数据源融合与续航估算
  gpu.py                  NVML 采样与休眠门控
  processes.py            Win32 进程统计
  rapl.py                 RAPL / Power Meter PDH 计数器
  ui_cards.py             主界面卡片
  floating.py             悬浮条
  dialogs.py              数据源诊断
  main.py                 生命周期、DPI、单实例
docs/                     架构、发布说明、截图
packaging/windows/        manifest 与版本资源
scripts/                  构建、图标、发布、截图脚本
tests/                    单元测试
```

更多说明：[docs/architecture.md](docs/architecture.md)。

## 已知限制

- 仅支持 Windows；界面目前为简体中文。
- 插电总功耗是 CPU+GPU 双烤计算值，不是墙插输入功率；真实交流功率仍需墙插功率计。
- CPU 温度没有可信的原生来源，因此不显示。
- 电池放电功率依赖固件/WMI 支持。
- 本工具显示传感器读数，不是经过校准的实验室功率计。

## 参与贡献

欢迎提交 Issue 和 Pull Request。提交 PR 前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)；参与本项目即表示同意 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

安全漏洞请按 [SECURITY.md](SECURITY.md) 私下报告，不要开公开 Issue。

## 许可

MIT，详见 [LICENSE](LICENSE)。
