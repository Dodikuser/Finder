<#
.SYNOPSIS
  Deploy (or update) Finder on Microsoft Azure.

.DESCRIPTION
  1. Creates the resource group and the infrastructure from main.bicep
     (Linux VM + public IP/DNS name + network rules). SSH is opened only for your current IP.
  2. Packs the project sources, copies them to the VM over SSH and builds the Docker image there
     (no local Docker and no container registry needed).
  3. Starts the stack: Finder + Caddy with automatic HTTPS.

  Re-run with -UpdateOnly after code changes: it re-uploads the sources, rebuilds and restarts.

.EXAMPLE
  az login
  .\deploy\azure\deploy.ps1 -ResourceGroup finder-rg -Location denmarkeast -InviteCode "my-secret-code"

.EXAMPLE
  .\deploy\azure\deploy.ps1 -ResourceGroup finder-rg -UpdateOnly
#>
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)][string]$ResourceGroup,
  [string]$Location = "westeurope",
  [string]$NamePrefix = "finder",
  [string]$VmSize = "Standard_B2ms",
  # Registration on the public site requires this code when set (recommended).
  [string]$InviteCode = "",
  # Set to close sign-up completely after you have created your accounts.
  [switch]$CloseRegistration,
  # E-mail sent to NCBI / OpenAlex "polite pool" APIs (optional).
  [string]$ContactEmail = "",
  # Your own domain already pointing at the VM (optional); default is the Azure DNS name.
  [string]$CustomDomain = "",
  # Address/CIDR allowed to use SSH. Default: the public IP of this computer, detected automatically.
  [string]$SshSourceAddress = "",
  [string]$SshKeyPath = "$HOME\.ssh\finder_azure",
  [switch]$UpdateOnly
)

# Native tools (az, ssh, tar) write progress and warnings to stderr; under "Stop" Windows
# PowerShell 5 turns those lines into terminating errors. Exit codes are checked explicitly instead.
$ErrorActionPreference = "Continue"
$env:PYTHONIOENCODING = "utf-8"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

function Assert-Ok([string]$what) {
  if ($LASTEXITCODE -ne 0) { throw "$what failed (exit code $LASTEXITCODE)" }
}

if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
  throw "Azure CLI is not installed. Install it from https://aka.ms/installazurecliwindows and run 'az login'."
}
$account = az account show --output json | ConvertFrom-Json
Assert-Ok "az account show (run 'az login' first)"
Write-Host "Subscription: $($account.name) ($($account.id))" -ForegroundColor Cyan

if (-not $SshSourceAddress) {
  $SshSourceAddress = (Invoke-RestMethod -Uri "https://api.ipify.org" -TimeoutSec 20).Trim()
  Write-Host "SSH will be allowed only from this computer's address: $SshSourceAddress"
}

$knownHosts = "$SshKeyPath.known_hosts"
if (-not $UpdateOnly) {
  if (-not (Test-Path "$SshKeyPath.pub")) {
    Write-Host "Creating an SSH key for the VM admin: $SshKeyPath"
    New-Item -ItemType Directory -Force (Split-Path $SshKeyPath) | Out-Null
    # Through cmd so the empty passphrase is passed the same way by Windows PowerShell 5 and PowerShell 7.
    & cmd /c "ssh-keygen -q -t ed25519 -N `"`" -f `"$SshKeyPath`" -C finder-azure"
    Assert-Ok "ssh-keygen"
  }
  $sshPublicKey = (Get-Content "$SshKeyPath.pub" -Raw).Trim()

  Write-Host "Creating resource group $ResourceGroup in $Location ..." -ForegroundColor Cyan
  az group create --name $ResourceGroup --location $Location --output none
  Assert-Ok "az group create"

  Write-Host "Deploying infrastructure (VM, network, address) - about 3-5 minutes ..." -ForegroundColor Cyan
  az deployment group create `
    --resource-group $ResourceGroup `
    --name finder-infra `
    --template-file (Join-Path $PSScriptRoot "main.bicep") `
    --parameters namePrefix=$NamePrefix vmSize=$VmSize adminSshPublicKey="$sshPublicKey" `
                 sshSourceAddress="$SshSourceAddress" customDomain="$CustomDomain" `
    --output none
  Assert-Ok "Infrastructure deployment"
  Remove-Item $knownHosts -ErrorAction SilentlyContinue   # a new VM has a new host key
} else {
  # Your IP may have changed since the last run: point the SSH rule at the current one.
  az network nsg rule create --resource-group $ResourceGroup --nsg-name "$NamePrefix-nsg" --name allow-ssh `
    --priority 120 --direction Inbound --access Allow --protocol Tcp `
    --source-address-prefixes $SshSourceAddress --destination-port-ranges 22 --output none
  Assert-Ok "Updating the SSH rule"
}

$outputs = az deployment group show --resource-group $ResourceGroup --name finder-infra `
    --query properties.outputs --output json | ConvertFrom-Json
Assert-Ok "Reading deployment outputs"
$vmHost = $outputs.publicIpAddress.value
$admin = $outputs.adminUsername.value
$siteUrl = $outputs.siteUrl.value
$target = "$admin@$vmHost"
$sshOpts = @("-i", $SshKeyPath, "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=$knownHosts",
             "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=30", "-o", "LogLevel=ERROR")

Write-Host "Waiting for the VM ($vmHost) to finish its first-boot setup ..." -ForegroundColor Cyan
$ready = $false
foreach ($i in 1..60) {
  & ssh @sshOpts $target "test -f /opt/finder/.cloud-init-done" 2>$null
  if ($LASTEXITCODE -eq 0) { $ready = $true; break }
  Start-Sleep -Seconds 10
}
if (-not $ready) { throw "The VM did not become ready over SSH within 10 minutes (check that $SshSourceAddress is your public IP)." }

Write-Host "Packing and uploading sources ..." -ForegroundColor Cyan
$tmp = Join-Path ([IO.Path]::GetTempPath()) "finder-deploy-$PID"
New-Item -ItemType Directory -Force $tmp | Out-Null
$archive = Join-Path $tmp "src.tgz"
# The tar that ships with Windows, by full path: started from Git Bash, PATH finds GNU tar first,
# and that one reads "C:\..." as a remote host.
$tarExe = Join-Path $env:SystemRoot "System32\tar.exe"
if (-not (Test-Path $tarExe)) { $tarExe = "tar.exe" }
& $tarExe -czf $archive -C $repoRoot `
    --exclude=node_modules --exclude=.venv --exclude=__pycache__ --exclude=.pytest_cache `
    --exclude=./data --exclude=./frontend/dist --exclude=./.git --exclude=./.claude `
    --exclude=./deploy --exclude=./hermes-plugins --exclude=./backend/tests --exclude=./backend/.env .
Assert-Ok "Packing sources"

# Settings are written on the VM itself (/opt/finder/.env), never into the ARM template.
$settings = [ordered]@{
  FINDER_ALLOW_REGISTRATION = $(if ($CloseRegistration) { "false" } else { "true" })
  FINDER_INVITE_CODE        = $InviteCode
  FINDER_CONTACT_EMAIL      = $ContactEmail
}
$envLines = ($settings.GetEnumerator() | ForEach-Object { "set_env $($_.Key) '$($_.Value -replace "'", '')'" }) -join "`n"
$remote = @"
#!/bin/bash
set -euo pipefail
cd /opt/finder
set_env() { grep -v "^`$1=" .env > .env.tmp 2>/dev/null || true; if [ -n "`$2" ]; then echo "`$1=`$2" >> .env.tmp; fi; mv .env.tmp .env; chmod 600 .env; }
$envLines
mv /tmp/finder-src.tgz /opt/finder/src.tgz
/opt/finder/update.sh
"@
$remoteFile = Join-Path $tmp "remote.sh"
[IO.File]::WriteAllText($remoteFile, ($remote -replace "`r", ""), (New-Object Text.UTF8Encoding($false)))

& scp @sshOpts $archive "${target}:/tmp/finder-src.tgz"
Assert-Ok "Uploading sources"
& scp @sshOpts $remoteFile "${target}:/tmp/finder-remote.sh"
Assert-Ok "Uploading the setup script"
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "Building the image on the VM and starting Finder (15-25 minutes the first time) ..." -ForegroundColor Cyan
& ssh @sshOpts $target "sudo bash /tmp/finder-remote.sh; rc=`$?; sudo rm -f /tmp/finder-remote.sh; exit `$rc"
Assert-Ok "Build / start on the VM"

Write-Host ""
Write-Host "Finder is deployed: $siteUrl" -ForegroundColor Green
Write-Host "The first HTTPS certificate can take a minute. Health check: $siteUrl/api/health"
if ($InviteCode) { Write-Host "Registration requires the invite code you passed." }
