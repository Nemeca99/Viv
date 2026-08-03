[CmdletBinding()]
param(
  [switch] $Install,
  [string] $BackupManifest = ""
)

# Build by default. Installation is explicit, backup-gated, and transactional.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$VivRoot = "L:\Continue\Viv"
$Foundation = Join-Path $VivRoot "foundation"
$EvidenceRoot = Join-Path $Foundation "artifacts\auto\backup_core"
$VaultRoot = Join-Path $EvidenceRoot "vault"
$BootstrapReport = Join-Path $EvidenceRoot "bootstrap_restore_verification.json"
$Python = "L:\Continue\.venv\Scripts\python.exe"
Set-Location $Root

cargo build --release --offline
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$Dll = Join-Path $Root "target\release\security_core.dll"
$RuntimeRoot = Join-Path $Root "runtime"
$Pyd = Join-Path $RuntimeRoot "security_core.pyd"
$HashSide = Join-Path $RuntimeRoot "security_core.pyd.sha256"
$LegacyPyd = "L:\Continue\.venv\Lib\site-packages\security_core.pyd"
$HashArtifact = Join-Path $Foundation "artifacts\audit\security_core.pyd.sha256"
$RollbackRoot = Join-Path $Foundation "artifacts\audit\security_core_rollback"
$Version = (Select-String -Path (Join-Path $Root "Cargo.toml") -Pattern '^version\s*=\s*"([^"]+)"').Matches[0].Groups[1].Value
$BuildHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Dll).Hash.ToLowerInvariant()
$BuildEvidence = Join-Path $EvidenceRoot "security_core_build_${Version}.json"
New-Item -ItemType Directory -Force -Path $EvidenceRoot | Out-Null
[ordered]@{
  ok = $true
  installed = $false
  version = $Version
  dll = ($Dll -replace "\\", "/")
  sha256 = $BuildHash
  built_at = (Get-Date).ToUniversalTime().ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $BuildEvidence -Encoding utf8

if (-not $Install) {
  Write-Host "Built security_core $Version (not installed)"
  Write-Host "Release SHA256=$BuildHash"
  Write-Host "Use -Install -BackupManifest <verified manifest> for the gated swap."
  exit 0
}

if (-not (Test-Path -LiteralPath $BootstrapReport -PathType Leaf)) {
  throw "Install denied: bootstrap restore verification is missing."
}
$bootstrap = Get-Content -LiteralPath $BootstrapReport -Raw | ConvertFrom-Json
if (-not $bootstrap.ok -or -not $bootstrap.snapshot_id) {
  throw "Install denied: bootstrap restore verification did not pass."
}
if ([string]::IsNullOrWhiteSpace($BackupManifest)) {
  $BackupManifest = Join-Path $VaultRoot ("manifests\" + $bootstrap.snapshot_id + ".json")
}
$ManifestResolved = [System.IO.Path]::GetFullPath($BackupManifest)
$ManifestRoot = [System.IO.Path]::GetFullPath((Join-Path $VaultRoot "manifests")) + "\"
if (-not $ManifestResolved.StartsWith($ManifestRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Install denied: backup manifest is outside the Viv vault."
}
if (-not (Test-Path -LiteralPath $ManifestResolved -PathType Leaf)) {
  throw "Install denied: backup manifest is missing."
}
$manifest = Get-Content -LiteralPath $ManifestResolved -Raw | ConvertFrom-Json
$ProtectedPyd = if (Test-Path -LiteralPath $Pyd) { $Pyd } else { $LegacyPyd }
$ProtectedHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $ProtectedPyd).Hash.ToLowerInvariant()
$protected = @($manifest.record.copied_items | Where-Object {
  $_.path.ToLowerInvariant() -eq (($ProtectedPyd -replace "\\", "/").ToLowerInvariant()) -and
  $_.sha256.ToLowerInvariant() -eq $ProtectedHash
})
if ($protected.Count -ne 1) {
  throw "Install denied: active security_core.pyd is not protected by the selected snapshot."
}

$OldHash = $null
$OldHashText = if (Test-Path -LiteralPath $HashSide) { Get-Content -LiteralPath $HashSide -Raw } else { "" }
$OldAuditText = if (Test-Path -LiteralPath $HashArtifact) { Get-Content -LiteralPath $HashArtifact -Raw } else { "" }
if (Test-Path -LiteralPath $Pyd) {
  $OldHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Pyd).Hash.ToLowerInvariant()
}

New-Item -ItemType Directory -Force -Path $RollbackRoot,$RuntimeRoot | Out-Null
$RollbackPyd = if ($OldHash) {
  Join-Path $RollbackRoot "security_core_pre_${Version}_${OldHash}.pyd"
} else {
  Join-Path $RollbackRoot "security_core_pre_${Version}_missing.pyd"
}
if ($OldHash -and -not (Test-Path -LiteralPath $RollbackPyd)) {
  Copy-Item -LiteralPath $Pyd -Destination $RollbackPyd
}

$PydStage = "$Pyd.staged"
$HashStage = "$HashSide.staged"
try {
  Copy-Item -LiteralPath $Dll -Destination $PydStage -Force
  if ((Get-FileHash -Algorithm SHA256 -LiteralPath $PydStage).Hash.ToLowerInvariant() -ne $BuildHash) {
    throw "Staged module hash differs from the release DLL."
  }
  $BuildHash | Set-Content -NoNewline -Encoding ascii -LiteralPath $HashStage
  Move-Item -LiteralPath $PydStage -Destination $Pyd -Force
  Move-Item -LiteralPath $HashStage -Destination $HashSide -Force
  @(
    "sha256=$BuildHash"
    "path=$Pyd"
    "built=$(Get-Date -Format o)"
    "version=$Version"
  ) | Set-Content -Encoding ascii -LiteralPath $HashArtifact

  & $Python -c "import sys; sys.path.insert(0, r'$RuntimeRoot'); import security_core; assert security_core.__version__ == '$Version'; assert hasattr(security_core, 'authorize_training'); assert hasattr(security_core, 'authorize_backup'); assert hasattr(security_core, 'verify_backup_ledger')"
  if ($LASTEXITCODE -ne 0) { throw "Native module smoke failed." }
  Push-Location $Foundation
  try {
    & $Python -c "from lib.security_bridge import integrity_status,verify_backup_ledger; assert integrity_status()['ok']; assert verify_backup_ledger()['ok']"
    if ($LASTEXITCODE -ne 0) { throw "Security bridge smoke failed." }
  } finally {
    Pop-Location
  }
} catch {
  if ($OldHash -and (Test-Path -LiteralPath $RollbackPyd)) {
    Copy-Item -LiteralPath $RollbackPyd -Destination $Pyd -Force
    $OldHashText | Set-Content -NoNewline -Encoding ascii -LiteralPath $HashSide
  } else {
    Remove-Item -LiteralPath $Pyd -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $HashSide -Force -ErrorAction SilentlyContinue
  }
  $OldAuditText | Set-Content -NoNewline -Encoding ascii -LiteralPath $HashArtifact
  Remove-Item -LiteralPath $PydStage -Force -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $HashStage -Force -ErrorAction SilentlyContinue
  throw "security_core install rolled back: $($_.Exception.Message)"
}

[ordered]@{
  ok = $true
  installed = $true
  version = $Version
  sha256 = $BuildHash
  backup_snapshot = $manifest.snapshot_id
  installed_at = (Get-Date).ToUniversalTime().ToString("o")
} | ConvertTo-Json | Set-Content -LiteralPath $BuildEvidence -Encoding utf8
Write-Host "Installed security_core $Version"
Write-Host "Integrity SHA256=$BuildHash"
Write-Host "Backup snapshot=$($manifest.snapshot_id)"
