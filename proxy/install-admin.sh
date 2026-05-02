#!/usr/bin/env bash
# Kick Raid Blocker — install the admin web UI.
#
# Adds a tiny Python stdlib HTTP server on port 9876 that lets you edit
# the blocklist / allowlist / mode from a phone browser. Requires that
# install-vps.sh (or upgrade.sh) has already been run.
#
# After installation, you ALSO need to add a ConoHa security group rule
# for TCP/9876 inbound. Then bookmark the printed URL on the iPhone.
#
# https://github.com/AIAIdaisuki/kick-raid-blocker-mobile

set -euo pipefail

REPO_RAW="https://raw.githubusercontent.com/AIAIdaisuki/kick-raid-blocker-mobile/main"
INSTALL_DIR=/opt/krb
PORT="${PORT:-9876}"

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo bash $0" >&2
  exit 1
fi

if [[ ! -d "$INSTALL_DIR/conf" ]]; then
  echo "ERROR: $INSTALL_DIR not found. Run install-vps.sh first." >&2
  exit 1
fi

echo "==> Fetching admin script and unit"
curl -fsSL "${REPO_RAW}/proxy/krb_admin.py"       -o "${INSTALL_DIR}/krb_admin.py"
curl -fsSL "${REPO_RAW}/proxy/krb-admin.service"  -o /etc/systemd/system/krb-admin.service
chown krb:krb "${INSTALL_DIR}/krb_admin.py"
chmod 0644 /etc/systemd/system/krb-admin.service

echo "==> Opening UFW for TCP/${PORT}"
ufw allow "${PORT}/tcp" >/dev/null 2>&1 || true

echo "==> Enabling and starting krb-admin"
systemctl daemon-reload
systemctl enable --now krb-admin

# Wait briefly so first run can generate the token file
for _ in 1 2 3 4 5; do
  [[ -s "${INSTALL_DIR}/conf/admin-token.txt" ]] && break
  sleep 1
done

if [[ ! -s "${INSTALL_DIR}/conf/admin-token.txt" ]]; then
  echo "WARNING: token file did not appear; check 'systemctl status krb-admin'" >&2
  exit 1
fi

token=$(cat "${INSTALL_DIR}/conf/admin-token.txt")
public_ip=$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null \
         || hostname -I 2>/dev/null | awk '{print $1}')

cat <<EOF

==============================================================
 Admin web UI is now running.

 Step 1 — open ConoHa management panel and add this rule to the
          security group attached to this VPS:
            Direction: IN
            Protocol:  TCP
            Port:      ${PORT}
            Source:    0.0.0.0/0

 Step 2 — on your iPhone (with WireGuard ON), open Safari to:

      http://${public_ip:-<your-vps-ip>}:${PORT}/?token=${token}

      Add it to the home screen for one-tap access:
      Share button (□↑) -> "Add to Home Screen"

 Step 3 — manage the blocklist by tapping that bookmark.
          Edits take effect on the next raid event automatically.

 The token is stored at ${INSTALL_DIR}/conf/admin-token.txt — anyone who
 obtains the URL can edit your blocklist, so do NOT share it.
 To regenerate the token: rm that file and run "systemctl restart krb-admin".

 To stop:        systemctl stop  krb-admin
 To uninstall:   systemctl disable --now krb-admin
                 rm /etc/systemd/system/krb-admin.service
                 ufw delete allow ${PORT}/tcp
==============================================================
EOF
