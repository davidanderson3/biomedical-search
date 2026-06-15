# Public Search Docker Deployment

This Compose deployment runs the release-candidate search interface with a local Elasticsearch container.

It does not make the RC fully self-contained. The app still mounts this repository because the runtime payload is multi-GB and includes UMLS-derived licensed indexes under `build/`.

## Requirements

- Docker Desktop or Docker Engine with Compose
- local `build/` payload from the RC manifest
- local Hugging Face cache for `cambridgeltl/SapBERT-from-PubMedBERT-fulltext`
- enough memory for Elasticsearch plus the Python search process

Recommended local resources:

- at least 12 GB RAM available to Docker
- 20 GB free disk for Elasticsearch data plus temporary bulk export files

## Start Elasticsearch

```sh
docker compose -f docker/public-search/docker-compose.yml up -d elasticsearch
```

## Load The SapBERT Search Index

```sh
docker compose -f docker/public-search/docker-compose.yml --profile load run --rm elastic-loader
```

This exports the current SapBERT vector shards to temporary Elasticsearch bulk files, loads them into `qe-scaling-sapbert-cls`, and deletes the temporary bulk files after each shard loads.

## Start The Interface

```sh
docker compose -f docker/public-search/docker-compose.yml up app
```

The app waits for the Elasticsearch container healthcheck and then waits for the
configured index to answer `_count` before enforcing `--require-elasticsearch`.
If the index has not been loaded, startup fails with an explicit readiness
message after the configured timeout.

Open:

```text
http://127.0.0.1:8766
```

For an unauthenticated/public web deployment, force public-safe API output:

```sh
PUBLIC_OUTPUT_ONLY=1 docker compose -f docker/public-search/docker-compose.yml up app
```

This still allows restricted/local source-vocabulary artifacts to participate in
backend retrieval and ranking, but the API omits source-code mappings and only
returns display labels, definitions, and MRREL relation rows from the configured
public display source allowlist.

## Low-Disk Interface Mode

If you do not currently have space for an Elasticsearch data volume and bulk-load staging files, you can run the interface container with Elasticsearch disabled:

```sh
docker compose -f docker/public-search/docker-compose.yml --profile low-disk up app-local-scan
```

Keep `app-local-scan` at the end of the command. Running `--profile low-disk up` without the service name also starts the default Elasticsearch-backed services.

Open:

```text
http://127.0.0.1:8766
```

For public-safe low-disk mode:

```sh
PUBLIC_OUTPUT_ONLY=1 docker compose -f docker/public-search/docker-compose.yml --profile low-disk up app-local-scan
```

This avoids the extra Elasticsearch copy of the vectors. It still mounts the existing local `build/` payload and uses local vector scanning, so searches are expected to be slower than the Elasticsearch-backed mode.

To reduce local scan memory and startup cost, run only the core shards:

```sh
LOCAL_SCAN_PROFILE=core docker compose -f docker/public-search/docker-compose.yml --profile low-disk up app-local-scan
```

## Useful Checks

```sh
curl -fsS http://127.0.0.1:9200/qe-scaling-sapbert-cls/_count
curl -fsS http://127.0.0.1:8766/api/health
```

Expected index count is about `474,543` records.

In low-disk mode, only the `/api/health` check applies because Elasticsearch is intentionally disabled.

## Configuration

Environment variables:

- `ELASTIC_IMAGE`: Elasticsearch image, default `docker.elastic.co/elasticsearch/elasticsearch:8.15.3`
- `ES_JAVA_OPTS`: Elasticsearch heap, default `-Xms4g -Xmx4g`
- `ELASTIC_INDEX`: target index, default `qe-scaling-sapbert-cls`
- `ELASTIC_STARTUP_TIMEOUT`: app wait time for the Elasticsearch index, default `180` seconds in Compose
- `APP_PORT`: host port for the UI/API, default `8766`
- `ELASTIC_PORT`: host port for Elasticsearch, default `9200`
- `BULK_DOCS_PER_FILE`: temporary bulk part size, default `25000`
- `LOCAL_SCAN_PROFILE`: low-disk mode shard set, `full` or `core`, default `full`
- `MAX_SEQ_LENGTH`: SapBERT max sequence length, default `128`
- `PUBLIC_OUTPUT_ONLY`: set to `1` for public-safe API output filtering; Compose defaults to `1`
- `PUBLIC_OUTPUT_SOURCE_ALLOWLIST`: optional source allowlist file mounted in the container

## Boundary

This is the intended portable local deployment shape for the interface. It still requires licensed local payload files and does not redistribute raw UMLS files, raw copyrighted full text, or restricted clinical artifacts.
