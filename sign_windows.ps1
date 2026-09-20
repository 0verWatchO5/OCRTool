param(
    [string]$Version = "1.1.6",
    [string]$PfxPath = "",
    [string]$PfxPassword = "",
    [switch]$InstallTestCert
)

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

$cert = $null

if ($PfxPath -and (Test-Path $PfxPath)) {
    Write-Host "Loading Code Signing Certificate from PFX file: $PfxPath"
    $securePassword = ConvertTo-SecureString $PfxPassword -AsPlainText -Force
    $cert = Get-PfxCertificate -FilePath $PfxPath
} else {
    Write-Host "Searching for existing Code Signing Certificate in Cert:\CurrentUser\My..."
    $existing = Get-ChildItem -Path Cert:\CurrentUser\My -CodeSigningCert -ErrorAction SilentlyContinue |
        Where-Object { $_.Subject -like "*OCR PDF Layer Tool*" } |
        Select-Object -First 1

    if ($existing) {
        $cert = $existing
        Write-Host "Found existing certificate: $($cert.Subject) [Thumbprint: $($cert.Thumbprint)]"
    } else {
        Write-Host "Creating self-signed Code Signing Certificate for development/testing..."
        $cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject "CN=OCR PDF Layer Tool, O=OCRTool" -CertStoreLocation Cert:\CurrentUser\My
        Write-Host "Created certificate: $($cert.Subject) [Thumbprint: $($cert.Thumbprint)]"
    }
}

if (-not $cert) {
    Write-Error "Failed to locate or create Code Signing Certificate."
    exit 1
}

# Export public certificate file (.cer)
$certExportPath = Join-Path $Root "OCRTool_CodeSigning.cer"
Export-Certificate -Cert $cert -FilePath $certExportPath | Out-Null
Write-Host "Exported public certificate to: $certExportPath"

# Trust self-signed certificate on local machine if requested
if ($InstallTestCert) {
    try {
        Import-Certificate -FilePath $certExportPath -CertStoreLocation Cert:\LocalMachine\Root -ErrorAction SilentlyContinue | Out-Null
        Write-Host "Trusted public certificate in Cert:\LocalMachine\Root"
    } catch {
        Write-Host "Note: To trust self-signed test cert in Windows, run PowerShell as Admin and import OCRTool_CodeSigning.cer to Trusted Root."
    }
}

# ONLY target current version build & binary
$targets = @()

$exePath = "dist\OCRTool\OCRTool.exe"
if (Test-Path $exePath) {
    $targets += (Resolve-Path $exePath).Path
}

$installerPath = "installer\output\OCRTool-Setup-$Version.exe"
if (Test-Path $installerPath) {
    $targets += (Resolve-Path $installerPath).Path
}

if ($targets.Count -eq 0) {
    Write-Host "No current version target binaries found to sign ($exePath or $installerPath)."
    exit 0
}

$timestampServers = @(
    "http://timestamp.digicert.com",
    "http://timestamp.sectigo.com",
    "http://timestamp.comodoca.com"
)

Write-Host "`nDigitally signing current version ($Version) binaries..."
foreach ($target in $targets) {
    Write-Host "Signing: $target"
    $signed = $false
    
    foreach ($ts in $timestampServers) {
        try {
            $sig = Set-AuthenticodeSignature -FilePath $target -Certificate $cert -TimestampServer $ts -ErrorAction Stop
            if ($sig -and $sig.SignerCertificate) {
                Write-Host "  -> Signed & Timestamped via $ts! Signer: $($sig.SignerCertificate.Subject)"
                $signed = $true
                break
            }
        } catch {
            # Try next timestamp server
        }
    }
    
    if (-not $signed) {
        # Fallback without timestamp server if offline or timestamp server timed out
        $sig = Set-AuthenticodeSignature -FilePath $target -Certificate $cert -ErrorAction SilentlyContinue
        Write-Host "  -> Signed (without timestamp). Signer: $($sig.SignerCertificate.Subject)"
    }
}

Write-Host "`nDigital Signature Verification Summary (Version $Version):"
foreach ($target in $targets) {
    $sig = Get-AuthenticodeSignature -FilePath $target
    Write-Host "File: $target"
    Write-Host "  Status: $($sig.Status)"
    Write-Host "  Signer: $($sig.SignerCertificate.Subject)"
    Write-Host "  Thumbprint: $($sig.SignerCertificate.Thumbprint)"
    if ($sig.TimeStamplerSignature) {
        Write-Host "  Timestamped: Yes ($($sig.TimeStamplerSignature.SignerCertificate.Subject))"
    }
}

Write-Host "`nCode signing step completed for version $Version."
