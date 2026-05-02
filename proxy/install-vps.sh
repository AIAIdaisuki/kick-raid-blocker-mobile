#!/usr/bin/env bash
# Kick Raid Blocker — VPS installer (Ubuntu / Debian).
#
# Installs mitmproxy in a venv under /opt/krb, drops in the addon and a
# systemd service, opens the WireGuard UDP port, and starts the service.
# After this completes, run `journalctl -u krb-mitmproxy -f` once to see
# the WireGuard QR code, scan it from the iPhone, then install the mitm
# CA from http://mitm.it (over the WireGuard tunnel).
#
# Tested on Ubuntu 22.04 / 24.04. Run as root or with sudo.
#
# https://github.com/AIAIdaisuki/kick-raid-blocker-mobile

set -euo pipefail

REPO_RAW="https://raw.githubusercontent.com/AIAIdaisuki/kick-raid-blocker-mobile/main"
PORT_WG="${PORT_WG:-51820}"
INSTALL_DIR="/opt/krb"

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo bash $0" >&2
  exit 1
fi

echo "==> Installing system packages"
apt-get update -y
apt-get install -y python3 python3-venv python3-pip curl ufw

echo "==> Creating service user and directories"
id -u krb >/dev/null 2>&1 || useradd --system --home "${INSTALL_DIR}" --shell /usr/sbin/nologin krb
mkdir -p "${INSTALL_DIR}/conf"
chown -R krb:krb "${INSTALL_DIR}"

echo "==> Installing mitmproxy in a venv"
sudo -u krb python3 -m venv "${INSTALL_DIR}/venv"
sudo -u krb "${INSTALL_DIR}/venv/bin/pip" install --upgrade pip
sudo -u krb "${INSTALL_DIR}/venv/bin/pip" install "mitmproxy>=11"

echo "==> Fetching the addon, systemd unit, and management CLI"
curl -fsSL "${REPO_RAW}/proxy/mitmproxy_addon.py"   -o "${INSTALL_DIR}/mitmproxy_addon.py"
curl -fsSL "${REPO_RAW}/proxy/krb-mitmproxy.service" -o /etc/systemd/system/krb-mitmproxy.service
curl -fsSL "${REPO_RAW}/proxy/krb-cli"               -o /usr/local/bin/krb
chown krb:krb "${INSTALL_DIR}/mitmproxy_addon.py"
chmod 0644 /etc/systemd/system/krb-mitmproxy.service
chmod 0755 /usr/local/bin/krb

echo "==> Seeding default mode + blocklist files"
if [[ ! -f "${INSTALL_DIR}/conf/mode.txt" ]]; then
  echo "blocklist" > "${INSTALL_DIR}/conf/mode.txt"
fi
if [[ ! -f "${INSTALL_DIR}/conf/blocklist.txt" ]]; then
  cat > "${INSTALL_DIR}/conf/blocklist.txt" <<'EOF'
# One Kick streamer slug per line. Lines starting with # are comments.
# Edit with: sudo krb add <slug> / sudo krb remove <slug>
EOF
fi
if [[ ! -f "${INSTALL_DIR}/conf/allowlist.txt" ]]; then
  cat > "${INSTALL_DIR}/conf/allowlist.txt" <<'EOF'
# Used only when mode is "allowlist". Same syntax as blocklist.
EOF
fi
chown -R krb:krb "${INSTALL_DIR}/conf"

echo "==> Opening firewall (UFW) for WireGuard UDP/${PORT_WG}"
if command -v ufw >/dev/null 2>&1; then
  ufw allow "${PORT_WG}/udp" || true
fi

echo "==> Enabling and starting the service"
systemctl daemon-reload
systemctl enable --now krb-mitmproxy

cat <<EOF

==============================================================
 Kick Raid Blocker is now running on this VPS.

 Next steps (on your iPhone):

  1. Install "WireGuard" from the App Store (free).

  2. Run on this VPS:
        journalctl -u krb-mitmproxy -f
     Wait until you see a WireGuard QR code printed.

  3. WireGuard app on iPhone -> "+" -> "Create from QR Code"
     -> scan the QR -> name it (e.g. "KRB").

  4. Toggle the WireGuard tunnel ON.

  5. Open Safari and visit  http://mitm.it
     -> tap "Apple iOS"  -> "Allow" the configuration profile.
     Settings -> General -> VPN & Device Management ->
        install the mitmproxy CA profile.
     Settings -> General -> About -> Certificate Trust Settings
     -> turn ON the mitmproxy switch.

  6. Open the Kick app. Raids no longer redirect you.

 To stop:        systemctl stop  krb-mitmproxy
 To uninstall:   bash ${REPO_RAW}/proxy/uninstall-vps.sh
==============================================================
EOF
