#!/usr/bin/env bash
# Kick Raid Blocker — display the WireGuard client QR code in the terminal.
#
# After install-vps.sh has run, the WireGuard server is up but the only place
# the client config appears is the journal (text). This script:
#   1. Installs qrencode if missing
#   2. Pulls the [Interface]…Endpoint block from the journal
#   3. Replaces a placeholder/local Endpoint with the VPS public IP
#   4. Renders the result as a terminal QR you can scan with the iPhone
#      WireGuard app
#
# https://github.com/AIAIdaisuki/kick-raid-blocker-mobile

set -uo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo bash $0" >&2
  exit 1
fi

if ! command -v qrencode >/dev/null 2>&1; then
  echo "==> Installing qrencode"
  apt-get update -qq
  apt-get install -y qrencode >/dev/null
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 missing. Install it via apt-get install -y python3 first." >&2
  exit 1
fi

echo "==> Extracting WireGuard client config from journal"
config=$(journalctl -u krb-mitmproxy --no-pager -o cat -n 500 | python3 -c '
import sys, re
data = sys.stdin.read()
# Capture each [Interface] … Endpoint block printed at startup.
matches = re.findall(r"\[Interface\][\s\S]*?Endpoint\s*=\s*\S+", data)
if matches:
    print(matches[-1])
')

if [[ -z "$config" ]]; then
  echo "ERROR: WireGuard client config not found in the journal." >&2
  echo "Try restarting the service: systemctl restart krb-mitmproxy" >&2
  echo "Then re-run this script after a few seconds." >&2
  exit 1
fi

echo "==> Detecting VPS public IP"
public_ip=$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null \
         || curl -fsS --max-time 5 https://ifconfig.me 2>/dev/null \
         || hostname -I 2>/dev/null | awk '{print $1}')

if [[ -z "${public_ip:-}" ]]; then
  echo "WARNING: could not auto-detect public IP. Using whatever Endpoint mitmproxy printed."
else
  echo "VPS public IP: ${public_ip}"
  # Replace any Endpoint with public_ip:51820 to make sure the client connects
  # to the externally-reachable address rather than a local one.
  config=$(printf '%s\n' "$config" | sed -E "s|^Endpoint\s*=.*$|Endpoint = ${public_ip}:51820|")
fi

cat <<EOF

==================================================================
 WireGuard client config (this is what your iPhone will use):
==================================================================
${config}

==================================================================
 QR code — scan this with the WireGuard iPhone app:
   1. Open WireGuard
   2. Tap the "+" button
   3. Choose "Create from QR Code"
   4. Point your phone camera at the screen below
==================================================================
EOF

printf '%s\n' "$config" | qrencode -t ANSIUTF8 -m 1

cat <<'EOF'

==================================================================
 If the QR is too dense to scan:
   - Zoom out the ConoHa console (Ctrl+- in browser)
   - Or shrink the terminal font
   - Or copy the text config above and import via "Create from
     File or Archive" on the WireGuard app instead

 IMPORTANT: do NOT share the QR or the [Interface] PrivateKey with
 anyone — they grant access to your iPhone's traffic via this VPS.
==================================================================
EOF
