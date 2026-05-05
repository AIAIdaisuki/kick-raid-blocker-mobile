#!/usr/bin/env bash
# Diagnose why a raid was NOT blocked.
#
# Run this immediately after a raid that should have been blocked but wasn't.
# Shows the recent decisions logged by the addon, the current mode, and the
# blocklist contents so we can see exactly why.
#
# https://github.com/AIAIdaisuki/kick-raid-blocker-mobile

set -uo pipefail

if [[ $EUID -ne 0 ]]; then
  exec sudo -E "$0" "$@"
fi

echo "================================================="
echo " Service status"
echo "================================================="
systemctl is-active krb-mitmproxy
systemctl is-active krb-admin
echo

echo "================================================="
echo " Current mode"
echo "================================================="
cat /opt/krb/conf/mode.txt 2>/dev/null || echo "(no mode.txt)"
echo

echo "================================================="
echo " Current blocklist"
echo "================================================="
grep -vE '^\s*(#|$)' /opt/krb/conf/blocklist.txt 2>/dev/null || echo "(empty)"
echo

echo "================================================="
echo " Current allowlist"
echo "================================================="
grep -vE '^\s*(#|$)' /opt/krb/conf/allowlist.txt 2>/dev/null || echo "(empty)"
echo

echo "================================================="
echo " Recent [KRB] decisions (last 30 min)"
echo "================================================="
DECISIONS=$(journalctl -u krb-mitmproxy --since "30 minutes ago" --no-pager 2>/dev/null | grep -E '\[KRB\]' | tail -50)
if [[ -z "$DECISIONS" ]]; then
  echo "(NO raid events seen in the last 30 min)"
  echo
  echo "This usually means one of:"
  echo "  - WireGuard was OFF when the raid happened"
  echo "    (check iPhone: Settings > VPN > WireGuard or the WG app)"
  echo "  - The addon does not match Kick's current event name"
  echo "  - The Kick app used a Pusher cluster we did not MITM"
else
  echo "$DECISIONS"
fi
echo

echo "================================================="
echo " All Pusher traffic in last 5 min (sample)"
echo "================================================="
journalctl -u krb-mitmproxy --since "5 minutes ago" --no-pager 2>/dev/null \
  | grep -iE 'pusher|websocket|wireguard' \
  | tail -10 \
  || echo "(none)"
echo

echo "================================================="
echo " Active WireGuard peers (handshakes)"
echo "================================================="
journalctl -u krb-mitmproxy --since "30 minutes ago" --no-pager 2>/dev/null \
  | grep -iE 'handshake|peer|wireguard' \
  | tail -5 \
  || echo "(none)"
echo

echo "================================================="
echo " Addon version (head of /opt/krb/mitmproxy_addon.py)"
echo "================================================="
head -3 /opt/krb/mitmproxy_addon.py 2>/dev/null
grep -E 'v0\.[0-9]' /opt/krb/mitmproxy_addon.py 2>/dev/null | head -2
echo

echo "================================================="
echo " Diagnosis hints"
echo "================================================="
cat <<'EOF'
1. If no [KRB] decisions appear:
   - Make sure WireGuard was ON during the raid (iPhone)
   - Check the iOS Shortcut auto-toggle did fire when Kick opened
2. If [KRB] PASS appears with the streamer's slug NOT being seen:
   - Open admin panel, check the slug spelling — may not match Kick's
3. If [KRB] PASS appears with users={['somename']} where somename != your blocklist entry:
   - Add that exact slug to the blocklist
4. If you see [KRB] DROP for a different streamer just before the raid:
   - The addon dropped a notification but the app redirected anyway —
     might be using a different event we don't yet recognize. Share the
     event name and we'll add it.
EOF
