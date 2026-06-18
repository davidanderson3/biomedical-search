param(
  [ValidateSet("auto", "install", "run")]
  [string]$Mode = "auto",
  [string]$RootDir = ""
)

$ErrorActionPreference = "Stop"

if ($RootDir) {
  $rootDir = (Resolve-Path -LiteralPath $RootDir).Path
} else {
  $rootDir = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
}

$composeFile = if ($env:COMPOSE_FILE) {
  if ([System.IO.Path]::IsPathRooted($env:COMPOSE_FILE)) {
    $env:COMPOSE_FILE
  } else {
    Join-Path $rootDir $env:COMPOSE_FILE
  }
} else {
  Join-Path $rootDir "docker\umls\docker-compose.yml"
}
$appPort = if ($env:APP_PORT) { $env:APP_PORT } else { "8766" }
$elasticBuildFromShards = if ($env:ELASTIC_BUILD_FROM_SHARDS) { $env:ELASTIC_BUILD_FROM_SHARDS } else { "0" }
$elasticSnapshotRepo = if ($env:ELASTIC_SNAPSHOT_REPO) { $env:ELASTIC_SNAPSHOT_REPO } else { "qe-public-search-sapbert" }
$autoOpenBrowser = if ($env:AUTO_OPEN_BROWSER) { $env:AUTO_OPEN_BROWSER } else { "1" }
$showDockerLogs = if ($env:PUBLIC_SEARCH_SHOW_DOCKER_LOGS) { $env:PUBLIC_SEARCH_SHOW_DOCKER_LOGS } else { "0" }
$installStateFile = if ($env:INSTALL_STATE_FILE) {
  $env:INSTALL_STATE_FILE
} else {
  Join-Path $rootDir "build\.umls-search-docker-installed"
}
$openedBrowser = $false

function Write-Header {
  param([string]$Title, [string]$Subtitle = "")
  Write-Host ""
  Write-Host "============================================================" -ForegroundColor Cyan
  Write-Host "UMLS Search" -ForegroundColor White
  Write-Host $Title -ForegroundColor White
  if ($Subtitle) {
    Write-Host $Subtitle -ForegroundColor DarkGray
  }
  Write-Host "============================================================" -ForegroundColor Cyan
  Write-Host ""
}

function Write-Step {
  param([string]$Message)
  Write-Host "[setup] " -NoNewline -ForegroundColor Cyan
  Write-Host $Message
}

function Write-ProgressLine {
  param([string]$Message, [int]$Percent = 0, [string]$Activity = "UMLS Search")
  Write-Host "[progress] " -NoNewline -ForegroundColor Cyan
  Write-Host $Message
  Update-ProgressStatus $Message $Percent $Activity
}

function Update-ProgressStatus {
  param([string]$Message, [int]$Percent = 0, [string]$Activity = "UMLS Search")
  if ($Percent -ge 0) {
    Write-Progress -Activity $Activity -Status $Message -PercentComplete $Percent
  }
}

function Get-StartupProgressPercent {
  param([string]$Message)
  if ($Message -match "Phase 1/4") { return 15 }
  if ($Message -match "Phase 2/4") { return 35 }
  if ($Message -match "Phase 3/4") { return 60 }
  if ($Message -match "Copying the search database.*?([0-9]{1,3})%") {
    $copyPercent = [Math]::Min(100, [int]$Matches[1])
    return [Math]::Min(84, 60 + [int]($copyPercent * 0.24))
  }
  if ($Message -match "Phase 4/4") { return 85 }
  if ($Message -match "Loading result details|Finished loading search data") { return 92 }
  if ($Message -match "Website ready") { return 100 }
  return 10
}

function Write-Done {
  param([string]$Message)
  Write-Host "[done] " -NoNewline -ForegroundColor Green
  Write-Host $Message
}

function Write-Notice {
  param([string]$Message)
  Write-Host "[notice] " -NoNewline -ForegroundColor Yellow
  Write-Host $Message
}

function Write-ErrorLine {
  param([string]$Message)
  Write-Host "[error] " -NoNewline -ForegroundColor Red
  Write-Host $Message
}

function Pause-AndExit {
  param([int]$Code)
  Write-Host ""
  Read-Host "Press Enter to close this window" | Out-Null
  exit $Code
}

function Stop-WithMessage {
  param([string]$Label, [string]$Message)
  Write-Host "[$Label] $Message"
  Pause-AndExit 1
}

function Test-RequiredSnapshot {
  if ($env:PUBLIC_SEARCH_PAYLOAD_REPO) {
    return $true
  }
  if ($elasticBuildFromShards -eq "1") {
    return $true
  }
  $snapshotDir = if ($env:ELASTIC_SNAPSHOT_DIR) {
    $env:ELASTIC_SNAPSHOT_DIR
  } else {
    Join-Path $rootDir "build\elasticsearch_snapshots\$elasticSnapshotRepo"
  }
  if (-not (Test-Path -LiteralPath $snapshotDir -PathType Container)) {
    return $false
  }
  $file = Get-ChildItem -LiteralPath $snapshotDir -File -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
  return $null -ne $file
}

function Require-InstallPayload {
  if (Test-RequiredSnapshot) {
    return
  }
  Stop-WithMessage "install" "The packaged search database is missing from build\elasticsearch_snapshots\$elasticSnapshotRepo. UMLS Search requires that database for installation. Rebuild or replace this release package, then run this file again."
}

function Open-DockerInstallPage {
  try {
    Start-Process "https://www.docker.com/products/docker-desktop/" | Out-Null
  } catch {
  }
}

function Test-DockerReady {
  & docker info *> $null
  return $LASTEXITCODE -eq 0
}

function Start-DockerDesktop {
  try {
    Start-Process "Docker Desktop" | Out-Null
    return $true
  } catch {
  }
  $paths = @(
    "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe",
    "${env:ProgramFiles(x86)}\Docker\Docker\Docker Desktop.exe",
    "$env:LOCALAPPDATA\Docker\Docker Desktop.exe"
  )
  foreach ($path in $paths) {
    if ($path -and (Test-Path -LiteralPath $path)) {
      Start-Process -FilePath $path | Out-Null
      return $true
    }
  }
  return $false
}

function Wait-DockerDesktop {
  Write-Host -NoNewline "[install] Waiting for Docker Desktop to finish starting"
  $deadline = (Get-Date).AddSeconds(120)
  while ((Get-Date) -lt $deadline) {
    if (Test-DockerReady) {
      Write-Host ""
      Write-Host "[install] Docker Desktop is ready."
      return $true
    }
    Write-Host -NoNewline "."
    Start-Sleep -Seconds 2
  }
  Write-Host ""
  return $false
}

function Ensure-Docker {
  if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Open-DockerInstallPage
    Stop-WithMessage "install" "Docker Desktop was not found. Opening the official Docker Desktop install page. Install and start Docker Desktop, then run this file again."
  }

  & docker compose version *> $null
  if ($LASTEXITCODE -ne 0) {
    Stop-WithMessage "install" "Docker Compose is not available. Start Docker Desktop, then run this file again."
  }

  if (-not (Test-DockerReady)) {
    Write-Host "[install] Docker Desktop is installed but is not running. Starting Docker Desktop now."
    if (-not (Start-DockerDesktop) -or -not (Wait-DockerDesktop)) {
      Stop-WithMessage "install" "Docker Desktop did not become ready. If Docker shows setup prompts, finish them, then run this file again."
    }
  }
}

function Test-AppImageExists {
  Push-Location $rootDir
  try {
    $imageId = (& docker compose -f $composeFile images -q app 2>$null | Select-Object -First 1)
    if (-not $imageId) {
      return $false
    }
    $imageId = "$imageId".Trim()
    if (-not $imageId) {
      return $false
    }
    & docker image inspect $imageId *> $null
    return $LASTEXITCODE -eq 0
  } finally {
    Pop-Location
  }
}

function Strip-ComposePrefix {
  param([string]$Line)
  if ($Line -match " \|\s?(.*)$") {
    return $Matches[1]
  }
  return $Line
}

function Test-UsefulLine {
  param([string]$Message)
  $alwaysShow = @(
    "[install ",
    "Loading result details for the website.",
    "Finished loading search data:",
    "Website ready:",
    "Stopping server"
  )
  foreach ($needle in $alwaysShow) {
    if ($Message.Contains($needle)) {
      return $true
    }
  }
  return $Message -match "(?i)error|failed|cannot|missing|invalid|denied|unavailable|exited|killed|traceback|exception"
}

function Open-Browser {
  $url = "http://127.0.0.1:$appPort/"
  try {
    Start-Process $url | Out-Null
    Write-Host "[ready] Opened $url in the default browser."
  } catch {
    Write-Host "[ready] Open $url in your browser."
  }
}

function Test-AppReady {
  $url = "http://127.0.0.1:$appPort/api/health"
  try {
    $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 3
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
  } catch {
    return $false
  }
}

function Open-ReadyApp {
  if ($script:openedBrowser) {
    return
  }
  $script:openedBrowser = $true
  Write-InstallState
  Write-Done "Website is ready at http://127.0.0.1:$appPort/"
  if ($autoOpenBrowser -ne "0") {
    Open-Browser
  }
}

function Write-InstallState {
  $stateDir = Split-Path -Parent $installStateFile
  if ($stateDir) {
    New-Item -ItemType Directory -Force -Path $stateDir *> $null
  }
  @(
    "installed_at=$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))",
    "app_port=$appPort"
  ) | Set-Content -LiteralPath $installStateFile -Encoding ASCII
}

function Invoke-DockerCompose {
  param([string[]]$Arguments)
  Push-Location $rootDir
  try {
    & docker compose @Arguments
    if ($LASTEXITCODE -ne 0) {
      throw "docker compose $($Arguments -join ' ') failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }
}

function Invoke-DockerComposeQuiet {
  param([string]$Description, [string[]]$Arguments, [string]$Activity = "UMLS Search")
  Write-Step $Description
  Write-ProgressLine $Description 0 $Activity
  if ($showDockerLogs -eq "1") {
    Invoke-DockerCompose $Arguments
    return
  }

  $logFile = Join-Path ([System.IO.Path]::GetTempPath()) "umls-compose-$([System.Guid]::NewGuid().ToString('N')).log"
  Push-Location $rootDir
  try {
    & docker compose @Arguments *> $logFile
    $status = $LASTEXITCODE
  } finally {
    Pop-Location
  }

  if ($status -ne 0) {
    Write-ErrorLine "Docker reported a problem. Recent details:"
    if (Test-Path -LiteralPath $logFile) {
      Get-Content -LiteralPath $logFile -Tail 80
      Remove-Item -LiteralPath $logFile -Force -ErrorAction SilentlyContinue
    }
    throw "docker compose $($Arguments -join ' ') failed with exit code $status"
  }

  Remove-Item -LiteralPath $logFile -Force -ErrorAction SilentlyContinue
  Write-Progress -Activity $Activity -Completed
}

function Invoke-InstallOnly {
  Write-Header "Install only" "Builds the Docker image and prepares the packaged search database."
  Invoke-DockerComposeQuiet "Step 1/3: Building the UMLS Search Docker image." @("-f", $composeFile, "--profile", "load", "build", "app", "elastic-loader")
  Invoke-DockerComposeQuiet "Step 2/3: Starting the search database service." @("-f", $composeFile, "up", "-d", "elasticsearch")
  Invoke-DockerComposeQuiet "Step 3/3: Preparing the packaged search database in Docker." @("-f", $composeFile, "--profile", "load", "run", "--rm", "elastic-loader")
  Write-InstallState

  try {
    Invoke-DockerCompose @("-f", $composeFile, "stop", "elasticsearch")
  } catch {
  }

  Write-Done "Install is complete."
}

function Get-LatestAppProgress {
  Push-Location $rootDir
  try {
    $lines = & docker compose -f $composeFile logs --tail=120 app 2>$null
  } finally {
    Pop-Location
  }

  $latest = ""
  foreach ($line in $lines) {
    $message = Strip-ComposePrefix "$line"
    if (Test-UsefulLine $message) {
      $latest = $message -replace '^\[install [^\]]*\] ', '[install] '
    }
  }
  return $latest
}

function Wait-AppReady {
  $timeout = if ($env:APP_READY_TIMEOUT) { [int]$env:APP_READY_TIMEOUT } else { 900 }
  $elapsed = 0
  $latest = "Starting Docker containers."

  while ($elapsed -lt $timeout) {
    if (Test-AppReady) {
      Open-ReadyApp
      Write-Progress -Activity "UMLS Search startup" -Completed
      return 0
    }
    Start-Sleep -Seconds 5
    $elapsed += 5
    if (($elapsed % 15) -eq 0) {
      $newLatest = Get-LatestAppProgress
      if ($newLatest) {
        $latest = $newLatest
      }
      $minutes = [int]($elapsed / 60)
      $seconds = $elapsed % 60
      Write-ProgressLine ("{0:D2}:{1:D2} {2}" -f $minutes, $seconds, $latest) (Get-StartupProgressPercent $latest) "UMLS Search startup"
    }
  }

  Write-ErrorLine "UMLS Search did not become ready within ${timeout}s. Recent app logs:"
  Push-Location $rootDir
  try {
    & docker compose -f $composeFile logs --tail=80 app
  } finally {
    Pop-Location
  }
  return 1
}

function Invoke-ComposeUp {
  param([string]$BuildFlag)

  if (Test-AppReady) {
    Open-ReadyApp
    Write-Step "UMLS Search is already running."
    return 0
  }

  $composeArgs = @("-f", $composeFile, "up", "-d")
  if ($BuildFlag) {
    $composeArgs += $BuildFlag
  }
  $composeArgs += "app"

  Write-Step "Preparing UMLS Search with Docker."
  Invoke-DockerComposeQuiet "Starting Docker containers." $composeArgs "UMLS Search startup"
  return Wait-AppReady
}

Ensure-Docker

if (($Mode -eq "run" -or $Mode -eq "auto") -and (Test-AppReady)) {
  Open-ReadyApp
  exit 0
}

try {
  switch ($Mode) {
    "install" {
      Require-InstallPayload
      Write-Host "[install] Installing UMLS Search. This builds the Docker app image and prepares the search database."
      Invoke-InstallOnly
      Write-Host ""
      Write-Host "[install] UMLS Search install is complete. Use install-run-commands\run-umls-search-windows.bat to start the website."
      exit 0
    }
    "run" {
      if (-not (Test-AppImageExists)) {
        Stop-WithMessage "run" "UMLS Search is not installed yet. Run install-run-commands\install-umls-search-windows.bat first, or use start-umls-search-windows.bat to install and start automatically."
      }
      Write-Header "Starting UMLS Search" "The website will open when it is ready."
      Write-Host "[run] Starting UMLS Search. The browser will open when it is ready."
      $status = Invoke-ComposeUp "--no-build"
      Write-Host ""
      Write-Host "[run] UMLS Search is running."
      exit $status
    }
    "auto" {
      if (Test-AppImageExists) {
        Write-Header "Starting UMLS Search" "The website will open when it is ready."
        Write-Host "[run] Starting UMLS Search. The browser will open when it is ready."
        $status = Invoke-ComposeUp "--no-build"
        $label = "run"
      } else {
        Require-InstallPayload
        Write-Header "First start" "No installed app image was found; installing and starting now."
        Write-Host "[install] UMLS Search is not installed yet. Installing and starting now. The browser will open when it is ready."
        $status = Invoke-ComposeUp "--build"
        $label = "install"
      }
      Write-Host ""
      Write-Host "[$label] UMLS Search is running."
      exit $status
    }
  }
} catch {
  Write-Host ""
  Write-Host "[install] UMLS Search stopped with an error."
  Write-Host $_.Exception.Message
  Pause-AndExit 1
}
