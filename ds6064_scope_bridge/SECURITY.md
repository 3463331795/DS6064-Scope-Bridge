# Security and Safety Policy

DS6064 Scope Bridge controls physical lab equipment. Treat all hardware access as safety-sensitive.

## Supported Scope

The project currently targets local RIGOL DS6064 / DS6000-series oscilloscopes over USB-TMC through PyVISA and NI-VISA. LAN/TCPIP control is intentionally out of scope.

## Reporting Issues

Please open a GitHub issue for safety or security concerns. If the issue could cause destructive hardware behavior, describe the risk and reproduction steps without publishing dangerous raw SCPI sequences when possible.

## Safety Boundaries

- The normal AI workflow should read measurements, capture waveforms, save CSV/PNG/manifest artifacts, and analyze saved data.
- The CLI should not expose arbitrary raw SCPI by default.
- Dangerous or destructive patterns such as `*RST`, `:STOR`, `:SAVE`, `:LOAD`, `:DISK`, and `:SYSTem:SECure` must remain blocked unless a future maintainer adds a clearly gated recovery mode.
- Do not run concurrent commands against the same USB-TMC instrument. Use the existing lock and watchdog model.
- Do not automatically change external experiment state in motor, power, battery, or high-voltage setups.

## Local Secrets and Artifacts

Keep `.env`, real instrument serial numbers, generated captures, logs, vendor manuals, and virtual environments out of Git. Generated evidence belongs under the project-root `outputs/` directory and is ignored by default.
