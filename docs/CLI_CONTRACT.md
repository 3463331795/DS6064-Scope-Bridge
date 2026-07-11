# RIGOL DS6064 CLI Contract

This project exposes a safe JSON CLI for AI agents that need to access the local RIGOL DS6064 oscilloscope over USB-TMC.

## Runtime

Run commands from the project root:

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py <command>
```

Default connection:

```text
USB0::0x1AB1::0x04B0::DS6C134300118::INSTR
```

The instrument timeout defaults to `RIGOL_SCOPE_TIMEOUT_MS=20000`. The CLI watchdog defaults to `RIGOL_CLI_TIMEOUT_MS=30000`. The cross-process instrument lock defaults to `RIGOL_LOCK_TIMEOUT_MS=5000`. VISA resource opening defaults to `RIGOL_VISA_ACCESS_MODE=no_lock`.

Hardware-touching commands take an exclusive lock at `outputs/logs/rigol_ds6064.lock` before starting the worker subprocess. If the lock cannot be acquired, the CLI returns a JSON error instead of allowing concurrent USB-TMC access.

## JSON Envelope

Every command writes one JSON object to stdout.

Success:

```json
{
  "ok": true,
  "data": {}
}
```

Failure:

```json
{
  "ok": false,
  "error": "message"
}
```

Agents should parse `ok` first. Do not rely on stderr for machine decisions.

## Recommended Agent Flow

1. Run `health`.
2. If `status` is `pass` or acceptable `degraded`, run `capture` or `capture-multi`.
3. Use returned `manifest_path` first, then CSV/PNG paths for downstream analysis.
4. If a channel returns zero points, run `diagnose-channel` for that channel.
5. If `list` sees the instrument but `idn` times out, run `probe-open --query-idn` to locate the stuck VISA stage.

## Measurement Policy

For direct scalar questions, use the oscilloscope's built-in measurement engine first:

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py freq --channel CHANnel1
.\.venv\Scripts\python.exe src\scope_cli.py period --channel CHANnel1
.\.venv\Scripts\python.exe src\scope_cli.py duty --channel CHANnel1
.\.venv\Scripts\python.exe src\scope_cli.py vpp --channel CHANnel1
```

The `freq`, `period`, `duty`, and `vpp` commands call the wrapped `:MEASure:ITEM?` path and return the DS6064's own measurement result. Treat those values as authoritative for frequency, period, duty, and peak-to-peak voltage.

Use `capture`, `summary`, or `analyze-pwm` when the user needs waveform evidence, timing relationships, CSV/PNG artifacts, or visual quality analysis. If a built-in measurement and a CSV-derived estimate disagree, report the built-in measurement as primary and label the waveform result as an estimate.

If a built-in measurement query times out, do not retry in parallel. Report the timeout, then optionally fall back to `capture --points 1200` or `analyze-pwm --points 1200 --save`.

## Capture Evidence Package

File-producing commands write an AI-friendly manifest under `outputs/manifests/`, refresh `outputs/manifests/latest.json`, and return `manifest_path` in the JSON response. Treat the manifest as the primary handoff artifact for another AI agent.

Stable manifest fields:

```json
{
  "schema_version": "1.0",
  "command": "capture|capture-multi|analyze-pwm",
  "captured_at_local": "20260711_103125",
  "connection": "USB-TMC",
  "identity": "RIGOL TECHNOLOGIES,DS6064,...",
  "points_requested": 1200,
  "sample_interval_s": 4e-7,
  "files": {
    "csv_path": "outputs/csv/...csv",
    "image_path": "outputs/images/...png",
    "manifest_path": "outputs/manifests/...json"
  }
}
```

### latest

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py latest
```

Returns the fixed latest manifest entrypoint without touching the oscilloscope:

```json
{
  "latest_path": "outputs/manifests/latest.json",
  "manifest": {}
}
```

Use this when another AI agent asks for the most recent waveform evidence package and no new hardware capture is needed.

## Commands

### health

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py health --channels CHANnel1 CHANnel2 CHANnel3 --points 64
```

Checks VISA resources, configured resource match, output directory writability, `*IDN?`, and a small read-only waveform probe per channel.

Stable fields:

```json
{
  "ok": true,
  "data": {
    "status": "pass|degraded|fail",
    "connection": "USB-TMC",
    "checks": {
      "visa_resources": {"ok": true, "resources": []},
      "resource_match": {"ok": true, "configured_resource": "..."},
      "output_dirs": {},
      "identity": {"ok": true, "value": "..."},
      "channels": []
    },
    "recommendations": []
  }
}
```

### idn

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py idn
```

Returns:

```json
{"identity": "RIGOL TECHNOLOGIES,DS6064,DS6C134300118,..."}
```

### probe-open

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py probe-open --query-idn
```

Diagnoses the USB-TMC open path through timed stages while still using the lock and watchdog. It is read-only unless `--query-idn` is supplied, in which case it sends `*IDN?` after the VISA session opens.

Useful options:

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py probe-open --access-mode no_lock --open-timeout-ms 5000 --query-idn
.\.venv\Scripts\python.exe src\scope_cli.py probe-open --access-mode default --open-timeout-ms 5000
```

Stable fields:

```json
{
  "status": "pass|fail",
  "connection": "USB-TMC",
  "identity": "RIGOL TECHNOLOGIES,DS6064,...",
  "config": {
    "resource": "USB0::0x1AB1::0x04B0::DS6C134300118::INSTR",
    "timeout_ms": 20000,
    "access_mode": "no_lock",
    "clear_on_connect": false
  },
  "stages": []
}
```

### capture

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py capture --channel CHANnel1 --points 1200
```

Stable fields:

```json
{
  "channel": "CHANnel1",
  "points_requested": 1200,
  "points_captured": 1400,
  "sample_interval_s": 2e-7,
  "csv_path": "outputs/csv/...csv",
  "image_path": "outputs/images/...png",
  "manifest_path": "outputs/manifests/...json",
  "stats": {
    "points": 1400,
    "min_v": 0.0,
    "max_v": 3.3,
    "mean_v": 1.65,
    "std_v": 1.65,
    "vpp_v": 3.3
  }
}
```

`sample_interval_s` may be `null` if the instrument does not report timing.

### capture-multi

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py capture-multi --channels CHANnel1 CHANnel2 CHANnel3 --points 1200
```

Reads channels serially and saves one wide CSV plus one overlay PNG.

CSV columns:

```csv
index,time_s,CH1_voltage_v,CH2_voltage_v,CH3_voltage_v
```

Stable fields:

```json
{
  "channels": ["CHANnel1", "CHANnel2", "CHANnel3"],
  "points_requested": 1200,
  "sample_interval_s": 2e-7,
  "csv_path": "outputs/csv/..._multi.csv",
  "image_path": "outputs/images/..._multi.png",
  "manifest_path": "outputs/manifests/..._multi.json",
  "channel_results": []
}
```

### diagnose-channel

```powershell
.\.venv\Scripts\python.exe src\scope_cli.py diagnose-channel --channel CHANnel3 --points 1200
```

Use when the front panel shows a waveform but capture returns zero points or odd values. It reports display state, scale, offset, coupling, probe, waveform source, preamble, raw payload length, and parsed point count.

## Safety Boundary

Default AI flows may read, capture, save CSV/PNG, and analyze saved data.

Avoid automatic use of configuration-changing commands such as `autoscale` unless the user explicitly allows it.

The CLI does not expose arbitrary raw SCPI. Dangerous patterns are blocked in the wrapper, including:

```text
*RST
:STOR
:SAVE
:LOAD
:DISK
:SYSTem:SECure
```

## Failure Guidance

- `visa_resources.ok=false`: check NI-VISA/PyVISA installation and driver state.
- `resource_match.ok=false`: replug the rear USB DEVICE port or update `.env`.
- `identity.ok=false`: close Ultra Sigma and other VISA tools, then retry after USB replug.
- `parsed_points=0`: run `diagnose-channel`, confirm the scope channel is enabled, and inspect raw payload fields.
- file output errors: verify `outputs/csv`, `outputs/images`, and `outputs/logs` are writable.

## USB-TMC Stability Notes

USB-TMC sessions can appear to hang when a previous command leaves unread data, another program owns the device, or waveform reads exceed the current timeout. Keep these rules in the agent contract:

- Close Ultra Sigma and other VISA tools before Python access.
- Any SCPI command containing `?` must consume its reply before the next command.
- Start waveform captures at `--points 1200`; use `12000` only when the link is stable and more detail is needed.
- Keep `RIGOL_SCOPE_TIMEOUT_MS=20000` and `RIGOL_CLI_TIMEOUT_MS=30000` for normal USB-TMC work.
- Keep `RIGOL_VISA_ACCESS_MODE=no_lock` unless `probe-open` shows a backend-specific reason to test `default`, `shared_lock`, or `exclusive_lock`.
- Do not run concurrent AI/tool calls against the DS6064. Hardware-touching CLI commands are guarded by `outputs/logs/rigol_ds6064.lock`; wait for the active command or retry after it finishes.
- Frequent open/close can be unstable on USB-TMC; if this becomes a blocker, preserve this CLI contract and add a persistent queued `scope_server.py` later.
- If the USB resource disappears after idle time, disable Windows USB selective suspend.
- On Windows, prefer NI-VISA when the backend intermittently loses the instrument.
