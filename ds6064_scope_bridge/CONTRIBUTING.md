# Contributing

Thanks for helping improve DS6064 Scope Bridge.

## Development Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Update `.env` with your own VISA resource before running hardware commands. Do not commit `.env`, generated captures, vendor PDFs/CHM files, or local virtual environments.

## Validation

Run offline checks before opening a pull request:

```powershell
.\.venv\Scripts\python.exe -m compileall src tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

For hardware changes, include the JSON command used and the generated manifest path under `outputs/manifests/`. Keep large CSV/PNG evidence out of Git unless a maintainer explicitly asks for a small fixture.

## Safety

Prefer read-only operations. Do not add broad raw SCPI execution paths. Configuration-changing operations such as autoscale, trigger changes, or timebase changes should be explicit and documented.
