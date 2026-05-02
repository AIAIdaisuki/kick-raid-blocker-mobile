#!/usr/bin/env bash
# Refresh /opt/krb/krb_admin.py to the latest from main and restart the
# admin service. Idempotent.
#
# https://github.com/AIAIdaisuki/kick-raid-blocker-mobile

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo bash $0" >&2
  exit 1
fi

REPO_RAW="https://raw.githubusercontent.com/AIAIdaisuki/kick-raid-blocker-mobile/main"
DEST=/opt/krb/krb_admin.py

if [[ ! -d /opt/krb ]]; then
  echo "ERROR: /opt/krb not found. Run install-vps.sh + install-admin.sh first." >&2
  exit 1
fi

echo "==> Downloading latest krb_admin.py"
curl -fsSL "${REPO_RAW}/proxy/krb_admin.py" -o "${DEST}.new"
mv "${DEST}.new" "${DEST}"
chown krb:krb "${DEST}"
chmod 0644 "${DEST}"

echo "==> Restarting krb-admin"
systemctl restart krb-admin
sleep 1

if systemctl is-active --quiet krb-admin; then
  echo "==> Done. Admin panel is running."
  echo "    On your iPhone, just reopen the bookmarked URL."
else
  echo "ERROR: krb-admin failed to start. Logs:" >&2
  journalctl -u krb-admin --no-pager -n 30
  exit 1
fi
