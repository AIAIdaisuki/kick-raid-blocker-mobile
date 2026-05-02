// ==UserScript==
// @name         Kick Raid Blocker Mobile
// @name:ja      Kick レイドブロッカー モバイル
// @namespace    https://github.com/AIAIdaisuki/kick-raid-blocker-mobile
// @version      0.1.0
// @description  Block Kick.com raid/host auto-redirects. Works on iPhone (Userscripts.app), Android (Tampermonkey on Kiwi/Firefox), and PC. Allow/block lists supported. Clean-room implementation.
// @description:ja Kick.comのレイド（ホスト）自動リダイレクトをブロックします。iPhone（Userscripts）/ Android（Tampermonkey）/ PC で動作。許可・ブロックリスト対応。クリーンルーム実装。
// @author       AIAIdaisuki
// @match        *://kick.com/*
// @match        *://*.kick.com/*
// @run-at       document-start
// @grant        GM.setValue
// @grant        GM.getValue
// @license      MIT
// @homepageURL  https://github.com/AIAIdaisuki/kick-raid-blocker-mobile
// @supportURL   https://github.com/AIAIdaisuki/kick-raid-blocker-mobile/issues
// @updateURL    https://raw.githubusercontent.com/AIAIdaisuki/kick-raid-blocker-mobile/main/kick-raid-blocker-mobile.user.js
// @downloadURL  https://raw.githubusercontent.com/AIAIdaisuki/kick-raid-blocker-mobile/main/kick-raid-blocker-mobile.user.js
// ==/UserScript==

(function () {
  'use strict';

  const SCRIPT_NAME = 'Kick Raid Blocker Mobile';
  const STORAGE_KEY = 'krb-mobile-config-v1';
  const LOG_MAX = 50;
  const USER_INPUT_GRACE_MS = 1500;

  const DEFAULT_CONFIG = {
    enabled: true,
    mode: 'block-all',
    allow: [],
    block: [],
    notify: true,
    log: [],
  };

  const hasGM = typeof GM !== 'undefined' && GM && typeof GM.getValue === 'function';

  async function loadConfig() {
    try {
      const raw = hasGM
        ? await GM.getValue(STORAGE_KEY, null)
        : localStorage.getItem(STORAGE_KEY);
      if (!raw) return { ...DEFAULT_CONFIG };
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw;
      return { ...DEFAULT_CONFIG, ...parsed };
    } catch (e) {
      console.warn('[KRB] loadConfig', e);
      return { ...DEFAULT_CONFIG };
    }
  }

  async function saveConfig(cfg) {
    try {
      const payload = JSON.stringify(cfg);
      if (hasGM) await GM.setValue(STORAGE_KEY, payload);
      else localStorage.setItem(STORAGE_KEY, payload);
    } catch (e) {
      console.warn('[KRB] saveConfig', e);
    }
  }

  let CONFIG = { ...DEFAULT_CONFIG };
  loadConfig().then((c) => {
    CONFIG = c;
    refreshButton();
  });

  // Slugs that are NOT channel pages on kick.com.
  // We add common reserved words; if Kick adds a new section we'll just be slightly conservative.
  const RESERVED_SLUGS = new Set([
    '', 'api', 'browse', 'categories', 'category',
    'login', 'signup', 'logout', 'help', 'support',
    'dashboard', 'messages', 'settings', 'profile',
    'account', 'vods', 'vod', 'clip', 'clips',
    'leaderboards', 'shop', 'store', 'gift', 'gifts',
    'slots', 'plinko', 'search', 'redirect',
    'chat', 'admin', 'upload', 'streams',
    '_next', 'static', 'img', 'images', 'assets',
    'about', 'contact', 'terms', 'privacy', 'tos',
    'partners', 'affiliate', 'affiliates',
    'creators', 'developer', 'developers',
    'blog', 'news', 'community',
    'subscriptions', 'subscribe',
    'following', 'followers',
    'verify', 'reset', 'auth',
  ]);

  function parseChannelSlug(pathname) {
    if (typeof pathname !== 'string') return null;
    const clean = pathname.split('#')[0].split('?')[0];
    const m = clean.match(/^\/([a-z0-9_\-]+)\/?$/i);
    if (!m) return null;
    const slug = m[1].toLowerCase();
    if (RESERVED_SLUGS.has(slug)) return null;
    return slug;
  }

  function urlToPath(url) {
    if (typeof url !== 'string') return null;
    try {
      if (/^https?:\/\//i.test(url)) {
        const u = new URL(url);
        if (!u.hostname.endsWith('kick.com')) return null;
        return u.pathname;
      }
      if (url.startsWith('//')) {
        const u = new URL('https:' + url);
        if (!u.hostname.endsWith('kick.com')) return null;
        return u.pathname;
      }
      return url.startsWith('/') ? url : '/' + url;
    } catch {
      return null;
    }
  }

  // Track recent user input so we can distinguish manual clicks from programmatic redirects.
  let lastInteraction = 0;
  const trackEvent = () => { lastInteraction = Date.now(); };
  ['pointerdown', 'touchstart', 'keydown', 'wheel', 'click'].forEach((t) => {
    window.addEventListener(t, trackEvent, { capture: true, passive: true });
  });
  function isUserInitiated() {
    return Date.now() - lastInteraction < USER_INPUT_GRACE_MS;
  }

  function shouldBlock(fromSlug, toSlug, programmatic) {
    if (!CONFIG.enabled) return false;
    if (!fromSlug || !toSlug) return false;
    if (fromSlug === toSlug) return false;
    if (!programmatic) return false;
    if (CONFIG.mode === 'allow-list') {
      return !CONFIG.allow.includes(fromSlug);
    }
    if (CONFIG.mode === 'block-list') {
      return CONFIG.block.includes(fromSlug);
    }
    return true;
  }

  function logBlock(fromSlug, toSlug, source) {
    const entry = { time: Date.now(), from: fromSlug, to: toSlug, src: source };
    CONFIG.log = [entry, ...(CONFIG.log || [])].slice(0, LOG_MAX);
    saveConfig(CONFIG);
    if (CONFIG.notify) showToast(`レイドをブロック: ${fromSlug} → ${toSlug}`);
    refreshPanel();
  }

  function attemptNavigation(url, source) {
    const targetPath = urlToPath(url);
    if (!targetPath) return false;
    const fromSlug = parseChannelSlug(location.pathname);
    const toSlug = parseChannelSlug(targetPath);
    const programmatic = !isUserInitiated();
    if (shouldBlock(fromSlug, toSlug, programmatic)) {
      console.warn(`[KRB] blocked ${source}: ${fromSlug} → ${toSlug}`);
      logBlock(fromSlug, toSlug, source);
      return true;
    }
    return false;
  }

  // --- history API patches (covers SPA / next-router / client-side navigation) ---
  const origPush = history.pushState.bind(history);
  history.pushState = function (state, title, url) {
    if (url != null && attemptNavigation(url, 'pushState')) return;
    return origPush(state, title, url);
  };
  const origReplace = history.replaceState.bind(history);
  history.replaceState = function (state, title, url) {
    if (url != null && attemptNavigation(url, 'replaceState')) return;
    return origReplace(state, title, url);
  };

  // --- Location.assign / Location.replace ---
  try {
    const Loc = Object.getPrototypeOf(location);
    const origAssign = Loc.assign;
    const origReplaceLoc = Loc.replace;
    Loc.assign = function (url) {
      if (attemptNavigation(url, 'location.assign')) return;
      return origAssign.call(this, url);
    };
    Loc.replace = function (url) {
      if (attemptNavigation(url, 'location.replace')) return;
      return origReplaceLoc.call(this, url);
    };
  } catch (e) {
    console.warn('[KRB] could not patch Location proto:', e);
  }

  // --- location.href setter (best-effort; some engines don't allow this) ---
  try {
    const Loc = Object.getPrototypeOf(location);
    const desc = Object.getOwnPropertyDescriptor(Loc, 'href');
    if (desc && desc.set) {
      Object.defineProperty(Loc, 'href', {
        configurable: true,
        enumerable: true,
        get: desc.get,
        set(value) {
          if (attemptNavigation(value, 'location.href=')) return;
          return desc.set.call(this, value);
        },
      });
    }
  } catch (e) {
    console.warn('[KRB] could not patch Location.href setter:', e);
  }

  // --- synthesized anchor click defense (real user clicks have isTrusted=true and pass through) ---
  document.addEventListener('click', (e) => {
    if (!CONFIG.enabled) return;
    if (e.isTrusted) return;
    const a = e.target && e.target.closest && e.target.closest('a[href]');
    if (!a) return;
    const targetPath = urlToPath(a.href);
    if (!targetPath) return;
    const fromSlug = parseChannelSlug(location.pathname);
    const toSlug = parseChannelSlug(targetPath);
    if (!fromSlug || !toSlug || fromSlug === toSlug) return;
    if (shouldBlock(fromSlug, toSlug, true)) {
      e.preventDefault();
      e.stopImmediatePropagation();
      console.warn('[KRB] blocked synthesized click', fromSlug, '->', toSlug);
      logBlock(fromSlug, toSlug, 'synth-click');
    }
  }, true);

  // --- toast ---
  let toastEl = null;
  function showToast(msg) {
    try {
      if (!document.body) return;
      if (!toastEl) {
        toastEl = document.createElement('div');
        toastEl.style.cssText = [
          'position:fixed', 'left:50%', 'bottom:88px', 'transform:translateX(-50%)',
          'background:rgba(20,20,20,0.92)', 'color:#fff',
          'padding:10px 16px', 'border-radius:8px',
          'font:14px/1.4 system-ui,sans-serif',
          'z-index:2147483647', 'pointer-events:none',
          'box-shadow:0 4px 12px rgba(0,0,0,0.3)',
          'opacity:0', 'transition:opacity .25s',
          'max-width:80vw', 'text-align:center',
        ].join(';');
        document.body.appendChild(toastEl);
      }
      toastEl.textContent = msg;
      toastEl.style.opacity = '1';
      clearTimeout(toastEl._t);
      toastEl._t = setTimeout(() => { if (toastEl) toastEl.style.opacity = '0'; }, 3500);
    } catch (e) {
      console.warn('[KRB] toast', e);
    }
  }

  // --- Settings UI ---
  let buttonEl = null;
  let panelEl = null;

  function injectUI() {
    if (buttonEl) return;
    if (!document.body) {
      document.addEventListener('DOMContentLoaded', injectUI);
      return;
    }
    buttonEl = document.createElement('button');
    buttonEl.type = 'button';
    buttonEl.textContent = '🛡';
    buttonEl.setAttribute('aria-label', SCRIPT_NAME + ' settings');
    buttonEl.style.cssText = [
      'position:fixed', 'right:12px', 'bottom:12px',
      'width:44px', 'height:44px', 'border-radius:50%',
      'background:#53fc18', 'color:#000', 'border:none',
      'font-size:20px', 'cursor:pointer',
      'box-shadow:0 2px 8px rgba(0,0,0,0.3)',
      'z-index:2147483646', 'padding:0',
      'display:flex', 'align-items:center', 'justify-content:center',
    ].join(';');
    buttonEl.addEventListener('click', togglePanel);
    document.body.appendChild(buttonEl);
    refreshButton();
  }

  function refreshButton() {
    if (!buttonEl) return;
    buttonEl.style.opacity = CONFIG.enabled ? '1' : '0.4';
    buttonEl.title = `${SCRIPT_NAME} (${CONFIG.enabled ? 'ON' : 'OFF'})`;
  }

  function togglePanel() {
    if (panelEl && panelEl.parentNode) {
      panelEl.parentNode.removeChild(panelEl);
      panelEl = null;
      return;
    }
    panelEl = document.createElement('div');
    panelEl.style.cssText = [
      'position:fixed', 'right:12px', 'bottom:64px',
      'width:min(340px,92vw)', 'max-height:75vh', 'overflow-y:auto',
      'background:#1a1a1a', 'color:#fff', 'border-radius:12px',
      'padding:16px', 'font:14px/1.5 system-ui,sans-serif',
      'box-shadow:0 8px 24px rgba(0,0,0,0.4)',
      'z-index:2147483646', 'box-sizing:border-box',
    ].join(';');
    panelEl.innerHTML = renderPanel();
    document.body.appendChild(panelEl);
    bindPanel();
  }

  function refreshPanel() {
    if (!panelEl) return;
    panelEl.innerHTML = renderPanel();
    bindPanel();
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function renderPanel() {
    const c = CONFIG;
    const rows = (c.log || []).slice(0, 10).map((e) =>
      `<li style="font-size:12px;color:#aaa;margin:2px 0;list-style:none;">
         <span style="color:#666;">${new Date(e.time).toLocaleTimeString()}</span>
         ${escapeHtml(e.from)} → ${escapeHtml(e.to)}
       </li>`
    ).join('') || '<li style="font-size:12px;color:#666;list-style:none;">記録なし</li>';

    const ta = 'width:100%;padding:6px;background:#2a2a2a;color:#fff;border:1px solid #444;border-radius:4px;font:12px monospace;box-sizing:border-box;';
    const sel = 'width:100%;padding:6px;background:#2a2a2a;color:#fff;border:1px solid #444;border-radius:4px;box-sizing:border-box;';

    return `
      <div style="font-weight:bold;font-size:16px;margin-bottom:10px;display:flex;justify-content:space-between;align-items:center;">
        <span>🛡 ${SCRIPT_NAME}</span>
        <button id="krb-close" type="button" aria-label="close" style="background:none;border:none;color:#888;font-size:20px;cursor:pointer;line-height:1;padding:0 4px;">×</button>
      </div>
      <label style="display:flex;align-items:center;gap:8px;margin:8px 0;">
        <input type="checkbox" id="krb-enabled" ${c.enabled ? 'checked' : ''}>
        <span>有効化</span>
      </label>
      <div style="margin:8px 0;">
        <div style="font-size:13px;color:#aaa;margin-bottom:4px;">モード</div>
        <select id="krb-mode" style="${sel}">
          <option value="block-all" ${c.mode === 'block-all' ? 'selected' : ''}>すべてブロック（既定）</option>
          <option value="allow-list" ${c.mode === 'allow-list' ? 'selected' : ''}>許可リストの配信者のみ通す</option>
          <option value="block-list" ${c.mode === 'block-list' ? 'selected' : ''}>ブロックリストの配信者のみブロック</option>
        </select>
      </div>
      <div style="margin:8px 0;">
        <div style="font-size:13px;color:#aaa;margin-bottom:4px;">許可リスト（カンマ/スペース区切り）</div>
        <textarea id="krb-allow" rows="2" style="${ta}">${escapeHtml((c.allow || []).join(', '))}</textarea>
      </div>
      <div style="margin:8px 0;">
        <div style="font-size:13px;color:#aaa;margin-bottom:4px;">ブロックリスト（カンマ/スペース区切り）</div>
        <textarea id="krb-block" rows="2" style="${ta}">${escapeHtml((c.block || []).join(', '))}</textarea>
      </div>
      <label style="display:flex;align-items:center;gap:8px;margin:8px 0;">
        <input type="checkbox" id="krb-notify" ${c.notify ? 'checked' : ''}>
        <span>ブロック時に通知</span>
      </label>
      <button id="krb-save" type="button" style="width:100%;padding:8px;background:#53fc18;color:#000;border:none;border-radius:6px;font-weight:bold;cursor:pointer;margin-top:8px;">保存</button>
      <details style="margin-top:12px;">
        <summary style="font-size:13px;color:#aaa;cursor:pointer;">最近のブロック履歴</summary>
        <ul style="margin:6px 0 0 0;padding:0;">${rows}</ul>
        <button id="krb-clear-log" type="button" style="margin-top:6px;padding:4px 8px;background:#333;color:#fff;border:1px solid #555;border-radius:4px;font-size:12px;cursor:pointer;">履歴をクリア</button>
      </details>
      <div style="margin-top:12px;font-size:11px;color:#666;text-align:center;">
        v0.1.0 · clean-room implementation · MIT
      </div>
    `;
  }

  function bindPanel() {
    panelEl.querySelector('#krb-close').addEventListener('click', togglePanel);
    panelEl.querySelector('#krb-save').addEventListener('click', () => {
      const enabled = panelEl.querySelector('#krb-enabled').checked;
      const mode = panelEl.querySelector('#krb-mode').value;
      const notify = panelEl.querySelector('#krb-notify').checked;
      const parseList = (raw) => raw.split(/[\s,]+/).filter(Boolean).map((s) => s.toLowerCase());
      const allow = parseList(panelEl.querySelector('#krb-allow').value);
      const block = parseList(panelEl.querySelector('#krb-block').value);
      CONFIG = { ...CONFIG, enabled, mode, allow, block, notify };
      saveConfig(CONFIG);
      showToast('設定を保存しました');
      refreshButton();
      togglePanel();
    });
    panelEl.querySelector('#krb-clear-log').addEventListener('click', () => {
      CONFIG = { ...CONFIG, log: [] };
      saveConfig(CONFIG);
      refreshPanel();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectUI);
  } else {
    injectUI();
  }

  console.log(`[KRB] ${SCRIPT_NAME} loaded`);
})();
