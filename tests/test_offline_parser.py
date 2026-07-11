from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC))

from rigol_ds6064 import parse_ascii_waveform, parse_waveform_payload, scale_waveform_values, validate_channel
from safety import assert_safe_scpi
from waveform_analysis import analyze_pwm, basic_waveform_stats, load_waveform_csv, save_json_manifest, save_multi_waveform_csv, save_waveform_csv


class OfflineParserTests(unittest.TestCase):
    def test_parse_ascii_waveform_ignores_non_numeric_tokens(self):
        self.assertEqual(parse_ascii_waveform("1.0,2.5,bad,-3"), [1.0, 2.5, -3.0])

    def test_parse_ascii_waveform_strips_ieee_block_header(self):
        self.assertEqual(parse_ascii_waveform("#2131.0,2.0,-3.0"), [1.0, 2.0, -3.0])

    def test_parse_waveform_payload_binary_fallback(self):
        self.assertEqual(parse_waveform_payload(b"#3004\x00\x7f\x80\xff"), [0.0, 127.0, 128.0, 255.0])

    def test_parse_waveform_payload_ascii_decodable_binary_fallback(self):
        self.assertEqual(parse_waveform_payload(b"#3004\x14\x12\x15\x16"), [20.0, 18.0, 21.0, 22.0])

    def test_scale_waveform_values_uses_preamble_y_fields(self):
        preamble = "0,0,1200,1,0,1,0,0.02,0,128"
        self.assertEqual(scale_waveform_values([128.0, 130.0], preamble), [0.0, 0.04])

    def test_analyze_pwm_estimates_period_frequency_and_duty(self):
        values = []
        for _ in range(5):
            values.extend([0.0] * 6)
            values.extend([3.3] * 4)
        result = analyze_pwm(values, sample_interval_s=1e-6)
        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["period_samples"], 10.0)
        self.assertAlmostEqual(result["frequency_hz"], 100000.0)
        self.assertAlmostEqual(result["duty_percent"], 40.0)

    def test_validate_channel_rejects_unknown_channel(self):
        with self.assertRaises(ValueError):
            validate_channel("CH1")

    def test_safe_scpi_blocks_destructive_patterns(self):
        with self.assertRaises(PermissionError):
            assert_safe_scpi("*RST")
        with self.assertRaises(PermissionError):
            assert_safe_scpi(":DISK:DELete")

    def test_basic_waveform_stats(self):
        stats = basic_waveform_stats([0.0, 1.0, 3.0])
        self.assertEqual(stats["points"], 3)
        self.assertEqual(stats["min_v"], 0.0)
        self.assertEqual(stats["max_v"], 3.0)
        self.assertEqual(stats["vpp_v"], 3.0)

    def test_save_waveform_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = save_waveform_csv([1.0, 2.0], Path(tmp) / "wave.csv")
            with output.open(newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f))
        self.assertEqual(rows, [["index", "voltage_v"], ["0", "1.0"], ["1", "2.0"]])

    def test_save_and_load_waveform_csv_with_time_axis(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = save_waveform_csv([1.0, 2.0, 3.0], Path(tmp) / "wave.csv", sample_interval_s=2e-6)
            values, sample_interval_s = load_waveform_csv(output)
        self.assertEqual(values, [1.0, 2.0, 3.0])
        self.assertAlmostEqual(sample_interval_s, 2e-6)

    def test_load_waveform_csv_without_time_axis(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = save_waveform_csv([1.0, 2.0], Path(tmp) / "wave.csv")
            values, sample_interval_s = load_waveform_csv(output)
        self.assertEqual(values, [1.0, 2.0])
        self.assertIsNone(sample_interval_s)

    def test_save_multi_waveform_csv_pads_short_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = save_multi_waveform_csv(
                {"CH1": [1.0, 2.0], "CH2": [3.0]},
                Path(tmp) / "multi.csv",
                sample_interval_s=1e-6,
            )
            with output.open(newline="", encoding="utf-8") as f:
                rows = list(csv.reader(f))
        self.assertEqual(rows[0], ["index", "time_s", "CH1_voltage_v", "CH2_voltage_v"])
        self.assertEqual(rows[1], ["0", "0.0", "1.0", "3.0"])
        self.assertEqual(rows[2], ["1", "1e-06", "2.0", ""])

    def test_save_json_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = save_json_manifest({"schema_version": "1.0", "ok": True}, Path(tmp) / "manifest.json")
            text = output.read_text(encoding="utf-8")
        self.assertIn('"schema_version": "1.0"', text)
        self.assertIn('"ok": true', text)

    def test_save_json_manifest_updates_latest_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "archive" / "manifest.json"
            latest = Path(tmp) / "latest.json"
            save_json_manifest({"schema_version": "1.0", "capture": "abc"}, manifest, latest_path=latest)
            archived_text = manifest.read_text(encoding="utf-8")
            latest_text = latest.read_text(encoding="utf-8")
        self.assertEqual(archived_text, latest_text)
        self.assertIn('"capture": "abc"', latest_text)


if __name__ == "__main__":
    unittest.main()
