param(
    [switch]$InstallIfMissing
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Find-Executable {
    param(
        [string]$Name,
        [string[]]$Candidates
    )

    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and (Test-Path $cmd.Source)) {
        return $cmd.Source
    }

    foreach ($candidate in $Candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return $null
}

function Ensure-Installed {
    param(
        [string]$WingetId,
        [string]$Display
    )

    Write-Host "Installing $Display using winget..."
    winget install --id $WingetId -e --accept-source-agreements --accept-package-agreements --silent
}

$tesseractCandidates = @(
    "C:\\Program Files\\Tesseract-OCR\\tesseract.exe",
    "$env:LOCALAPPDATA\\Programs\\Tesseract-OCR\\tesseract.exe"
)

$ghostscriptCandidates = @(
    "C:\\Program Files (x86)\\gs\\gs8.64\\bin\\gswin32c.exe",
    "C:\\Program Files\\gs\\gs10.06.0\\bin\\gswin64c.exe",
    "C:\\Program Files\\gs\\gs10.05.1\\bin\\gswin64c.exe",
    "C:\\Program Files\\gs\\gs10.04.0\\bin\\gswin64c.exe"
)

$tesseractExe = Find-Executable -Name "tesseract.exe" -Candidates $tesseractCandidates
$gsExe = Find-Executable -Name "gswin64c.exe" -Candidates $ghostscriptCandidates

if (-not $gsExe) {
    $gsExe = Find-Executable -Name "gswin32c.exe" -Candidates $ghostscriptCandidates
}

if (-not $gsExe) {
    $scanDirs = @("C:\\Program Files\\gs", "C:\\Program Files (x86)\\gs")
    foreach ($scanDir in $scanDirs) {
        if (Test-Path $scanDir) {
            $found = Get-ChildItem -Path $scanDir -Recurse -Include "gswin64c.exe", "gswin32c.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($found) {
                $gsExe = $found.FullName
                break
            }
        }
    }
}

if (-not $tesseractExe -and $InstallIfMissing) {
    Ensure-Installed -WingetId "UB-Mannheim.TesseractOCR" -Display "Tesseract OCR"
    $tesseractExe = Find-Executable -Name "tesseract.exe" -Candidates $tesseractCandidates
}

if (-not $gsExe -and $InstallIfMissing) {
    Ensure-Installed -WingetId "ArtifexSoftware.GhostScript" -Display "Ghostscript"
    $gsExe = Find-Executable -Name "gswin64c.exe" -Candidates $ghostscriptCandidates
    if (-not $gsExe) {
        $gsExe = Find-Executable -Name "gswin32c.exe" -Candidates $ghostscriptCandidates
    }
}

if (-not $tesseractExe) {
    throw "Tesseract was not found. Install it or rerun with -InstallIfMissing."
}

if (-not $gsExe) {
    throw "Ghostscript was not found. Install it or rerun with -InstallIfMissing."
}

$tesseractDir = Split-Path -Parent $tesseractExe
$gsBinDir = Split-Path -Parent $gsExe
$gsRootDir = Split-Path -Parent $gsBinDir
$gsLibDir = Join-Path $gsRootDir "lib"

if (-not (Test-Path $gsLibDir)) {
    throw "Ghostscript lib directory not found at '$gsLibDir'."
}

$destTesseract = "runtime\\tesseract"
$destGsBin = "runtime\\ghostscript\\bin"
$destGsLib = "runtime\\ghostscript\\lib"

New-Item -ItemType Directory -Force -Path $destTesseract | Out-Null
New-Item -ItemType Directory -Force -Path $destGsBin | Out-Null
New-Item -ItemType Directory -Force -Path $destGsLib | Out-Null

Write-Host "Copying Tesseract files from: $tesseractDir"
Get-ChildItem -Path $tesseractDir -File | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination $destTesseract -Force
}
if (Test-Path (Join-Path $tesseractDir "tessdata")) {
    Copy-Item -Path (Join-Path $tesseractDir "tessdata") -Destination $destTesseract -Recurse -Force
}

Write-Host "Copying Ghostscript bin files from: $gsBinDir"
Get-ChildItem -Path $gsBinDir -File | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination $destGsBin -Force
}

Write-Host "Copying Ghostscript lib files from: $gsLibDir"
Copy-Item -Path (Join-Path $gsLibDir "*") -Destination $destGsLib -Recurse -Force

Write-Host "Runtime collection complete."
Write-Host "- Tesseract: $destTesseract"
Write-Host "- Ghostscript bin: $destGsBin"
Write-Host "- Ghostscript lib: $destGsLib"
