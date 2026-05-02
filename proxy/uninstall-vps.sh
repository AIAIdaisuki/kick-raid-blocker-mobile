#!/usr/bin/env bash
# Kick Raid Blocker — VPS uninstaller. Removes everything install-vps.sh added.
#
# https://github.com/AIAIdaisuki/kick-raid-blocker-mobile

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo bash $0" >&2
  exit 1
fi

echo "==> Stopping and disabling the service"
systemctl disable --now krb-mitmproxy 2>/dev/null || true
rm -f /etc/systemd/system/krb-mitmproxy.service
systemctl daemon-reload

echo "==> Removing /opt/krb and the krb user"
rm -rf /opt/krb
id -u krb >/dev/null 2>&1 && userdel krb || true

echo "==> Closing UFW rule (if any)"
if command -v ufw >/dev/null 2>&1; then
  ufw delete allow 51820/udp 2>/dev/null || true
fi

echo "Done. On the iPhone, please remove the WireGuard tunnel and the"
echo "mitmproxy CA profile (Settings -> General -> VPN & Device Management)."
