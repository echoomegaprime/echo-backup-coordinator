"""Verify a local backup sample with an independent manifest and a separate scratch volume."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import ntpath
from pathlib import Path, PureWindowsPath
import platform
import re
import shutil
import stat
import sys
import tempfile
import time


def is_link(metadata):
    return stat.S_ISLNK(metadata.st_mode) or bool(getattr(metadata, "st_file_attributes", 0) & 0x400)


def directory_path(directory):
    path = Path(directory).absolute()
    if ".." in path.parts:
        raise ValueError("directory path must not traverse parent directories")
    for parent in (*reversed(path.parents), path):
        metadata = parent.lstat()
        if is_link(metadata) or not stat.S_ISDIR(metadata.st_mode):
            raise ValueError("directory path contains a link or is not a directory")
    return path


def capacity(directory):
    root = directory_path(directory)
    device = root.stat().st_dev
    if not device:
        raise ValueError("filesystem identity unavailable")
    usage = shutil.disk_usage(root)
    return {"observed_utc": datetime.now(timezone.utc).isoformat(), "host": platform.node(),
            "device": str(device), "total_bytes": usage.total, "free_bytes": usage.free}


def trend(current, previous):
    now = datetime.fromisoformat(current["observed_utc"])
    readings = {now: current["free_bytes"]}
    for p in previous:
        if any(p[k] != current[k] for k in ("device", "host", "total_bytes")):
            raise ValueError("history belongs to another host, filesystem or capacity")
        dt = datetime.fromisoformat(p["observed_utc"])
        free = p["free_bytes"]
        if dt.tzinfo is None or dt >= now or type(free) is not int or not 0 <= free <= current["total_bytes"]:
            raise ValueError("invalid capacity history")
        if now - dt <= timedelta(days=30):
            if dt in readings and readings[dt] != free:
                raise ValueError("conflicting capacity readings at the same time")
            readings[dt] = free

    timeline = sorted(readings.items())
    first, initial_free = timeline[0]
    low_time, low_free = min(timeline, key=lambda observation: observation[1])
    peak = initial_free
    largest_drop = 0
    for _, free in timeline:
        peak = max(peak, free)
        largest_drop = max(largest_drop, peak - free)
    window = {"observations": len(timeline), "minimum_free_bytes": low_free,
              "minimum_free_utc": low_time.astimezone(timezone.utc).isoformat(),
              "largest_observed_drop_bytes": largest_drop}
    if now - first < timedelta(days=1):
        return {"status": "insufficient_history", "days_to_full": None, "capacity_window": window}
    span = (now - first).total_seconds() / 86400
    loss = (initial_free - current["free_bytes"]) / span
    return {"status": "declining" if loss > 0 else "stable_or_growing",
            "start_utc": first.isoformat(), "span_days": round(span, 3),
            "net_bytes_used_per_day": round(loss, 2),
            "days_to_full": round(current["free_bytes"] / loss, 2) if loss > 0 else None,
            "capacity_window": window}


def windows_reserved(name):
    if hasattr(ntpath, "isreserved"):
        return ntpath.isreserved(name)
    return PureWindowsPath(name).is_reserved()


def verify_sample(source, scratch, records):
    if not isinstance(records, list) or not 1 <= len(records) <= 64:
        raise ValueError("manifest must name 1 to 64 files")
    seen = set()
    expected = []
    for item in records:
        name, size, digest = item["name"], item["bytes"], item["raw_source_and_restore_sha256"]
        if (not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._ -]{0,127}", name)
                or name.endswith((".", " ")) or windows_reserved(name) or name.casefold() in seen):
            raise ValueError("invalid or duplicate sample filename")
        if type(size) is not int or not 0 <= size <= 16 * 1024 * 1024 or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError("invalid sample length or SHA-256")
        seen.add(name.casefold())
        expected.append((name, size, digest.lower()))
    if sum(x[1] for x in expected) > 64 * 1024 * 1024:
        raise ValueError("sample exceeds 64 MiB")
    checked = []
    with tempfile.TemporaryDirectory(prefix="echo-restore-", dir=scratch) as tmp:
        for name, size, digest in expected:
            origin = source / name
            metadata = origin.lstat()
            if is_link(metadata) or not stat.S_ISREG(metadata.st_mode):
                raise ValueError("sample is not a regular file directly inside the archive directory")
            copy = Path(tmp) / name
            with origin.open("rb") as reader, copy.open("xb") as writer:
                remaining = size
                while remaining:
                    chunk = reader.read(min(remaining, 1024 * 1024))
                    if not chunk:
                        raise ValueError("sample is smaller than manifest")
                    writer.write(chunk)
                    remaining -= len(chunk)
                if reader.read(1):
                    raise ValueError("sample is larger than manifest")
            with copy.open("rb") as restored:
                actual = hashlib.file_digest(restored, "sha256").hexdigest()
            if actual != digest:
                raise ValueError("restored file SHA-256 mismatch")
            checked.append({"name": name, "bytes": size, "sha256": actual})
    return checked


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--previous", type=Path, action="append", default=[],
                        help="previous JSON output of this command, from the same filesystem")
    parser.add_argument("--manifest", type=Path, help="trusted, independently retained restore receipt")
    parser.add_argument("--scratch", type=Path, help="existing scratch directory on a different volume")
    parser.add_argument("--expect-device", help="expected device value from an independently identified source")
    args = parser.parse_args()
    source = directory_path(args.source)
    observation = capacity(source)
    history = [read_json(path)["capacity"] for path in args.previous]
    result = {"capacity": observation, "trend": trend(observation, history)}
    if any(x is not None for x in (args.manifest, args.scratch, args.expect_device)):
        if args.manifest is None or args.scratch is None or args.expect_device is None:
            parser.error("supply --manifest, --scratch and --expect-device together for a restore")
        scratch = directory_path(args.scratch)
        if args.expect_device != observation["device"] or capacity(scratch)["device"] == observation["device"]:
            raise ValueError("source identity mismatch or scratch shares the source device")
        started = time.monotonic()
        checked = verify_sample(source, scratch, read_json(args.manifest)["restored_files"])
        result["sample_restore"] = {"files": checked, "bytes": sum(x["bytes"] for x in checked),
                                    "elapsed_ms": round(1000 * (time.monotonic() - started))}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (KeyError, TypeError, ValueError, OSError) as error:
        print(f"Verification failed: {error}", file=sys.stderr)
        sys.exit(1)
