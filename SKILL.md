---
name: rigol-ds6064-scope
description: Control and analyze a local RIGOL DS6064 or DS6000-series oscilloscope over USB-TMC with Python, PyVISA, NI-VISA, and safe SCPI wrappers. Use when Codex or another AI agent needs to list VISA resources, query identity, read built-in measurements, capture CH1-CH4 waveforms, save CSV/PNG/manifest artifacts, diagnose USB-TMC stability, or analyze PWM, CAN, clock, noise, ringing, overshoot, and power ripple signals.
---

# RIGOL DS6064 Scope Bridge

Use this skill in `G:\资料\Agants\AI_DS6064` to operate the local RIGOL DS6064 through the project CLI. Prefer the CLI over raw SCPI. Do not send arbitrary SCPI unless the user explicitly asks for low-level recovery and the command has been checked against the safety rules.

## Command Runner

Run commands from the project root. Prefer the virtual environment when it exists:

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py <command>
```

Fallback:

```powershell
python src\scope_cli.py <command>
```

All CLI output is a single JSON object. Parse `ok` first. Hardware-touching commands use `outputs/logs/rigol_ds6064.lock` plus a watchdog so concurrent AI calls are rejected as JSON instead of hanging the session.

## Known Configuration

```env
RIGOL_CONNECTION=USB
RIGOL_SCOPE_RESOURCE=USB0::0x1AB1::0x04B0::DS6C134300118::INSTR
RIGOL_SCOPE_TIMEOUT_MS=20000
RIGOL_DEFAULT_CHANNEL=CHANnel1
RIGOL_CLEAR_ON_CONNECT=0
RIGOL_VISA_ACCESS_MODE=no_lock
RIGOL_VISA_LIBRARY=auto
RIGOL_CLI_TIMEOUT_MS=30000
RIGOL_LOCK_TIMEOUT_MS=5000
```

Use only USB-TMC. LAN/TCPIP is intentionally not part of this bridge.

## Core Workflows

Bring up or diagnose the link:

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py list
.\.venv\Scripts\python.exe src\scope_cli.py probe-open --query-idn --open-timeout-ms 5000
.\.venv\Scripts\python.exe src\scope_cli.py health --channels CHANnel1 CHANnel2 CHANnel3 --points 64
.\.venv\Scripts\python.exe src\scope_cli.py idn
```

Answer direct scalar measurement questions with the DS6064 built-in measurement engine:

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py freq --channel CHANnel1
.\.venv\Scripts\python.exe src\scope_cli.py period --channel CHANnel1
.\.venv\Scripts\python.exe src\scope_cli.py duty --channel CHANnel1
.\.venv\Scripts\python.exe src\scope_cli.py vpp --channel CHANnel1
.\.venv\Scripts\python.exe src\scope_cli.py summary --channel CHANnel1
```

Capture waveform evidence:

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py capture --channel CHANnel1 --points 1200
.\.venv\Scripts\python.exe src\scope_cli.py capture-multi --channels CHANnel1 CHANnel2 CHANnel3 --points 1200
.\.venv\Scripts\python.exe src\scope_cli.py snapshot --channels CHANnel1 CHANnel2 CHANnel3 --points 1200
.\.venv\Scripts\python.exe src\scope_cli.py latest
```

Analyze PWM:

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py analyze-pwm --channel CHANnel1 --points 1200 --save
.\.venv\Scripts\python.exe src\scope_cli.py analyze-pwm-file --csv outputs\csv\<capture>.csv
```

Investigate a channel that looks active on the front panel but returns bad capture data:

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py diagnose-channel --channel CHANnel3 --points 1200
```

## Agent Policy

Use `health` before fresh captures unless the user only asks for already captured data. If the user asks for the latest evidence without new hardware access, use `latest`.

Run oscilloscope commands strictly one at a time. Never parallelize VISA or CLI calls against the DS6064.

Default to `CHANnel1` if the user does not name a channel. Accept only `CHANnel1`, `CHANnel2`, `CHANnel3`, and `CHANnel4`.

For frequency, period, duty, and Vpp, report built-in scope measurements as primary. Use CSV-derived estimates only as secondary evidence or fallback, and label them as estimates when they disagree.

If a measurement field contains `value: null` with `raw_value` near `9.9e37`, report that scalar as unavailable from the instrument instead of treating the raw sentinel as a real number.

For multi-channel timing analysis, prefer `snapshot` when another AI agent needs both DS6064 built-in measurements and waveform evidence. It uses one USB-TMC session to read identity, per-channel Vpp/frequency/period/duty, one combined CSV, one overlay PNG, and one manifest under `outputs/manifests/`. Use `capture-multi` when only waveform files are needed. Treat `manifest_path` as the primary handoff artifact for other AI agents.

For PWM, report frequency, period, duty cycle, Vpp, approximate high/low level, and visible concerns such as overshoot, ringing, jitter, slow edges, or missing pulses.

For CAN, do not claim protocol correctness from one analog waveform alone. Comment on level, timing, and signal quality, and recommend proper decoding or differential capture when needed.

For power ripple, report ripple Vpp and approximate shape/frequency if visible. Suggest probe-ground and coupling checks before treating measured noise as real board noise.

## Safety Rules

Default AI flows may read, capture, save CSV/PNG/manifest files, and analyze saved data. Do not automatically change high-risk external hardware states in motor, power, battery, or high-voltage setups.

Treat `autoscale` as configuration-changing. Use it only when the user explicitly allows it or when connection debugging clearly requires it.

The CLI blocks dangerous SCPI patterns by default:

```text
*RST
:STOR
:SAVE
:LOAD
:DISK
:SYSTem:SECure
```

Keep using CLI wrappers instead of raw SCPI. The DS6000 command notes live in `.agents/skills/rigol-ds6064-scope/references/DS6000_SCPI_NOTES.md`; read that file only when low-level SCPI details are needed.

## USB-TMC Stability

USB-TMC is not a serial console. Avoid stuck sessions by following these rules:

- Close Ultra Sigma, NI MAX, and other VISA tools before Python controls the scope.
- Any SCPI command containing `?` must consume its reply before the next command.
- Start captures at `--points 1200`; use larger point counts only after the link is stable.
- Keep the baseline timeouts at `RIGOL_SCOPE_TIMEOUT_MS=20000` and `RIGOL_CLI_TIMEOUT_MS=30000`.
- If `list` sees the DS6064 but `idn` or `open_resource` hangs, run `probe-open --query-idn` and compare NI-VISA backends only under the watchdog.
- If Windows loses the instrument after idle time, disable USB selective suspend.
- On Windows, prefer a current NI-VISA install. An old NI-VISA runtime may enumerate the resource while hanging during `open_resource`.

Known-good hardware validation after updating NI-VISA:

```text
Identity: RIGOL TECHNOLOGIES,DS6064,DS6C134300118,00.01.03.SP01
CH1 frequency: 20000.0 Hz
CH2 frequency: 20000.0 Hz
CH3 frequency: 20000.0 Hz
Latest verified multi-channel artifacts:
outputs/csv/20260711_160032_CH1_CH2_CH3_multi.csv
outputs/images/20260711_160032_CH1_CH2_CH3_multi.png
outputs/manifests/20260711_160032_CH1_CH2_CH3_multi.json
```

## Output Style

Respond in concise Chinese engineering language. Include connection state, device identity when relevant, channel list, primary measurements, generated file paths, and a short engineering judgment.

```text
连接状态：成功
设备信息：RIGOL TECHNOLOGIES,DS6064,DS6C134300118,00.01.03.SP01
通道：CH1 / CH2 / CH3
频率：20.00 kHz / 20.00 kHz / 20.00 kHz
波形文件：outputs/images/...
数据文件：outputs/csv/...
初步判断：三路信号均可被 AI 链路采集，后续分析应优先基于 manifest + PNG + CSV 证据包。
```
