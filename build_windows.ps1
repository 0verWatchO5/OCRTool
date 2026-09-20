param(
    [string]$Version = "1.1.4",
    [switch]$SkipVenv,
    [string]$PfxPath = "",
    [string]$PfxPassword = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not $SkipVenv) {
    if (-not (Test-Path ".venv")) {
        $pyCmd = Get-Command "py" -ErrorAction SilentlyContinue
        if ($pyCmd) {
            & py -3 -m venv .venv
        } else {
            & python -m venv .venv
        }
    }

    .\.venv\Scripts\python.exe -m pip install --upgrade pip
    .\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
}

if (-not (Test-Path "runtime\tesseract")) {
    throw "Missing runtime\tesseract folder. Put portable Tesseract files there before building."
}

if (-not (Test-Path "runtime\ghostscript\bin")) {
    throw "Missing runtime\ghostscript\bin folder. Put Ghostscript binaries there before building."
}

if (-not (Test-Path "runtime\ghostscript\lib")) {
    throw "Missing runtime\ghostscript\lib folder. Copy Ghostscript lib files before building."
}

$tesseractExe = "runtime\tesseract\tesseract.exe"
if (-not (Test-Path $tesseractExe)) {
    throw "Missing '$tesseractExe'. Copy portable Tesseract binaries before building."
}

$gsExe = Get-ChildItem -Path "runtime\ghostscript\bin" -Filter "gswin*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $gsExe) {
    throw "Missing Ghostscript executable in runtime\ghostscript\bin (expected gswin*.exe)."
}

if (Test-Path "dist") {
    Remove-Item -Recurse -Force "dist"
}
if (Test-Path "build") {
    Remove-Item -Recurse -Force "build"
}

Write-Host "`n1. Building PyInstaller onedir bundle..."
.\.venv\Scripts\pyinstaller.exe --clean --noconfirm OCRTool.spec

# STEP 1 SIGNING: Sign OCRTool.exe BEFORE packaging into Inno Setup installer
if (Test-Path "sign_windows.ps1") {
    Write-Host "`n2. Digitally signing app executable (dist\OCRTool\OCRTool.exe)..."
    if ($PfxPath) {
        powershell -File "sign_windows.ps1" -Version "$Version" -PfxPath "$PfxPath" -PfxPassword "$PfxPassword"
    } else {
        powershell -File "sign_windows.ps1" -Version "$Version"
    }
}

$innoCandidates = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
)

$inno = $innoCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $inno) {
    throw "Inno Setup not found. Install Inno Setup 6 first."
}

Write-Host "`n3. Building Inno Setup installer package with pre-signed OCRTool.exe..."
& $inno "/DAppVersion=$Version" "installer\OCRTool.iss"

# STEP 2 SIGNING: Sign the resulting setup installer package
if (Test-Path "sign_windows.ps1") {
    Write-Host "`n4. Digitally signing installer setup executable (installer\output\OCRTool-Setup-$Version.exe)..."
    if ($PfxPath) {
        powershell -File "sign_windows.ps1" -Version "$Version" -PfxPath "$PfxPath" -PfxPassword "$PfxPassword"
    } else {
        powershell -File "sign_windows.ps1" -Version "$Version"
    }
}

Write-Host "`nBuild complete. Signed executable and signed installer created in installer\output\OCRTool-Setup-$Version.exe"
