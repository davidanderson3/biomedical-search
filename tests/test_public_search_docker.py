from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
DOCKER_DIR = ROOT / "docker" / "umls"
COMPOSE_FILE = DOCKER_DIR / "docker-compose.yml"
LEVEL_ZERO_COMPOSE_FILE = DOCKER_DIR / "docker-compose.level-zero.yml"
PRODUCT_HTML = ROOT / "web" / "search_quality_product.html"
PRODUCT_APP_JS = ROOT / "web" / "search_quality" / "app.js"
RELEASE_DIR = Path("/Volumes/Crucial X10/umls-search-docker-20260617T204421Z")
EXPECTED_RELEASE_SCRIPTS = [
    "ensure_public_search_payload.py",
    "ensure_sapbert_cache.py",
    "public_search_preflight.py",
    "runtime_elastic.py",
    "scaling_status.py",
    "search_quality_server.py",
    "start_search_quality_server.sh",
]
EXPECTED_RELEASE_SRC_MODULES = [
    "__init__.py",
    "clinical_query_expansion.py",
    "code_index.py",
    "compact_vectors.py",
    "compat.py",
    "definition_index.py",
    "display_names.py",
    "documents.py",
    "elastic_client.py",
    "elastic_export.py",
    "embeddings.py",
    "entity_mentions.py",
    "evidence.py",
    "external_cui_vectors.py",
    "generic_filters.py",
    "label_index.py",
    "lexical_normalization.py",
    "mrconso_labels.py",
    "provenance_index.py",
    "public_output.py",
    "relation_index.py",
    "relationship_edge_index.py",
    "research_relations.py",
    "schema.py",
    "search.py",
    "search_assertions.py",
    "search_denial.py",
    "search_execution.py",
    "search_hit_features.py",
    "search_hydration.py",
    "search_label_fallback.py",
    "search_label_scoring.py",
    "search_long_documents.py",
    "search_mrrel.py",
    "search_quality_http.py",
    "search_ranking.py",
    "search_ranking_constants.py",
    "search_related.py",
    "search_rerank.py",
    "search_role_tokens.py",
    "search_semantic_buckets.py",
    "search_semantics.py",
    "search_service.py",
    "search_tokens.py",
    "search_types.py",
    "search_utils.py",
    "semantic_profiles.py",
    "semantic_type_index.py",
    "text.py",
    "umls_search_compat.py",
    "universal_relationship.py",
]
INSTALL_RUN_DIR = ROOT / "install-run-commands"
MAC_LAUNCHER = ROOT / "start-umls-search-mac.command"
MAC_INSTALL_LAUNCHER = INSTALL_RUN_DIR / "install-umls-search-mac.command"
MAC_RUN_LAUNCHER = INSTALL_RUN_DIR / "run-umls-search-mac.command"
WINDOWS_LAUNCHER = ROOT / "start-umls-search-windows.bat"
WINDOWS_INSTALL_LAUNCHER = INSTALL_RUN_DIR / "install-umls-search-windows.bat"
WINDOWS_RUN_LAUNCHER = INSTALL_RUN_DIR / "run-umls-search-windows.bat"
FULL_RELEASE_FORBIDDEN_LEVEL_ZERO_PATHS = [
    "docker/umls/docker-compose.level-zero.yml",
    "docker/umls/start-umls-search-level-zero.sh",
    "start-umls-search-level-zero-mac.command",
    "start-umls-search-level-zero-windows.bat",
    "install-run-commands/install-umls-search-level-zero-mac.command",
    "install-run-commands/run-umls-search-level-zero-mac.command",
    "install-run-commands/install-umls-search-level-zero-windows.bat",
    "install-run-commands/run-umls-search-level-zero-windows.bat",
    "build/docker_elastic/qe-level-zero-sapbert-cls",
]
RC_DIR = ROOT / "build" / "release_candidates" / "rc_public_search_20260604T211825Z"
RUNTIME_MANIFEST = ROOT / "build" / "runtime_payload_manifest.json"
MANIFEST_RELATIVE = "build/runtime_payload_manifest.json"
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
    scripts = [
        DOCKER_DIR / "load_sapbert_elastic.sh",
        DOCKER_DIR / "mac-launcher.sh",
        DOCKER_DIR / "start_app_with_bootstrap.sh",
        DOCKER_DIR / "start-umls-search.sh",
        DOCKER_DIR / "start-umls-search-level-zero.sh",
        ROOT / "scripts" / "start_search_quality_server.sh",
        MAC_LAUNCHER,
        MAC_INSTALL_LAUNCHER,
        MAC_RUN_LAUNCHER,
    ]

    for script in scripts:
        result = run_command(["sh", "-n", str(script)])
        assert result.returncode == 0, f"{script}: {result.stderr}"


def test_public_search_click_launchers_are_present() -> None:
    readme = (DOCKER_DIR / "README.md").read_text(encoding="utf-8")

    assert MAC_LAUNCHER.exists()
    assert MAC_INSTALL_LAUNCHER.exists()
    assert MAC_RUN_LAUNCHER.exists()
    assert WINDOWS_LAUNCHER.exists()
    assert WINDOWS_INSTALL_LAUNCHER.exists()
    assert WINDOWS_RUN_LAUNCHER.exists()
    assert not (ROOT / "install-umls-search-mac.command").exists()
    assert not (ROOT / "run-umls-search-mac.command").exists()
    assert not (ROOT / "install-umls-search-windows.bat").exists()
    assert not (ROOT / "run-umls-search-windows.bat").exists()
    assert not (ROOT / "start-umls-search-level-zero-mac.command").exists()
    assert not (ROOT / "start-umls-search-level-zero-windows.bat").exists()
    assert not (INSTALL_RUN_DIR / "install-umls-search-level-zero-mac.command").exists()
    assert not (INSTALL_RUN_DIR / "run-umls-search-level-zero-mac.command").exists()
    assert not (INSTALL_RUN_DIR / "install-umls-search-level-zero-windows.bat").exists()
    assert not (INSTALL_RUN_DIR / "run-umls-search-level-zero-windows.bat").exists()
    assert not (DOCKER_DIR / "start-umls-search-mac.command").exists()
    assert not (DOCKER_DIR / "start-umls-search-windows.bat").exists()
    assert not (DOCKER_DIR / "Start Public Search.command").exists()
    assert not (DOCKER_DIR / "Start Public Search.bat").exists()
    assert MAC_LAUNCHER.stat().st_mode & 0o111
    assert MAC_INSTALL_LAUNCHER.stat().st_mode & 0o111
    assert MAC_RUN_LAUNCHER.stat().st_mode & 0o111

    mac_text = MAC_LAUNCHER.read_text(encoding="utf-8")
    mac_install_text = MAC_INSTALL_LAUNCHER.read_text(encoding="utf-8")
    mac_run_text = MAC_RUN_LAUNCHER.read_text(encoding="utf-8")
    mac_support_text = (DOCKER_DIR / "mac-launcher.sh").read_text(encoding="utf-8")

    assert "docker/umls/mac-launcher.sh" in mac_text
    assert '" auto "$@"' in mac_text
    assert '" install "$@"' in mac_install_text
    assert '" run "$@"' in mac_run_text
    assert "--install-and-run" in mac_support_text
    assert "--install" in mac_support_text
    assert "--run" in mac_support_text
    assert "--open-ready" in mac_support_text
    assert 'COMPOSE_FILE="${COMPOSE_FILE:-docker/umls/docker-compose.yml}"' in mac_support_text
    assert "ELASTIC_BUILD_FROM_SHARDS" in mac_support_text
    assert "compose_app_image_exists" in mac_support_text
    assert "install-run-commands/install-umls-search-mac.command" in mac_support_text
    assert "install-run-commands/run-umls-search-mac.command" in mac_support_text
    assert "Docker Desktop was not found" in mac_support_text
    assert "Keep this window open" not in mac_support_text
    assert "Starting UMLS Search" in mac_support_text
    assert "not installed yet" in mac_support_text
    assert "Run only" not in mac_support_text
    assert "Starts the already installed app without rebuilding" not in mac_support_text
    assert "--build" not in mac_text
    assert "public search app" not in mac_text
    assert "public search app" not in mac_support_text

    windows_text = WINDOWS_LAUNCHER.read_text(encoding="utf-8")
    windows_install_text = WINDOWS_INSTALL_LAUNCHER.read_text(encoding="utf-8")
    windows_run_text = WINDOWS_RUN_LAUNCHER.read_text(encoding="utf-8")
    windows_support_text = (DOCKER_DIR / "windows-launcher.ps1").read_text(encoding="utf-8")
    assert "windows-launcher.ps1" in windows_text
    assert "-Mode auto" in windows_text
    assert "-Mode install" in windows_install_text
    assert "-Mode run" in windows_run_text
    assert "docker\\umls\\docker-compose.yml" in windows_support_text
    assert "Invoke-InstallOnly" in windows_support_text
    assert "Test-AppImageExists" in windows_support_text
    assert "--build" in windows_support_text
    assert "--no-build" in windows_support_text
    assert "Test-AppReady" in windows_support_text
    assert "Open-ReadyApp" in windows_support_text
    assert "exit 0" in windows_support_text
    assert "Start-Process $url" in windows_support_text
    assert "PUBLIC_SEARCH_SHOW_DOCKER_LOGS" in windows_support_text
    assert "Website ready:" in windows_support_text
    assert "Docker Desktop was not found" in windows_support_text
    assert "$env:COMPOSE_FILE" in windows_support_text
    assert "ELASTIC_BUILD_FROM_SHARDS" in windows_support_text
    assert "Keep this window open" not in windows_support_text
    assert "Starting UMLS Search" in windows_support_text
    assert "not installed yet" in windows_support_text
    assert "Run only" not in windows_support_text
    assert "Starts the already installed app without rebuilding" not in windows_support_text
    assert "install-run-commands\\install-umls-search-windows.bat" in windows_support_text
    assert "install-run-commands\\run-umls-search-windows.bat" in windows_support_text
    assert "--build app" not in windows_text
    assert "public search app" not in windows_text
    assert "public search app" not in windows_support_text

    assert "start-umls-search-mac.command" in readme
    assert "start-umls-search-windows.bat" in readme
    assert "install-run-commands/install-umls-search-mac.command" in readme
    assert "install-run-commands/run-umls-search-mac.command" in readme
    assert "install-run-commands\\install-umls-search-windows.bat" in readme
    assert "install-run-commands\\run-umls-search-windows.bat" in readme
    assert "level-zero/category-zero package is a separate release" in readme
    assert "from the distribution root" in readme
    assert "UMLS Search Docker Deployment" in readme
    assert "Start Public Search" not in readme
    assert "support files" in readme
    assert "can close" in readme


def test_public_search_compose_config_renders_when_compose_is_available() -> None:
    docker = shutil.which("docker")
    if not docker:
        pytest.skip("docker CLI is not installed")

    version = run_command([docker, "compose", "version"])
    if version.returncode != 0:
        pytest.skip(f"docker compose is not available: {version.stderr.strip()}")

    for profile in ([], ["--profile", "load"]):
        result = run_command([docker, "compose", "-f", str(COMPOSE_FILE), *profile, "config"])
        assert result.returncode == 0, result.stderr
        assert "healthcheck:" in result.stdout

    default_config = run_command([docker, "compose", "-f", str(COMPOSE_FILE), "config"]).stdout
    assert "condition: service_healthy" in default_config
    assert "ELASTIC_STARTUP_TIMEOUT: \"900\"" in default_config
    assert "ELASTIC_READY_TIMEOUT: \"600\"" in default_config
    assert "ELASTIC_EXPECTED_DOCS: \"190051\"" in default_config
    assert "path.repo: /workspace/build/elasticsearch_snapshots" in default_config
    assert "SAPBERT_MODEL: /workspace/build/models/sapbert" in default_config
    assert "huggingface-cache:" not in default_config
    assert "start_app_with_bootstrap.sh" in default_config
    assert "PUBLIC_UI_ONLY: \"1\"" in default_config
    assert "/workspace/web/search_quality_product.html" in default_config
    assert "/workspace/docs/search_quality_product.html" not in default_config
    assert "/workspace/docs/search_quality_server.html" not in default_config
    assert "/workspace/docs/scaling_progress.html" not in default_config
    assert "/workspace/docs/source_evidence_dashboard.html" not in default_config

    level_zero_config = run_command(
        [docker, "compose", "-f", str(LEVEL_ZERO_COMPOSE_FILE), "config"]
    )
    assert level_zero_config.returncode == 0, level_zero_config.stderr
    assert "name: umls-level-zero" in level_zero_config.stdout
    assert "ELASTIC_INDEX: qe-level-zero-sapbert-cls" in level_zero_config.stdout
    assert "PUBLIC_SEARCH_PAYLOAD_PROFILE: level-zero" in level_zero_config.stdout
    assert "INCLUDE_CODE_INDEX: \"0\"" in level_zero_config.stdout
    assert "ELASTIC_BUILD_FROM_SHARDS: \"1\"" in level_zero_config.stdout
    assert "ELASTIC_EXPECTED_DOCS: \"60967\"" in level_zero_config.stdout
    assert "published: \"8776\"" in level_zero_config.stdout
    assert "published: \"9210\"" in level_zero_config.stdout


def test_public_search_loader_uses_packaged_runtime_manifest() -> None:
    loader = (DOCKER_DIR / "load_sapbert_elastic.sh").read_text(encoding="utf-8")

    assert MANIFEST_RELATIVE in loader
    assert OLD_MANIFEST_RELATIVE not in loader
    assert "PUBLIC_SEARCH_PAYLOAD_PROFILE" in loader
    assert "level_zero_stems" in loader
    assert "scripts/runtime_elastic.py" in loader
    assert "scripts/evidence_vectors.py" not in loader
    assert "FORCE_RELOAD" in loader
    assert "restore_elasticsearch_snapshot" in loader
    assert "ELASTIC_BUILD_FROM_SHARDS" in loader
    assert "ELASTIC_EXPECTED_DOCS" in loader
    assert "this release expects" in loader
    assert "requires the packaged search database" in loader
    assert "Copying the search database into Docker:" in loader
    assert "Could not copy the packaged search database into Docker." in loader

    if not RUNTIME_MANIFEST.exists():
        pytest.skip("runtime payload manifest is not present in this checkout")

    manifest = json.loads(RUNTIME_MANIFEST.read_text(encoding="utf-8"))
    vector_shards = manifest.get("vector_shards", [])
    document_shards = manifest.get("document_shards", [])
    assert len(vector_shards) == 13
    assert len(document_shards) == 13
    assert all((ROOT / item["path"]).exists() for item in vector_shards)
    assert all((ROOT / item["path"]).exists() for item in document_shards)


def test_public_search_release_has_no_degraded_local_scan_path() -> None:
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    readme = (DOCKER_DIR / "README.md").read_text(encoding="utf-8")

    assert not (DOCKER_DIR / "start_app_local_scan.sh").exists()
    assert "app-local-scan" not in compose
    assert "low-disk" not in compose
    assert "LOCAL_SCAN_PROFILE" not in compose
    assert "app-local-scan" not in readme
    assert "low-disk" not in readme


def test_public_search_bootstrap_downloads_payload_and_sapbert_before_start() -> None:
    script = (DOCKER_DIR / "start_app_with_bootstrap.sh").read_text(encoding="utf-8")
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    dockerfile = (DOCKER_DIR / "Dockerfile").read_text(encoding="utf-8")

    assert "ensure_public_search_payload.py" in script
    assert "ensure_sapbert_cache.py" in script
    assert "public_search_preflight.py" in script
    assert "load_sapbert_elastic.sh" in script
    assert "start_search_quality_server.sh" in script
    assert ".jsonl.gz" in (ROOT / "scripts" / "ensure_public_search_payload.py").read_text(
        encoding="utf-8"
    )
    assert "PUBLIC_SEARCH_PAYLOAD_REPO" in compose
    assert "PUBLIC_SEARCH_PAYLOAD_PROFILE" in compose
    assert "SAPBERT_MODEL: ${SAPBERT_MODEL:-/workspace/build/models/sapbert}" in compose
    assert "SAPBERT_PRELOAD" in compose
    assert "SAPBERT_ALLOW_DOWNLOAD" in compose
    assert "INCLUDE_CODE_INDEX" in compose
    assert "PUBLIC_UI_ONLY" in compose
    assert "ELASTIC_SNAPSHOT_DIR" in compose
    assert "context: ../.." in compose
    assert "dockerfile: docker/umls/Dockerfile" in compose
    assert "../..:/workspace" not in compose
    assert "search_quality_server.html:/workspace/docs/search_quality_server.html" not in compose
    assert "scaling_progress.html:/workspace/docs/scaling_progress.html" not in compose
    assert "source_evidence_dashboard.html:/workspace/docs/source_evidence_dashboard.html" not in compose
    assert "COPY web/search_quality_product.html /workspace/web/search_quality_product.html" in dockerfile
    assert "COPY web/search_quality/nih-nlm-logo.png /workspace/web/search_quality/nih-nlm-logo.png" in dockerfile
    assert "COPY docs/search_quality_product.html" not in dockerfile
    assert "COPY scripts/search_quality_server.py /workspace/scripts/search_quality_server.py" in dockerfile
    assert "COPY scripts/runtime_elastic.py /workspace/scripts/runtime_elastic.py" in dockerfile
    assert "COPY scripts/evidence_vectors.py" not in dockerfile
    assert "COPY src /workspace/src" in dockerfile

    launcher = (DOCKER_DIR / "start-umls-search.sh").read_text(encoding="utf-8")
    assert "AUTO_OPEN_BROWSER" in launcher
    assert "PUBLIC_SEARCH_SHOW_DOCKER_LOGS" in launcher
    assert 'COMPOSE_FILE="${COMPOSE_FILE:-docker/umls/docker-compose.yml}"' in launcher
    assert "open_browser" in launcher
    assert "focus_existing_browser_tab" in launcher
    assert "focus_safari_tab" in launcher
    assert "focus_chrome_tab" in launcher
    assert "focus_edge_tab" in launcher
    assert "Google Chrome" in launcher
    assert "Microsoft Edge" in launcher
    assert "Safari" in launcher
    assert "useful_line" in launcher
    assert "--install" in launcher
    assert "--install-and-run" in launcher
    assert "--run" in launcher
    assert "--open-ready" in launcher
    assert "--no-build" in launcher
    assert "--profile load build app elastic-loader" in launcher
    assert "run --rm elastic-loader" in launcher
    assert ".umls-search-docker-installed" in launcher
    assert "compose_app_image_exists" in launcher
    assert "docker compose" in launcher
    assert 'up -d "$build_flag"' in launcher
    assert 'up -d "$@" app' in launcher
    assert "wait_for_app_ready" in launcher
    assert "latest_app_progress" in launcher
    assert "Website ready:" in launcher
    assert "http://127.0.0.1:${APP_PORT}/" in launcher
    assert "Preparing UMLS Search with Docker" in launcher
    assert "start_progress_indicator" in launcher
    assert "format_elapsed" in launcher
    assert "app_ready" in launcher
    assert "open_ready_app" in launcher
    assert "/api/health" in launcher
    assert "UMLS Search is already running" in launcher
    assert "Starting Docker containers." in launcher
    assert "Detailed Docker messages are hidden" not in launcher
    assert "public search app" not in launcher

    windows_launcher = (DOCKER_DIR / "windows-launcher.ps1").read_text(encoding="utf-8")
    assert "Invoke-InstallOnly" in windows_launcher
    assert "Invoke-ComposeUp" in windows_launcher
    assert "--profile\", \"load\", \"build\", \"app\", \"elastic-loader" in windows_launcher
    assert "\"run\", \"--rm\", \"elastic-loader\"" in windows_launcher
    assert ".umls-search-docker-installed" in windows_launcher
    assert "Test-AppImageExists" in windows_launcher
    assert "Write-ProgressLine" in windows_launcher
    assert "Get-StartupProgressPercent" in windows_launcher
    assert "Test-AppReady" in windows_launcher
    assert "Open-ReadyApp" in windows_launcher
    assert "Wait-AppReady" in windows_launcher
    assert "Get-LatestAppProgress" in windows_launcher
    assert '"up", "-d"' in windows_launcher
    assert "/api/health" in windows_launcher
    assert "UMLS Search is running" in windows_launcher
    assert "Starting Docker containers." in windows_launcher
    assert "Detailed Docker messages are hidden" not in windows_launcher
    assert "$env:COMPOSE_FILE" in windows_launcher


def test_public_product_ui_excludes_internal_judgment_tools() -> None:
    product_html = PRODUCT_HTML.read_text(encoding="utf-8")
    app_js = PRODUCT_APP_JS.read_text(encoding="utf-8")

    assert "Evaluation tools and system details" not in product_html
    assert "Save judgments" not in product_html
    assert "Export judgments CSV" not in product_html
    assert 'id="querySet"' not in product_html
    assert 'id="metrics"' not in product_html

    assert "const ENABLE_JUDGMENTS = Boolean" in app_js
    assert "const ENABLE_QUERY_SET = Boolean" in app_js
    assert 'if (!ENABLE_JUDGMENTS) return "";' in app_js
    assert "if (!els.metrics) return;" in app_js
    assert "if (ENABLE_JUDGMENTS) {\n      clearLegacyJudgmentCache();\n      loadStatus().then(loadServerJudgments);" in app_js


def test_public_search_install_progress_is_explanatory() -> None:
    bootstrap = (DOCKER_DIR / "start_app_with_bootstrap.sh").read_text(encoding="utf-8")
    loader = (DOCKER_DIR / "load_sapbert_elastic.sh").read_text(encoding="utf-8")
    preflight_script = (ROOT / "scripts" / "public_search_preflight.py").read_text(
        encoding="utf-8"
    )
    payload_script = (ROOT / "scripts" / "ensure_public_search_payload.py").read_text(
        encoding="utf-8"
    )
    sapbert_script = (ROOT / "scripts" / "ensure_sapbert_cache.py").read_text(
        encoding="utf-8"
    )
    server_script = (ROOT / "scripts" / "start_search_quality_server.sh").read_text(
        encoding="utf-8"
    )
    server_py = (ROOT / "scripts" / "search_quality_server.py").read_text(encoding="utf-8")
    search_service = (ROOT / "src" / "qe_evidence_vectors" / "search_service.py").read_text(
        encoding="utf-8"
    )

    assert "[install $(" in bootstrap
    assert "Phase 1/4" in bootstrap
    assert "Phase 2/4" in bootstrap
    assert "Phase 3/4" in bootstrap
    assert "Phase 4/4" in bootstrap
    assert "Startup check" in bootstrap
    assert "checking the search data files" in bootstrap
    assert "packaged medical language model, SapBERT" in bootstrap
    assert "checking the search database" in bootstrap

    assert "Starting the search database service inside Docker" in loader
    assert "Copying the packaged search database into Docker" in loader
    assert "The packaged search database was not found" in loader
    assert "already ready" in loader
    assert "The search database is ready" in loader

    assert "Search data files found" in payload_script
    assert "PUBLIC_SEARCH_PAYLOAD_STRICT_PROFILE" in payload_script
    assert "unexpected_runtime_files" in payload_script
    assert "avoids rebuilding the data on this computer" in payload_script
    assert "Packaged SapBERT model found" in sapbert_script
    assert "Include build/models/sapbert" in sapbert_script
    assert "SAPBERT_ALLOW_DOWNLOAD=1" in sapbert_script
    assert "SapBERT download plan" in sapbert_script
    assert "SapBERT file {index}/{total_files}" in sapbert_script
    assert "still downloading" in sapbert_script
    assert "Computer resources OK" in preflight_script
    assert "PUBLIC_SEARCH_PREFLIGHT_STRICT" in preflight_script
    assert "low-disk" not in preflight_script

    assert "search database is ready" in server_script
    assert "--public-ui-only" in server_script
    assert "Loading result details for the website" in server_py
    assert "install_progress" in server_py
    assert "Loading result detail file" in search_service
    assert "Loading search result records" in search_service
    assert "Website result details are loaded" in search_service
    assert "internal review and build dashboards are disabled" not in server_py


def test_public_search_defaults_to_full_payload_with_level_zero_separate_path() -> None:
    payload_script = (ROOT / "scripts" / "ensure_public_search_payload.py").read_text(
        encoding="utf-8"
    )
    app_script = (ROOT / "scripts" / "start_search_quality_server.sh").read_text(
        encoding="utf-8"
    )
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    level_zero_compose = LEVEL_ZERO_COMPOSE_FILE.read_text(encoding="utf-8")
    level_zero_launcher = (DOCKER_DIR / "start-umls-search-level-zero.sh").read_text(
        encoding="utf-8"
    )

    assert 'PUBLIC_SEARCH_PAYLOAD_PROFILE:-full' in compose
    assert 'INCLUDE_CODE_INDEX:-1' in compose
    assert 'PUBLIC_SEARCH_PAYLOAD_PROFILE:-level-zero' in level_zero_compose
    assert 'PUBLIC_SEARCH_PAYLOAD_STRICT_PROFILE:-1' in level_zero_compose
    assert 'INCLUDE_CODE_INDEX:-0' in level_zero_compose
    assert 'ELASTIC_INDEX:-qe-level-zero-sapbert-cls' in level_zero_compose
    assert 'ELASTIC_EXPECTED_DOCS:-60967' in level_zero_compose
    assert 'ELASTIC_BUILD_FROM_SHARDS:-1' in level_zero_compose
    assert 'APP_PORT="${APP_PORT:-8776}"' in level_zero_launcher
    assert 'COMPOSE_FILE="${COMPOSE_FILE:-docker/umls/docker-compose.level-zero.yml}"' in level_zero_launcher
    assert "elasticsearch_snapshots/**" in payload_script
    assert '"level-zero": "level-zero"' in payload_script
    assert '"category-zero": "level-zero"' in payload_script
    assert 'profile == "full"' in payload_script
    assert "LEVEL_ZERO_VECTOR_STEMS" in payload_script
    assert "FULL_VECTOR_STEMS" in payload_script
    assert '"umls_rrf_subset/META/MRCONSO.RRF"' in payload_script
    assert '"umls_rrf_subset/META/MRHIER.RRF"' in payload_script
    assert '"umls_rrf_subset/META/MRSAT.RRF"' in payload_script
    assert '"umls_rrf_subset/META/*.RRF"' in payload_script
    assert '"cui_code_index.runtime.sqlite"' in payload_script
    assert '"cui_code_index.sqlite"' not in payload_script
    assert '"umls_semantic_types.sqlite"' in payload_script
    assert '"umls_definitions.sqlite"' in payload_script
    assert '"umls_research_relations.sqlite"' in payload_script
    assert '"relationship_edges.sqlite"' in payload_script
    assert '"models/sapbert/*"' in payload_script
    assert 'f"compact_vectors/{stem}_sapbert_cls.manifest.json"' in payload_script
    assert 'f"compact_vectors/{stem}_sapbert_cls.vectors.f32"' in payload_script
    assert 'f"compact_vectors/{stem}_sapbert_cls.metadata.jsonl.gz"' in payload_script
    assert 'f"{stem}_concept_documents.jsonl.gz"' in payload_script
    assert '"compact_vectors/*_sapbert_cls.*"' not in payload_script
    assert '"*_concept_vectors.sapbert_cls.jsonl"' not in payload_script
    assert '"*_concept_documents.jsonl",' not in payload_script
    assert '"*_concept_documents.jsonl.gz"' not in payload_script
    assert 'INCLUDE_CODE_INDEX="${INCLUDE_CODE_INDEX:-1}"' in app_script
    assert 'PUBLIC_SEARCH_PAYLOAD_PROFILE="${PUBLIC_SEARCH_PAYLOAD_PROFILE:-full}"' in app_script
    assert "add_level_zero_shards" in app_script
    assert "add_full_shards" in app_script
    assert "add_full_extra_shards" not in app_script
    assert 'SAPBERT_MODEL="${SAPBERT_MODEL:-build/models/sapbert}"' in app_script
    assert '--model "$SAPBERT_MODEL"' in app_script
    assert 'build/cui_code_index.runtime.sqlite' in app_script
    assert 'build/cui_code_index.sqlite' not in app_script
    assert '--umls-search-label-index build/umls_search_label_index.sqlite' not in app_script
    assert '--semantic-type-index build/umls_semantic_types.sqlite' in app_script
    assert '--definition-index build/umls_definitions.sqlite' in app_script
    assert '--research-relation-index build/umls_research_relations.sqlite' in app_script
    assert '--relationship-edge-index build/relationship_edges.sqlite' in app_script
    assert 'GZ_PATH="$1.gz"' in app_script
    assert "CODE_INDEX_ARGS" in app_script

    readme = (DOCKER_DIR / "README.md").read_text(encoding="utf-8")
    assert "build/umls_rrf_subset/META" in readme
    assert "build_pruned_umls_rrf_subset.py" not in readme
    assert "internal/source-checkout build step" in readme
    assert "start-umls-search-level-zero-mac.command" not in readme
    assert "install-umls-search-level-zero" not in readme
    assert "level-zero/category-zero package is a separate release" in readme


def test_level_zero_strict_profile_rejects_full_payload_content(tmp_path: Path) -> None:
    from scripts.ensure_public_search_payload import unexpected_runtime_files

    build_dir = tmp_path / "build"
    compact_dir = build_dir / "compact_vectors"
    compact_dir.mkdir(parents=True)
    (compact_dir / "scaling_chunk_001_gap_topics_sapbert_cls.manifest.json").write_text(
        "{}", encoding="utf-8"
    )
    (compact_dir / "pubmed_bulk_recent_baseline_sapbert_cls.manifest.json").write_text(
        "{}", encoding="utf-8"
    )
    (build_dir / "scaling_chunk_001_gap_topics_concept_documents.jsonl.gz").write_bytes(b"")
    (build_dir / "pubmed_bulk_recent_baseline_concept_documents.jsonl.gz").write_bytes(b"")
    (build_dir / "cui_code_index.runtime.sqlite").write_bytes(b"")
    (build_dir / "umls_rrf_subset").mkdir()
    (build_dir / "elasticsearch_snapshots" / "qe-public-search-sapbert").mkdir(parents=True)

    unexpected = unexpected_runtime_files(build_dir, profile="level-zero")

    assert "compact_vectors/pubmed_bulk_recent_baseline_sapbert_cls.manifest.json" in unexpected
    assert "pubmed_bulk_recent_baseline_concept_documents.jsonl.gz" in unexpected
    assert "cui_code_index.runtime.sqlite" in unexpected
    assert "umls_rrf_subset/" in unexpected
    assert "elasticsearch_snapshots/qe-public-search-sapbert/" in unexpected
    assert not any("scaling_chunk_001_gap_topics" in item for item in unexpected)


def test_elasticsearch_app_startup_has_health_and_retry_guards() -> None:
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    app_script = (ROOT / "scripts" / "start_search_quality_server.sh").read_text(
        encoding="utf-8"
    )

    assert "_cluster/health?wait_for_status=yellow" in compose
    assert "condition: service_healthy" in compose
    assert "ELASTIC_STARTUP_TIMEOUT" in compose
    assert "ELASTIC_READY_TIMEOUT" in compose
    assert "retries: 60" in compose
    assert "wait_for_elasticsearch_index" in app_script
    assert "/_count" in app_script
    assert "If this computer is slow" in app_script
    assert "--require-elasticsearch" in app_script


def test_search_ui_has_default_off_molecular_association_control() -> None:
    html = (ROOT / "docs" / "search_quality_server.html").read_text(encoding="utf-8")
    app_js = PRODUCT_APP_JS.read_text(encoding="utf-8")

    input_match = re.search(r"<input[^>]+id=\"molecularAssociations\"[^>]*>", html)
    assert input_match is not None
    molecular_input = input_match.group(0)
    assert 'type="checkbox"' in molecular_input
    assert "checked" not in molecular_input
    assert "Explore genes/proteins" in html

    assert '"molecularAssociations"' in app_js
    assert "function selectedMolecularAssociations()" in app_js
    assert "function molecularAssociationQueryParam" in app_js
    assert app_js.count("molecularAssociationQueryParam(includeMolecularAssociations)") >= 2
    assert "payload.molecular_associations_enabled" in app_js
    assert "Molecular Associations" in app_js
    assert "Molecular mode" in app_js


def test_crucial_release_docs_are_trimmed_when_present() -> None:
    if not RELEASE_DIR.exists():
        pytest.skip("Crucial release directory is not mounted")

    docs_files = sorted(
        path.relative_to(RELEASE_DIR / "docs").as_posix()
        for path in (RELEASE_DIR / "docs").rglob("*")
        if path.is_file()
    )
    assert docs_files == ["explain_like_im_5.html", "technical_pipeline.html"]
    assert (RELEASE_DIR / "web" / "search_quality_product.html").exists()
    assert (RELEASE_DIR / "web" / "search_quality" / "app.js").exists()


def test_crucial_full_release_has_no_level_zero_distribution_files_when_present() -> None:
    if not RELEASE_DIR.exists():
        pytest.skip("Crucial release directory is not mounted")

    for relative_path in FULL_RELEASE_FORBIDDEN_LEVEL_ZERO_PATHS:
        assert not (RELEASE_DIR / relative_path).exists(), relative_path


def test_crucial_release_scripts_are_runtime_only_when_present() -> None:
    if not RELEASE_DIR.exists():
        pytest.skip("Crucial release directory is not mounted")

    script_files = sorted(
        path.relative_to(RELEASE_DIR / "scripts").as_posix()
        for path in (RELEASE_DIR / "scripts").rglob("*")
        if path.is_file()
    )
    assert script_files == EXPECTED_RELEASE_SCRIPTS


def test_crucial_release_src_is_runtime_only_when_present() -> None:
    if not RELEASE_DIR.exists():
        pytest.skip("Crucial release directory is not mounted")

    src_files = sorted(
        path.relative_to(RELEASE_DIR / "src" / "qe_evidence_vectors").as_posix()
        for path in (RELEASE_DIR / "src" / "qe_evidence_vectors").glob("*.py")
    )
    assert src_files == EXPECTED_RELEASE_SRC_MODULES


def test_release_candidate_has_no_shell_history_file() -> None:
    if not RC_DIR.exists():
        pytest.skip("release candidate directory is not present in this checkout")

    assert not any(RC_DIR.glob(".*history"))
