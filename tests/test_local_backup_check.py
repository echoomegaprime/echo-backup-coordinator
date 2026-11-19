import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import local_backup_check as backup


class RestoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "source"
        self.scratch = self.root / "scratch"
        self.source.mkdir()
        self.scratch.mkdir()
        self.data = b"known sample"
        (self.source / "sample.txt").write_bytes(self.data)
        self.row = {"name": "sample.txt", "bytes": len(self.data),
                    "raw_source_and_restore_sha256": hashlib.sha256(self.data).hexdigest()}

    def test_copy_then_readback_hashes_without_modifying_source(self):
        self.assertEqual(backup.verify_sample(self.source, self.scratch, [self.row])[0]["sha256"],
                         self.row["raw_source_and_restore_sha256"])
        self.assertEqual((self.source / "sample.txt").read_bytes(), self.data)
        self.assertEqual(list(self.scratch.iterdir()), [])

    def test_content_size_path_and_duplicate_fail_closed(self):
        for records in ([dict(self.row, raw_source_and_restore_sha256="0"*64)],
                        [dict(self.row, bytes=1)], [dict(self.row, bytes=128)],
                        [dict(self.row, name="../sample.txt")], [dict(self.row, name="CON.txt")],
                        [self.row, self.row]):
            with self.subTest(records=records), self.assertRaises(ValueError):
                backup.verify_sample(self.source, self.scratch, records)
            self.assertEqual(list(self.scratch.iterdir()), [])

    def test_cli_rejects_same_device_before_reading_manifest(self):
        observed = backup.capacity(self.source)
        with patch.object(sys, "argv", ["check", "--source", str(self.source), "--scratch", str(self.scratch),
                                       "--manifest", "unread-file", "--expect-device", observed["device"]]):
            with self.assertRaisesRegex(ValueError, "shares"):
                backup.main()


class TrendTests(unittest.TestCase):
    current = {"observed_utc": "2026-11-19T10:00:00+00:00", "host": "sample",
               "device": "42", "free_bytes": 400, "total_bytes": 1000}

    def test_dated_decline_and_non_decline(self):
        prior = dict(self.current, observed_utc="2026-11-17T10:00:00+00:00", free_bytes=600)
        self.assertEqual(backup.trend(self.current, [prior])["days_to_full"], 4)
        self.assertIsNone(backup.trend(self.current, [dict(prior, free_bytes=390)])["days_to_full"])

    def test_insufficient_history_does_not_extrapolate(self):
        recent = dict(self.current, observed_utc="2026-11-19T09:59:59+00:00")
        for history in ([], [recent]):
            self.assertEqual(backup.trend(self.current, history)["status"], "insufficient_history")

    def test_recovered_dip_is_visible_with_flat_endpoint_rate(self):
        start = dict(self.current, observed_utc="2026-11-16T10:00:00+00:00")
        dip = dict(self.current, observed_utc="2026-11-19T06:00:00+00:00", free_bytes=150)
        result = backup.trend(self.current, [dip, start, dict(dip)])
        self.assertEqual(result["net_bytes_used_per_day"], 0)
        self.assertIsNone(result["days_to_full"])
        self.assertEqual(result["capacity_window"], {
            "observations": 3, "minimum_free_bytes": 150,
            "minimum_free_utc": dip["observed_utc"], "largest_observed_drop_bytes": 250})

    def test_drawdown_requires_peak_before_trough_and_excludes_old_samples(self):
        old = dict(self.current, observed_utc="2026-10-01T10:00:00+00:00", free_bytes=0)
        low = dict(self.current, observed_utc="2026-11-19T04:00:00+02:00", free_bytes=100)
        high = dict(self.current, observed_utc="2026-11-19T03:00:00+00:00", free_bytes=600)
        result = backup.trend(self.current, [high, old, low])
        self.assertEqual(result["status"], "insufficient_history")
        self.assertEqual(result["capacity_window"], {
            "observations": 3, "minimum_free_bytes": 100,
            "minimum_free_utc": "2026-11-19T02:00:00+00:00", "largest_observed_drop_bytes": 200})

    def test_conflicting_readings_at_same_instant_fail(self):
        recent = dict(self.current, observed_utc="2026-11-19T09:00:00+00:00")
        conflicting = dict(recent, observed_utc="2026-11-19T10:00:00+01:00", free_bytes=150)
        with self.assertRaisesRegex(ValueError, "conflicting"):
            backup.trend(self.current, [recent, conflicting])

    def test_rejects_other_volume_and_invalid_time(self):
        for prior in (dict(self.current, device="other"), dict(self.current, host="other"),
                      dict(self.current, total_bytes=900), self.current):
            with self.assertRaises(ValueError):
                backup.trend(self.current, [prior])


if __name__ == "__main__":
    unittest.main()
