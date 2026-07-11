from __future__ import annotations


BLOCKED_SCPI_PATTERNS = [
    "*RST",
    ":STOR",
    ":SAVE",
    ":LOAD",
    ":DISK",
    ":SYSTem:SECure",
]


def assert_safe_scpi(command: str) -> None:
    normalized = command.strip().upper()
    for pattern in BLOCKED_SCPI_PATTERNS:
        if pattern.upper() in normalized:
            raise PermissionError(f"Blocked unsafe SCPI command: {command}")
