#!/usr/bin/env python3
"""Kick Raid Blocker — admin web UI.

A tiny single-file HTTP server that exposes a mobile-friendly form for
editing /opt/krb/conf/{mode,blocklist,allowlist}.txt. No external deps —
just the Python stdlib. Same files are read by mitmproxy_addon.py, so
edits take effect on the very next raid event.

Authentication: a 256-bit random token is generated on first run and
stored in /opt/krb/conf/admin-token.txt. The full URL with token must
be bookmarked once on the iPhone; nobody without the token can access.
The token can be regenerated at any time by deleting that file and
restarting krb-admin.

Listens on 0.0.0.0:9876 by default. Override with `KRB_ADMIN_PORT`.

License: MIT
"""
from __future__ import annotations

import html
import http.server
import json
import os
import re
import secrets
import socketserver
import urllib.parse
from pathlib import Path

CONF_DIR = Path("/opt/krb/conf")
MODE_PATH = CONF_DIR / "mode.txt"
BLOCKLIST_PATH = CONF_DIR / "blocklist.txt"
ALLOWLIST_PATH = CONF_DIR / "allowlist.txt"
TOKEN_PATH = CONF_DIR / "admin-token.txt"

PORT = int(os.environ.get("KRB_ADMIN_PORT", "9876"))
SLUG_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
VALID_MODES = ("block-all", "blocklist", "allowlist")


# -------------------- helpers --------------------

def get_or_make_token() -> str:
    if TOKEN_PATH.exists():
        v = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if v:
            return v
    new = secrets.token_hex(32)
    TOKEN_PATH.write_text(new + "\n", encoding="utf-8")
    try:
        TOKEN_PATH.chmod(0o600)
    except OSError:
        pass
    return new


def read_list(p: Path) -> list[str]:
    if not p.exists():
        return []
    out = []
    seen = set()
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        token = s.split()[0].lstrip("@").lower()
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return out


def write_list(p: Path, items: list[str], header: str) -> None:
    body = header.rstrip("\n") + "\n"
    body += "\n".join(items)
    if items:
        body += "\n"
    p.write_text(body, encoding="utf-8")


def normalize_slug(raw: str) -> str | None:
    s = raw.strip().lstrip("@").lower()
    return s if SLUG_RE.match(s) else None


def get_mode() -> str:
    if not MODE_PATH.exists():
        return "block-all"
    v = MODE_PATH.read_text(encoding="utf-8").strip().lower()
    return v if v in VALID_MODES else "block-all"


def set_mode(m: str) -> bool:
    if m in VALID_MODES:
        MODE_PATH.write_text(m + "\n", encoding="utf-8")
        return True
    return False


# -------------------- rendering --------------------

CSS = """
body { background:#0e0e10; color:#eee; font-family:-apple-system,BlinkMacSystemFont,sans-serif; padding:14px; max-width:640px; margin:0 auto; line-height:1.5; }
h1 { font-size:20px; margin:0 0 12px 0; }
h2 { font-size:16px; margin:0 0 8px 0; }
.card { background:#1a1a1d; border:1px solid #2b2b30; border-radius:12px; padding:14px; margin:12px 0; }
input[type=text], select { width:100%; padding:10px 12px; background:#2a2a2d; color:#fff; border:1px solid #444; border-radius:8px; font:16px monospace; box-sizing:border-box; -webkit-appearance:none; }
button { background:#53fc18; color:#000; border:none; padding:11px 14px; border-radius:8px; font-weight:bold; cursor:pointer; font-size:15px; }
button.del { background:#c44; color:#fff; padding:6px 10px; font-size:13px; }
.row { display:flex; gap:8px; margin:8px 0; align-items:center; }
.row > input { flex:1; }
.row > select { flex:1; }
.list-item { display:flex; gap:10px; align-items:center; padding:8px 0; border-bottom:1px solid #2b2b30; }
.list-item:last-child { border-bottom:none; }
.list-item code { flex:1; font-size:15px; word-break:break-all; }
.empty { color:#666; font-style:italic; padding:8px 0; }
.msg { padding:10px 12px; border-radius:8px; margin:10px 0; font-size:14px; }
.msg.ok { background:#1f3d1f; color:#a3f5a3; border:1px solid #2f6f2f; }
.msg.err { background:#3d1f1f; color:#f5a3a3; border:1px solid #6f2f2f; }
.muted { color:#888; font-size:13px; margin-top:6px; }
.tabs { display:flex; gap:4px; background:#161618; padding:4px; border-radius:10px; border:1px solid #2b2b30; margin-bottom:8px; }
.tabs span { flex:1; text-align:center; padding:8px 4px; font-size:13px; color:#888; }
.tabs span.active { background:#1a1a1d; color:#fff; border-radius:6px; }
.footer { text-align:center; color:#666; font-size:12px; margin-top:24px; }
.modepill { display:inline-block; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:bold; }
.modepill.block-all { background:#553; color:#fc4; }
.modepill.blocklist { background:#535; color:#f4c; }
.modepill.allowlist { background:#355; color:#4cf; }
"""


def page(token: str, message: str = "", error: str = "") -> bytes:
    bl = read_list(BLOCKLIST_PATH)
    al = read_list(ALLOWLIST_PATH)
    mode = get_mode()

    msg_html = ""
    if message:
        msg_html = f'<div class="msg ok">{html.escape(message)}</div>'
    if error:
        msg_html = f'<div class="msg err">{html.escape(error)}</div>'

    def render_list_section(label: str, items: list[str], list_kind: str) -> str:
        if items:
            rows = "\n".join(
                f'''<div class="list-item">
                       <code>{html.escape(s)}</code>
                       <form method="POST" action="?token={html.escape(token)}" style="margin:0">
                         <input type="hidden" name="action" value="remove_{list_kind}">
                         <input type="hidden" name="slug" value="{html.escape(s)}">
                         <button class="del" type="submit">削除</button>
                       </form>
                     </div>'''
                for s in items
            )
        else:
            rows = '<div class="empty">(空)</div>'

        return f'''
        <div class="card">
          <h2>{label} ({len(items)})</h2>
          <form method="POST" action="?token={html.escape(token)}">
            <input type="hidden" name="action" value="add_{list_kind}">
            <div class="row">
              <input type="text" name="slug" placeholder="kick.com の配信者slug" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" required>
              <button type="submit">+ 追加</button>
            </div>
          </form>
          {rows}
        </div>
        '''

    body = f'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>KRB Admin</title>
<style>{CSS}</style>
</head>
<body>
<h1>🛡 Kick Raid Blocker</h1>
{msg_html}

<div class="card">
  <h2>現在のモード</h2>
  <p><span class="modepill {html.escape(mode)}">{html.escape(mode)}</span></p>
  <form method="POST" action="?token={html.escape(token)}">
    <input type="hidden" name="action" value="setmode">
    <div class="row">
      <select name="mode">
        <option value="block-all" {"selected" if mode == "block-all" else ""}>block-all — 全レイドブロック</option>
        <option value="blocklist" {"selected" if mode == "blocklist" else ""}>blocklist — リストの配信者だけブロック</option>
        <option value="allowlist" {"selected" if mode == "allowlist" else ""}>allowlist — リストの配信者だけ通す</option>
      </select>
      <button type="submit">変更</button>
    </div>
  </form>
</div>

{render_list_section("ブロックリスト", bl, "block")}
{render_list_section("許可リスト", al, "allow")}

<div class="card">
  <h2>📊 動作確認</h2>
  <p class="muted">レイド発生時の判定はSSHで <code>sudo krb watch</code> でライブ表示できます。</p>
</div>

<div class="footer">
  Kick Raid Blocker · Admin Panel · 編集は即時反映（restart 不要）
</div>
</body>
</html>'''
    return body.encode("utf-8")


# -------------------- HTTP handler --------------------

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "krb-admin/1.0"

    def _check_token(self) -> bool:
        parsed = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(parsed.query)
        return qs.get("token", [""])[0] == TOKEN

    def _send(self, code: int, body: bytes, content_type: str = "text/html; charset=utf-8") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _redirect_back(self, message: str = "", error: str = "") -> None:
        params = {"token": TOKEN}
        if message:
            params["m"] = message
        if error:
            params["e"] = error
        self.send_response(303)
        self.send_header("Location", "/?" + urllib.parse.urlencode(params))
        self.end_headers()

    def do_GET(self) -> None:
        if not self._check_token():
            self._send(401, b"<h1>401</h1><p>token required</p>")
            return
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/":
            self._send(404, b"<h1>404</h1>")
            return
        qs = urllib.parse.parse_qs(parsed.query)
        msg = qs.get("m", [""])[0][:200]
        err = qs.get("e", [""])[0][:200]
        self._send(200, page(TOKEN, msg, err))

    def do_POST(self) -> None:
        if not self._check_token():
            self._send(401, b"<h1>401</h1><p>token required</p>")
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length > 16384:
            self._send(413, b"too large")
            return
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        form = urllib.parse.parse_qs(raw)

        action = form.get("action", [""])[0]
        slug_raw = form.get("slug", [""])[0]
        mode_raw = form.get("mode", [""])[0]

        try:
            if action == "setmode":
                if set_mode(mode_raw):
                    self._redirect_back(f"モードを {mode_raw} に変更しました")
                else:
                    self._redirect_back(error="無効なモードです")
                return

            if action in ("add_block", "add_allow"):
                slug = normalize_slug(slug_raw)
                if not slug:
                    self._redirect_back(error=f"'{slug_raw}' は無効なslugです（a-z 0-9 _ - 1〜32文字）")
                    return
                path = BLOCKLIST_PATH if action == "add_block" else ALLOWLIST_PATH
                items = read_list(path)
                if slug in items:
                    self._redirect_back(f"'{slug}' は既にあります")
                    return
                items.append(slug)
                header = "# Edited via admin web UI."
                write_list(path, items, header)
                self._redirect_back(f"'{slug}' を追加しました")
                return

            if action in ("remove_block", "remove_allow"):
                slug = normalize_slug(slug_raw)
                if not slug:
                    self._redirect_back(error="無効なslugです")
                    return
                path = BLOCKLIST_PATH if action == "remove_block" else ALLOWLIST_PATH
                items = read_list(path)
                if slug not in items:
                    self._redirect_back(error=f"'{slug}' はリストにありません")
                    return
                items = [s for s in items if s != slug]
                header = "# Edited via admin web UI."
                write_list(path, items, header)
                self._redirect_back(f"'{slug}' を削除しました")
                return

            self._redirect_back(error="不明なアクションです")
        except OSError as e:
            self._redirect_back(error=f"書き込みエラー: {e}")

    def log_message(self, fmt: str, *args) -> None:  # quiet logs
        pass


# -------------------- main --------------------

def main() -> None:
    if not CONF_DIR.exists():
        raise SystemExit(f"{CONF_DIR} not found — install Kick Raid Blocker first")
    global TOKEN
    TOKEN = get_or_make_token()
    print(f"[krb-admin] listening on 0.0.0.0:{PORT}")
    print(f"[krb-admin] token URL ends with ...{TOKEN[-8:]} (full token in {TOKEN_PATH})")
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("", PORT), Handler) as srv:
        srv.serve_forever()


if __name__ == "__main__":
    main()
