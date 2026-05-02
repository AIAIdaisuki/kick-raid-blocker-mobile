#!/usr/bin/env bash
# Kick Raid Blocker — VPS upgrade script.
#
# For users who already ran install-vps.sh once. This refreshes:
#   - /opt/krb/mitmproxy_addon.py        (the WS frame interceptor)
#   - /usr/local/bin/krb                 (management CLI; new in v0.3.0)
#   - /opt/krb/conf/{mode,blocklist,allowlist}.txt (created if missing)
# Then restarts the service.
#
# Safe to run multiple times (idempotent). Does NOT touch your WireGuard
# private key, mitmproxy CA, or any other state under /opt/krb/conf.
#
# https://github.com/AIAIdaisuki/kick-raid-blocker-mobile

set -euo pipefail

REPO_RAW="https://raw.githubusercontent.com/AIAIdaisuki/kick-raid-blocker-mobile/main"
INSTALL_DIR=/opt/krb
CONF_DIR="$INSTALL_DIR/conf"

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo bash $0" >&2
  exit 1
fi

if [[ ! -d "$INSTALL_DIR/venv" ]]; then
  echo "ERROR: $INSTALL_DIR/venv not found. Looks like you haven't run" >&2
  echo "       install-vps.sh yet. Run that first." >&2
  exit 1
fi

echo "==> Refreshing addon"
curl -fsSL "${REPO_RAW}/proxy/mitmproxy_addon.py" -o "${INSTALL_DIR}/mitmproxy_addon.py.new"
mv "${INSTALL_DIR}/mitmproxy_addon.py.new" "${INSTALL_DIR}/mitmproxy_addon.py"
chown krb:krb "${INSTALL_DIR}/mitmproxy_addon.py"

echo "==> Installing krb CLI to /usr/local/bin/krb"
curl -fsSL "${REPO_RAW}/proxy/krb-cli" -o /usr/local/bin/krb
chmod 0755 /usr/local/bin/krb

echo "==> Seeding default config files (if missing)"
mkdir -p "$CONF_DIR"
if [[ ! -f "$CONF_DIR/mode.txt" ]]; then
  echo "blocklist" > "$CONF_DIR/mode.txt"
  echo "  default mode set to: blocklist"
fi
if [[ ! -f "$CONF_DIR/blocklist.txt" ]]; then
  cat > "$CONF_DIR/blocklist.txt" <<'EOF'
# One Kick streamer slug per line. Lines starting with # are comments.
# Example:
#   badactor
#   another_streamer
# Edit with: krb add <slug> / krb remove <slug>
EOF
  echo "  created empty blocklist"
fi
if [[ ! -f "$CONF_DIR/allowlist.txt" ]]; then
  cat > "$CONF_DIR/allowlist.txt" <<'EOF'
# Used only when mode is "allowlist". Same syntax as blocklist.
EOF
fi
chown -R krb:krb "$CONF_DIR"

echo "==> Restarting service"
systemctl restart krb-mitmproxy
sleep 1
systemctl is-active krb-mitmproxy >/dev/null && echo "  service: active" || {
  echo "ERROR: service failed to come up" >&2
  systemctl status krb-mitmproxy --no-pager | tail -20
  exit 1
}

cat <<EOF

==============================================================
 Upgrade complete!

 Try it:
   sudo krb status
   sudo krb add <streamer-slug>
   sudo krb watch        # tails [KRB] decisions live

 Default mode is now "blocklist": raids pass through except for
 streamers you've added with `sudo krb add`.

 To go back to blocking every raid:
   sudo krb mode block-all
==============================================================
EOF
