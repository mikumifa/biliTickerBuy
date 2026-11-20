$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$submoduleRoot = Join-Path $repoRoot "tools\understand-anything"
$graphPath = Join-Path $repoRoot ".understand-anything\knowledge-graph.json"

function Test-DashboardRoot {
    param([string]$Root)
    if (-not $Root) {
        return $false
    }
    return Test-Path (Join-Path $Root "packages\dashboard\package.json")
}

function Resolve-PluginRoot {
    param([string]$Root)
    if (Test-DashboardRoot $Root) {
        return (Resolve-Path $Root)
    }

    $nested = Join-Path $Root "understand-anything-plugin"
    if (Test-DashboardRoot $nested) {
        return (Resolve-Path $nested)
    }

    return $null
}

function Resolve-DashboardRoot {
    $submodulePluginRoot = Resolve-PluginRoot $submoduleRoot
    if ($submodulePluginRoot) {
        return $submodulePluginRoot
    }

    Write-Host "Understand Anything submodule is not ready. Trying to initialize it..."
    git -C $repoRoot submodule update --init --recursive tools/understand-anything
    $submodulePluginRoot = Resolve-PluginRoot $submoduleRoot
    if ($LASTEXITCODE -eq 0 -and $submodulePluginRoot) {
        return $submodulePluginRoot
    }

    $fallbacks = @(
        (Join-Path $HOME ".understand-anything\repo\understand-anything-plugin"),
        (Join-Path $HOME ".understand-anything-plugin"),
        (Join-Path $HOME "understand-anything\understand-anything-plugin")
    )

    foreach ($candidate in $fallbacks) {
        $candidatePluginRoot = Resolve-PluginRoot $candidate
        if ($candidatePluginRoot) {
            Write-Host "Using local Understand Anything checkout: $candidate"
            return $candidatePluginRoot
        }
    }

    throw @"
Could not find Understand Anything dashboard.

The submodule clone failed or is incomplete:
  $submoduleRoot

Try one of these:
  git submodule update --init --recursive tools/understand-anything
  git -C tools/understand-anything pull

If GitHub is unreachable from your network, clone the project manually or place an existing checkout at:
  $submoduleRoot
"@
}

if (-not (Test-Path $graphPath)) {
    throw "Knowledge graph not found: $graphPath. Generate or commit it first."
}

if (-not (Get-Command corepack -ErrorAction SilentlyContinue)) {
    throw "corepack was not found. Install Node.js 22 or newer and try again."
}

$dashboardRoot = Resolve-DashboardRoot
$dashboardPackage = Join-Path $dashboardRoot "packages\dashboard"

Write-Host "Installing dashboard dependencies..."
Push-Location $dashboardRoot
try {
    corepack pnpm install --frozen-lockfile
    if ($LASTEXITCODE -ne 0) {
        throw "pnpm install failed."
    }

    corepack pnpm --filter "@understand-anything/core" build
    if ($LASTEXITCODE -ne 0) {
        throw "core build failed."
    }
}
finally {
    Pop-Location
}

Write-Host "Starting Understand Anything Dashboard..."
Write-Host "Open the Dashboard URL printed by Vite, including the token query parameter."
$env:GRAPH_DIR = $repoRoot
Push-Location $dashboardPackage
try {
    corepack pnpm exec vite --host 127.0.0.1
}
finally {
    Pop-Location
}
