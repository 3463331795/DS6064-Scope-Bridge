# AI 使用 RIGOL DS6064 示波器链路部署指南（USB 版）

> 目标：把 **RIGOL DS6064 示波器** 通过 **USB-TMC** 接入电脑，用 **Python + PyVISA + SCPI** 封装成安全工具层，再交给 **Codex** 部署为一个可复用的 **Agent Skill**。  
> 最终效果：你可以用自然语言要求 AI 完成“连接示波器、读取测量值、采集波形、保存 CSV、画图、分析 PWM/CAN/电源纹波”等任务。

---

## 0. 当前已确认的信息

你已经通过 RIGOL Ultra Sigma 识别到 DS6064，资源地址为：

```text
USB0::0x1AB1::0x04B0::DS6C134300118::INSTR
```

Ultra Sigma 底部也已经能返回：

```text
RIGOL TECHNOLOGIES,DS6064,DS6C134300118,...
```

这说明：

```text
PC → USB-TMC → RIGOL DS6064
```

这条底层通信链路已经打通。

后续所有 Python / Codex / Skill 都应该优先使用这个 USB VISA 资源地址。

---

## 1. 最终链路架构

USB 版推荐架构如下：

```text
用户自然语言
   ↓
Codex / AI Agent
   ↓ 调用 skill 中定义的工具说明和脚本
rigol-ds6064-scope skill
   ↓
Python 工具层：scope_cli.py / rigol_ds6064.py
   ↓
PyVISA / VISA
   ↓
USB-TMC
   ↓
RIGOL DS6064 示波器
   ↓
测量值 / 波形数据 / CSV / 图片
   ↓
AI 分析并给出结论
```

核心原则：

1. **AI 不直接裸发任意 SCPI 命令**。
2. **AI 只能调用封装好的安全函数**。
3. **默认使用 USB-TMC，不使用 LAN**。
4. **所有危险操作都要加入保护**，例如恢复出厂设置、删除存储、改变关键触发配置等。
5. **先实现本地 Python 控制成功，再封装为 skill**。

---

## 2. 硬件和软件准备

### 2.1 硬件

需要准备：

- RIGOL DS6064 示波器
- 一台 Windows / Linux / macOS 电脑
- USB-A 转 USB-B 数据线，也就是常见打印机线

注意：

- 要连接示波器后面板的 **USB DEVICE** 口。
- 不要连接前面板 USB 口。
- 前面板 USB 口通常是给 U 盘使用的 **USB HOST**，不是给电脑远程控制用的。

---

### 2.2 软件

电脑上建议安装：

- Python 3.10+
- Git
- Codex CLI 或 Codex 开发环境
- RIGOL Ultra Sigma，用于首次验证 USB-TMC 连接
- PyVISA
- numpy
- matplotlib
- pandas
- python-dotenv

Windows 用户建议优先安装：

- RIGOL Ultra Sigma
- 或 NI-VISA Runtime

Python 依赖：

```bash
pip install pyvisa numpy matplotlib pandas pydantic python-dotenv
```

说明：

- 如果使用 Windows + Ultra Sigma / NI-VISA，通常不强制需要 `pyvisa-py`。
- 如果使用 Linux/macOS 或想使用纯 Python 后端，可以再安装 `pyvisa-py`。
- 但 USB-TMC 在 Windows 上最推荐先用系统 VISA 后端，稳定性更好。

可选安装：

```bash
pip install pyvisa-py
```

---

## 3. 示波器 USB 设置

在示波器上确认：

```text
UTIL → IO Setting → USB Device
```

选择：

```text
Computer
```

如果这里不是 `Computer`，电脑可能无法把它识别成 USB-TMC 测试测量设备。

---

## 4. 用 Ultra Sigma 验证 USB-TMC

在写 Python 代码前，先用 RIGOL Ultra Sigma 确认连接。

步骤：

1. 打开 RIGOL Ultra Sigma。
2. 点击 `USB-TMC`。
3. 搜索或刷新设备。
4. 找到 DS6064。
5. 选中设备后发送：

```text
*IDN?
```

正常返回类似：

```text
RIGOL TECHNOLOGIES,DS6064,DS6C134300118,00.01.03.SP01
```

你当前识别到的资源名：

```text
USB0::0x1AB1::0x04B0::DS6C134300118::INSTR
```

后续 `.env` 和 Python 代码中就使用这个资源名。

---

## 5. 创建项目目录

建议创建一个独立项目：

```bash
mkdir ai-rigol-ds6064-scope
cd ai-rigol-ds6064-scope
```

项目结构建议如下：

```text
ai-rigol-ds6064-scope/
├── README.md
├── requirements.txt
├── .env.example
├── .env
├── src/
│   ├── rigol_ds6064.py
│   ├── scope_cli.py
│   ├── waveform_analysis.py
│   └── safety.py
├── outputs/
│   ├── csv/
│   ├── images/
│   └── logs/
├── tests/
│   └── test_offline_parser.py
└── .agents/
    └── skills/
        └── rigol-ds6064-scope/
            ├── SKILL.md
            ├── scripts/
            │   └── scope_cli.py
            └── references/
                └── DS6000_SCPI_NOTES.md
```

说明：

- `src/`：真实 Python 控制代码。
- `outputs/`：保存波形 CSV、图片、日志。
- `.agents/skills/rigol-ds6064-scope/`：最终给 Codex 使用的 skill。
- `SKILL.md`：skill 的核心说明文件。

---

## 6. 创建 Python 虚拟环境

Windows PowerShell：

```powershell
python -m venv .venv
.venv\Scripts\activate
```

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

---

## 7. 创建 requirements.txt

新建：

```bash
touch requirements.txt
```

写入：

```txt
pyvisa>=1.14
numpy>=1.26
matplotlib>=3.8
pandas>=2.0
pydantic>=2.0
python-dotenv>=1.0
```

如果你决定用纯 Python VISA 后端，可以额外加入：

```txt
pyvisa-py>=0.7
```

安装依赖：

```bash
pip install -r requirements.txt
```

---

## 8. 创建环境变量文件

新建 `.env.example`：

```bash
touch .env.example
```

写入：

```env
RIGOL_CONNECTION=USB
RIGOL_SCOPE_RESOURCE=USB0::0x1AB1::0x04B0::DS6C134300118::INSTR
RIGOL_SCOPE_TIMEOUT_MS=5000
RIGOL_DEFAULT_CHANNEL=CHANnel1
```

复制为真实配置：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

如果以后更换示波器或换电脑，资源名可能变化，需要重新在 Ultra Sigma 或 PyVISA 中查看资源名。

---

## 9. 最小 Python 连接测试

在项目根目录创建：

```bash
touch test_scope.py
```

写入：

```python
import pyvisa

RESOURCE = "USB0::0x1AB1::0x04B0::DS6C134300118::INSTR"

rm = pyvisa.ResourceManager()

print("当前 VISA 资源：")
print(rm.list_resources())

scope = rm.open_resource(RESOURCE)
scope.timeout = 5000

print("示波器身份信息：")
print(scope.query("*IDN?"))

scope.close()
rm.close()
```

运行：

```bash
python test_scope.py
```

预期输出中应该包含：

```text
RIGOL TECHNOLOGIES,DS6064,DS6C134300118,...
```

如果报设备被占用，请先关闭 Ultra Sigma，再运行 Python。

---

## 10. 编写示波器底层控制模块

创建文件：

```bash
mkdir -p src
touch src/rigol_ds6064.py
```

写入以下代码：

```python
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

import pyvisa
from dotenv import load_dotenv


load_dotenv()


@dataclass
class ScopeConfig:
    resource: str
    timeout_ms: int = 5000

    @classmethod
    def from_env(cls) -> "ScopeConfig":
        resource = os.getenv(
            "RIGOL_SCOPE_RESOURCE",
            "USB0::0x1AB1::0x04B0::DS6C134300118::INSTR",
        )
        timeout_ms = int(os.getenv("RIGOL_SCOPE_TIMEOUT_MS", "5000"))
        return cls(resource=resource, timeout_ms=timeout_ms)


class RigolDS6064:
    """Safe wrapper for RIGOL DS6064 / DS6000 series oscilloscope."""

    def __init__(self, config: Optional[ScopeConfig] = None):
        self.config = config or ScopeConfig.from_env()
        self.rm = None
        self.inst = None

    def connect(self):
        self.rm = pyvisa.ResourceManager()

        resources = self.rm.list_resources()
        if self.config.resource not in resources:
            print("Warning: configured resource not found in list_resources().")
            print("Configured:", self.config.resource)
            print("Detected:", resources)

        self.inst = self.rm.open_resource(self.config.resource)
        self.inst.timeout = self.config.timeout_ms

        # RIGOL 通常使用 \n 作为终止符
        self.inst.write_termination = "\n"
        self.inst.read_termination = "\n"
        return self

    def close(self):
        if self.inst is not None:
            self.inst.close()
            self.inst = None
        if self.rm is not None:
            self.rm.close()
            self.rm = None

    def query(self, command: str) -> str:
        self._ensure_connected()
        return self.inst.query(command).strip()

    def write(self, command: str):
        self._ensure_connected()
        self.inst.write(command)

    def _ensure_connected(self):
        if self.inst is None:
            raise RuntimeError("Scope is not connected. Call connect() first.")

    def identify(self) -> str:
        return self.query("*IDN?")

    def run(self):
        self.write(":RUN")

    def stop(self):
        self.write(":STOP")

    def single(self):
        self.write(":SINGle")

    def autoscale(self):
        self.write(":AUToscale")

    def measure_vpp(self, channel: str = "CHANnel1") -> float:
        return float(self.query(f":MEASure:ITEM? VPP,{channel}"))

    def measure_freq(self, channel: str = "CHANnel1") -> float:
        return float(self.query(f":MEASure:ITEM? FREQuency,{channel}"))

    def measure_period(self, channel: str = "CHANnel1") -> float:
        return float(self.query(f":MEASure:ITEM? PERiod,{channel}"))

    def measure_duty(self, channel: str = "CHANnel1") -> float:
        return float(self.query(f":MEASure:ITEM? PDUTy,{channel}"))

    def set_timebase_scale(self, seconds_per_div: float):
        if seconds_per_div <= 0:
            raise ValueError("seconds_per_div must be positive")
        self.write(f":TIMebase:SCALe {seconds_per_div}")

    def set_channel_scale(self, channel: int, volts_per_div: float):
        if channel not in [1, 2, 3, 4]:
            raise ValueError("channel must be 1, 2, 3, or 4")
        if volts_per_div <= 0:
            raise ValueError("volts_per_div must be positive")
        self.write(f":CHANnel{channel}:SCALe {volts_per_div}")

    def set_trigger_edge(self, channel: int = 1, level: float = 0.0, slope: str = "POSitive"):
        if channel not in [1, 2, 3, 4]:
            raise ValueError("channel must be 1, 2, 3, or 4")
        if slope not in ["POSitive", "NEGative", "RFALl"]:
            raise ValueError("slope must be POSitive, NEGative, or RFALl")
        self.write(":TRIGger:MODE EDGE")
        self.write(f":TRIGger:EDGE:SOURce CHANnel{channel}")
        self.write(f":TRIGger:EDGE:SLOPe {slope}")
        self.write(f":TRIGger:EDGE:LEVel {level}")

    def capture_waveform_ascii(self, channel: str = "CHANnel1", points: int = 1200):
        """Capture waveform using ASCII mode.

        ASCII 模式速度慢，但最容易调试。
        后续稳定后可以改成 BYTE/WORD 二进制模式。
        """
        if channel not in ["CHANnel1", "CHANnel2", "CHANnel3", "CHANnel4"]:
            raise ValueError("invalid channel")
        if points <= 0 or points > 120000:
            raise ValueError("points must be between 1 and 120000")

        self.write(f":WAVeform:SOURce {channel}")
        self.write(":WAVeform:MODE NORMal")
        self.write(":WAVeform:FORMat ASCii")
        self.write(f":WAVeform:POINts {points}")

        raw = self.query(":WAVeform:DATA?")
        values = []
        for item in raw.replace("#", "").replace(",", " ").split():
            try:
                values.append(float(item))
            except ValueError:
                pass
        return values

    def wait_after_single(self, seconds: float = 0.5):
        time.sleep(seconds)
```

---

## 11. 编写波形分析模块

创建：

```bash
touch src/waveform_analysis.py
```

写入：

```python
from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt
import numpy as np


def save_waveform_csv(values: Sequence[float], output_path: str | Path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["index", "voltage_v"])
        for i, value in enumerate(values):
            writer.writerow([i, value])
    return output_path


def plot_waveform(values: Sequence[float], output_path: str | Path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    arr = np.asarray(values, dtype=float)

    plt.figure()
    plt.plot(arr)
    plt.xlabel("Sample Index")
    plt.ylabel("Voltage / V")
    plt.title("Captured Waveform")
    plt.grid(True)
    plt.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close()

    return output_path


def basic_waveform_stats(values: Sequence[float]) -> dict:
    arr = np.asarray(values, dtype=float)
    if arr.size == 0:
        return {"points": 0}

    return {
        "points": int(arr.size),
        "min_v": float(np.min(arr)),
        "max_v": float(np.max(arr)),
        "mean_v": float(np.mean(arr)),
        "std_v": float(np.std(arr)),
        "vpp_v": float(np.max(arr) - np.min(arr)),
    }
```

---

## 12. 编写安全策略模块

创建：

```bash
touch src/safety.py
```

写入：

```python
BLOCKED_SCPI_PATTERNS = [
    "*RST",
    ":STOR",
    ":SAVE",
    ":LOAD",
    ":DISK",
    ":SYSTem:SECure",
]


def assert_safe_scpi(command: str):
    normalized = command.strip().upper()
    for pattern in BLOCKED_SCPI_PATTERNS:
        if pattern.upper() in normalized:
            raise PermissionError(f"Blocked unsafe SCPI command: {command}")
```

建议：

- 默认不开放 `raw_scpi`。
- 如果后续确实需要原始 SCPI 调试，必须加白名单。
- 所有 AI 调用都记录到 `outputs/logs/`。
- 对电机、电源、功率系统进行测试时，AI 只能辅助判断，不能自动闭环改变高风险硬件状态。

---

## 13. 编写命令行工具 scope_cli.py

这个工具是给 Codex / AI 调用的入口。AI 不直接改底层代码，而是执行这些固定命令。

创建：

```bash
touch src/scope_cli.py
```

写入：

```python
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from rigol_ds6064 import RigolDS6064
from waveform_analysis import (
    save_waveform_csv,
    plot_waveform,
    basic_waveform_stats,
)


VALID_CHANNELS = ["CHANnel1", "CHANnel2", "CHANnel3", "CHANnel4"]


def ok(data):
    print(json.dumps({"ok": True, "data": data}, ensure_ascii=False, indent=2))


def fail(message: str, code: int = 1):
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False, indent=2))
    sys.exit(code)


def validate_channel(channel: str) -> str:
    if channel not in VALID_CHANNELS:
        raise ValueError(f"Invalid channel: {channel}. Use one of {VALID_CHANNELS}")
    return channel


def main():
    parser = argparse.ArgumentParser(description="Safe CLI for RIGOL DS6064 oscilloscope over USB-TMC")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")
    sub.add_parser("idn")
    sub.add_parser("run")
    sub.add_parser("stop")
    sub.add_parser("single")
    sub.add_parser("autoscale")

    p_vpp = sub.add_parser("vpp")
    p_vpp.add_argument("--channel", default="CHANnel1")

    p_freq = sub.add_parser("freq")
    p_freq.add_argument("--channel", default="CHANnel1")

    p_period = sub.add_parser("period")
    p_period.add_argument("--channel", default="CHANnel1")

    p_duty = sub.add_parser("duty")
    p_duty.add_argument("--channel", default="CHANnel1")

    p_summary = sub.add_parser("summary")
    p_summary.add_argument("--channel", default="CHANnel1")

    p_capture = sub.add_parser("capture")
    p_capture.add_argument("--channel", default="CHANnel1")
    p_capture.add_argument("--points", type=int, default=1200)

    args = parser.parse_args()

    try:
        if args.cmd == "list":
            import pyvisa
            rm = pyvisa.ResourceManager()
            try:
                ok({"resources": list(rm.list_resources())})
            finally:
                rm.close()
            return

        scope = RigolDS6064().connect()

        try:
            if args.cmd == "idn":
                ok({"identity": scope.identify()})

            elif args.cmd == "run":
                scope.run()
                ok({"state": "running"})

            elif args.cmd == "stop":
                scope.stop()
                ok({"state": "stopped"})

            elif args.cmd == "single":
                scope.single()
                scope.wait_after_single(0.5)
                ok({"state": "single_acquisition_requested"})

            elif args.cmd == "autoscale":
                scope.autoscale()
                ok({"state": "autoscale_requested"})

            elif args.cmd == "vpp":
                channel = validate_channel(args.channel)
                ok({"channel": channel, "vpp_v": scope.measure_vpp(channel)})

            elif args.cmd == "freq":
                channel = validate_channel(args.channel)
                ok({"channel": channel, "frequency_hz": scope.measure_freq(channel)})

            elif args.cmd == "period":
                channel = validate_channel(args.channel)
                ok({"channel": channel, "period_s": scope.measure_period(channel)})

            elif args.cmd == "duty":
                channel = validate_channel(args.channel)
                ok({"channel": channel, "positive_duty_percent": scope.measure_duty(channel)})

            elif args.cmd == "summary":
                channel = validate_channel(args.channel)
                ok({
                    "channel": channel,
                    "vpp_v": scope.measure_vpp(channel),
                    "frequency_hz": scope.measure_freq(channel),
                    "period_s": scope.measure_period(channel),
                    "positive_duty_percent": scope.measure_duty(channel),
                })

            elif args.cmd == "capture":
                channel = validate_channel(args.channel)
                values = scope.capture_waveform_ascii(channel=channel, points=args.points)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                channel_short = channel.replace("CHANnel", "CH")
                csv_path = Path("outputs/csv") / f"{timestamp}_{channel_short}.csv"
                image_path = Path("outputs/images") / f"{timestamp}_{channel_short}.png"

                save_waveform_csv(values, csv_path)
                plot_waveform(values, image_path)
                stats = basic_waveform_stats(values)

                ok({
                    "channel": channel,
                    "points_requested": args.points,
                    "points_captured": len(values),
                    "csv_path": str(csv_path),
                    "image_path": str(image_path),
                    "stats": stats,
                })

        finally:
            scope.close()

    except Exception as e:
        fail(str(e))


if __name__ == "__main__":
    main()
```

---

## 14. 本地验证流程

### 14.1 查看 PyVISA 能识别到什么设备

```bash
python src/scope_cli.py list
```

预期输出中应该包含：

```text
USB0::0x1AB1::0x04B0::DS6C134300118::INSTR
```

---

### 14.2 查询示波器身份

```bash
python src/scope_cli.py idn
```

预期输出：

```json
{
  "ok": true,
  "data": {
    "identity": "RIGOL TECHNOLOGIES,DS6064,DS6C134300118,..."
  }
}
```

---

### 14.3 测试基础控制

```bash
python src/scope_cli.py stop
python src/scope_cli.py run
python src/scope_cli.py single
```

如果示波器响应这些状态变化，说明 Python 已经能控制示波器。

---

### 14.4 读取基础测量

```bash
python src/scope_cli.py summary --channel CHANnel1
```

预期输出：

```json
{
  "ok": true,
  "data": {
    "channel": "CHANnel1",
    "vpp_v": 3.3,
    "frequency_hz": 20000.0,
    "period_s": 0.00005,
    "positive_duty_percent": 50.0
  }
}
```

如果返回 `9.9E37` 或非常离谱的数值，通常表示：

- 当前通道没有有效信号
- 没有稳定触发
- 示波器测量源不合适
- 时基/垂直档位不合适

---

### 14.5 采集波形并保存 CSV/PNG

```bash
python src/scope_cli.py capture --channel CHANnel1 --points 1200
```

成功后会生成：

```text
outputs/csv/xxxx_CH1.csv
outputs/images/xxxx_CH1.png
```

这一步完成后，AI 就不仅能读取测量值，还能拿到波形数据做进一步分析。

---

## 15. 创建 Codex Skill

Codex skill 的核心是一个目录，里面必须有 `SKILL.md`。

创建目录：

```bash
mkdir -p .agents/skills/rigol-ds6064-scope/scripts
mkdir -p .agents/skills/rigol-ds6064-scope/references
```

复制 CLI 脚本：

```bash
cp src/scope_cli.py .agents/skills/rigol-ds6064-scope/scripts/scope_cli.py
```

Windows PowerShell：

```powershell
Copy-Item src/scope_cli.py .agents/skills/rigol-ds6064-scope/scripts/scope_cli.py
```

---

## 16. 编写 SKILL.md

创建文件：

```bash
touch .agents/skills/rigol-ds6064-scope/SKILL.md
```

写入：

```md
---
name: rigol-ds6064-scope
summary: Control and analyze a RIGOL DS6064 oscilloscope through a safe local USB-TMC Python/SCPI bridge.
description: Use this skill when the user wants Codex or an AI agent to connect to, control, measure, capture, or analyze waveforms from a RIGOL DS6064 or DS6000-series oscilloscope over USB-TMC using Python, PyVISA, and SCPI.
---

# RIGOL DS6064 Oscilloscope Skill

## Purpose

This skill helps Codex operate a RIGOL DS6064 oscilloscope through a safe local Python bridge over USB-TMC. It should be used for tasks such as:

- checking oscilloscope connectivity
- listing VISA resources
- reading `*IDN?`
- starting/stopping acquisition
- running single acquisition
- measuring Vpp, frequency, period, duty cycle
- capturing waveform data
- saving waveform CSV files
- plotting waveforms
- analyzing PWM, CAN, clock, power ripple, overshoot, ringing, or noise

## Safety Rules

Never send arbitrary raw SCPI commands unless the user explicitly asks for low-level SCPI debugging.
Prefer the provided CLI commands.
Do not run destructive commands such as reset, storage erase, disk operations, secure erase, or factory reset.
Do not automatically change high-risk hardware states in motor, power, battery, or high-voltage experiments.
Always explain what measurement action will be taken before suggesting hardware changes.

## Expected Local Project Layout

```text
ai-rigol-ds6064-scope/
├── src/
│   ├── rigol_ds6064.py
│   ├── scope_cli.py
│   ├── waveform_analysis.py
│   └── safety.py
├── outputs/
│   ├── csv/
│   ├── images/
│   └── logs/
└── .env
```

## Environment Variables

The local project should define:

```env
RIGOL_CONNECTION=USB
RIGOL_SCOPE_RESOURCE=USB0::0x1AB1::0x04B0::DS6C134300118::INSTR
RIGOL_SCOPE_TIMEOUT_MS=5000
RIGOL_DEFAULT_CHANNEL=CHANnel1
```

## Basic Commands

Use these commands from the project root:

```bash
python src/scope_cli.py list
python src/scope_cli.py idn
python src/scope_cli.py run
python src/scope_cli.py stop
python src/scope_cli.py single
python src/scope_cli.py summary --channel CHANnel1
python src/scope_cli.py vpp --channel CHANnel1
python src/scope_cli.py freq --channel CHANnel1
python src/scope_cli.py duty --channel CHANnel1
python src/scope_cli.py capture --channel CHANnel1 --points 1200
```

## Standard Workflow

When the user asks to inspect a signal:

1. Check connection with `python src/scope_cli.py idn`.
2. Ask for or infer the channel, defaulting to CHANnel1.
3. Stop or single-acquire if needed.
4. Read summary measurements.
5. If waveform shape matters, capture waveform and save CSV/plot.
6. Analyze the result in engineering terms.
7. Give practical next actions.

## Measurement Interpretation Guidelines

For PWM:

- Report frequency, period, duty cycle, Vpp, min/max if available.
- Check whether logic high/low level matches expected 3.3 V or 5 V logic.
- Watch for overshoot, ringing, jitter, slow edge, or missing pulses.

For CAN:

- Do not claim protocol correctness from an analog waveform alone.
- Check amplitude, differential/common-mode expectations if both CAN_H and CAN_L are captured.
- Suggest using decoder only if the oscilloscope has the option enabled.

For power ripple:

- Use AC coupling if appropriate, but ask/confirm before changing coupling.
- Report ripple Vpp and approximate dominant frequency if available.
- Suggest checking probe ground length before diagnosing real noise.

## Output Style

Return results in this style:

```text
连接状态：成功
设备信息：RIGOL TECHNOLOGIES,DS6064,...
通道：CH1
峰峰值：3.31 V
频率：20.00 kHz
占空比：49.8 %
初步判断：PWM 基本正常，边沿可能有轻微振铃。
建议：缩短探头地线，必要时检查驱动端串联电阻。
```

## Failure Handling

If USB connection fails:

- Check whether Ultra Sigma can still detect the DS6064.
- Confirm the USB cable is connected to the rear USB DEVICE port.
- Confirm `UTIL → IO Setting → USB Device` is set to `Computer`.
- Close Ultra Sigma before running Python if the device is occupied.
- Run `python src/scope_cli.py list` to check the actual VISA resource name.
- Update `.env` if the resource name changed.
- Reinstall or repair Ultra Sigma / NI-VISA if no USB-TMC device is found.
```

---

## 17. 创建参考文档 DS6000_SCPI_NOTES.md

创建：

```bash
touch .agents/skills/rigol-ds6064-scope/references/DS6000_SCPI_NOTES.md
```

写入：

```md
# DS6000 / DS6064 SCPI Notes

## Common Commands

```text
*IDN?                         Query instrument identity
:RUN                          Start acquisition
:STOP                         Stop acquisition
:SINGle                       Single acquisition
:AUToscale                    Autoscale
:MEASure:ITEM? VPP,CHANnel1   Measure peak-to-peak voltage on CH1
:MEASure:ITEM? FREQuency,CHANnel1
:MEASure:ITEM? PERiod,CHANnel1
:MEASure:ITEM? PDUTy,CHANnel1
:WAVeform:SOURce CHANnel1     Set waveform source
:WAVeform:FORMat ASCii        Set waveform data format to ASCII
:WAVeform:DATA?               Query waveform data
```

## USB-TMC Resource Example

```text
USB0::0x1AB1::0x04B0::DS6C134300118::INSTR
```

## Safety

Avoid exposing these directly to the AI agent:

```text
*RST
:STORage
:SAVE
:LOAD
:DISK
:SYSTem:SECure
```
```

---

## 18. 给 Codex 的部署提示词

在项目根目录打开 Codex，然后输入：

```text
我已经通过 RIGOL Ultra Sigma 识别到 RIGOL DS6064 示波器，使用 USB-TMC 连接，不使用 LAN。

VISA 资源地址是：
USB0::0x1AB1::0x04B0::DS6C134300118::INSTR

请帮我创建一个本地 Python 项目 ai-rigol-ds6064-scope，用于通过 PyVISA 控制示波器。

要求：
1. 使用 USB-TMC 连接，不使用 LAN。
2. 把资源地址写入 .env。
3. 创建 requirements.txt、.env.example。
4. 创建 src/rigol_ds6064.py，封装 DS6064 类。
5. 创建 src/scope_cli.py，提供安全命令行入口。
6. 创建 src/waveform_analysis.py，用于保存 CSV、画图、基础统计。
7. 创建 src/safety.py，用于拦截危险 SCPI。
8. CLI 支持 list、idn、run、stop、single、autoscale、vpp、freq、period、duty、summary、capture。
9. CLI 输出统一使用 JSON。
10. 创建 .agents/skills/rigol-ds6064-scope/SKILL.md。
11. Skill 的目标是让 AI 能安全调用示波器，只允许使用封装好的安全函数，不允许直接任意发送 SCPI。
12. 不要自动执行任何可能改变实验硬件状态的危险命令。
13. 给出本地验证命令：list、idn、summary、capture。
```

如果你希望 Codex 继续完善波形采集，可以追加：

```text
继续完善 waveform capture 功能：
1. 在 rigol_ds6064.py 中优化 capture_waveform_ascii。
2. 在 scope_cli.py 中完善 capture 命令。
3. capture 命令保存 CSV 到 outputs/csv/，保存图片到 outputs/images/。
4. 输出 JSON，包含文件路径和基础统计值。
5. 后续再考虑 BYTE/WORD 二进制高速采集，不要一开始就做复杂优化。
```

---

## 19. 常见问题排查

### 19.1 Ultra Sigma 能识别，但 Python 找不到资源

先执行：

```bash
python src/scope_cli.py list
```

如果输出为空：

1. 关闭 Ultra Sigma。
2. 重新插拔 USB 线。
3. 重启示波器。
4. 重启电脑。
5. 检查 NI-VISA / Ultra Sigma 是否安装正确。
6. 在设备管理器中查看是否有 USB Test and Measurement Device。

---

### 19.2 `VI_ERROR_RSRC_NFOUND`

可能原因：

- `.env` 中资源名写错。
- 资源名和当前电脑识别到的不一致。
- Ultra Sigma 占用了设备。
- VISA 后端没有正确安装。

处理：

```bash
python src/scope_cli.py list
```

复制实际输出中的资源名，更新 `.env`：

```env
RIGOL_SCOPE_RESOURCE=实际识别到的USB资源名
```

---

### 19.3 `VI_ERROR_TMO` 超时

可能原因：

- 示波器没有响应当前 SCPI。
- 采集还没有完成。
- 波形数据点数太多。
- USB 连接不稳定。

处理：

1. 把 `RIGOL_SCOPE_TIMEOUT_MS` 改大，例如：

```env
RIGOL_SCOPE_TIMEOUT_MS=10000
```

2. 先测试简单命令：

```bash
python src/scope_cli.py idn
```

3. 再测试测量：

```bash
python src/scope_cli.py summary --channel CHANnel1
```

4. 最后测试波形采集：

```bash
python src/scope_cli.py capture --channel CHANnel1 --points 1200
```

---

### 19.4 测量值返回异常或 `9.9E37`

常见原因：

- 当前通道没有有效信号。
- 触发不稳定。
- 时基或垂直档位不合适。
- 示波器没有完成采集。
- 信号幅度太小或超出屏幕。

处理：

```bash
python src/scope_cli.py autoscale
python src/scope_cli.py single
python src/scope_cli.py summary --channel CHANnel1
```

注意：`autoscale` 会改变示波器显示配置，正式实验中建议谨慎使用。

---

### 19.5 设备被占用

如果 Ultra Sigma 正在打开这个设备，Python 可能无法访问。

处理：

1. 关闭 Ultra Sigma。
2. 重新运行 Python。
3. 不要让多个程序同时控制同一台示波器。

---

## 20. 推荐开发里程碑

### 阶段 1：打通 Python 连接

目标：

```bash
python src/scope_cli.py idn
```

成功返回 DS6064 设备信息。

---

### 阶段 2：读取基础测量

目标：

```bash
python src/scope_cli.py summary --channel CHANnel1
```

可以获得：

- Vpp
- frequency
- period
- duty

---

### 阶段 3：采集波形

目标：

```bash
python src/scope_cli.py capture --channel CHANnel1 --points 1200
```

可以输出：

- CSV 文件
- PNG 波形图
- 基础统计值

---

### 阶段 4：AI 分析

目标：用户可以说：

```text
帮我检查 CH1 的 PWM 波形是否正常。
```

AI 应该执行：

1. `idn`
2. `summary --channel CHANnel1`
3. `capture --channel CHANnel1`
4. 分析频率、占空比、Vpp、过冲、噪声
5. 给出调试建议

---

### 阶段 5：封装为 skill

目标：Codex 能自动识别此类任务并使用：

```text
$rigol-ds6064-scope 帮我读取 CH1 的峰峰值和频率。
```

或用户自然语言触发：

```text
用示波器看一下 PWM 有没有异常。
```

---

## 21. 最小可用版本定义

只要满足下面 4 点，就算链路已经打通：

1. Ultra Sigma 能识别 USB-TMC 设备。
2. Ultra Sigma 能发送 `*IDN?` 并返回 DS6064 信息。
3. Python 能执行：

```bash
python src/scope_cli.py idn
```

4. Codex 能根据 skill 调用：

```bash
python src/scope_cli.py summary --channel CHANnel1
```

这时 AI 已经可以“使用”你的 DS6064 了。

---

## 22. 后续增强方向

可以逐步让 Codex 实现：

```text
任务 1：完成基础连接和 idn 测试。
任务 2：完成 summary 测量命令。
任务 3：完成 waveform capture，保存 CSV 和 PNG。
任务 4：添加 PWM 分析函数，输出频率、占空比、Vpp、过冲估计。
任务 5：添加 CAN 波形分析模板。
任务 6：添加电源纹波分析模板。
任务 7：完善 SKILL.md，让 Codex 自动选择该 skill。
任务 8：增加日志记录和安全命令拦截。
任务 9：加入二进制波形读取，提高采样数据读取速度。
任务 10：加入实验报告自动生成功能。
```

---

## 23. USB 版和 LAN 版差异总结

| 项目 | USB 版 | LAN 版 |
|---|---|---|
| 连接方式 | USB-B 数据线 | 网线 / 局域网 |
| 资源名 | `USB0::...::INSTR` | `TCPIP::IP::INSTR` |
| 是否需要配置 IP | 不需要 | 需要 |
| 是否适合首次调通 | 很适合 | 需要网络配置 |
| 是否适合远程共享 | 不适合 | 适合 |
| 稳定性 | 本机直连稳定 | 依赖网络 |
| 推荐当前阶段 | 推荐 | 后期再考虑 |

当前阶段建议：

```text
先用 USB 打通 AI 使用示波器链路。
后续如果需要远程访问或多电脑共享，再切换到 LAN。
```

---

## 24. 参考资料

- RIGOL DS6000 User Guide
- RIGOL DS6000 Datasheet
- PyVISA 文档
- PyVISA-py 文档
- OpenAI Codex Skills 文档
- OpenAI Codex Customization 文档
