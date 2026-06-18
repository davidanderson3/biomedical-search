#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

DEFAULT_PACKAGED_SAPBERT_MODEL = ROOT / "build" / "models" / "sapbert"
REQUIRED_MODEL_FILES = (
    "config.json",
    "vocab.txt",
    "tokenizer_config.json",
    "special_tokens_map.json",
)
WEIGHT_FILES = ("model.safetensors", "pytorch_model.bin")


def log(message: str) -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[install {timestamp}] {message}", flush=True)


def truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def human_size(size: int | None) -> str:
    if size is None:
        return "unknown size"
    units = ["B", "KiB", "MiB", "GiB"]
    value = float(size)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024
    return f"{size} B"


def run_with_heartbeat(action, *, message: str, interval_seconds: int = 15):
    done = threading.Event()

    def report() -> None:
        started = time.monotonic()
        while not done.wait(interval_seconds):
            elapsed = int(time.monotonic() - started)
            log(f"{message} still downloading ({elapsed}s elapsed).")

    thread = threading.Thread(target=report, daemon=True)
    thread.start()
    try:
        return action()
    finally:
        done.set()
        thread.join(timeout=1)


def snapshot_root_for_file(path: str | Path, filename: str) -> Path:
    root = Path(path)
    for _ in Path(filename).parts:
        root = root.parent
    return root


def resolve_local_model_dir(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path


def validate_local_model_dir(path: Path) -> list[str]:
    missing = [name for name in REQUIRED_MODEL_FILES if not (path / name).exists()]
    if not any((path / name).exists() for name in WEIGHT_FILES):
        missing.append("model.safetensors or pytorch_model.bin")
    return missing


def looks_like_local_model_path(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    return (
        text.startswith("/")
        or text.startswith(".")
        or text.startswith("~")
        or text.startswith("build/")
        or text.startswith("models/")
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ensure the SapBERT medical language model is available."
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("SAPBERT_MODEL", str(DEFAULT_PACKAGED_SAPBERT_MODEL)),
        help=(
            "Local SapBERT model directory, or an explicit Hugging Face model id when "
            "--allow-download is set."
        ),
    )
    parser.add_argument(
        "--cache-dir",
        default=os.environ.get("HF_HUB_CACHE") or None,
        help="Optional Hugging Face hub cache directory. Defaults to HF_HUB_CACHE/HF_HOME/default cache.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        default=truthy(os.environ.get("SAPBERT_OFFLINE"))
        or truthy(os.environ.get("TRANSFORMERS_OFFLINE"))
        or truthy(os.environ.get("HF_HUB_OFFLINE")),
        help="Only verify that the model is already cached.",
    )
    parser.add_argument(
        "--allow-download",
        action="store_true",
        default=truthy(os.environ.get("SAPBERT_ALLOW_DOWNLOAD")),
        help="Allow downloading SapBERT from Hugging Face when it is not packaged locally.",
    )
    args = parser.parse_args()
    model_value = str(args.model or "").strip()

    local_model_dir = resolve_local_model_dir(model_value)
    if local_model_dir.exists():
        missing = validate_local_model_dir(local_model_dir)
        if missing:
            raise SystemExit(
                f"Packaged SapBERT model at {local_model_dir} is incomplete. "
                f"Missing: {', '.join(missing)}"
            )
        log(f"Packaged SapBERT model found at {local_model_dir}; continuing.")
        return 0

    if looks_like_local_model_path(model_value):
        raise SystemExit(
            f"Packaged SapBERT model is missing at {local_model_dir}. "
            "Include build/models/sapbert in the Docker runtime payload."
        )

    if not args.allow_download:
        raise SystemExit(
            f"SapBERT model {model_value!r} is not packaged locally. "
            "Set SAPBERT_MODEL to a local model directory, or set SAPBERT_ALLOW_DOWNLOAD=1 "
            "for development-only Hugging Face downloads."
        )

    try:
        from huggingface_hub import HfApi, hf_hub_download, snapshot_download
    except Exception as exc:
        raise SystemExit(
            "huggingface-hub is required to download SapBERT; install Docker requirements first"
        ) from exc

    try:
        path = snapshot_download(
            repo_id=model_value,
            cache_dir=args.cache_dir,
            local_files_only=True,
        )
        log(f"SapBERT is already saved at {path}; continuing.")
        return 0
    except Exception as local_exc:
        if args.offline:
            log("SapBERT is not saved yet, and offline mode is on. Startup cannot download it.")
            raise SystemExit(
                f"SapBERT model {model_value!r} is not available locally and offline mode is set"
            ) from local_exc

    log(
        f"SapBERT is not saved yet; downloading {model_value!r} now because "
        "SAPBERT_ALLOW_DOWNLOAD=1."
    )
    try:
        info = HfApi().model_info(model_value, files_metadata=True)
        siblings = [
            sibling
            for sibling in sorted(info.siblings, key=lambda item: item.rfilename)
            if getattr(sibling, "rfilename", "")
        ]
    except Exception as exc:
        log(
            "Could not get the SapBERT file list before downloading. "
            "Docker will use the standard downloader and print a status line while it waits."
        )
        path = run_with_heartbeat(
            lambda: snapshot_download(
                repo_id=model_value,
                cache_dir=args.cache_dir,
                local_files_only=False,
            ),
            message="SapBERT model download",
        )
        log(f"SapBERT download is complete. Saved at {path}.")
        return 0

    total_files = len(siblings)
    total_bytes = sum(
        int(sibling.size)
        for sibling in siblings
        if getattr(sibling, "size", None) is not None
    )
    log(f"SapBERT download plan: {total_files} files, about {human_size(total_bytes)} total.")
    downloaded_bytes = 0
    snapshot_root: Path | None = None
    for index, sibling in enumerate(siblings, start=1):
        filename = sibling.rfilename
        size = getattr(sibling, "size", None)
        log(f"SapBERT file {index}/{total_files}: downloading {filename} ({human_size(size)}).")
        downloaded_path = run_with_heartbeat(
            lambda filename=filename: hf_hub_download(
                repo_id=model_value,
                filename=filename,
                cache_dir=args.cache_dir,
                local_files_only=False,
            ),
            message=f"SapBERT file {index}/{total_files}: {filename}",
        )
        snapshot_root = snapshot_root or snapshot_root_for_file(downloaded_path, filename)
        if size is not None:
            downloaded_bytes += int(size)
            log(
                f"SapBERT file {index}/{total_files}: saved {filename}. "
                f"Downloaded about {human_size(downloaded_bytes)} of {human_size(total_bytes)}."
            )
        else:
            log(f"SapBERT file {index}/{total_files}: saved {filename}.")

    path = snapshot_root or Path(
        snapshot_download(
            repo_id=model_value,
            cache_dir=args.cache_dir,
            local_files_only=True,
        )
    )
    log(f"SapBERT download is complete. Saved at {path}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
