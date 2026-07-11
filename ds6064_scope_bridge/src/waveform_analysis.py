from __future__ import annotations

import csv
import json
import math
import os
from pathlib import Path
from typing import Sequence


def save_json_manifest(
    manifest: dict,
    output_path: str | Path,
    latest_path: str | Path | None = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest, ensure_ascii=False, indent=2)
    output_path.write_text(text, encoding="utf-8")
    if latest_path is not None:
        latest_path = Path(latest_path)
        latest_path.parent.mkdir(parents=True, exist_ok=True)
        latest_path.write_text(text, encoding="utf-8")
    return output_path


def save_waveform_csv(
    values: Sequence[float],
    output_path: str | Path,
    sample_interval_s: float | None = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if sample_interval_s and sample_interval_s > 0:
            writer.writerow(["index", "time_s", "voltage_v"])
            for i, value in enumerate(values):
                writer.writerow([i, i * sample_interval_s, value])
        else:
            writer.writerow(["index", "voltage_v"])
            for i, value in enumerate(values):
                writer.writerow([i, value])
    return output_path


def save_multi_waveform_csv(
    waveforms: dict[str, Sequence[float]],
    output_path: str | Path,
    sample_interval_s: float | None = None,
) -> Path:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    max_len = max((len(values) for values in waveforms.values()), default=0)
    channel_names = list(waveforms.keys())

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        header = ["index"]
        if sample_interval_s and sample_interval_s > 0:
            header.append("time_s")
        header.extend(f"{channel}_voltage_v" for channel in channel_names)
        writer.writerow(header)

        for i in range(max_len):
            row: list[int | float | str] = [i]
            if sample_interval_s and sample_interval_s > 0:
                row.append(i * sample_interval_s)
            for channel in channel_names:
                values = waveforms[channel]
                row.append(values[i] if i < len(values) else "")
            writer.writerow(row)
    return output_path


def load_waveform_csv(input_path: str | Path) -> tuple[list[float], float | None]:
    input_path = Path(input_path)
    values: list[float] = []
    times: list[float] = []

    with input_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "voltage_v" not in reader.fieldnames:
            raise ValueError("CSV must contain a voltage_v column")
        has_time = "time_s" in reader.fieldnames
        for row in reader:
            values.append(float(row["voltage_v"]))
            if has_time and row.get("time_s") not in {None, ""}:
                times.append(float(row["time_s"]))

    sample_interval_s = infer_sample_interval(times) if len(times) == len(values) else None
    return values, sample_interval_s


def infer_sample_interval(times: Sequence[float]) -> float | None:
    if len(times) < 2:
        return None
    deltas = [b - a for a, b in zip(times, times[1:]) if b > a]
    if not deltas:
        return None
    return sum(deltas) / len(deltas)


def plot_waveform(
    values: Sequence[float],
    output_path: str | Path,
    sample_interval_s: float | None = None,
) -> Path:
    try:
        output_path = Path(output_path)
        mpl_config = output_path.parents[1] / "logs" / "matplotlib"
        mpl_config.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", str(mpl_config))

        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("matplotlib is required to plot waveform images") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    arr = [float(value) for value in values]

    plt.figure()
    if sample_interval_s and sample_interval_s > 0:
        x_values = [i * sample_interval_s for i in range(len(arr))]
        plt.plot(x_values, arr)
        plt.xlabel("Time / s")
    else:
        plt.plot(arr)
        plt.xlabel("Sample Index")
    plt.ylabel("Voltage / V")
    plt.title("Captured Waveform")
    plt.grid(True)
    plt.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close()
    return output_path


def plot_multi_waveform(
    waveforms: dict[str, Sequence[float]],
    output_path: str | Path,
    sample_interval_s: float | None = None,
) -> Path:
    try:
        output_path = Path(output_path)
        mpl_config = output_path.parents[1] / "logs" / "matplotlib"
        mpl_config.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("MPLCONFIGDIR", str(mpl_config))

        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as exc:
        raise RuntimeError("matplotlib is required to plot waveform images") from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure()
    for channel, values in waveforms.items():
        arr = [float(value) for value in values]
        if not arr:
            continue
        if sample_interval_s and sample_interval_s > 0:
            x_values = [i * sample_interval_s for i in range(len(arr))]
            plt.plot(x_values, arr, label=channel)
        else:
            plt.plot(arr, label=channel)

    plt.xlabel("Time / s" if sample_interval_s and sample_interval_s > 0 else "Sample Index")
    plt.ylabel("Voltage / V")
    plt.title("Captured Multi-Channel Waveforms")
    plt.grid(True)
    plt.legend()
    plt.savefig(output_path, dpi=160, bbox_inches="tight")
    plt.close()
    return output_path


def basic_waveform_stats(values: Sequence[float]) -> dict:
    arr = [float(value) for value in values]
    if not arr:
        return {"points": 0}

    mean = sum(arr) / len(arr)
    variance = sum((value - mean) ** 2 for value in arr) / len(arr)

    return {
        "points": len(arr),
        "min_v": min(arr),
        "max_v": max(arr),
        "mean_v": mean,
        "std_v": math.sqrt(variance),
        "vpp_v": max(arr) - min(arr),
    }


def analyze_pwm(values: Sequence[float], sample_interval_s: float | None = None) -> dict:
    arr = [float(value) for value in values]
    stats = basic_waveform_stats(arr)
    if len(arr) < 4:
        return {"ok": False, "error": "Need at least 4 samples", "stats": stats}

    low_level = percentile(arr, 10)
    high_level = percentile(arr, 90)
    amplitude = high_level - low_level
    if amplitude <= 0:
        return {"ok": False, "error": "Waveform amplitude is too small to classify PWM", "stats": stats}

    threshold = low_level + amplitude * 0.5
    states = [value >= threshold for value in arr]
    rising_edges = find_edges(states, rising=True)
    falling_edges = find_edges(states, rising=False)
    periods = [b - a for a, b in zip(rising_edges, rising_edges[1:]) if b > a]
    duty_values = [compute_cycle_duty(states, start, end) for start, end in zip(rising_edges, rising_edges[1:]) if end > start]
    duty_values = [value for value in duty_values if value is not None]

    period_samples = average(periods) if periods else None
    duty_percent = average(duty_values) if duty_values else None
    period_s = period_samples * sample_interval_s if period_samples and sample_interval_s else None
    frequency_hz = 1.0 / period_s if period_s and period_s > 0 else None

    high_overshoot_v = stats.get("max_v", high_level) - high_level
    low_undershoot_v = low_level - stats.get("min_v", low_level)
    notes = pwm_notes(
        amplitude=amplitude,
        rising_count=len(rising_edges),
        frequency_hz=frequency_hz,
        duty_percent=duty_percent,
        high_overshoot_v=high_overshoot_v,
        low_undershoot_v=low_undershoot_v,
    )

    return {
        "ok": bool(periods),
        "points": len(arr),
        "sample_interval_s": sample_interval_s,
        "low_level_v": low_level,
        "high_level_v": high_level,
        "threshold_v": threshold,
        "amplitude_v": amplitude,
        "rising_edges": len(rising_edges),
        "falling_edges": len(falling_edges),
        "period_samples": period_samples,
        "period_s": period_s,
        "frequency_hz": frequency_hz,
        "duty_percent": duty_percent,
        "high_overshoot_v": high_overshoot_v,
        "low_undershoot_v": low_undershoot_v,
        "stats": stats,
        "notes": notes,
    }


def percentile(values: Sequence[float], percent: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("percentile requires at least one value")
    position = (len(ordered) - 1) * percent / 100.0
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[int(position)]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def find_edges(states: Sequence[bool], rising: bool) -> list[int]:
    edges: list[int] = []
    for index in range(1, len(states)):
        if rising and not states[index - 1] and states[index]:
            edges.append(index)
        elif not rising and states[index - 1] and not states[index]:
            edges.append(index)
    return edges


def compute_cycle_duty(states: Sequence[bool], start: int, end: int) -> float | None:
    if end <= start:
        return None
    high_samples = sum(1 for state in states[start:end] if state)
    return high_samples * 100.0 / (end - start)


def average(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def pwm_notes(
    amplitude: float,
    rising_count: int,
    frequency_hz: float | None,
    duty_percent: float | None,
    high_overshoot_v: float,
    low_undershoot_v: float,
) -> list[str]:
    notes: list[str] = []
    if rising_count < 2:
        notes.append("Not enough rising edges to compute frequency and duty cycle reliably")
    if frequency_hz is not None:
        notes.append(f"Estimated frequency is {frequency_hz:.3f} Hz")
    if duty_percent is not None:
        notes.append(f"Estimated duty cycle is {duty_percent:.2f}%")
    if high_overshoot_v > amplitude * 0.1:
        notes.append("High-level overshoot may be visible")
    if low_undershoot_v > amplitude * 0.1:
        notes.append("Low-level undershoot may be visible")
    if not notes:
        notes.append("PWM waveform classification completed")
    return notes
