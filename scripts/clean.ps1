<#
.SYNOPSIS
    Remove generated build artifacts from the DocumentTools workspace.

.DESCRIPTION
    Deletes directories that are produced by the build and are never tracked by
    Git (build, dist, release, caches and the legacy embedded runtime). Every
    target is resolved and verified to stay inside the repository root before
    anything is removed.

.PARAMETER KeepDist
    Keep the dist directory (useful when only intermediate files should go).

.PARAMETER KeepRelease
    Keep the release directory (useful when the installer should be preserved).
#>
param(
    [switch]$KeepDist,
    [switch]$KeepRelease
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

$targets = @(
    "build",
    "dist",
    "release",
    ".pytest_cache",
    ".pytest-tmp",
    "vendor"
)

function Remove-Target([string]$RelativePath) {
    $candidate = Join-Path $projectRoot $RelativePath
    if (-not (Test-Path -LiteralPath $candidate)) { return }
    $resolved = (Resolve-Path -LiteralPath $candidate).Path
    if (-not $resolved.StartsWith($projectRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to delete outside the project root: $resolved"
    }
    try {
        Remove-Item -LiteralPath $resolved -Recurse -Force -ErrorAction Stop
        Write-Host "Removed $resolved"
    } catch {
        Write-Warning "Could not remove ${resolved}: $($_.Exception.Message)"
    }
}

foreach ($target in $targets) {
    if ($KeepDist -and $target -eq "dist") { continue }
    if ($KeepRelease -and $target -eq "release") { continue }
    Remove-Target $target
}

$size = (Get-ChildItem -LiteralPath $projectRoot -Recurse -File -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
Write-Host "Workspace size: $([math]::Round($size / 1MB, 1)) MB"
