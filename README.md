# UMLS Search

This folder contains a packaged local UMLS Search app. It runs with Docker and
uses the search data already included in this folder.

You do not need to point the app at a separate UMLS release to use it. The raw
UMLS files were used earlier to build the packaged data under `build/`.

## Start UMLS Search

From this folder, double-click the launcher for your operating system:

- macOS: `start-umls-search-mac.command`
- Windows: `start-umls-search-windows.bat`

The launcher starts Docker if needed, starts UMLS Search, and opens the website
in your browser when it is ready. After startup, the terminal or command window
can close. UMLS Search keeps running in Docker.

If UMLS Search is already running, the launcher opens or focuses the existing
browser tab and exits.

## Install And Run Checks

To test install and run separately, use the files in `install-run-commands/`:

- macOS install only: `install-run-commands/install-umls-search-mac.command`
- macOS run only: `install-run-commands/run-umls-search-mac.command`
- Windows install only: `install-run-commands\install-umls-search-windows.bat`
- Windows run only: `install-run-commands\run-umls-search-windows.bat`

The install-only launcher builds the Docker app image and prepares the packaged
search database. The run-only launcher starts UMLS Search from an existing local
install and reports if installation is still needed.

## Release Profile

This package is the full UMLS Search release. The level-zero/category-zero
package is built and distributed as its own release, with its own `build/`
payload and ordinary start/install/run launchers. Do not combine level-zero
launchers or payload artifacts into this full release folder.

## Stop UMLS Search

You can stop UMLS Search in Docker Desktop. Look for the `umls` app/group and
stop the app container, usually named `umls-app-1`.

You can also stop it from a terminal:

```sh
docker compose -f docker/umls/docker-compose.yml stop app
```

## Requirements

- Docker Desktop
- Enough Docker memory for Elasticsearch and the search app
- The packaged `build/` folder included with this release

Recommended Docker resources: at least 12 GB RAM and 20 GB free disk.

## Documentation

The `docs/` folder contains only the user explainer and technical documentation.
Runtime website files live under `web/`.

## More Details

Advanced Docker notes are in `docker/umls/README.md`.
