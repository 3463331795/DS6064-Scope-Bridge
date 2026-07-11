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

The CLI watchdog defaults to `RIGOL_CLI_TIMEOUT_MS=15000`.

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
