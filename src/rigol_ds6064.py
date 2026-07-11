from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Optional

from safety import assert_safe_scpi


try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv() -> bool:
        return False


load_dotenv()


VALID_CHANNELS = ["CHANnel1", "CHANnel2", "CHANnel3", "CHANnel4"]


@dataclass(frozen=True)
class ScopeConfig:
    resource: str
    timeout_ms: int = 5000
    clear_on_connect: bool = False

    @classmethod
    def from_env(cls) -> "ScopeConfig":
        resource = os.getenv(
            "RIGOL_SCOPE_RESOURCE",
            "USB0::0x1AB1::0x04B0::DS6C134300118::INSTR",
        )
        timeout_ms = int(os.getenv("RIGOL_SCOPE_TIMEOUT_MS", "5000"))
        clear_on_connect = os.getenv("RIGOL_CLEAR_ON_CONNECT", "0").lower() in {"1", "true", "yes", "on"}
        return cls(resource=resource, timeout_ms=timeout_ms, clear_on_connect=clear_on_connect)


class RigolDS6064:
    """Safe wrapper for a RIGOL DS6064 / DS6000 oscilloscope."""

    def __init__(self, config: Optional[ScopeConfig] = None):
        self.config = config or ScopeConfig.from_env()
        self.rm = None
        self.inst = None

    def connect(self) -> "RigolDS6064":
        import pyvisa

        self.rm = pyvisa.ResourceManager()
        resources = self.rm.list_resources()
        if resources and self.config.resource not in resources:
            print("Warning: configured resource not found in list_resources().", file=sys.stderr)
            print("Configured:", self.config.resource, file=sys.stderr)
            print("Detected:", resources, file=sys.stderr)

        self.inst = self.rm.open_resource(self.config.resource, open_timeout=self.config.timeout_ms)
        self.inst.timeout = self.config.timeout_ms
        self.inst.write_termination = "\n"
        self.inst.read_termination = "\n"
        self.inst.send_end = True
        if self.config.clear_on_connect:
            try:
                self.inst.clear()
            except Exception:
                pass
        return self

    def close(self) -> None:
        if self.inst is not None:
            self.inst.close()
            self.inst = None
        if self.rm is not None:
            self.rm.close()
            self.rm = None

    def query(self, command: str) -> str:
        self._ensure_connected()
        return self.inst.query(command).strip()

    def safe_query(self, command: str) -> dict:
        try:
            return {"ok": True, "value": self.query(command)}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def write(self, command: str) -> None:
        assert_safe_scpi(command)
        self._ensure_connected()
        self.inst.write(command)

    def _ensure_connected(self) -> None:
        if self.inst is None:
            raise RuntimeError("Scope is not connected. Call connect() first.")

    def identify(self) -> str:
        return self.query("*IDN?")

    def run(self) -> None:
        self.write(":RUN")

    def stop(self) -> None:
        self.write(":STOP")

    def single(self) -> None:
        self.write(":SINGle")

    def autoscale(self) -> None:
        self.write(":AUToscale")

    def measure_vpp(self, channel: str = "CHANnel1") -> float:
        channel = validate_channel(channel)
        return float(self.query(f":MEASure:ITEM? VPP,{channel}"))

    def measure_freq(self, channel: str = "CHANnel1") -> float:
        channel = validate_channel(channel)
        return float(self.query(f":MEASure:ITEM? FREQuency,{channel}"))

    def measure_period(self, channel: str = "CHANnel1") -> float:
        channel = validate_channel(channel)
        return float(self.query(f":MEASure:ITEM? PERiod,{channel}"))

    def measure_duty(self, channel: str = "CHANnel1") -> float:
        channel = validate_channel(channel)
        return float(self.query(f":MEASure:ITEM? PDUTy,{channel}"))

    def set_timebase_scale(self, seconds_per_div: float) -> None:
        if seconds_per_div <= 0:
            raise ValueError("seconds_per_div must be positive")
        self.write(f":TIMebase:SCALe {seconds_per_div}")

    def set_channel_scale(self, channel: int, volts_per_div: float) -> None:
        if channel not in [1, 2, 3, 4]:
            raise ValueError("channel must be 1, 2, 3, or 4")
        if volts_per_div <= 0:
            raise ValueError("volts_per_div must be positive")
        self.write(f":CHANnel{channel}:SCALe {volts_per_div}")

    def set_trigger_edge(
        self,
        channel: int = 1,
        level: float = 0.0,
        slope: str = "POSitive",
    ) -> None:
        if channel not in [1, 2, 3, 4]:
            raise ValueError("channel must be 1, 2, 3, or 4")
        if slope not in ["POSitive", "NEGative", "RFALl"]:
            raise ValueError("slope must be POSitive, NEGative, or RFALl")
        self.write(":TRIGger:MODE EDGE")
        self.write(f":TRIGger:EDGE:SOURce CHANnel{channel}")
        self.write(f":TRIGger:EDGE:SLOPe {slope}")
        self.write(f":TRIGger:EDGE:LEVel {level}")

    def capture_waveform_ascii(self, channel: str = "CHANnel1", points: int = 1200) -> list[float]:
        return self.capture_waveform_data(channel=channel, points=points)["values"]

    def capture_waveform_data(self, channel: str = "CHANnel1", points: int = 1200) -> dict:
        channel = validate_channel(channel)
        if points <= 0 or points > 120000:
            raise ValueError("points must be between 1 and 120000")

        self.write(f":WAVeform:SOURce {channel}")
        self.write(":WAVeform:MODE NORMal")
        self.write(":WAVeform:FORMat ASCii")
        self.write(f":WAVeform:POINts {points}")
        preamble = self.query(":WAVeform:PREamble?")

        self.write(":WAVeform:DATA?")
        raw = self.inst.read_raw()
        values = parse_waveform_payload(raw)
        preamble_data = parse_waveform_preamble(preamble)
        scaled_values = scale_waveform_values(values, preamble)
        sample_interval_s = self._resolve_sample_interval(preamble_data)
        return {
            "values": scaled_values,
            "preamble_raw": preamble,
            "preamble": preamble_data,
            "sample_interval_s": sample_interval_s,
        }

    def diagnose_channel(self, channel: str = "CHANnel1", points: int = 1200) -> dict:
        channel = validate_channel(channel)
        if points <= 0 or points > 120000:
            raise ValueError("points must be between 1 and 120000")

        diagnostics = {
            "channel": channel,
            "display": self.safe_query(f":{channel}:DISPlay?"),
            "scale_v_per_div": self.safe_query(f":{channel}:SCALe?"),
            "offset_v": self.safe_query(f":{channel}:OFFSet?"),
            "coupling": self.safe_query(f":{channel}:COUPling?"),
            "probe": self.safe_query(f":{channel}:PROBe?"),
            "timebase_scale_s_per_div": self.safe_query(":TIMebase:SCALe?"),
        }

        self.write(f":WAVeform:SOURce {channel}")
        self.write(":WAVeform:MODE NORMal")
        self.write(":WAVeform:FORMat ASCii")
        self.write(f":WAVeform:POINts {points}")

        source = self.safe_query(":WAVeform:SOURce?")
        points_query = self.safe_query(":WAVeform:POINts?")
        x_increment = self.safe_query(":WAVeform:XINCrement?")
        preamble_raw = self.safe_query(":WAVeform:PREamble?")
        raw_length = None
        raw_preview_hex = None
        parsed_points = None
        raw_error = None

        try:
            self.write(":WAVeform:DATA?")
            raw = self.inst.read_raw()
            raw_length = len(raw)
            raw_preview_hex = raw[:80].hex(" ")
            parsed_points = len(parse_waveform_payload(raw))
        except Exception as exc:
            raw_error = str(exc)

        diagnostics.update(
            {
                "waveform_source": source,
                "waveform_points": points_query,
                "waveform_x_increment_s": x_increment,
                "preamble_raw": preamble_raw,
                "preamble": parse_waveform_preamble(preamble_raw.get("value", "")) if preamble_raw.get("ok") else {},
                "raw_length_bytes": raw_length,
                "raw_preview_hex": raw_preview_hex,
                "parsed_points": parsed_points,
                "raw_error": raw_error,
            }
        )
        return diagnostics

    def _resolve_sample_interval(self, preamble_data: dict) -> float | None:
        x_increment = preamble_data.get("x_increment_s")
        if isinstance(x_increment, (int, float)) and x_increment > 0:
            return float(x_increment)

        try:
            queried = float(self.query(":WAVeform:XINCrement?"))
        except Exception:
            return None
        if queried > 0:
            return queried
        return None

    def wait_after_single(self, seconds: float = 0.5) -> None:
        time.sleep(seconds)


def validate_channel(channel: str) -> str:
    if channel not in VALID_CHANNELS:
        raise ValueError(f"Invalid channel: {channel}. Use one of {VALID_CHANNELS}")
    return channel


def parse_ascii_waveform(raw: str) -> list[float]:
    values: list[float] = []
    normalized = strip_ieee_block_header(raw.strip()).replace(",", " ")
    for item in normalized.split():
        try:
            values.append(float(item))
        except ValueError:
            continue
    return values


def parse_waveform_payload(raw: bytes | str) -> list[float]:
    if isinstance(raw, str):
        return parse_ascii_waveform(raw)

    payload = strip_ieee_block_header_bytes(raw.strip())
    try:
        text = payload.decode("ascii")
    except UnicodeDecodeError:
        return [float(sample) for sample in payload]
    values = parse_ascii_waveform(text)
    if values:
        return values
    if payload and any(byte not in b"+-.0123456789, \t\r\nEe" for byte in payload):
        return [float(sample) for sample in payload]
    return values


def scale_waveform_values(values: list[float], preamble: str) -> list[float]:
    preamble_data = parse_waveform_preamble(preamble)
    if not preamble_data:
        return values

    y_increment = preamble_data.get("y_increment_v")
    y_origin = preamble_data.get("y_origin")
    y_reference = preamble_data.get("y_reference")
    if y_increment is None or y_origin is None or y_reference is None:
        return values

    return [(value - y_origin - y_reference) * y_increment for value in values]


def parse_waveform_preamble(preamble: str) -> dict:
    try:
        fields = [float(item) for item in preamble.replace(",", " ").split()]
    except ValueError:
        return {}

    if len(fields) < 10:
        return {}

    return {
        "format": int(fields[0]),
        "type": int(fields[1]),
        "points": int(fields[2]),
        "count": int(fields[3]),
        "x_increment_s": fields[4],
        "x_origin_s": fields[5],
        "x_reference": fields[6],
        "y_increment_v": fields[7],
        "y_origin": fields[8],
        "y_reference": fields[9],
    }


def strip_ieee_block_header(raw: str) -> str:
    if len(raw) < 2 or raw[0] != "#" or not raw[1].isdigit():
        return raw
    length_digits = int(raw[1])
    header_end = 2 + length_digits
    if length_digits == 0 or len(raw) < header_end:
        return raw.lstrip("#")
    length_text = raw[2:header_end]
    if not length_text.isdigit():
        return raw.lstrip("#")
    payload_length = int(length_text)
    payload = raw[header_end:header_end + payload_length]
    return payload or raw[header_end:]


def strip_ieee_block_header_bytes(raw: bytes) -> bytes:
    if len(raw) < 2 or raw[:1] != b"#" or not chr(raw[1]).isdigit():
        return raw
    length_digits = int(chr(raw[1]))
    header_end = 2 + length_digits
    if length_digits == 0 or len(raw) < header_end:
        return raw.lstrip(b"#")
    length_text = raw[2:header_end]
    if not length_text.isdigit():
        return raw.lstrip(b"#")
    payload_length = int(length_text.decode("ascii"))
    payload = raw[header_end:header_end + payload_length]
    return payload or raw[header_end:]
