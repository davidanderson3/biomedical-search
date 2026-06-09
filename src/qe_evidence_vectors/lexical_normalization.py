from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from itertools import product
from pathlib import Path

from .text import normalized_key


SINGULAR_S_SUFFIXES = (
    "itis",
    "osis",
    "sis",
    "ss",
    "us",
)

SINGULAR_S_TOKENS = {
    "analysis",
    "arthritis",
    "basis",
    "cirrhosis",
    "diabetes",
    "diagnosis",
    "fibrosis",
    "mellitus",
    "psoriasis",
    "sepsis",
    "sclerosis",
    "status",
    "stenosis",
    "thrombosis",
}

SPECIALIST_TOKEN_OVERRIDES = {
    "arteries": "artery",
    "bacteria": "bacterium",
    "bacterial": "bacterium",
    "bacilli": "bacillus",
    "cocci": "coccus",
    "diagnoses": "diagnosis",
    "diagnosed": "diagnose",
    "diagnosing": "diagnose",
    "emboli": "embolus",
    "fevers": "fever",
    "indices": "index",
    "infarcted": "infarct",
    "infarcting": "infarct",
    "infarction": "infarct",
    "infarctions": "infarct",
    "infarcts": "infarct",
    "metastases": "metastasis",
    "phenomena": "phenomenon",
    "thrombi": "thrombus",
    "treated": "treat",
    "treating": "treat",
    "treats": "treat",
}

CANONICAL_SURFACE_VARIANTS = {
    "artery": {"arteries"},
    "bacterium": {"bacteria", "bacterial"},
    "diagnose": {"diagnosed", "diagnosing"},
    "diagnosis": {"diagnoses"},
    "embolus": {"emboli"},
    "fever": {"fevers"},
    "infarct": {"infarcted", "infarcting", "infarction", "infarctions", "infarcts"},
    "metastasis": {"metastases"},
    "thrombus": {"thrombi"},
    "treat": {"treated", "treating", "treats"},
}


def lexical_token_key(token: str) -> str:
    token = normalized_key(token)
    if not token:
        return ""
    override = SPECIALIST_TOKEN_OVERRIDES.get(token)
    if override:
        return override
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith("ves") and len(token) > 5:
        return f"{token[:-3]}f"
    if token.endswith("ing") and len(token) > 6:
        stem = token[:-3]
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            stem = stem[:-1]
        if f"{stem}e" in SPECIALIST_TOKEN_OVERRIDES:
            return SPECIALIST_TOKEN_OVERRIDES[f"{stem}e"]
        return SPECIALIST_TOKEN_OVERRIDES.get(stem, stem)
    if token.endswith("ed") and len(token) > 5:
        stem = token[:-2]
        if len(stem) >= 2 and stem[-1] == stem[-2]:
            stem = stem[:-1]
        if f"{stem}e" in SPECIALIST_TOKEN_OVERRIDES:
            return SPECIALIST_TOKEN_OVERRIDES[f"{stem}e"]
        return SPECIALIST_TOKEN_OVERRIDES.get(stem, stem)
    if (
        token.endswith("s")
        and len(token) > 4
        and token not in SINGULAR_S_TOKENS
        and not token.endswith(SINGULAR_S_SUFFIXES)
    ):
        return SPECIALIST_TOKEN_OVERRIDES.get(token[:-1], token[:-1])
    return token


def lexical_normalized_tokens(text: str) -> list[str]:
    return [
        token
        for raw_token in normalized_key(text).split()
        if (token := lexical_token_key(raw_token))
    ]


def lexical_normalized_key(text: str) -> str:
    return " ".join(lexical_normalized_tokens(text))


def lexical_variant_keys(text: str) -> list[str]:
    keys: list[str] = []
    seen: set[str] = set()
    for key in (normalized_key(text), lexical_normalized_key(text)):
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def lexical_lookup_keys(text: str, *, max_keys: int = 16) -> list[str]:
    keys = lexical_variant_keys(text)
    seen = set(keys)
    tokens = lexical_normalized_tokens(text)
    if not tokens:
        return keys
    variant_lists: list[list[str]] = []
    variant_token_count = 0
    for token in tokens:
        variants = sorted(CANONICAL_SURFACE_VARIANTS.get(token, set()))
        if variants:
            variant_token_count += 1
        variant_lists.append([token, *variants])
    if variant_token_count > 3:
        return keys
    for combo in product(*variant_lists):
        key = " ".join(combo)
        if key and key not in seen:
            seen.add(key)
            keys.append(key)
            if len(keys) >= max_keys:
                break
    return keys


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_lvg_dir() -> Path:
    return repo_root() / "build" / "vendor" / "lvg2026lite"


def resolve_lvg_dir(value: str | Path | None = None) -> Path | None:
    raw = value or os.environ.get("QE_LVG_DIR")
    path = Path(raw).expanduser() if raw else default_lvg_dir()
    return path if path.exists() else None


def resolve_java_bin(value: str | Path | None = None) -> Path | None:
    raw = value or os.environ.get("QE_JAVA")
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw).expanduser())
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        candidates.append(Path(java_home).expanduser() / "bin" / "java")
    candidates.extend(sorted((repo_root() / "build" / "vendor").glob("jdk-*-jre/Contents/Home/bin/java")))
    system_java = shutil.which("java")
    if system_java:
        candidates.append(Path(system_java))
    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return candidate
    return None


def lvg_is_available(
    *,
    lvg_dir: str | Path | None = None,
    java_bin: str | Path | None = None,
) -> bool:
    return bool(resolve_lvg_dir(lvg_dir) and resolve_java_bin(java_bin))


@lru_cache(maxsize=512)
def lvg_normalized_key(
    text: str,
    *,
    lvg_dir: str | Path | None = None,
    java_bin: str | Path | None = None,
    timeout: float = 10.0,
) -> str:
    return lvg_normalize_lines(
        [text],
        lvg_dir=lvg_dir,
        java_bin=java_bin,
        timeout=timeout,
    )[0]


def lvg_normalize_lines(
    lines: list[str],
    *,
    lvg_dir: str | Path | None = None,
    java_bin: str | Path | None = None,
    timeout: float = 10.0,
) -> list[str]:
    resolved_lvg = resolve_lvg_dir(lvg_dir)
    resolved_java = resolve_java_bin(java_bin)
    if not resolved_lvg or not resolved_java:
        return [lexical_normalized_key(line) for line in lines]
    payload = "\n".join(str(line or "") for line in lines) + "\n"
    cmd = [
        str(resolved_java),
        "-Xms32m",
        "-Xmx128m",
        "-classpath",
        f".:lib/lvg2026dist.jar",
        "gov.nih.nlm.nls.lvg.Tools.CmdLineTools.norm",
    ]
    try:
        completed = subprocess.run(
            cmd,
            input=payload,
            capture_output=True,
            cwd=resolved_lvg,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return [lexical_normalized_key(line) for line in lines]
    if completed.returncode != 0:
        return [lexical_normalized_key(line) for line in lines]
    normalized: list[str] = []
    for raw_line, output_line in zip(lines, completed.stdout.splitlines()):
        parts = output_line.split("|", 1)
        value = parts[1] if len(parts) == 2 else output_line
        normalized.append(normalized_key(value) or lexical_normalized_key(raw_line))
    while len(normalized) < len(lines):
        normalized.append(lexical_normalized_key(lines[len(normalized)]))
    return normalized
