#!/usr/bin/env bash
# Kick Raid Blocker — generate the WireGuard QR as a PNG and serve it once
# over a temporary HTTP server bound to the public address.
#
# Why: terminal-rendered ANSI QR codes are sometimes unreadable on a phone
# camera (aspect ratio / resolution issues). A real PNG is reliably
# scannable.
#
# Workflow:
#   1. Build the WG client config (same as show-qr.sh)
#   2. Render it as PNG via qrencode
#   3. Open UFW for TCP/8642 just for this run
#   4. Start a one-shot HTTP server on port 8642 that serves the PNG
#   5. Print the URL — open it on your PC browser, scan from iPhone
#   6. Once you fetch the page once, the server shuts down automatically
#
# Note: ALSO requires the ConoHa security group to allow TCP/8642 inbound
# (one-time additional rule). If you can't add the security group rule,
# use the "ssh tunnel" fallback at the bottom of this file instead.
#
# https://github.com/AIAIdaisuki/kick-raid-blocker-mobile

set -uo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo bash $0" >&2
  exit 1
fi

PORT="${PORT:-8642}"

if ! command -v qrencode >/dev/null 2>&1; then
  echo "==> Installing qrencode (one moment)"
  NEEDRESTART_MODE=a apt-get update -qq
  NEEDRESTART_MODE=a DEBIAN_FRONTEND=noninteractive apt-get install -y qrencode >/dev/null
fi

echo "==> Reconstructing WireGuard config"
config=$(journalctl -u krb-mitmproxy --no-pager -o cat -n 500 | python3 -c '
import sys, re
data = sys.stdin.read()
matches = re.findall(r"\[Interface\][\s\S]*?Endpoint\s*=\s*\S+", data)
print(matches[-1] if matches else "")
')

if [[ -z "$config" ]]; then
  echo "ERROR: WireGuard config not found in journal." >&2
  echo "Try: systemctl restart krb-mitmproxy && sleep 3 && bash $0" >&2
  exit 1
fi

public_ip=$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}')
if [[ -n "${public_ip:-}" ]]; then
  config=$(printf '%s\n' "$config" | sed -E "s|^Endpoint\s*=.*$|Endpoint = ${public_ip}:51820|")
fi

OUT=/tmp/krb-qr.png
echo "==> Rendering PNG QR to ${OUT}"
printf '%s\n' "$config" | qrencode -o "$OUT" -s 8 -m 4

echo "==> Opening UFW for TCP/${PORT} (will be removed on exit)"
ufw allow "${PORT}/tcp" >/dev/null 2>&1 || true

trap 'ufw delete allow "'${PORT}'/tcp" >/dev/null 2>&1 || true; rm -f "'$OUT'"; echo "Cleaned up."' EXIT

cat <<EOF

==================================================================
 Open this URL in your PC browser:

     http://${public_ip:-<your-vps-ip>}:${PORT}/

 You'll see the QR as a sharp PNG image. Then:
   1. WireGuard app on iPhone -> "+" -> "Create from QR Code"
   2. Point iPhone camera at the QR on the PC monitor

 NOTE: You may also need to allow TCP/${PORT} INBOUND in the
       ConoHa security group (https://manage.conoha.jp/) if the
       page doesn't load. Add it the same way you added UDP/51820,
       then reload.

 The page disappears as soon as you load it once (single-shot).
 Press Ctrl+C here at any time to abort and cleanup.
==================================================================
EOF

# Single-shot HTTP server: serves the PNG once then exits.
python3 - "$OUT" "$PORT" <<'PYEOF'
import http.server, socketserver, sys, os, threading

png = sys.argv[1]
port = int(sys.argv[2])

class Once(http.server.BaseHTTPRequestHandler):
    served = False
    def do_GET(self):
        if Once.served:
            self.send_error(410, "Gone")
            return
        Once.served = True
        with open(png, "rb") as f:
            data = f.read()
        body = (
            b"<!doctype html><html><head><meta charset=utf-8>"
            b"<title>Scan with WireGuard iPhone app</title>"
            b"<style>body{background:#111;color:#eee;text-align:center;font-family:sans-serif}img{max-width:90vw;height:auto}</style>"
            b"</head><body><h1>Scan with the WireGuard iPhone app</h1>"
            b"<p>Use the +&nbsp;&rarr;&nbsp;Create from QR Code option.</p>"
            b"<img src=\"data:image/png;base64,"
        )
        import base64
        body += base64.b64encode(data)
        body += b"\"><p style=\"color:#888\">This page only renders once. After scanning, this VPS will close the temporary HTTP port.</p></body></html>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        # Kill the server after a short grace period so the response completes
        threading.Timer(2.0, lambda: os._exit(0)).start()
    def log_message(self, fmt, *args):
        pass

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", port), Once) as httpd:
    print(f"Listening on 0.0.0.0:{port} — waiting for one request...")
    httpd.serve_forever()
PYEOF
