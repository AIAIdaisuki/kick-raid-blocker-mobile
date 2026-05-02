"""
Kick Raid Blocker — mitmproxy addon (v0.3.0).

Modes (configured by /opt/krb/conf/mode.txt):

  block-all   Drop every Pusher StreamHost(ed)?Event.
              (= old default; keeps the iPhone on the current channel
               regardless of where Kick wanted to redirect to.)

  blocklist   Drop only when ANY username extracted from the raid event
              matches /opt/krb/conf/blocklist.txt. Other raids pass through.

  allowlist   Drop everything EXCEPT raids whose target matches
              /opt/krb/conf/allowlist.txt.

The blocklist / allowlist are plain newline-separated usernames (lower-case
internally). Lines starting with `#` are comments, blank lines ignored.

Designed to be run on a user's own VPS so the Kick mobile app keeps
working from anywhere (cellular included), with chat fully alive.

Usage on the VPS (after installing mitmproxy >= 11):

    mitmdump --mode wireguard -s mitmproxy_addon.py

License: MIT
Source : https://github.com/AIAIdaisuki/kick-raid-blocker-mobile
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Final

from mitmproxy import http

logger = logging.getLogger("kick-raid-blocker")

RAID_EVENTS: Final[frozenset[str]] = frozenset({
    "App\\Events\\StreamHostEvent",
    "App\\Events\\StreamHostedEvent",
})

# Pusher cluster hostnames. Kick has used ws-us2, ws-mt1, ws-eu, ws-ap1,
# ws-ap2 historically; we accept any `ws-<cluster>.pusher.com` to be safe.
PUSHER_HOST_RE: Final[re.Pattern[str]] = re.compile(
    r"^ws-[a-z0-9-]+\.pusher\.com$",
    re.IGNORECASE,
)

VALID_MODES: Final[frozenset[str]] = frozenset({
    "block-all", "blocklist", "allowlist",
})

CONF_DIR: Final[Path] = Path("/opt/krb/conf")
MODE_PATH: Final[Path] = CONF_DIR / "mode.txt"
BLOCKLIST_PATH: Final[Path] = CONF_DIR / "blocklist.txt"
ALLOWLIST_PATH: Final[Path] = CONF_DIR / "allowlist.txt"


# ---------- helpers (factored out for unit tests) ----------

def parse_list(text: str) -> set[str]:
    """Parse newline-separated usernames; case-insensitive; ignore #comments.

    Same normalization as event-side: leading @ stripped, lower-cased. So
    ``@FooBar`` in the file matches ``foobar`` in an event payload.
    """
    out: set[str] = set()
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        # Take only first token in case the user typed "user # comment"
        token = s.split()[0].lstrip("@").lower()
        if token:
            out.add(token)
    return out


_list_cache: dict[Path, tuple[float, set[str]]] = {}

def load_list(path: Path) -> set[str]:
    """Read a list with mtime-based caching so edits take effect immediately."""
    try:
        if not path.exists():
            _list_cache.pop(path, None)
            return set()
        mtime = path.stat().st_mtime
        cached = _list_cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        s = parse_list(path.read_text(encoding="utf-8"))
        _list_cache[path] = (mtime, s)
        return s
    except OSError as e:
        logger.warning("[KRB] could not read %s: %s", path, e)
        return set()


def get_mode() -> str:
    try:
        if not MODE_PATH.exists():
            return "block-all"
        val = MODE_PATH.read_text(encoding="utf-8").strip().lower()
        return val if val in VALID_MODES else "block-all"
    except OSError:
        return "block-all"


def extract_usernames(data) -> set[str]:
    """Pull every username we can find out of a StreamHost(ed)?Event payload.

    Kick's payload shape has varied across versions / event names. Rather than
    guess which field is "the target", we collect ALL usernames present and
    let the caller match any of them against the user-configured list.
    Practical result: if you put @badactor on your blocklist, raids touching
    that streamer in any role get blocked.
    """
    out: set[str] = set()
    if not isinstance(data, dict):
        return out

    def add(v):
        if isinstance(v, str) and v:
            cleaned = v.strip().lstrip("@").lower()
            if cleaned:
                out.add(cleaned)

    # Direct top-level fields seen across libraries
    for key in ("host_username", "username", "target_username", "raid_username", "slug"):
        add(data.get(key))

    # Nested user / target / channel objects
    for key in ("user", "target", "channel", "host"):
        nested = data.get(key)
        if isinstance(nested, dict):
            for sub in ("username", "slug", "name"):
                add(nested.get(sub))

    return out


def decide(event_name: str, data) -> tuple[bool, str]:
    """Return (drop?, reason) given the configured mode."""
    if event_name not in RAID_EVENTS:
        return False, "non-raid event"

    mode = get_mode()
    usernames = extract_usernames(data)

    if mode == "block-all":
        return True, f"block-all mode; saw users={sorted(usernames) or 'none'}"

    if mode == "blocklist":
        blocked = load_list(BLOCKLIST_PATH)
        hit = usernames & blocked
        if hit:
            return True, f"target {sorted(hit)} on blocklist"
        return False, f"users={sorted(usernames) or 'none'} not on blocklist"

    if mode == "allowlist":
        allowed = load_list(ALLOWLIST_PATH)
        hit = usernames & allowed
        if hit:
            return False, f"target {sorted(hit)} on allowlist"
        return True, f"users={sorted(usernames) or 'none'} not on allowlist; default-deny"

    return False, f"unknown mode {mode!r}; default-pass"


def parse_frame(content) -> dict | None:
    """Best-effort: decode the outer Pusher envelope."""
    try:
        if isinstance(content, bytes):
            text = content.decode("utf-8", errors="replace")
        else:
            text = content
        obj = json.loads(text)
        return obj if isinstance(obj, dict) else None
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None


def parse_inner_data(envelope: dict):
    """Pusher's `data` field is itself JSON-encoded; unwrap it."""
    raw = envelope.get("data")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return raw


# ---------- mitmproxy hook ----------

def websocket_message(flow: http.HTTPFlow) -> None:
    if flow.websocket is None:
        return
    if not PUSHER_HOST_RE.match(flow.request.pretty_host):
        return

    message = flow.websocket.messages[-1]
    if message.from_client or not message.is_text:
        return

    envelope = parse_frame(message.content)
    if not envelope:
        return

    event_name = envelope.get("event")
    if event_name not in RAID_EVENTS:
        return

    inner = parse_inner_data(envelope)
    drop, reason = decide(event_name, inner)
    channel = envelope.get("channel", "?")

    if drop:
        logger.info("[KRB] DROP %s on %s — %s", event_name, channel, reason)
        message.drop()
    else:
        logger.info("[KRB] PASS %s on %s — %s", event_name, channel, reason)


addons = [type("KickRaidBlocker", (), {"websocket_message": websocket_message})()]
