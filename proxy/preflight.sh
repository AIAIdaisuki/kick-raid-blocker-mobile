#!/usr/bin/env bash
# Kick Raid Blocker — VPS preflight (run before install-vps.sh).
# Adds a 4G swap file (helps on small VPSes that share with other workloads,
# e.g. video processing pipelines), then prints diagnostics so we can confirm
# the box is ready for mitmproxy.
#
# https://github.com/AIAIdaisuki/kick-raid-blocker-mobile

set -uo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo bash $0" >&2
  exit 1
fi

echo "================================================="
echo " 1) Memory / swap / disk before"
echo "================================================="
free -h
echo "--"
swapon --show || true
echo "--"
df -h / | tail -1
echo

echo "================================================="
echo " 2) Add 4G swap (skipped if already present)"
echo "================================================="
if [[ -f /swapfile ]] || swapon --show | grep -q '/swapfile'; then
  echo "/swapfile already exists, skipping."
else
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  if ! grep -q swapfile /etc/fstab; then
    echo '/swapfile none swap sw 0 0' >> /etc/fstab
  fi
  echo "Swap added."
fi
echo

echo "================================================="
echo " 3) Memory after swap"
echo "================================================="
free -h
echo

echo "================================================="
echo " 4) OS / architecture / disk"
echo "================================================="
cat /etc/os-release | head -5
echo "--"
uname -a
echo

echo "================================================="
echo " 5) UDP listeners (51820 should be empty)"
echo "================================================="
ss -ulnp 2>/dev/null | head -15 || netstat -ulnp 2>/dev/null | head -15
echo

echo "================================================="
echo " 6) UFW status"
echo "================================================="
ufw status verbose 2>/dev/null | head -20 || echo "(UFW not installed - that's fine, install-vps.sh will add it)"
echo

echo "================================================="
echo " 7) Existing tools"
echo "================================================="
which python3 mitmdump wg 2>&1 || true
echo "/opt contents:"
ls /opt/ 2>/dev/null || echo "(empty)"
echo

echo "================================================="
echo " 8) Currently running services (count and top mem)"
echo "================================================="
echo "Running services:"
systemctl list-units --type=service --state=running --no-pager 2>/dev/null | wc -l
echo "Top 5 memory consumers:"
ps aux --sort=-%mem 2>/dev/null | head -6
echo

echo "================================================="
echo " Preflight complete. Share this entire output back"
echo " in chat to confirm we can proceed to install-vps.sh"
echo "================================================="
