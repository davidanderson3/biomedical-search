from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCKER_DIR = ROOT / "docker" / "public-search"
COMPOSE_FILE = DOCKER_DIR / "docker-compose.yml"
RC_DIR = ROOT / "build" / "release_candidates" / "rc_public_search_20260604T211825Z"
RUNTIME_MANIFEST = (
    ROOT
    / "build"
    / "release_candidates"
    / "rc_public_search_20260604T211825Z"
    / "supporting"
    / "manifests"
    / "runtime_payload_manifest.json"
)
MANIFEST_RELATIVE = (
    "build/release_candidates/rc_public_search_20260604T211825Z/"
    "supporting/manifests/runtime_payload_manifest.json"
)
OLD_MANIFEST_RELATIVE = (
    "build/release_candidates/rc_public_search_20260604T211825Z/"
    "runtime_payload_manifest.json"
)


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


def test_public_search_shell_entrypoints_parse() -> None:
    result = run_command(
        [
            "sh",
            "-n",
            str(DOCKER_DIR / "load_sapbert_elastic.sh"),
            str(DOCKER_DIR / "start_app_local_scan.sh"),
            str(ROOT / "scripts" / "start_search_quality_server.sh"),
        ]
    )

    assert result.returncode == 0, result.stderr


def test_public_search_compose_config_renders_when_compose_is_available() -> None:
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("docker CLI is not installed")

    version = run_command([docker, "compose", "version"])
    if version.returncode != 0:
        pytest.skip(f"docker compose is not available: {version.stderr.strip()}")

    for profile in ([], ["--profile", "load"], ["--profile", "low-disk"]):
        result = run_command([docker, "compose", "-f", str(COMPOSE_FILE), *profile, "config"])
        assert result.returncode == 0, result.stderr
        assert "healthcheck:" in result.stdout

    default_config = run_command([docker, "compose", "-f", str(COMPOSE_FILE), "config"]).stdout
    assert "condition: service_healthy" in default_config
    assert "ELASTIC_STARTUP_TIMEOUT: \"180\"" in default_config


def test_public_search_loader_uses_packaged_runtime_manifest() -> None:
    loader = (DOCKER_DIR / "load_sapbert_elastic.sh").read_text(encoding="utf-8")

    assert MANIFEST_RELATIVE in loader
    assert OLD_MANIFEST_RELATIVE not in loader

    if not RUNTIME_MANIFEST.exists():
        pytest.skip("runtime payload manifest is not present in this checkout")

    manifest = json.loads(RUNTIME_MANIFEST.read_text(encoding="utf-8"))
    vector_shards = manifest.get("vector_shards", [])
    document_shards = manifest.get("document_shards", [])
    assert len(vector_shards) == 13
    assert len(document_shards) == 13
    assert all((ROOT / item["path"]).exists() for item in vector_shards)
    assert all((ROOT / item["path"]).exists() for item in document_shards)


def test_public_search_low_disk_script_has_profile_controls() -> None:
    script = (DOCKER_DIR / "start_app_local_scan.sh").read_text(encoding="utf-8")

    assert 'LOCAL_SCAN_PROFILE="${LOCAL_SCAN_PROFILE:-full}"' in script
    assert 'MAX_SEQ_LENGTH="${MAX_SEQ_LENGTH:-128}"' in script
    assert 'case "$LOCAL_SCAN_PROFILE" in' in script
    assert "add_core_vectors" in script
    assert "add_full_pubmed_vectors" in script


def test_elasticsearch_app_startup_has_health_and_retry_guards() -> None:
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    app_script = (ROOT / "scripts" / "start_search_quality_server.sh").read_text(
        encoding="utf-8"
    )

    assert "_cluster/health?wait_for_status=yellow" in compose
    assert "condition: service_healthy" in compose
    assert "ELASTIC_STARTUP_TIMEOUT" in compose
    assert "wait_for_elasticsearch_index" in app_script
    assert "/_count" in app_script
    assert "--require-elasticsearch" in app_script


def test_release_candidate_has_no_shell_history_file() -> None:
    if not RC_DIR.exists():
        pytest.skip("release candidate directory is not present in this checkout")

    assert not any(RC_DIR.glob(".*history"))
