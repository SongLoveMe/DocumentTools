param(
    [string]$Environment = "D:\Anaconda\envs\documenttools",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$env:PYTHONNOUSERSITE = "1"
$env:APPDATA = $env:TEMP
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $Environment "python.exe"
$pyinstaller = Join-Path $Environment "Scripts\pyinstaller.exe"
$distRoot = Join-Path $projectRoot "dist\DocumentTools"
$buildRoot = Join-Path $projectRoot "build"

if (-not (Test-Path $python)) { throw "The DocumentTools Python environment is missing: $Environment" }
if (-not (Test-Path $pyinstaller)) { throw "PyInstaller is missing. Install requirements.lock in the isolated environment first." }

# Patterns that must never ship: external runtimes and unused heavy libraries.
$forbiddenPatterns = @(
    "soffice.exe",
    "cv2",
    "numpy",
    "opencv_videoio_ffmpeg*.dll",
    "opengl32sw.dll",
    "Qt5Qml*.dll",
    "Qt5Quick*.dll",
    "tcl86t.dll",
    "tk86t.dll",
    "_tkinter.pyd",
    "icudt73.dll",
    "icuin73.dll",
    "icuuc73.dll",
    "pandas",
    "scipy",
    "matplotlib",
    "pythonwin",
    "win32comext"
)

function Remove-ForbiddenArtifacts([string]$Root) {
    foreach ($pattern in $forbiddenPatterns) {
        Get-ChildItem -LiteralPath $Root -Recurse -Force -File -Filter $pattern -ErrorAction SilentlyContinue |
            ForEach-Object {
                Write-Host "Removing disallowed artifact: $($_.FullName)"
                Remove-Item -LiteralPath $_.FullName -Force
            }
        Get-ChildItem -LiteralPath $Root -Recurse -Force -Directory -Filter $pattern -ErrorAction SilentlyContinue |
            ForEach-Object {
                Write-Host "Removing disallowed artifact: $($_.FullName)"
                Remove-Item -LiteralPath $_.FullName -Recurse -Force
            }
    }
}

Push-Location $projectRoot
try {
    & $python -m PyInstaller --noconfirm --clean --windowed --name DocumentTools --icon assets\documenttools.ico --paths src `
        --collect-all pypdf --collect-all fitz --collect-all pptx --collect-all docx `
        --collect-all reportlab --collect-all xlsxwriter `
        --hidden-import win32com.client --hidden-import pythoncom --hidden-import pywintypes `
        --collect-binaries pywin32 `
        --exclude-module cv2 --exclude-module numpy --exclude-module pandas `
        --exclude-module scipy --exclude-module matplotlib --exclude-module tkinter `
        --exclude-module PyQt5.QtQml --exclude-module PyQt5.QtQuick `
        --exclude-module win32comext --exclude-module pythonwin --exclude-module win32com.gen_py `
        main.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed with exit code $LASTEXITCODE." }

    Remove-ForbiddenArtifacts $distRoot

    $exe = Join-Path $distRoot "DocumentTools.exe"
    if (-not (Test-Path $exe)) { throw "Build output is missing: $exe" }

    # The COM helper must be importable from the frozen executable: pywin32
    # ships its loader DLLs in pywin32_system32, so verify those are present.
    $pythoncom = Get-ChildItem -LiteralPath $distRoot -Recurse -Force -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "pythoncom*.dll" -or $_.Name -like "pythoncom*.pyd" } |
        Select-Object -First 1
    if (-not $pythoncom) { throw "pywin32 was not bundled; COM conversion would fail in the packaged build." }

    # Qt must survive the cleanup, or the windowed app cannot start.
    $qtCore = Get-ChildItem -LiteralPath $distRoot -Recurse -Force -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "Qt5Core*.dll" } |
        Select-Object -First 1
    if (-not $qtCore) { throw "Qt5Core was not bundled; the packaged application cannot start." }

    if ($SkipInstaller) {
        Write-Host "Skipped installer generation."
    } else {
        $iss = Join-Path $projectRoot "installer\DocumentTools.iss"
        $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
        if (Test-Path $iscc) {
            & $iscc $iss
            if ($LASTEXITCODE -ne 0) { throw "Inno Setup build failed with exit code $LASTEXITCODE." }
        } else {
            Write-Warning "Inno Setup 6 was not found; the PyInstaller build is available under dist."
        }
    }
} finally {
    Pop-Location
    if (Test-Path $buildRoot) {
        Remove-Item -LiteralPath $buildRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
