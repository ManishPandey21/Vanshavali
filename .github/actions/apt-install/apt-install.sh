#!/usr/bin/env bash
# Install apt packages for CI without letting a slow Ubuntu mirror stall the job (Nov 2026: a
# runner's mirror served ~30 KB/s and a plain `apt-get install` hung until the job's time limit).
#
#   apt-install.sh <deb-cache-dir> <package>...
#
# 1. If the cache directory holds .deb files from an earlier run on the same runner image, install
#    them with dpkg: no mirror involved.
# 2. Otherwise download with apt, bounded: each attempt has a hard time limit, apt retries stalled
#    transfers, and from the second attempt on the Azure mirror is swapped for archive.ubuntu.com.
#    The downloaded .deb files are left in the cache directory for the next run.
# Every package is checked with dpkg at the end, so a partial install never passes as success.
set -euo pipefail

cache=$1
shift
[ $# -gt 0 ] || { echo "usage: $0 <deb-cache-dir> <package>..." >&2; exit 2; }
pkgs=("$@")
attempts=${APT_INSTALL_ATTEMPTS:-3}
attempt_timeout=${APT_INSTALL_ATTEMPT_TIMEOUT:-300}   # seconds per update + install attempt
fallback_mirror=${APT_INSTALL_FALLBACK_MIRROR:-http://archive.ubuntu.com/ubuntu}
# the Ubuntu archive URL to replace (e.g. http://azure.archive.ubuntu.com/ubuntu); third-party
# repositories never match
primary_pattern=${APT_INSTALL_PRIMARY_PATTERN:-https?://[a-z0-9.-]*archive\.ubuntu\.com/ubuntu/?}
sudo=""
[ "$(id -u)" -eq 0 ] || sudo="sudo"

installed() {
  local p
  for p in "${pkgs[@]}"; do
    dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q "install ok installed" || return 1
  done
}

if installed; then
  echo "apt-install: already installed: ${pkgs[*]}"
  exit 0
fi

mkdir -p "$cache"
shopt -s nullglob
debs=("$cache"/*.deb)
if [ ${#debs[@]} -gt 0 ]; then
  echo "apt-install: installing ${#debs[@]} cached packages (no mirror)"
  if $sudo dpkg -i --skip-same-version "${debs[@]}" && installed; then
    echo "apt-install: done from cache"
    exit 0
  fi
  echo "apt-install: the cached packages did not install cleanly; downloading instead" >&2
  $sudo apt-get install -y -f >/dev/null 2>&1 || true
fi

apt_opts=(-o Acquire::Retries=3 -o Acquire::http::Timeout=30 -o Acquire::https::Timeout=30
  -o "Dir::Cache::archives=$cache")
$sudo mkdir -p "$cache/partial"

use_fallback_mirror() {
  local f
  for f in /etc/apt/sources.list /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list; do
    [ -f "$f" ] || continue
    $sudo sed -i -E "s#${primary_pattern}#${fallback_mirror}/#g" "$f"
  done
  echo "apt-install: switched the Ubuntu archive to ${fallback_mirror}"
}

for i in $(seq 1 "$attempts"); do
  [ "$i" -gt 1 ] && use_fallback_mirror
  echo "apt-install: attempt $i/$attempts: ${pkgs[*]}"
  if timeout "$attempt_timeout" $sudo apt-get update -q "${apt_opts[@]}" &&
    timeout "$attempt_timeout" $sudo apt-get install -y -q --no-install-recommends "${apt_opts[@]}" "${pkgs[@]}" &&
    installed; then
    $sudo rm -rf "$cache/partial" "$cache/lock"
    $sudo chown -R "$(id -u):$(id -g)" "$cache"
    debs=("$cache"/*.deb)
    echo "apt-install: done (downloaded ${#debs[@]} packages, kept for the cache)"
    exit 0
  fi
  echo "apt-install: attempt $i failed or timed out after ${attempt_timeout}s" >&2
done
echo "apt-install: could not install ${pkgs[*]} after $attempts attempts" >&2
exit 1
