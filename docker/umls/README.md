# UMLS Search Docker Deployment

This Compose deployment runs UMLS Search with a local Elasticsearch container.

The default `app` service is the one-command path: it verifies the runtime
payload, verifies the packaged SapBERT model under `build/models/sapbert`,
requires and restores the packaged SapBERT Elasticsearch snapshot, then starts
UMLS Search. If the snapshot is missing or cannot be restored, startup fails
with a specific error instead of switching to a slower or reduced mode.

The UMLS Search Docker distribution is intentionally not the internal
build/review workbench. Compose mounts only the UMLS Search page, static UI assets,
runtime code, selected configuration files, and `build/` search artifacts. It
does not mount the review workbench, progress dashboard, source dashboard, or
the full repository into the app container. UMLS Search also starts with
`PUBLIC_UI_ONLY=1`, which disables `/review`, `/progress`, `/source-dashboard`,
`/api/judgments`, `/api/progress`, and `/api/full-progress`.

It does not require the whole local `build/` directory. UMLS Search needs a
compact runtime payload under `build/`: compact SapBERT vector files,
gzipped concept-document JSONL shards, the packaged SapBERT model under
`build/models/sapbert`, and the public lookup/provenance SQLite indexes.
UMLS `/search` compatibility uses compact normalized term-search rows inside
`build/cui_code_index.runtime.sqlite`, semantic-type, definition, and
relationship SQLite indexes, and the full-profile source-code runtime index.
The full licensed payload also
includes a pruned raw RRF subset under `build/umls_rrf_subset/META` for local
inspection and rebuild provenance. The app does not scan those RRF files or
the larger build-time `build/cui_code_index.sqlite` on startup; the compact
SQLite indexes remain the runtime path.
If those files are hosted in a Hugging Face dataset, set
`PUBLIC_SEARCH_PAYLOAD_REPO` and Docker will download them on first startup.
For the smallest full-quality payload, host the concept-document shards as
`*_concept_documents.jsonl.gz` and compact-vector metadata as
`compact_vectors/*_sapbert_cls.metadata.jsonl.gz`; startup will read both
directly. Packaged releases must include an Elasticsearch filesystem snapshot
under `build/elasticsearch_snapshots/qe-public-search-sapbert/`; Docker restores
that already-built kNN index for full local functionality.
The packaged runtime manifest lives at `build/runtime_payload_manifest.json`;
release-candidate histories and experiment outputs are development artifacts and
are not required under `build/` for the public Docker release.

The default payload profile is `full` so the Docker release keeps source-code
lookup, CUI resolution, source asserted code mappings, and AUI rows needed for
UMLS `/search` `returnIdType=aui`, compact `/search` term matching rows, plus
the pruned UMLS RRF subset at
`build/umls_rrf_subset/META`. The public artifact is
`build/cui_code_index.runtime.sqlite`; the larger
`build/cui_code_index.sqlite` full build index is a rebuild input and is not
part of the Docker runtime payload.
Use
`PUBLIC_SEARCH_PAYLOAD_PROFILE=public-slim INCLUDE_CODE_INDEX=0` only for a
smaller package that intentionally omits the source-code resolver and raw RRF
subset.

The level-zero/category-zero package is a separate release, not an alternate
mode inside the full release folder. It uses the five curated scaling shards,
skips the source-code resolver by default, and ships with its own `build/`
payload and ordinary start/install/run launchers.

Regenerating the pruned RRF subset is an internal/source-checkout build step,
not part of this portable release. The subset is still UMLS-licensed source
data; only include it in distributions whose recipients are authorized for the
corresponding UMLS release.

## Requirements

- Docker Desktop or Docker Engine with Compose
- local compact runtime payload under `build/`, or `PUBLIC_SEARCH_PAYLOAD_REPO`
  pointing at a hosted Hugging Face dataset with that payload
- packaged Elasticsearch snapshot under
  `build/elasticsearch_snapshots/qe-public-search-sapbert/`
- internet access on first startup only when downloading a hosted runtime payload;
  packaged releases include the runtime payload and SapBERT model
- enough memory for Elasticsearch plus the Python search process

Recommended local resources:

- at least 12 GB RAM available to Docker
- 20 GB free disk for the runtime payload, packaged SapBERT model, Elasticsearch data,
  and temporary bulk export files

## Start The Interface

For a packaged release, use the clickable launcher for your operating system
from the distribution root, next to the `docker/` folder:

- macOS: double-click `start-umls-search-mac.command`
- Windows: double-click `start-umls-search-windows.bat`

The launcher opens the website in the default browser when startup is ready,
then the terminal or command window can close. UMLS Search keeps running in
Docker. Files inside the `docker/` folder are support files; leave them in
place, but users do not need to open them directly.

The start launchers choose the right path automatically: they install and start
UMLS Search the first time, then start UMLS Search directly on later runs. To
test the two paths separately, use the launchers in `install-run-commands/`:

- macOS install only: double-click
  `install-run-commands/install-umls-search-mac.command`
- macOS run only: double-click
  `install-run-commands/run-umls-search-mac.command`
- Windows install only: double-click
  `install-run-commands\install-umls-search-windows.bat`
- Windows run only: double-click
  `install-run-commands\run-umls-search-windows.bat`

The install-only launchers build the Docker image and prepare the packaged
search database, then exit without opening the website. The run-only launchers
start UMLS Search from an existing local install; they report that installation
is needed if the Docker app image is missing.

If macOS says the launcher cannot be opened because it was downloaded from the
internet, Control-click `start-umls-search-mac.command`, choose Open, then
choose Open again.

Advanced users can also start from a terminal:

```sh
docker/umls/start-umls-search.sh
```

The terminal launcher defaults to the same automatic mode. Explicit modes are
also available:

```sh
docker/umls/start-umls-search.sh --install
docker/umls/start-umls-search.sh --run
docker/umls/start-umls-search.sh --install-and-run
```

The launcher shows user-facing startup messages, opens the UMLS Search website
in the default browser when startup is ready, and then exits while Docker keeps
the website running. Docker build/container details are hidden unless there is a
problem, and install-only launchers show a short step-by-step summary instead
of raw Docker output. To choose a different host port:

```sh
APP_PORT=8767 docker/umls/start-umls-search.sh
```

To pass Compose `up` flags through the launcher:

```sh
APP_PORT=8767 docker/umls/start-umls-search.sh --build --force-recreate
```

To start without opening a browser:

```sh
AUTO_OPEN_BROWSER=0 docker/umls/start-umls-search.sh
```

To show Docker command output during launcher startup:

```sh
PUBLIC_SEARCH_SHOW_DOCKER_LOGS=1 docker/umls/start-umls-search.sh
```

To follow the running app logs after startup:

```sh
docker compose -f docker/umls/docker-compose.yml logs -f app
```

You can still run Compose directly:

```sh
docker compose -f docker/umls/docker-compose.yml up -d app
```

To stop UMLS Search later:

```sh
docker compose -f docker/umls/docker-compose.yml stop app
```

On first startup the app container:

1. Checks memory, CPU, and free disk.
2. Verifies or downloads the search data files.
3. Verifies the packaged SapBERT model in `build/models/sapbert`.
4. Restores the required prebuilt local search database.
5. Starts the UMLS Search website and API only after the search database is ready.

First startup shows progress for each phase. The app container logs also include
plain-language `[install ...]` lines that say whether Docker is checking search
files, checking the packaged SapBERT model, restoring a prebuilt search
database, waiting for Elasticsearch, skipping an already-built database, or
starting the website.

To use a hosted runtime payload:

```sh
PUBLIC_SEARCH_PAYLOAD_REPO=your-org/your-runtime-payload \
  docker compose -f docker/umls/docker-compose.yml up -d app
```

To use a smaller public-slim payload without source-code/CUI resolver mappings:

```sh
PUBLIC_SEARCH_PAYLOAD_PROFILE=public-slim INCLUDE_CODE_INDEX=0 \
PUBLIC_SEARCH_PAYLOAD_REPO=your-org/your-runtime-payload \
  docker compose -f docker/umls/docker-compose.yml up -d app
```

To force a rebuild of an existing Elasticsearch index:

```sh
FORCE_RELOAD=1 docker compose -f docker/umls/docker-compose.yml up -d app
```

## Slow Or Older Machines

Startup does not fail just because preflight sees low memory, low CPU, or low
disk; it prints warnings and continues by default. To make those warnings fail
early in automated release checks:

```sh
PUBLIC_SEARCH_PREFLIGHT_STRICT=1 docker compose -f docker/umls/docker-compose.yml up -d app
```

If Elasticsearch is just slow to start or restore, increase the timeouts:

```sh
ELASTIC_READY_TIMEOUT=900 ELASTIC_STARTUP_TIMEOUT=1200 \
  docker compose -f docker/umls/docker-compose.yml up -d app
```

If Docker memory is constrained, lower the Elasticsearch heap and expect slower
index work:

```sh
ES_JAVA_OPTS="-Xms2g -Xmx2g" \
  ELASTIC_READY_TIMEOUT=900 ELASTIC_STARTUP_TIMEOUT=1200 \
  docker compose -f docker/umls/docker-compose.yml up -d app
```

## Manual Elasticsearch Load

The app service auto-loads Elasticsearch by default. The loader can still be run
manually when needed:

```sh
docker compose -f docker/umls/docker-compose.yml --profile load run --rm elastic-loader
```

The loader restores the required prebuilt Elasticsearch snapshot from
`build/elasticsearch_snapshots/qe-public-search-sapbert/`. If the snapshot is
absent, empty, or cannot be restored, startup fails. If the target index already
has documents, the loader exits without restoring unless `FORCE_RELOAD=1` is
set.

For an unauthenticated/public web deployment, force public-safe API output:

```sh
PUBLIC_OUTPUT_ONLY=1 docker compose -f docker/umls/docker-compose.yml up -d app
```

This still allows restricted/local source-vocabulary artifacts to participate in
backend retrieval and ranking, but the API omits source-code mappings and only
returns display labels, definitions, and MRREL relation rows from the configured
public display source allowlist.

## Useful Checks

```sh
curl -fsS http://127.0.0.1:9200/qe-scaling-sapbert-cls/_count
curl -fsS http://127.0.0.1:8766/api/health
```

Expected Elasticsearch active document count is about `190,051`. The runtime
payload contains `474,543` vector rows; duplicate concept/view document IDs are
overwritten during index load.

## Configuration

Environment variables:

- `ELASTIC_IMAGE`: Elasticsearch image, default `docker.elastic.co/elasticsearch/elasticsearch:8.15.3`
- `ES_JAVA_OPTS`: Elasticsearch heap, default `-Xms4g -Xmx4g`
- `ELASTIC_INDEX`: target index, default `qe-scaling-sapbert-cls`
- `ELASTIC_READY_TIMEOUT`: loader wait time for Elasticsearch, default `600` seconds in Compose
- `ELASTIC_STARTUP_TIMEOUT`: app wait time for the Elasticsearch index, default `900` seconds in Compose
- `ELASTIC_AUTO_LOAD`: set to `0` to skip automatic index loading in the `app` container
- `ELASTIC_EXPECTED_DOCS`: expected active Elasticsearch document count, default `190051`
- `ELASTIC_SNAPSHOT_REPO`: snapshot repository name, default `qe-public-search-sapbert`
- `ELASTIC_SNAPSHOT_NAME`: snapshot name to restore, default `latest`
- `ELASTIC_SNAPSHOT_DIR`: Elasticsearch-visible snapshot directory, default `/workspace/build/elasticsearch_snapshots/qe-public-search-sapbert`
- `APP_PORT`: host port for the UI/API, default `8766`
- `ELASTIC_PORT`: host port for Elasticsearch, default `9200`
- `BULK_DOCS_PER_FILE`: temporary bulk part size, default `5000`
- `FORCE_RELOAD`: set to `1` to rebuild a non-empty Elasticsearch index
- `SAPBERT_MODEL`: SapBERT model path, default `/workspace/build/models/sapbert`
- `SAPBERT_PRELOAD`: set to `0` to skip the packaged SapBERT check in the `app` container
- `SAPBERT_ALLOW_DOWNLOAD`: set to `1` only for development-only Hugging Face downloads when `SAPBERT_MODEL` is a model id
- `SAPBERT_OFFLINE`: set to `1` to require any Hugging Face override to already be cached
- `PUBLIC_SEARCH_PAYLOAD_REPO`: optional Hugging Face dataset repo id for the compact runtime payload
- `PUBLIC_SEARCH_PAYLOAD_REPO_TYPE`: Hugging Face repo type, default `dataset`
- `PUBLIC_SEARCH_PAYLOAD_PROFILE`: `public-slim` or `full`, default `full`
- `PUBLIC_SEARCH_PAYLOAD_OFFLINE`: set to `1` to require the runtime payload to already exist locally
- `PUBLIC_SEARCH_PREFLIGHT_STRICT`: set to `1` to fail instead of warn on low resource preflight checks
- `PUBLIC_SEARCH_MIN_MEMORY_GB`: preflight memory recommendation, default `10`
- `PUBLIC_SEARCH_MIN_DISK_GB`: preflight disk recommendation, default `20`
- `PUBLIC_SEARCH_MIN_CPUS`: preflight CPU recommendation, default `2`
- `CODE_INDEX_PATH`: optional override for the SQLite code resolver; by default startup uses `build/cui_code_index.runtime.sqlite`
- `INCLUDE_CODE_INDEX`: set to `0` to skip the SQLite code resolver, default `1` in Docker
- `PUBLIC_OUTPUT_ONLY`: set to `1` for public-safe API output filtering; Compose defaults to `1`
- `PUBLIC_OUTPUT_SOURCE_ALLOWLIST`: optional source allowlist file mounted in the container
- `PUBLIC_UI_ONLY`: set to `1` to expose only the UMLS Search website/API and
  disable internal review/build pages; Compose defaults to `1`

## Boundary

This is the intended portable local deployment shape for the interface. The
runtime payload should contain only reviewed artifacts with terms appropriate
for the intended recipients. The `public-slim` profile omits raw UMLS RRF files
while keeping the full shard set. The `full` licensed profile includes only the
pruned RRF subset described above. Level-zero/category-zero must be shipped as a
separate release, not mixed into this full folder. Do not include raw
copyrighted full text or restricted clinical artifacts. Internal build/review
pages and dashboards are not part of the public Docker runtime.
