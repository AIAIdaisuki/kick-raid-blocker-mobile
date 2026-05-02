#!/usr/bin/env bash
# Kick Raid Blocker — render the admin URL (with auth token) as a PNG QR
# code and serve it once over a temporary HTTP server, so the URL can be
# transferred onto the iPhone via camera scan instead of error-prone
# copy/paste.
#
# Pre-req: TCP/8642 must be allowed in your ConoHa security group.
# This script also opens UFW for TCP/8642 (and removes that rule on exit).
#
# https://github.com/AIAIdaisuki/kick-raid-blocker-mobile

set -uo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root: sudo bash $0" >&2
  exit 1
fi

PORT=8642

# Need qrencode
if ! command -v qrencode >/dev/null 2>&1; then
  NEEDRESTART_MODE=a DEBIAN_FRONTEND=noninteractive apt-get install -y qrencode >/dev/null
fi

TOKEN_FILE=/opt/krb/conf/admin-token.txt
if [[ ! -s "$TOKEN_FILE" ]]; then
  echo "ERROR: $TOKEN_FILE missing or empty. Is krb-admin running?" >&2
  exit 1
fi

PUBIP=$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null \
     || hostname -I 2>/dev/null | awk '{print $1}')
if [[ -z "${PUBIP:-}" ]]; then
  echo "ERROR: could not detect public IP." >&2
  exit 1
fi

URL="http://${PUBIP}:9876/?token=$(cat "$TOKEN_FILE")"
PNG=/tmp/krb-admin-qr.png

qrencode -o "$PNG" -s 8 -m 4 "$URL"
ufw allow "${PORT}/tcp" >/dev/null 2>&1 || true

trap 'ufw delete allow "'${PORT}'/tcp" >/dev/null 2>&1 || true; rm -f "'$PNG'"; echo Cleaned up.' EXIT

cat <<EOF

==================================================================
 STEP 1 — open this URL in your PC browser:

     http://${PUBIP}:${PORT}/

 STEP 2 — a black page with a big QR code appears.

 STEP 3 — point your iPhone camera at the QR.
          Tap the yellow banner to open in Safari.
          The admin panel loads — bookmark or "Add to Home Screen".

 STEP 4 — close this command (Ctrl+C) when done. Cleanup is automatic.
==================================================================
EOF

python3 - "$PNG" "$PORT" <<'PYEOF'
import http.server, socketserver, sys, os, threading, base64

png_path, port = sys.argv[1], int(sys.argv[2])
with open(png_path, "rb") as f:
    png_b64 = base64.b64encode(f.read()).decode()

class H(http.server.BaseHTTPRequestHandler):
    served = False
    def do_GET(self):
        if H.served:
            self.send_error(410, "Gone")
            return
        H.served = True
        body = (
            "<!doctype html><html><head><meta charset=utf-8>"
            "<title>Scan with iPhone Camera</title>"
            "<style>body{background:#111;color:#eee;text-align:center;"
            "font-family:-apple-system,sans-serif;padding:20px}"
            "img{max-width:92vw;height:auto}</style></head>"
            "<body><h1>Scan with iPhone Camera</h1>"
            f'<img src="data:image/png;base64,{png_b64}">'
            "<p>1. Point iPhone Camera at the QR<br>"
            "2. Tap the yellow Safari banner<br>"
            "3. The Kick Raid Blocker admin panel opens</p>"
            "<p style=\"color:#888;font-size:12px\">"
            "This page disappears after one load. Do not share the URL.</p>"
            "</body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        threading.Timer(2.0, lambda: os._exit(0)).start()
    def log_message(self, *_a):
        pass

socketserver.TCPServer.allow_reuse_address = True
with socketserver.TCPServer(("", port), H) as srv:
    print(f"Listening on 0.0.0.0:{port} — waiting for one PC browser request...")
    srv.serve_forever()
PYEOF
