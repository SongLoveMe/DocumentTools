param(
    [string]$Environment = "D:\Anaconda\envs\documenttools"
)

$ErrorActionPreference = "Stop"
$env:PYTHONNOUSERSITE = "1"
$env:APPDATA = $env:TEMP
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $Environment "python.exe"
$pyinstaller = Join-Path $Environment "Scripts\pyinstaller.exe"
$runtime = Join-Path $projectRoot "vendor\libreoffice\program\soffice.exe"

if (-not (Test-Path $python)) { throw "DocumentTools Conda environment is missing: $Environment" }
if (-not (Test-Path $pyinstaller)) { throw "PyInstaller is missing. Install requirements.lock in the isolated environment first." }
if (-not (Test-Path $runtime)) { throw "Embedded conversion runtime is missing: $runtime" }

Push-Location $projectRoot
try {
    & $python -m PyInstaller --noconfirm --clean --windowed --name DocumentTools --icon assets\documenttools.ico --paths src `
        --collect-all pypdf --collect-all fitz --collect-all pdf2docx --collect-all pptx --collect-all reportlab --collect-all xlsxwriter main.py
    $iss = Join-Path $projectRoot "installer\DocumentTools.iss"
    $iscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    if (Test-Path $iscc) {
        & $iscc $iss
    } else {
        Write-Warning "Inno Setup 6 was not found; the PyInstaller build is available under dist."
    }
} finally {
    Pop-Location
}
