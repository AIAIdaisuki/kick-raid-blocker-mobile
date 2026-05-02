#!/usr/bin/env python3
"""Kick Raid Blocker — admin web UI (v0.4.0, with Shobon Kick Ranking).

A tiny single-file HTTP server that:
  - reads/writes /opt/krb/conf/{mode,blocklist,allowlist}.txt
    (same files mitmproxy_addon.py reads — edits take effect immediately)
  - pulls live Japanese Kick streamer data from
    https://shobon-ranking.ddns.net/ and renders a mobile-friendly card
    list, so blocking is a single tap on the streamer's avatar/name
    instead of typing slugs.

No external dependencies — Python stdlib only.

Authentication: a 256-bit hex token in /opt/krb/conf/admin-token.txt is
required on every request as `?token=...` query parameter.

Listens on 0.0.0.0:9876 by default. Override with KRB_ADMIN_PORT.

License: MIT
"""
from __future__ import annotations

import html
import http.server
import json
import logging
import os
import re
import secrets
import socketserver
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

logger = logging.getLogger("krb-admin")

CONF_DIR = Path("/opt/krb/conf")
MODE_PATH = CONF_DIR / "mode.txt"
BLOCKLIST_PATH = CONF_DIR / "blocklist.txt"
ALLOWLIST_PATH = CONF_DIR / "allowlist.txt"
TOKEN_PATH = CONF_DIR / "admin-token.txt"

PORT = int(os.environ.get("KRB_ADMIN_PORT", "9876"))
SLUG_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
VALID_MODES = ("block-all", "blocklist", "allowlist")

SHOBON_LIST_URL = "https://shobon-ranking.ddns.net/api/getJsonData?file=./mnt/jp/live/min/list.json"
SHOBON_SNAP_BASE = "https://shobon-ranking.ddns.net/api/getJsonData?file=./mnt/jp/live/min/"
SHOBON_TEAMS_URL = "https://shobon-ranking.ddns.net/data/teamlist.json"
SHOBON_CACHE_TTL = 60  # seconds for streamers
SHOBON_TEAMS_TTL = 1800  # seconds for teams (changes rarely)


# -------------------- list / mode IO --------------------

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
    if items:
        body += "\n".join(items) + "\n"
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


# -------------------- Shobon ranking fetch --------------------

_shobon_cache: dict = {"ts": 0.0, "streamers": [], "error": None}
_shobon_teams_cache: dict = {"ts": 0.0, "teams": [], "error": None}
_shobon_lock = threading.Lock()


def _http_get_json(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers={
        "User-Agent": "kick-raid-blocker-admin/0.4 (+https://github.com/AIAIdaisuki/kick-raid-blocker-mobile)",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def fetch_shobon_streamers() -> tuple[list[dict], str | None]:
    """Return (streamers, error_message). Falls back to cached value on error."""
    with _shobon_lock:
        now = time.time()
        if now - _shobon_cache["ts"] < SHOBON_CACHE_TTL and _shobon_cache["streamers"]:
            return _shobon_cache["streamers"], _shobon_cache["error"]
        try:
            files = _http_get_json(SHOBON_LIST_URL)
            if not isinstance(files, list) or not files:
                raise RuntimeError("empty list.json")
            latest = files[0]
            snap = _http_get_json(SHOBON_SNAP_BASE + urllib.parse.quote(latest, safe=""))
            raw = snap.get("data") if isinstance(snap, dict) else None
            if not isinstance(raw, list):
                raise RuntimeError("snapshot has no data array")
            live: list[dict] = []
            for s in raw:
                if not isinstance(s, dict):
                    continue
                slug = (s.get("slug") or "").strip().lower()
                if not slug or not SLUG_RE.match(slug):
                    continue
                stream = s.get("stream") if isinstance(s.get("stream"), dict) else {}
                if not stream.get("is_live"):
                    continue
                cat = stream.get("category") if isinstance(stream.get("category"), dict) else {}
                live.append({
                    "slug": slug,
                    "viewers": int(stream.get("viewer_count") or 0),
                    "title": (stream.get("title") or "").strip()[:120],
                    "category": (cat.get("name") or "").strip()[:40],
                    "picture": s.get("profile_picture") or "",
                    "duration_hour": float(stream.get("duration_hour") or 0),
                })
            live.sort(key=lambda x: -x["viewers"])
            _shobon_cache.update(ts=now, streamers=live, error=None)
            return live, None
        except Exception as e:
            err = f"Shobon fetch failed: {e}"
            logger.warning(err)
            _shobon_cache["error"] = err
            # Keep stale data if any
            return _shobon_cache["streamers"], err


def fetch_shobon_teams() -> tuple[list[dict], str | None]:
    """Return (teams, error_message). Cached separately from streamer list."""
    with _shobon_lock:
        now = time.time()
        if now - _shobon_teams_cache["ts"] < SHOBON_TEAMS_TTL and _shobon_teams_cache["teams"]:
            return _shobon_teams_cache["teams"], _shobon_teams_cache["error"]
        try:
            data = _http_get_json(SHOBON_TEAMS_URL)
            if not isinstance(data, list):
                raise RuntimeError("teamlist.json is not an array")
            teams: list[dict] = []
            for t in data:
                if not isinstance(t, dict):
                    continue
                if t.get("frozen"):
                    continue  # skip dissolved / inactive teams
                members = t.get("members") or []
                if not isinstance(members, list):
                    continue
                clean_members = [
                    s.strip().lower() for s in members
                    if isinstance(s, str) and SLUG_RE.match(s.strip().lower())
                ]
                teams.append({
                    "id": str(t.get("team_id") or "")[:16],
                    "name": (t.get("team_name_display") or t.get("team_name") or "").strip()[:40],
                    "color": (t.get("color") or "#888")[:16],
                    "members": clean_members,
                })
            _shobon_teams_cache.update(ts=now, teams=teams, error=None)
            return teams, None
        except Exception as e:
            err = f"Shobon teams fetch failed: {e}"
            logger.warning(err)
            _shobon_teams_cache["error"] = err
            return _shobon_teams_cache["teams"], err


# -------------------- HTML rendering --------------------

CSS = """
* { box-sizing: border-box; }
body { background:#0e0e10; color:#eee; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; margin:0; padding:14px 12px 80px; max-width:760px; margin:0 auto; line-height:1.5; }
h1 { font-size:20px; margin:0 0 12px 0; }
h2 { font-size:15px; margin:0 0 8px 0; color:#aaa; }
.card { background:#1a1a1d; border:1px solid #2b2b30; border-radius:12px; padding:12px; margin:10px 0; }
input[type=text], input[type=search], select { width:100%; padding:10px 12px; background:#2a2a2d; color:#fff; border:1px solid #444; border-radius:8px; font:16px monospace; -webkit-appearance:none; }
.search { font:16px sans-serif; }
button { background:#53fc18; color:#000; border:none; padding:9px 12px; border-radius:8px; font-weight:bold; cursor:pointer; font-size:14px; }
button.del, button.unblock { background:#c44; color:#fff; }
button.tiny { padding:6px 10px; font-size:12px; }
.row { display:flex; gap:8px; margin:8px 0; align-items:center; }
.row > input, .row > select { flex:1; }
.streamer { display:flex; gap:10px; align-items:center; padding:10px; border-bottom:1px solid #2b2b30; }
.streamer:last-child { border-bottom:none; }
.streamer img { width:40px; height:40px; border-radius:50%; flex-shrink:0; background:#222; }
.streamer .info { flex:1; min-width:0; }
.streamer .name { font-weight:bold; font-size:15px; }
.streamer .slug { color:#888; font-size:12px; font-family:monospace; }
.streamer .meta { color:#888; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:2px; }
.streamer .title { color:#bbb; font-size:12px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; margin-top:2px; }
.viewers { color:#53fc18; font-weight:bold; font-size:13px; }
.category { color:#888; }
.duration { color:#888; }
.msg { padding:10px 12px; border-radius:8px; margin:10px 0; font-size:14px; }
.msg.ok { background:#1f3d1f; color:#a3f5a3; border:1px solid #2f6f2f; }
.msg.err { background:#3d1f1f; color:#f5a3a3; border:1px solid #6f2f2f; }
.msg.warn { background:#3d2f1f; color:#f5d3a3; border:1px solid #6f5f2f; }
.modepill { display:inline-block; padding:4px 10px; border-radius:999px; font-size:12px; font-weight:bold; }
.modepill.block-all { background:#553; color:#fc4; }
.modepill.blocklist { background:#535; color:#f4c; }
.modepill.allowlist { background:#355; color:#4cf; }
.muted { color:#888; font-size:12px; }
.footer { text-align:center; color:#666; font-size:12px; margin-top:24px; }
.tag { display:inline-block; padding:1px 6px; background:#2a2a2d; border-radius:4px; font-size:11px; color:#bbb; margin-right:4px; font-family:monospace; }
.list-item { display:flex; gap:10px; align-items:center; padding:8px 0; border-bottom:1px solid #2b2b30; }
.list-item:last-child { border-bottom:none; }
.list-item code { flex:1; font-size:14px; }
.teamblock { margin:6px 0; border:1px solid #2b2b30; border-radius:10px; background:#15151a; }
.teamblock > summary { padding:12px; cursor:pointer; font-size:14px; list-style:none; -webkit-tap-highlight-color:transparent; }
.teamblock > summary::-webkit-details-marker { display:none; }
.teamblock > summary::before { content:"▶"; display:inline-block; transition:transform .15s; color:#888; margin-right:6px; font-size:11px; }
.teamblock[open] > summary::before { transform:rotate(90deg); }
.teamblock > div { padding:0 12px 8px; }
.teamcolor { display:inline-block; width:10px; height:10px; border-radius:50%; vertical-align:middle; margin-right:6px; }
.livebadge { color:#53fc18; font-size:12px; font-weight:bold; margin-left:4px; }
.tabs { display:flex; gap:4px; background:#161618; padding:4px; border-radius:10px; border:1px solid #2b2b30; margin:8px 0; }
.tabs > a { flex:1; text-align:center; padding:8px 4px; font-size:13px; color:#888; text-decoration:none; border-radius:6px; }
.tabs > a.active { background:#1a1a1d; color:#fff; }
"""


def render_streamer_card(s: dict, is_blocked: bool, token: str) -> str:
    slug = s["slug"]
    pic = s.get("picture") or ""
    viewers = s["viewers"]
    title = s.get("title", "")
    cat = s.get("category", "")
    dur = s.get("duration_hour", 0)
    btn_action = "remove_block" if is_blocked else "add_block"
    btn_label = "解除" if is_blocked else "ブロック"
    btn_cls = "unblock" if is_blocked else ""
    img_html = f'<img src="{html.escape(pic)}" alt="" loading="lazy" referrerpolicy="no-referrer">' if pic else '<div style="width:40px;height:40px;border-radius:50%;background:#333"></div>'
    return f'''
    <div class="streamer" data-slug="{html.escape(slug)}">
      {img_html}
      <div class="info">
        <div class="name">{html.escape(slug)}</div>
        <div class="meta"><span class="viewers">👁 {viewers:,}</span> · <span class="category">{html.escape(cat)}</span> · <span class="duration">{dur:.1f}h</span></div>
        <div class="title">{html.escape(title)}</div>
      </div>
      <form method="POST" action="?token={html.escape(token)}" style="margin:0">
        <input type="hidden" name="action" value="{btn_action}">
        <input type="hidden" name="slug" value="{html.escape(slug)}">
        <button class="tiny {btn_cls}" type="submit">{btn_label}</button>
      </form>
    </div>'''


def render_offline_member(slug: str, is_blocked: bool, token: str) -> str:
    btn_action = "remove_block" if is_blocked else "add_block"
    btn_label = "解除" if is_blocked else "ブロック"
    btn_cls = "unblock" if is_blocked else ""
    return f'''
    <div class="streamer" data-slug="{html.escape(slug)}">
      <div style="width:40px;height:40px;border-radius:50%;background:#333"></div>
      <div class="info">
        <div class="name">{html.escape(slug)}</div>
        <div class="meta muted">オフライン</div>
      </div>
      <form method="POST" action="?token={html.escape(token)}" style="margin:0">
        <input type="hidden" name="action" value="{btn_action}">
        <input type="hidden" name="slug" value="{html.escape(slug)}">
        <button class="tiny {btn_cls}" type="submit">{btn_label}</button>
      </form>
    </div>'''


def render_team_section(team: dict, streamers_by_slug: dict, blocklist_set: set, token: str) -> str:
    members = team.get("members", [])
    if not members:
        return ""
    live_count = sum(1 for s in members if s in streamers_by_slug)
    color = team.get("color") or "#888"
    cards = []
    # Live members first, by viewer count desc
    live_members = sorted(
        (m for m in members if m in streamers_by_slug),
        key=lambda m: -streamers_by_slug[m]["viewers"]
    )
    for m in live_members:
        cards.append(render_streamer_card(streamers_by_slug[m], m in blocklist_set, token))
    for m in members:
        if m not in streamers_by_slug:
            cards.append(render_offline_member(m, m in blocklist_set, token))

    summary_badge = f'<span class="livebadge">●{live_count}名ライブ</span>' if live_count else '<span class="muted">全員オフライン</span>'
    return f'''
    <details class="teamblock">
      <summary>
        <span class="teamcolor" style="background:{html.escape(color)}"></span>
        <strong>{html.escape(team["name"])}</strong>
        <span class="muted">({len(members)}人)</span>
        · {summary_badge}
      </summary>
      <div>
        {"".join(cards)}
      </div>
    </details>
    '''


def page(token: str, message: str = "", error: str = "", view: str = "rank") -> bytes:
    bl = read_list(BLOCKLIST_PATH)
    al = read_list(ALLOWLIST_PATH)
    mode = get_mode()
    streamers, shobon_err = fetch_shobon_streamers()
    teams, teams_err = fetch_shobon_teams() if view == "teams" else ([], None)

    bl_set = set(bl)
    streamers_by_slug = {s["slug"]: s for s in streamers}

    msg_html = ""
    if message:
        msg_html = f'<div class="msg ok">{html.escape(message)}</div>'
    if error:
        msg_html = f'<div class="msg err">{html.escape(error)}</div>'

    shobon_warn = ""
    if shobon_err:
        shobon_warn = f'<div class="msg warn">⚠ Shobon ranking fetch failed (showing cached or empty list): {html.escape(shobon_err)}</div>'

    # Blocked streamers section: show ALL blocked entries (even those not currently live)
    blocked_cards_parts = []
    for slug in bl:
        if slug in streamers_by_slug:
            blocked_cards_parts.append(render_streamer_card(streamers_by_slug[slug], True, token))
        else:
            blocked_cards_parts.append(render_offline_member(slug, True, token))
    blocked_section = "\n".join(blocked_cards_parts) if blocked_cards_parts else '<div class="muted" style="padding:8px 0;">(空)</div>'

    # Live streamer cards (excluding already-blocked, those are shown above)
    live_cards = "\n".join(
        render_streamer_card(s, False, token)
        for s in streamers if s["slug"] not in bl_set
    ) if streamers else '<div class="muted" style="padding:8px 0;">(配信者リスト未取得)</div>'

    # Team-grouped cards
    if view == "teams":
        team_section_html = "\n".join(
            render_team_section(t, streamers_by_slug, bl_set, token)
            for t in teams if t.get("members")
        ) if teams else '<div class="muted" style="padding:8px 0;">(チームデータ未取得)</div>'
        teams_warn = ""
        if teams_err:
            teams_warn = f'<div class="msg warn">⚠ チームデータ取得失敗: {html.escape(teams_err)}</div>'
        main_view_block = f'''
<div class="card">
  <h2>👥 チーム別</h2>
  {teams_warn}
  <div class="row">
    <input class="search" type="search" placeholder="🔍 配信者slugで絞り込み" oninput="filt(this)">
  </div>
  {team_section_html}
</div>'''
    else:
        main_view_block = f'''
<div class="card">
  <h2>📺 ライブ中の配信者（Shobon Ranking）</h2>
  {shobon_warn}
  <div class="row">
    <input class="search" type="search" placeholder="🔍 配信者名で絞り込み" oninput="filt(this)">
  </div>
  <div id="streamers">
    {live_cards}
  </div>
</div>'''

    # Tab navigation
    tab_token = html.escape(token)
    tabs_html = f'''
<div class="tabs">
  <a href="/?token={tab_token}&view=rank" class="{'active' if view != 'teams' else ''}">📺 ランキング</a>
  <a href="/?token={tab_token}&view=teams" class="{'active' if view == 'teams' else ''}">👥 チーム別</a>
</div>'''

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
  <h2>モード</h2>
  <p style="margin:0 0 8px 0"><span class="modepill {html.escape(mode)}">{html.escape(mode)}</span></p>
  <form method="POST" action="?token={html.escape(token)}">
    <input type="hidden" name="action" value="setmode">
    <div class="row">
      <select name="mode">
        <option value="block-all" {"selected" if mode == "block-all" else ""}>block-all (全レイドブロック)</option>
        <option value="blocklist" {"selected" if mode == "blocklist" else ""}>blocklist (リストの配信者だけブロック)</option>
        <option value="allowlist" {"selected" if mode == "allowlist" else ""}>allowlist (リストの配信者だけ通す)</option>
      </select>
      <button type="submit">変更</button>
    </div>
  </form>
</div>

<div class="card">
  <h2>📛 ブロックリスト ({len(bl)})</h2>
  {blocked_section}
</div>

{tabs_html}

{main_view_block}

<div class="card">
  <h2>+ 手動でslugを追加（リストにない配信者など）</h2>
  <form method="POST" action="?token={html.escape(token)}">
    <input type="hidden" name="action" value="add_block">
    <div class="row">
      <input type="text" name="slug" placeholder="streamer-slug" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" required>
      <button type="submit">+ 追加</button>
    </div>
    <p class="muted">小文字英数字 + アンダースコア・ハイフン、1〜32文字</p>
  </form>
</div>

<div class="footer">
  Kick Raid Blocker v0.4 · データ提供: <a href="https://shobon-ranking.ddns.net/" target="_blank" rel="noopener" style="color:#888">Shobon Kick Ranking</a><br>
  編集は次のレイドイベントから即時反映
</div>

<script>
function filt(input) {{
  const q = input.value.trim().toLowerCase();
  const items = document.querySelectorAll('.streamer');
  for (const it of items) {{
    const slug = (it.dataset.slug || '').toLowerCase();
    it.style.display = slug.includes(q) ? '' : 'none';
  }}
  // When filtering, auto-expand teams that have visible members
  for (const team of document.querySelectorAll('.teamblock')) {{
    if (q.length === 0) {{ team.removeAttribute('open'); continue; }}
    const visibleMembers = Array.from(team.querySelectorAll('.streamer')).filter(s => s.style.display !== 'none');
    if (visibleMembers.length > 0) team.setAttribute('open', '');
    else team.removeAttribute('open');
  }}
}}
</script>
</body>
</html>'''
    return body.encode("utf-8")


# -------------------- HTTP handler --------------------

class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "krb-admin/0.4"

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
        view = qs.get("view", ["rank"])[0]
        if view not in ("rank", "teams"):
            view = "rank"
        self._send(200, page(TOKEN, msg, err, view))

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
                write_list(path, items, "# Edited via admin web UI.")
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
                write_list(path, items, "# Edited via admin web UI.")
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
