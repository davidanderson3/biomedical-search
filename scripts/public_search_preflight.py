#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[install {timestamp}] {message}", flush=True)


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def float_env(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return default
    try:
        return float(value)
    except ValueError:
        log(f"Ignoring invalid {name}={value!r}; expected a number.")
        return default


def memory_gib() -> float | None:
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("MemTotal:"):
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        return int(parts[1]) / (1024 * 1024)
                    except ValueError:
                        return None
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (AttributeError, OSError, ValueError):
        return None
    return (pages * page_size) / (1024**3)


def cpu_count() -> int:
    return os.cpu_count() or 1


def main() -> int:
    strict = truthy(os.environ.get("PUBLIC_SEARCH_PREFLIGHT_STRICT"))
    min_memory_gb = float_env("PUBLIC_SEARCH_MIN_MEMORY_GB", 10.0)
    min_disk_gb = float_env("PUBLIC_SEARCH_MIN_DISK_GB", 20.0)
    min_cpus = int(float_env("PUBLIC_SEARCH_MIN_CPUS", 2.0))
    build_dir = Path(os.environ.get("PUBLIC_SEARCH_PAYLOAD_BUILD_DIR", ROOT / "build")).expanduser()
    disk_path = build_dir if build_dir.exists() else ROOT

    problems: list[str] = []
    warnings: list[str] = []

    total_memory = memory_gib()
    if total_memory is None:
        warnings.append("could not determine available memory")
    elif total_memory < min_memory_gb:
        problems.append(
            f"memory is {total_memory:.1f} GiB; recommended is at least {min_memory_gb:.1f} GiB"
        )

    cpus = cpu_count()
    if cpus < min_cpus:
        warnings.append(f"CPU count is {cpus}; recommended is at least {min_cpus}")

    free_disk = shutil.disk_usage(disk_path).free / (1024**3)
    if free_disk < min_disk_gb:
        problems.append(
            f"free disk under {disk_path} is {free_disk:.1f} GiB; recommended is at least {min_disk_gb:.1f} GiB"
        )

    for warning in warnings:
        log(f"Startup warning: {warning}. Startup may be slower on this computer.")
    for problem in problems:
        log(f"Startup warning: {problem}.")

    if problems:
        advice = (
            "Ways to continue: give Docker more memory or disk space, allow more startup time with "
            "ELASTIC_STARTUP_TIMEOUT=900, then run the launcher again."
        )
        if strict:
            raise SystemExit(f"Startup check failed in strict mode. {advice}")
        log(f"Continuing with startup warnings. {advice}")
    else:
        memory_text = f"{total_memory:.1f} GiB memory" if total_memory is not None else "memory unknown"
        log(
            f"Computer resources OK: Docker can use {memory_text}, {cpus} CPU cores, "
            f"and {free_disk:.1f} GiB disk space for search files."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
