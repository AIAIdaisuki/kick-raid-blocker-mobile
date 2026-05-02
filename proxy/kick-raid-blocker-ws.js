// Kick Raid Blocker — WebSocket frame interceptor
//
// Drops Pusher messages with event names that trigger Kick's auto-redirect
// (`App\\Events\\StreamHostEvent` / `StreamHostedEvent`), so the Kick mobile
// app never sees the raid notification and stays on the current channel.
// All other real-time messages (chat, followers, subs, gifts) pass through
// unchanged.
//
// Designed for Surge (`type=websocket-message`) but the core logic also
// works in any iOS proxy app whose script engine exposes the WebSocket
// frame body and can return a modified body.
//
// IMPORTANT: this script must be loaded via an HTTPS-MITM proxy app
// (Surge, Loon, etc.) with MITM enabled for `ws-*.pusher.com`. It cannot
// run inside the Kick app or a normal browser by itself.
//
// License: MIT
// Source : https://github.com/AIAIdaisuki/kick-raid-blocker-mobile

const RAID_EVENTS = new Set([
  'App\\Events\\StreamHostEvent',
  'App\\Events\\StreamHostedEvent',
]);

(function main() {
  // Surge passes the frame body in $websocket.body for type=websocket-message
  const body = (typeof $websocket !== 'undefined' && $websocket.body) || '';
  if (!body) {
    safeDone({});
    return;
  }

  let frame;
  try {
    frame = JSON.parse(body);
  } catch (_) {
    // Non-JSON frame (e.g. pusher:ping). Pass through.
    safeDone({});
    return;
  }

  const eventName = (frame && typeof frame.event === 'string') ? frame.event : '';
  if (RAID_EVENTS.has(eventName)) {
    // Replace the event name so it has no handler in the app, while keeping
    // the frame syntactically valid. Returning an empty body would also work
    // but some clients log the empty frame as a protocol error.
    frame.event = 'App\\Events\\__krb_dropped__';
    if (typeof console !== 'undefined' && console.log) {
      console.log('[KRB] dropped raid event on', frame.channel || '?');
    }
    safeDone({ body: JSON.stringify(frame) });
    return;
  }

  safeDone({});
})();

function safeDone(payload) {
  if (typeof $done === 'function') {
    $done(payload);
  }
}
