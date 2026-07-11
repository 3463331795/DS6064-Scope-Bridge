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
python src/scope_cli.py idn
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

`RIGOL_CLI_TIMEOUT_MS` defaults to `15000`. The CLI uses a worker subprocess watchdog so a stuck VISA read returns JSON instead of hanging the AI session.

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

The stable CLI contract is documented in `docs/CLI_CONTRACT.md`. Prefer that document when another AI agent needs to call this project.

For multi-channel waveform requests, use `python src/scope_cli.py capture-multi --channels CHANnel1 CHANnel2 CHANnel3 --points 1200`. It reads each channel serially, then saves one combined CSV, one combined PNG, and one manifest JSON under `outputs/manifests/`. If a channel returns zero points, report that channel explicitly and ask the user to verify that the scope channel is enabled on the front panel.

When handing waveform data to another AI agent, prefer the manifest JSON returned as `manifest_path`. It records schema version, command, capture time, connection type, scope identity, requested points, sample interval, CSV/PNG paths, manifest path, and per-channel statistics.

If the user asks for the latest already-captured waveform and does not need a fresh acquisition, run `python src/scope_cli.py latest`. This returns `outputs/manifests/latest.json` without touching the oscilloscope hardware.

If the scope front panel shows a waveform but the CLI returns zero points for a channel, run `python src/scope_cli.py diagnose-channel --channel <channel> --points 1200`. This is read-only apart from selecting the waveform source, and reports display state, channel scale/offset/coupling/probe, waveform source, preamble, raw payload length, and parsed point count.

Run oscilloscope commands strictly one at a time. Do not parallelize VISA calls against the same USB-TMC instrument.

For PWM, report frequency, period, duty cycle, Vpp, approximate logic level, and visible concerns such as overshoot, ringing, jitter, slow edges, or missing pulses.

For PWM inspection, prefer `python src/scope_cli.py analyze-pwm --channel <channel> --points 1200 --save`. This command captures the waveform, estimates low/high level, threshold, frequency, period, duty cycle, overshoot/undershoot, and optionally saves CSV/PNG.

If the instrument session is unstable after a capture, use `python src/scope_cli.py analyze-pwm-file --csv <path>` to analyze a saved CSV offline. CSV files saved after this update include a `time_s` column when the scope reports a valid sample interval, so offline PWM analysis can recover frequency and duty cycle without reopening USB-TMC.

The DS6064 `:MEASure:ITEM?` query path can be unstable on this local USB-TMC setup. Prefer `capture` and waveform-derived statistics unless the user explicitly asks for the scope's built-in measurement engine.

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
