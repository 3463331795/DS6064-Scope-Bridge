from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from rigol_ds6064 import RigolDS6064, ScopeConfig, validate_channel
from waveform_analysis import (
    analyze_pwm,
    basic_waveform_stats,
    load_waveform_csv,
    plot_multi_waveform,
    plot_waveform,
    save_json_manifest,
    save_multi_waveform_csv,
    save_waveform_csv,
)


MEASUREMENT_COMMANDS = {"vpp", "freq", "period", "duty", "summary", "capture", "capture-multi", "analyze-pwm"}
INSTRUMENT_COMMANDS = {
    "list",
    "health",
    "probe-open",
    "idn",
    "run",
    "stop",
    "single",
    "autoscale",
    "vpp",
    "freq",
    "period",
    "duty",
    "summary",
    "capture",
    "capture-multi",
    "diagnose-channel",
    "analyze-pwm",
}


def ok(data: dict) -> None:
    print(json.dumps({"ok": True, "data": data}, ensure_ascii=False, indent=2))


def fail(message: str, code: int = 1, data: dict | None = None) -> None:
    payload = {"ok": False, "error": message}
    if data is not None:
        payload["data"] = data
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    sys.exit(code)


def parse_cli_timeout_ms() -> int:
    value = os.getenv("RIGOL_CLI_TIMEOUT_MS", "30000")
    try:
        timeout_ms = int(value)
    except ValueError:
        timeout_ms = 30000
    return max(timeout_ms, 1000)


def parse_lock_timeout_ms() -> int:
    value = os.getenv("RIGOL_LOCK_TIMEOUT_MS", "5000")
    try:
        timeout_ms = int(value)
    except ValueError:
        timeout_ms = 5000
    return max(timeout_ms, 0)


def command_uses_instrument(argv: list[str]) -> bool:
    return bool(argv) and argv[0] in INSTRUMENT_COMMANDS


class InstrumentLock:
    def __init__(self, path: Path):
        self.path = path
        self.handle = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.lockf(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.handle.close()
            self.handle = None
            raise
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(f"pid={os.getpid()} acquired_at={datetime.now().isoformat()}\n")
        self.handle.flush()

    def release(self) -> None:
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.lockf(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None


@contextmanager
def acquire_instrument_lock(timeout_ms: int | None = None):
    timeout_ms = parse_lock_timeout_ms() if timeout_ms is None else max(timeout_ms, 0)
    lock_path = Path(os.getenv("RIGOL_LOCK_PATH", "outputs/logs/rigol_ds6064.lock"))
    lock = InstrumentLock(lock_path)
    deadline = time.monotonic() + timeout_ms / 1000.0
    while True:
        try:
            lock.acquire()
            break
        except OSError:
            if timeout_ms == 0 or time.monotonic() >= deadline:
                fail(
                    f"Instrument is busy; could not acquire lock {lock_path} within {timeout_ms} ms",
                    code=75,
                )
            time.sleep(0.1)
    try:
        yield
    finally:
        lock.release()


def run_with_watchdog(argv: list[str]) -> None:
    if not argv or argv[0] in {"-h", "--help"}:
        main(argv)
        return

    if command_uses_instrument(argv):
        with acquire_instrument_lock():
            run_worker_with_watchdog(argv)
        return

    run_worker_with_watchdog(argv)


def run_worker_with_watchdog(argv: list[str]) -> None:

    command = [sys.executable, __file__, "--worker", *argv]
    timeout_s = parse_cli_timeout_ms() / 1000.0
    env = os.environ.copy()
    trace_path = None
    if argv and argv[0] == "probe-open":
        trace_path = Path("outputs/logs/probe_open_last.jsonl")
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text("", encoding="utf-8")
        env["RIGOL_PROBE_TRACE_PATH"] = str(trace_path)
    proc = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=Path.cwd(),
        env=env,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        kill_process_tree(proc.pid)
        fail(
            f"Instrument command timed out after {timeout_s:.1f}s",
            code=124,
            data=read_probe_trace(trace_path) if trace_path is not None else None,
        )

    if stdout.strip():
        print(stdout, end="")
    elif proc.returncode != 0:
        error = stderr.strip() or f"Worker exited with code {proc.returncode}"
        fail(error, code=proc.returncode)

    if stderr.strip():
        print(stderr, file=sys.stderr, end="")

    sys.exit(proc.returncode)


def kill_process_tree(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return
    try:
        os.kill(pid, 9)
    except OSError:
        pass


def read_probe_trace(path: Path) -> dict:
    stages = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                stages.append(json.loads(line))
            except json.JSONDecodeError:
                stages.append({"stage": "trace_parse_error", "raw": line})
    return {"probe_trace_path": str(path), "stages": stages}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safe CLI for RIGOL DS6064 oscilloscope over USB-TMC",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="List VISA resources")
    sub.add_parser("latest", help="Return the latest capture manifest")
    p_health = sub.add_parser("health", help="Run a read-only link health check")
    p_health.add_argument("--channels", nargs="+", default=["CHANnel1", "CHANnel2", "CHANnel3"])
    p_health.add_argument("--points", type=int, default=64)
    p_probe_open = sub.add_parser("probe-open", help="Diagnose VISA resource opening in timed read-only stages")
    p_probe_open.add_argument("--access-mode", default=None, help="VISA access mode: no_lock, shared_lock, exclusive_lock, or default")
    p_probe_open.add_argument("--open-timeout-ms", type=int, default=None, help="Override VISA open timeout for this probe")
    p_probe_open.add_argument("--query-idn", action="store_true", help="Query *IDN? after opening the resource")
    sub.add_parser("idn", help="Query *IDN?")
    sub.add_parser("run", help="Start acquisition")
    sub.add_parser("stop", help="Stop acquisition")
    sub.add_parser("single", help="Run one acquisition")
    sub.add_parser("autoscale", help="Request oscilloscope autoscale")

    for cmd in ["vpp", "freq", "period", "duty"]:
        p = sub.add_parser(cmd)
        p.add_argument("--channel", default="CHANnel1")

    p_summary = sub.add_parser("summary")
    p_summary.add_argument("--channel", default="CHANnel1")
    p_summary.add_argument("--points", type=int, default=1200)

    p_capture = sub.add_parser("capture")
    p_capture.add_argument("--channel", default="CHANnel1")
    p_capture.add_argument("--points", type=int, default=1200)

    p_capture_multi = sub.add_parser("capture-multi")
    p_capture_multi.add_argument("--channels", nargs="+", default=["CHANnel1", "CHANnel2", "CHANnel3"])
    p_capture_multi.add_argument("--points", type=int, default=1200)

    p_diag = sub.add_parser("diagnose-channel")
    p_diag.add_argument("--channel", default="CHANnel1")
    p_diag.add_argument("--points", type=int, default=1200)

    p_pwm = sub.add_parser("analyze-pwm")
    p_pwm.add_argument("--channel", default="CHANnel1")
    p_pwm.add_argument("--points", type=int, default=1200)
    p_pwm.add_argument("--save", action="store_true", help="Save captured CSV and PNG alongside the analysis")

    p_pwm_file = sub.add_parser("analyze-pwm-file")
    p_pwm_file.add_argument("--csv", required=True, help="CSV captured by the capture or analyze-pwm command")
    p_pwm_file.add_argument("--sample-interval-s", type=float, default=None, help="Override sample interval when CSV has no time_s column")
    p_pwm_file.add_argument("--save", action="store_true", help="Save a PNG next to the CSV")
    return parser


def list_resources() -> None:
    import pyvisa

    rm = pyvisa.ResourceManager()
    try:
        ok({"resources": list(rm.list_resources())})
    finally:
        rm.close()


def list_visa_resources_data() -> dict:
    import pyvisa

    rm = pyvisa.ResourceManager()
    try:
        resources = list(rm.list_resources())
        return {"ok": True, "resources": resources}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "resources": []}
    finally:
        rm.close()


def probe_open_resource_data(
    *,
    access_mode: str | None = None,
    open_timeout_ms: int | None = None,
    query_idn: bool = False,
) -> dict:
    import pyvisa
    from rigol_ds6064 import resolve_visa_access_mode

    config = ScopeConfig.from_env()
    if access_mode is not None:
        config = ScopeConfig(
            resource=config.resource,
            timeout_ms=config.timeout_ms,
            clear_on_connect=config.clear_on_connect,
            visa_access_mode=access_mode,
        )
    if open_timeout_ms is not None:
        if open_timeout_ms <= 0:
            raise ValueError("open timeout must be positive")
        config = ScopeConfig(
            resource=config.resource,
            timeout_ms=open_timeout_ms,
            clear_on_connect=config.clear_on_connect,
            visa_access_mode=config.visa_access_mode,
        )

    stages: list[dict] = []
    started = time.monotonic()
    rm = None
    inst = None

    def stage(name: str, ok_value: bool, **extra) -> None:
        item = {
            "stage": name,
            "ok": ok_value,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3),
            **extra,
        }
        stages.append(item)
        trace_path = os.getenv("RIGOL_PROBE_TRACE_PATH")
        if trace_path:
            with Path(trace_path).open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    try:
        rm = pyvisa.ResourceManager()
        stage("resource_manager", True)

        resources = list(rm.list_resources())
        stage(
            "list_resources",
            True,
            resources=resources,
            configured_resource=config.resource,
            resource_match=config.resource in resources,
        )

        open_kwargs = {"open_timeout": config.timeout_ms}
        resolved_access_mode = resolve_visa_access_mode(config.visa_access_mode)
        if resolved_access_mode is not None:
            open_kwargs["access_mode"] = resolved_access_mode
        stage(
            "open_resource_start",
            True,
            resource=config.resource,
            open_timeout_ms=config.timeout_ms,
            access_mode=config.visa_access_mode,
        )
        inst = rm.open_resource(config.resource, **open_kwargs)
        stage("open_resource", True, resource_class=inst.__class__.__name__)

        inst.timeout = config.timeout_ms
        inst.write_termination = "\n"
        inst.read_termination = "\n"
        inst.send_end = True
        stage("configure_session", True, timeout_ms=config.timeout_ms)

        identity = None
        if query_idn:
            stage("query_idn_start", True)
            identity = inst.query("*IDN?").strip()
            stage("query_idn", True, identity=identity)

        return {
            "status": "pass",
            "connection": "USB-TMC",
            "identity": identity,
            "config": {
                "resource": config.resource,
                "timeout_ms": config.timeout_ms,
                "access_mode": config.visa_access_mode,
                "clear_on_connect": config.clear_on_connect,
            },
            "stages": stages,
        }
    except Exception as exc:
        stage("error", False, error=str(exc), error_type=exc.__class__.__name__)
        return {
            "status": "fail",
            "connection": "USB-TMC",
            "config": {
                "resource": config.resource,
                "timeout_ms": config.timeout_ms,
                "access_mode": config.visa_access_mode,
                "clear_on_connect": config.clear_on_connect,
            },
            "stages": stages,
        }
    finally:
        if inst is not None:
            try:
                inst.close()
            except Exception:
                pass
        if rm is not None:
            rm.close()


def check_output_dirs() -> dict:
    results = {}
    for path in [Path("outputs/csv"), Path("outputs/images"), Path("outputs/logs"), Path("outputs/manifests")]:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".health_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            results[str(path)] = {"ok": True}
        except Exception as exc:
            results[str(path)] = {"ok": False, "error": str(exc)}
    return results


def health_status(checks: dict) -> str:
    if not checks["visa_resources"].get("ok") or not checks["identity"].get("ok"):
        return "fail"
    if not checks["resource_match"].get("ok"):
        return "fail"
    output_ok = all(item.get("ok") for item in checks["output_dirs"].values())
    channels_ok = all(item.get("capture_ok") for item in checks["channels"])
    if output_ok and channels_ok:
        return "pass"
    return "degraded"


def health_recommendations(status: str, checks: dict) -> list[str]:
    recommendations: list[str] = []
    if not checks["visa_resources"].get("ok"):
        recommendations.append("Check NI-VISA/PyVISA installation and USB-TMC driver state.")
    elif not checks["resource_match"].get("ok"):
        recommendations.append("Configured VISA resource was not found. Replug USB DEVICE or update RIGOL_SCOPE_RESOURCE in .env.")
    if not checks["identity"].get("ok"):
        recommendations.append("VISA resource is visible but *IDN? failed. Close Ultra Sigma and retry after replugging the rear USB DEVICE port.")
    for channel in checks["channels"]:
        if not channel.get("capture_ok"):
            recommendations.append(f"{channel['channel']} did not return waveform points. Run diagnose-channel for that channel and confirm it is enabled on the scope.")
    if status == "pass":
        recommendations.append("Link is healthy. Capture commands can be used directly.")
    return recommendations


def read_measurement(label: str, reader) -> dict:
    try:
        return {"value": reader(), "error": None}
    except Exception as exc:
        return {"value": None, "error": str(exc)}


def latest_manifest_path() -> Path:
    return Path("outputs/manifests/latest.json")


def read_latest_manifest() -> None:
    path = latest_manifest_path()
    if not path.exists():
        fail("No latest manifest found. Run capture, capture-multi, or analyze-pwm --save first.", code=2)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"Latest manifest is not valid JSON: {exc}", code=2)
    ok({"latest_path": str(path), "manifest": data})


def capture_manifest_base(
    *,
    command: str,
    timestamp: str,
    identity: str | None,
    points_requested: int,
    sample_interval_s: float | None,
    csv_path: Path | None,
    image_path: Path | None,
) -> dict:
    return {
        "schema_version": "1.0",
        "command": command,
        "captured_at_local": timestamp,
        "connection": "USB-TMC",
        "identity": identity,
        "points_requested": points_requested,
        "sample_interval_s": sample_interval_s,
        "files": {
            "csv_path": str(csv_path) if csv_path else None,
            "image_path": str(image_path) if image_path else None,
            "manifest_path": None,
        },
    }


def write_capture_manifest(manifest: dict, manifest_path: Path) -> Path:
    manifest.setdefault("files", {})["manifest_path"] = str(manifest_path)
    return save_json_manifest(manifest, manifest_path, latest_path=latest_manifest_path())


def scope_identity_or_none(scope: RigolDS6064) -> str | None:
    try:
        return scope.identify()
    except Exception:
        return None


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.cmd == "list":
            list_resources()
            return

        if args.cmd == "latest":
            read_latest_manifest()
            return

        if args.cmd == "health":
            args.channels = [validate_channel(channel) for channel in args.channels]
            if args.points <= 0 or args.points > 120000:
                raise ValueError("points must be between 1 and 120000")

            config = ScopeConfig.from_env()
            visa_resources = list_visa_resources_data()
            resources = visa_resources.get("resources", [])
            checks = {
                "visa_resources": visa_resources,
                "resource_match": {
                    "ok": config.resource in resources,
                    "configured_resource": config.resource,
                },
                "output_dirs": check_output_dirs(),
                "identity": {"ok": False, "error": "not_checked"},
                "channels": [],
            }

            if checks["resource_match"]["ok"]:
                scope = RigolDS6064(config).connect()
                try:
                    checks["identity"] = scope.safe_query("*IDN?")
                    for channel in args.channels:
                        diagnosis = scope.diagnose_channel(channel=channel, points=args.points)
                        parsed_points = diagnosis.get("parsed_points") or 0
                        checks["channels"].append(
                            {
                                "channel": channel,
                                "display": diagnosis.get("display"),
                                "waveform_source": diagnosis.get("waveform_source"),
                                "raw_length_bytes": diagnosis.get("raw_length_bytes"),
                                "parsed_points": parsed_points,
                                "sample_interval_s": diagnosis.get("waveform_x_increment_s"),
                                "capture_ok": parsed_points > 0,
                            }
                        )
                finally:
                    scope.close()

            status = health_status(checks)
            ok(
                {
                    "status": status,
                    "connection": "USB-TMC",
                    "checks": checks,
                    "recommendations": health_recommendations(status, checks),
                }
            )
            return

        if args.cmd == "probe-open":
            ok(
                probe_open_resource_data(
                    access_mode=args.access_mode,
                    open_timeout_ms=args.open_timeout_ms,
                    query_idn=args.query_idn,
                )
            )
            return

        if args.cmd == "analyze-pwm-file":
            values, csv_sample_interval_s = load_waveform_csv(args.csv)
            sample_interval_s = args.sample_interval_s if args.sample_interval_s is not None else csv_sample_interval_s
            if sample_interval_s is not None and sample_interval_s <= 0:
                raise ValueError("sample interval must be positive")
            analysis = analyze_pwm(values, sample_interval_s=sample_interval_s)
            data = {
                "csv_path": str(Path(args.csv)),
                "points": len(values),
                "sample_interval_s": sample_interval_s,
                "analysis": analysis,
            }
            if args.save:
                image_path = Path(args.csv).with_suffix(".png")
                plot_waveform(values, image_path, sample_interval_s=sample_interval_s)
                data["image_path"] = str(image_path)
            ok(data)
            return

        if args.cmd == "capture-multi":
            args.channels = [validate_channel(channel) for channel in args.channels]
        elif args.cmd == "diagnose-channel":
            args.channel = validate_channel(args.channel)
        elif args.cmd in MEASUREMENT_COMMANDS:
            args.channel = validate_channel(args.channel)
        if args.cmd in {"capture", "capture-multi", "diagnose-channel", "summary", "analyze-pwm"} and (args.points <= 0 or args.points > 120000):
            raise ValueError("points must be between 1 and 120000")

        scope = RigolDS6064().connect()
        try:
            if args.cmd == "idn":
                ok({"identity": scope.identify()})
            elif args.cmd == "run":
                scope.run()
                ok({"state": "running"})
            elif args.cmd == "stop":
                scope.stop()
                ok({"state": "stopped"})
            elif args.cmd == "single":
                scope.single()
                scope.wait_after_single(0.5)
                ok({"state": "single_acquisition_requested"})
            elif args.cmd == "autoscale":
                scope.autoscale()
                ok({"state": "autoscale_requested"})
            elif args.cmd == "vpp":
                ok({"channel": args.channel, "vpp_v": scope.measure_vpp(args.channel)})
            elif args.cmd == "freq":
                ok({"channel": args.channel, "frequency_hz": scope.measure_freq(args.channel)})
            elif args.cmd == "period":
                ok({"channel": args.channel, "period_s": scope.measure_period(args.channel)})
            elif args.cmd == "duty":
                ok({"channel": args.channel, "positive_duty_percent": scope.measure_duty(args.channel)})
            elif args.cmd == "summary":
                capture = scope.capture_waveform_data(channel=args.channel, points=args.points)
                values = capture["values"]
                stats = basic_waveform_stats(values)
                ok(
                    {
                        "channel": args.channel,
                        "points_requested": args.points,
                        "points_captured": len(values),
                        "sample_interval_s": capture.get("sample_interval_s"),
                        "measurement_source": "waveform_capture_stats",
                        "vpp_v": stats.get("vpp_v"),
                        "frequency_hz": None,
                        "period_s": None,
                        "positive_duty_percent": None,
                        "stats": stats,
                        "measurement_errors": {
                            "vpp_v": None,
                            "frequency_hz": "Not computed from waveform in summary mode",
                            "period_s": "Not computed from waveform in summary mode",
                            "positive_duty_percent": "Not computed from waveform in summary mode",
                        },
                    }
                )
            elif args.cmd == "capture":
                capture = scope.capture_waveform_data(channel=args.channel, points=args.points)
                values = capture["values"]
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                channel_short = args.channel.replace("CHANnel", "CH")
                csv_path = Path("outputs/csv") / f"{timestamp}_{channel_short}.csv"
                image_path = Path("outputs/images") / f"{timestamp}_{channel_short}.png"
                manifest_path = Path("outputs/manifests") / f"{timestamp}_{channel_short}.json"

                sample_interval_s = capture.get("sample_interval_s")
                stats = basic_waveform_stats(values)
                save_waveform_csv(values, csv_path, sample_interval_s=sample_interval_s)
                plot_waveform(values, image_path, sample_interval_s=sample_interval_s)
                manifest = capture_manifest_base(
                    command="capture",
                    timestamp=timestamp,
                    identity=scope_identity_or_none(scope),
                    points_requested=args.points,
                    sample_interval_s=sample_interval_s,
                    csv_path=csv_path,
                    image_path=image_path,
                )
                manifest.update(
                    {
                        "channel": args.channel,
                        "points_captured": len(values),
                        "stats": stats,
                        "preamble": capture.get("preamble"),
                    }
                )
                write_capture_manifest(manifest, manifest_path)

                ok(
                    {
                        "channel": args.channel,
                        "points_requested": args.points,
                        "points_captured": len(values),
                        "sample_interval_s": capture.get("sample_interval_s"),
                        "csv_path": str(csv_path),
                        "image_path": str(image_path),
                        "manifest_path": str(manifest_path),
                        "stats": stats,
                    }
                )
            elif args.cmd == "capture-multi":
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                channel_suffix = "_".join(channel.replace("CHANnel", "CH") for channel in args.channels)
                csv_path = Path("outputs/csv") / f"{timestamp}_{channel_suffix}_multi.csv"
                image_path = Path("outputs/images") / f"{timestamp}_{channel_suffix}_multi.png"
                manifest_path = Path("outputs/manifests") / f"{timestamp}_{channel_suffix}_multi.json"
                waveforms: dict[str, list[float]] = {}
                channel_results: list[dict] = []
                sample_intervals: list[float] = []
                preambles: dict[str, dict] = {}

                for channel in args.channels:
                    capture = scope.capture_waveform_data(channel=channel, points=args.points)
                    values = capture["values"]
                    waveforms[channel.replace("CHANnel", "CH")] = values
                    preambles[channel] = capture.get("preamble") or {}
                    sample_interval_s = capture.get("sample_interval_s")
                    if sample_interval_s and sample_interval_s > 0:
                        sample_intervals.append(sample_interval_s)
                    channel_results.append(
                        {
                            "channel": channel,
                            "points_captured": len(values),
                            "sample_interval_s": sample_interval_s,
                            "stats": basic_waveform_stats(values),
                        }
                    )

                common_sample_interval_s = sample_intervals[0] if sample_intervals else None
                if sample_intervals and any(abs(value - common_sample_interval_s) > common_sample_interval_s * 1e-6 for value in sample_intervals):
                    common_sample_interval_s = None

                save_multi_waveform_csv(waveforms, csv_path, sample_interval_s=common_sample_interval_s)
                plot_multi_waveform(waveforms, image_path, sample_interval_s=common_sample_interval_s)
                manifest = capture_manifest_base(
                    command="capture-multi",
                    timestamp=timestamp,
                    identity=scope_identity_or_none(scope),
                    points_requested=args.points,
                    sample_interval_s=common_sample_interval_s,
                    csv_path=csv_path,
                    image_path=image_path,
                )
                manifest.update(
                    {
                        "channels": args.channels,
                        "channel_results": channel_results,
                        "preambles": preambles,
                    }
                )
                write_capture_manifest(manifest, manifest_path)
                ok(
                    {
                        "channels": args.channels,
                        "points_requested": args.points,
                        "sample_interval_s": common_sample_interval_s,
                        "csv_path": str(csv_path),
                        "image_path": str(image_path),
                        "manifest_path": str(manifest_path),
                        "channel_results": channel_results,
                    }
                )
            elif args.cmd == "diagnose-channel":
                ok(scope.diagnose_channel(channel=args.channel, points=args.points))
            elif args.cmd == "analyze-pwm":
                capture = scope.capture_waveform_data(channel=args.channel, points=args.points)
                values = capture["values"]
                analysis = analyze_pwm(values, sample_interval_s=capture.get("sample_interval_s"))
                data = {
                    "channel": args.channel,
                    "points_requested": args.points,
                    "points_captured": len(values),
                    "sample_interval_s": capture.get("sample_interval_s"),
                    "analysis": analysis,
                }
                if args.save:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    channel_short = args.channel.replace("CHANnel", "CH")
                    csv_path = Path("outputs/csv") / f"{timestamp}_{channel_short}_pwm.csv"
                    image_path = Path("outputs/images") / f"{timestamp}_{channel_short}_pwm.png"
                    manifest_path = Path("outputs/manifests") / f"{timestamp}_{channel_short}_pwm.json"
                    sample_interval_s = capture.get("sample_interval_s")
                    save_waveform_csv(values, csv_path, sample_interval_s=sample_interval_s)
                    plot_waveform(values, image_path, sample_interval_s=sample_interval_s)
                    manifest = capture_manifest_base(
                        command="analyze-pwm",
                        timestamp=timestamp,
                        identity=scope_identity_or_none(scope),
                        points_requested=args.points,
                        sample_interval_s=sample_interval_s,
                        csv_path=csv_path,
                        image_path=image_path,
                    )
                    manifest.update(
                        {
                            "channel": args.channel,
                            "points_captured": len(values),
                            "analysis": analysis,
                            "preamble": capture.get("preamble"),
                        }
                    )
                    write_capture_manifest(manifest, manifest_path)
                    data["csv_path"] = str(csv_path)
                    data["image_path"] = str(image_path)
                    data["manifest_path"] = str(manifest_path)
                ok(data)
        finally:
            scope.close()
    except Exception as exc:
        fail(str(exc))


if __name__ == "__main__":
    cli_args = sys.argv[1:]
    if "--worker" in cli_args:
        worker_index = cli_args.index("--worker")
        main(cli_args[:worker_index] + cli_args[worker_index + 1:])
    else:
        run_with_watchdog(cli_args)
