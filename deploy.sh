#!/usr/bin/env bash
# Send the current project folder to the Azure server, rebuild the image there and restart the site.
# Usage (Git Bash, from the project root):  ./deploy.sh
# Needs: Azure CLI signed in (az login) and the settings saved by the first deploy in
# deploy/azure/.deploy-info.txt (resource group and invite code; the file is not committed).
set -euo pipefail
cd "$(dirname "$0")"

# A terminal opened before Azure CLI was installed does not have it on PATH yet.
for d in "/c/Program Files/Microsoft SDKs/Azure/CLI2/wbin" "/c/Program Files (x86)/Microsoft SDKs/Azure/CLI2/wbin"; do
  if [ -d "$d" ]; then PATH="$PATH:$d"; fi
done

info="deploy/azure/.deploy-info.txt"
if [ ! -f "$info" ]; then
  echo "No $info - run the first deploy with deploy/azure/deploy.ps1 (see deploy/azure/README.md)." >&2
  exit 1
fi

# The file is written by PowerShell: UTF-8 with a BOM and CRLF line ends.
read_setting() { sed '1s/^\xEF\xBB\xBF//' "$info" | tr -d '\r' | sed -n "s/^$1=//p" | head -n 1; }
group="$(read_setting ResourceGroup)"
invite="$(read_setting InviteCode)"
if [ -z "$group" ]; then
  echo "ResourceGroup is missing in $info." >&2
  exit 1
fi

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Commit: $(git log -1 --format='%h %s' 2>/dev/null || echo 'none yet')"
  if [ -n "$(git status --porcelain)" ]; then
    echo "Note: there are uncommitted changes - they are deployed too (the folder is sent as it is)."
  fi
fi

# The server settings are rewritten on every run, so the invite code has to be passed again;
# without it registration on the public site would become open.
args=(-ResourceGroup "$group" -UpdateOnly)
if [ -n "$invite" ]; then args+=(-InviteCode "$invite"); fi

powershell.exe -NoProfile -ExecutionPolicy Bypass -File deploy/azure/deploy.ps1 "${args[@]}"
