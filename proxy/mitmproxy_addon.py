"""
Kick Raid Blocker — mitmproxy addon.

Drops Pusher messages with `App\\Events\\StreamHostEvent` /
`App\\Events\\StreamHostedEvent` so the Kick mobile app never sees the
raid notification and stays on the current channel. All other real-time
messages (chat, follows, subs, gifts, …) pass through unchanged.

Designed to be run on a user's own VPS so the Kick mobile app keeps
working from anywhere (cellular included), with chat fully alive.

Usage on the VPS (after installing mitmproxy >= 11):

    mitmdump --mode wireguard -s mitmproxy_addon.py

Then on the iPhone:
  1. Install the WireGuard client (free, Apple App Store)
  2. Scan the QR code mitmproxy printed on stdout
  3. Activate the WireGuard tunnel
  4. Visit http://mitm.it and install + trust the mitmproxy CA cert
  5. Open the Kick app — raids stop, everything else works

License: MIT
Source : https://github.com/AIAIdaisuki/kick-raid-blocker-mobile
"""

from __future__ import annotations

import json
import logging
import re
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


def _is_pusher(flow: http.HTTPFlow) -> bool:
    host = flow.request.pretty_host
    return bool(PUSHER_HOST_RE.match(host))


def websocket_message(flow: http.HTTPFlow) -> None:
    """mitmproxy hook: invoked once per WebSocket frame in either direction."""
    if flow.websocket is None:
        return
    if not _is_pusher(flow):
        return

    message = flow.websocket.messages[-1]

    # We only block events delivered FROM the Pusher server TO the client.
    # Client-to-server frames (subscribe, pings) are forwarded as-is so chat
    # and other features keep working.
    if message.from_client:
        return

    if message.is_text is False:
        # Pusher only sends JSON text frames for events; binary payloads
        # are not part of our threat model.
        return

    try:
        # Content can be bytes or str depending on mitmproxy version.
        raw = message.content
        if isinstance(raw, bytes):
            text = raw.decode("utf-8", errors="replace")
        else:
            text = raw
        frame = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return

    if not isinstance(frame, dict):
        return

    event_name = frame.get("event")
    if event_name in RAID_EVENTS:
        channel = frame.get("channel", "?")
        logger.info("[KRB] dropped %s on %s", event_name, channel)
        message.drop()


addons = [type("KickRaidBlocker", (), {"websocket_message": websocket_message})()]
