#!/usr/bin/env bash
# k — Kick Raid Blocker unified launcher.
#
# Single short URL for every install/upgrade/utility step, so ConoHa Web
# Console pastes never get truncated by line-wrapping.
#
# Usage from VPS:
#   bash <(curl -fsSL https://raw.githubusercontent.com/AIAIdaisuki/kick-raid-blocker-mobile/main/k) <subcommand>
#
# Subcommands:
#   install         — fresh VPS install (mitmproxy + WG + addon + CLI)
#   upgrade         — refresh mitmproxy addon + CLI
#   install-admin   — install admin web UI
#   upgrade-admin   — refresh admin web UI to latest
#   qr              — show WireGuard QR (terminal)
#   admin-qr        — serve admin URL as PNG QR
#   preflight       — preflight diagnostics + swap
#   uninstall       — completely remove everything
#   status          — show all KRB services status
#
# https://github.com/AIAIdaisuki/kick-raid-blocker-mobile

set -euo pipefail

REPO_RAW="https://raw.githubusercontent.com/AIAIdaisuki/kick-raid-blocker-mobile/main"
SUB="${1:-help}"

run() {
  local script="$1"
  shift || true
  bash <(curl -fsSL "${REPO_RAW}/proxy/${script}") "$@"
}

case "$SUB" in
  install)        run install-vps.sh ;;
  upgrade)        run upgrade.sh ;;
  install-admin)  run install-admin.sh ;;
  upgrade-admin)  run upgrade-admin.sh ;;
  qr)             run show-qr.sh ;;
  admin-qr)       run serve-admin-qr.sh ;;
  preflight)      run preflight.sh ;;
  uninstall)      run uninstall-vps.sh ;;
  status)
    if [[ $EUID -ne 0 ]]; then exec sudo -E "$0" "$@"; fi
    systemctl status krb-mitmproxy --no-pager 2>&1 | head -10
    echo "---"
    systemctl status krb-admin --no-pager 2>&1 | head -10
    ;;
  *)
    cat <<EOF
Kick Raid Blocker — unified launcher

Usage:
  bash <(curl -fsSL ${REPO_RAW}/k) <subcommand>

Subcommands:
  install         Fresh VPS install
  upgrade         Refresh mitmproxy addon + CLI
  install-admin   Install admin web UI
  upgrade-admin   Refresh admin web UI to latest
  qr              Show WireGuard QR (terminal)
  admin-qr        Serve admin URL as PNG QR
  preflight       Preflight diagnostics + swap
  uninstall       Completely remove everything
  status          Show all KRB services status
EOF
    ;;
esac
