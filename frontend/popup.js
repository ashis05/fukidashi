// Fukidashi popup. Talks to the background worker; all heavy lifting happens there.
const DEFAULTS = { serverUrl: 'http://127.0.0.1:8000', sourceLang: 'ja' };
const $ = (id) => document.getElementById(id);

const els = {
  lang: $('language'), translate: $('translate'), label: $('translate-label'),
  auto: $('auto'), overlay: $('overlay'), status: $('status'),
  server: $('server'), url: $('server-url'), save: $('save'), test: $('test'),
  dot: $('dot'), serverMsg: $('server-msg'),
};

let tab = null;

const send = (msg) => chrome.runtime.sendMessage({ ...msg, tabId: tab?.id });

function setStatus(text, kind = 'info') {
  els.status.textContent = text;
  els.status.dataset.kind = kind;
}

function setBusy(busy) {
  els.translate.disabled = busy;
  els.translate.classList.toggle('is-busy', busy);
  els.label.textContent = busy ? 'Translating…' : 'Translate page';
}

function setOverlay({ hasOverlay, hidden }) {
  els.overlay.disabled = !hasOverlay;
  els.overlay.textContent = hidden ? 'Show translation' : 'Hide translation';
}

function applyStatus({ phase, text }) {
  if (phase === 'running') { setBusy(true); setStatus(text); return; }
  setBusy(false);
  setStatus(text, phase === 'error' ? 'error' : phase === 'done' ? 'success' : 'info');
}

// ---------------------------------------------------------------- permissions

/** Match pattern covering a URL's host (host permissions ignore ports). */
function originPattern(url) {
  const u = new URL(url);
  return `${u.protocol}//${u.hostname}/*`;
}

/** Ask for host access if the manifest doesn't already grant it. Needs a user gesture. */
async function ensureAccess(url) {
  const origins = [originPattern(url)];
  if (await chrome.permissions.contains({ origins })) return true;
  return chrome.permissions.request({ origins });
}

function normalizeUrl(raw) {
  let value = raw.trim().replace(/\/+$/, '');
  if (!/^https?:\/\//i.test(value)) value = 'http://' + value;
  const u = new URL(value); // throws on garbage
  return u.origin + (u.pathname === '/' ? '' : u.pathname.replace(/\/+$/, ''));
}

// ---------------------------------------------------------------- server settings

function setServerState(state, text) {
  els.dot.dataset.state = state;
  els.serverMsg.textContent = text;
}

async function saveServer() {
  let url;
  try {
    url = normalizeUrl(els.url.value);
  } catch {
    setServerState('fail', 'That is not a valid URL.');
    return null;
  }
  if (!(await ensureAccess(url))) {
    setServerState('fail', 'Access to that server was not granted.');
    return null;
  }
  await chrome.storage.sync.set({ serverUrl: url });
  els.url.value = url;
  return url;
}

async function testServer() {
  const url = await saveServer();
  if (!url) return;
  setServerState('busy', 'Connecting…');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 8000);
  try {
    const res = await fetch(`${url}/health`, {
      headers: { 'ngrok-skip-browser-warning': '1' },
      signal: controller.signal,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const body = await res.json();
    if (body.status !== 'ok') throw new Error(`status "${body.status}"`);
    setServerState('ok', 'Connected');
  } catch (err) {
    setServerState('fail', err.name === 'AbortError' ? 'Timed out after 8 s' : `Unreachable (${err.message})`);
  } finally {
    clearTimeout(timer);
  }
}

// ---------------------------------------------------------------- init

async function init() {
  [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const settings = await chrome.storage.sync.get(DEFAULTS);
  els.lang.value = settings.sourceLang;
  els.url.value = settings.serverUrl;

  const state = await send({ action: 'get_state' }).catch(() => null);
  if (state) {
    els.auto.checked = !!state.auto;
    if (state.auto) els.lang.value = state.auto;
    setOverlay(state.overlay);
    if (state.running) setBusy(true);
    if (state.running) setStatus('Translating…');
    else if (state.status) applyStatus(state.status);
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.action === 'status' && msg.tabId === tab?.id) {
      applyStatus(msg);
      send({ action: 'get_state' }).then((s) => s && setOverlay(s.overlay)).catch(() => {});
    }
  });

  els.lang.addEventListener('change', async () => {
    await chrome.storage.sync.set({ sourceLang: els.lang.value });
    if (els.auto.checked) send({ action: 'set_auto', enabled: true, sourceLang: els.lang.value, runNow: false });
  });

  els.translate.addEventListener('click', async () => {
    await chrome.storage.sync.set({ sourceLang: els.lang.value });
    setBusy(true);
    setStatus('Translating…');
    const r = await send({ action: 'translate', sourceLang: els.lang.value });
    if (r?.busy) setStatus('Already translating this tab…');
  });

  els.auto.addEventListener('change', async () => {
    if (els.auto.checked) {
      // Auto mode captures after navigations, when activeTab no longer applies,
      // so it needs access to the site itself.
      const pageUrl = tab?.url;
      if (/^https?:/.test(pageUrl || '') && !(await ensureAccess(pageUrl))) {
        els.auto.checked = false;
        setStatus('Auto mode needs access to this site.', 'error');
        return;
      }
      await chrome.storage.sync.set({ sourceLang: els.lang.value });
      await send({ action: 'set_auto', enabled: true, sourceLang: els.lang.value, runNow: true });
      setStatus('Auto mode on');
    } else {
      await send({ action: 'set_auto', enabled: false });
      setStatus('Auto mode off');
    }
  });

  els.overlay.addEventListener('click', async () => {
    const r = await send({ action: 'toggle_overlay' });
    if (r?.ok === false) setStatus(r.error, 'error');
    else setOverlay(r);
  });

  els.save.addEventListener('click', async () => {
    if (await saveServer()) setServerState('idle', 'Saved');
  });
  els.test.addEventListener('click', testServer);
}

init();
