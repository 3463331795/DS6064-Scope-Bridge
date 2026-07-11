---
name: rigol-ds6064-scope
description: Control and analyze a RIGOL DS6064 or DS6000-series oscilloscope over USB-TMC with Python, PyVISA, and safe SCPI wrappers. Use when the user asks Codex to connect to a RIGOL DS6064 oscilloscope, list VISA resources, read measurements, capture waveforms, save CSV/PNG files, or analyze PWM, CAN, clock, noise, ringing, overshoot, or power ripple signals from the scope.
---

# RIGOL DS6064 Oscilloscope

Use this skill to operate the local RIGOL DS6064 through the project CLI. Prefer the CLI over raw SCPI. Do not send arbitrary SCPI unless the user explicitly requests low-level debugging and the command has been checked against the safety rules.

## Local Bridge

Run commands from the project root:

```powershell
python src/scope_cli.py list
python src/scope_cli.py latest
python src/scope_cli.py health --channels CHANnel1 CHANnel2 CHANnel3 --points 64
python src/scope_cli.py probe-open --query-idn
python src/scope_cli.py idn
python src/scope_cli.py freq --channel CHANnel1
python src/scope_cli.py period --channel CHANnel1
python src/scope_cli.py duty --channel CHANnel1
python src/scope_cli.py vpp --channel CHANnel1
python src/scope_cli.py capture --channel CHANnel1 --points 1200
python src/scope_cli.py capture-multi --channels CHANnel1 CHANnel2 CHANnel3 --points 1200
python src/scope_cli.py diagnose-channel --channel CHANnel3 --points 1200
python src/scope_cli.py analyze-pwm --channel CHANnel1 --points 1200 --save
python src/scope_cli.py analyze-pwm-file --csv outputs/csv/<capture>.csv
python src/scope_cli.py summary --channel CHANnel1 --points 1200
```

The default USB-TMC VISA resource is:

```text
USB0::0x1AB1::0x04B0::DS6C134300118::INSTR
```

Valid channels are `CHANnel1`, `CHANnel2`, `CHANnel3`, and `CHANnel4`. Default to `CHANnel1` when the user does not specify a channel.

`RIGOL_SCOPE_TIMEOUT_MS` defaults to `20000`, `RIGOL_CLI_TIMEOUT_MS` defaults to `30000`, `RIGOL_LOCK_TIMEOUT_MS` defaults to `5000`, `RIGOL_VISA_ACCESS_MODE` defaults to `no_lock`, and `RIGOL_VISA_LIBRARY` defaults to `auto`. The CLI uses a parent-process lock plus a worker subprocess watchdog so concurrent AI calls are rejected as JSON and a stuck VISA read returns JSON instead of hanging the AI session.

## Workflow

For link bring-up and routine checks:

1. Run `python src/scope_cli.py health --channels CHANnel1 CHANnel2 CHANnel3 --points 64`.
2. If `status` is `pass`, proceed to capture.
3. If `status` is `degraded`, inspect `recommendations` and the per-channel checks before deciding whether capture is still useful.
4. If `status` is `fail`, report the failed check and recommended physical/software recovery step.

For signal inspection requests:

1. Run `python src/scope_cli.py health --channels <channels> --points 64` to confirm the link.
2. Run `python src/scope_cli.py capture --channel <channel> --points 1200` to save CSV/PNG and get waveform statistics.
3. Run `python src/scope_cli.py summary --channel <channel> --points 1200` only when a quick waveform-statistics summary is enough.
4. Inspect the returned `manifest_path` first, then the generated CSV/PNG paths.
5. Report connection status, device identity, channel, measurements, manifest path, waveform files, and an engineering interpretation.

For direct scalar measurement questions, prefer the oscilloscope's built-in measurement engine first:

```powershell
python src/scope_cli.py freq --channel CHANnel1
python src/scope_cli.py period --channel CHANnel1
python src/scope_cli.py duty --channel CHANnel1
python src/scope_cli.py vpp --channel CHANnel1
```

Use waveform-derived estimates only as secondary evidence or fallback. When the built-in measurement and CSV-derived estimate disagree, treat the built-in measurement as authoritative for frequency/period/duty and clearly label the CSV result as an estimate.

The stable CLI contract is documented in `docs/CLI_CONTRACT.md`. Prefer that document when another AI agent needs to call this project.

For multi-channel waveform requests, use `python src/scope_cli.py capture-multi --channels CHANnel1 CHANnel2 CHANnel3 --points 1200`. It reads each channel serially, then saves one combined CSV, one combined PNG, and one manifest JSON under `outputs/manifests/`. If a channel returns zero points, report that channel explicitly and ask the user to verify that the scope channel is enabled on the front panel.

When handing waveform data to another AI agent, prefer the manifest JSON returned as `manifest_path`. It records schema version, command, capture time, connection type, scope identity, requested points, sample interval, CSV/PNG paths, manifest path, and per-channel statistics.

If the user asks for the latest already-captured waveform and does not need a fresh acquisition, run `python src/scope_cli.py latest`. This returns `outputs/manifests/latest.json` without touching the oscilloscope hardware.

If the scope front panel shows a waveform but the CLI returns zero points for a channel, run `python src/scope_cli.py diagnose-channel --channel <channel> --points 1200`. This is read-only apart from selecting the waveform source, and reports display state, channel scale/offset/coupling/probe, waveform source, preamble, raw payload length, and parsed point count.

If `list` sees the DS6064 but `idn` times out, run `python src/scope_cli.py probe-open --query-idn`. It reports timed stages for ResourceManager creation, VISA resource enumeration, `open_resource`, session configuration, and optional `*IDN?`, while still using the CLI lock and watchdog.

If `probe-open` stops after `open_resource_start`, compare the NI-VISA libraries under the watchdog:

```powershell
python src/scope_cli.py probe-open --visa-library C:\Windows\System32\visa32.dll --open-timeout-ms 5000 --query-idn
python src/scope_cli.py probe-open --visa-library C:\Windows\System32\visa64.dll --open-timeout-ms 5000 --query-idn
```

Run oscilloscope commands strictly one at a time. Do not parallelize VISA calls against the same USB-TMC instrument.

For PWM, report frequency, period, duty cycle, Vpp, approximate logic level, and visible concerns such as overshoot, ringing, jitter, slow edges, or missing pulses.

For PWM inspection, prefer `python src/scope_cli.py analyze-pwm --channel <channel> --points 1200 --save`. This command captures the waveform, estimates low/high level, threshold, frequency, period, duty cycle, overshoot/undershoot, and optionally saves CSV/PNG.

If the instrument session is unstable after a capture, use `python src/scope_cli.py analyze-pwm-file --csv <path>` to analyze a saved CSV offline. CSV files saved after this update include a `time_s` column when the scope reports a valid sample interval, so offline PWM analysis can recover frequency and duty cycle without reopening USB-TMC.

The DS6064 measurement query path is the preferred source for direct frequency, period, duty, and Vpp questions because it uses the instrument's own measurement engine. The DS6000 programming guide documents direct queries such as `:MEASure:FREQuency? CHANnel1`, `:MEASure:PERiod? CHANnel1`, `:MEASure:PDUTy? CHANnel1`, and `:MEASure:VPP? CHANnel1`; use the CLI wrappers instead of sending them directly. If that query times out on USB-TMC, report the timeout, then fall back to `capture` or `analyze-pwm` and label the result as waveform-derived.

## USB-TMC Stability

USB-TMC is a test-and-measurement protocol, not a serial console. Follow these rules to avoid stuck sessions:

- Close Ultra Sigma and other VISA tools before Python access; only one controller should own the DS6064.
- Commands ending in `?` must be handled through query/read paths so their replies are consumed before the next command.
- Keep waveform captures bounded first: use `--points 1200` for routine checks and increase only when needed.
- Use longer timeouts for USB-TMC waveform reads: `RIGOL_SCOPE_TIMEOUT_MS=20000` and `RIGOL_CLI_TIMEOUT_MS=30000` are the baseline.
- Never run multiple VISA commands in parallel against this scope. The CLI creates `outputs/logs/rigol_ds6064.lock`; if another command owns it, wait or retry after the active command finishes.
- If frequent open/close becomes unstable, move the same CLI contract behind a future persistent `scope_server.py` queue instead of adding raw SCPI calls.
- If Windows drops the device after idle time, disable USB selective suspend for the active power plan.
- Prefer NI-VISA on Windows if the VISA backend intermittently loses the USB-TMC resource.

For CAN, do not claim protocol correctness from one analog waveform alone. Comment on level, timing, and signal quality, and recommend a proper decoder or differential capture when needed.

For power ripple, report ripple Vpp and approximate shape/frequency if visible. Suggest probe-ground and coupling checks before treating measured noise as real board noise.

## Safety Rules

Do not automatically change high-risk external hardware states in motor, power, battery, or high-voltage setups. The AI may read, capture, analyze, and recommend.

Treat `autoscale` as configuration-changing. Use it only when the user asks for it or when connection/measurement debugging clearly needs it.

Avoid these SCPI patterns unless the user explicitly asks for low-level recovery and understands the risk:

```text
*RST
:STOR
:SAVE
:LOAD
:DISK
:SYSTem:SECure
```

If USB fails, ask the user to close Ultra Sigma, verify the rear USB DEVICE port, set `UTIL -> IO Setting -> USB Device` to `Computer`, then run `python src/scope_cli.py list` and update `.env` if the VISA resource changed.

If `list` sees the DS6064 but `idn` times out, close Ultra Sigma and any other VISA tool, power-cycle the oscilloscope USB connection, and retry `python src/scope_cli.py idn`. Keep `RIGOL_CLEAR_ON_CONNECT=0` unless low-level USB-TMC clearing is explicitly needed.

If commands were accidentally run in parallel and even `list` starts timing out, unplug/replug the rear USB DEVICE cable or power-cycle the oscilloscope USB interface, then retry only one command at a time.

## Output Style

Prefer concise Chinese engineering output:

```text
连接状态：成功
设备信息：RIGOL TECHNOLOGIES,DS6064,...
通道：CH1
峰峰值：3.31 V
频率：20.00 kHz
占空比：49.8 %
波形文件：outputs/images/...
初步判断：PWM 基本正常，边沿存在轻微振铃。
建议：缩短探头地线，必要时检查驱动端串联电阻。
```
