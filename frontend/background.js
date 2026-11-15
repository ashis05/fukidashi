// Fukidashi service worker.
// MV3 workers are killed when idle, so nothing important lives in module-level
// state: auto-mode and last status are kept in chrome.storage.session.
// The only in-memory sets (in-flight runs, debounce timers) are fine to lose.

const DEFAULTS = { serverUrl: 'http://127.0.0.1:8000', sourceLang: 'ja' };
const REQUEST_TIMEOUT_MS = 60_000;
const AUTO_DELAY_MS = 2000;

const inFlight = new Set();       // tabIds with a run in progress
const autoTimers = new Map();     // tabId -> pending auto-run timeout

// ---------------------------------------------------------------- storage

const autoKey = (tabId) => `auto:${tabId}`;
const statusKey = (tabId) => `status:${tabId}`;

async function getSettings() {
  const s = await chrome.storage.sync.get(DEFAULTS);
  return { serverUrl: (s.serverUrl || DEFAULTS.serverUrl).replace(/\/+$/, ''), sourceLang: s.sourceLang };
}

async function getAutoLang(tabId) {
  const r = await chrome.storage.session.get(autoKey(tabId));
  return r[autoKey(tabId)] ?? null;
}

/** Remember the latest status for a tab and tell any open popup. */
async function setStatus(tabId, phase, text) {
  await chrome.storage.session.set({ [statusKey(tabId)]: { phase, text } });
  chrome.runtime.sendMessage({ action: 'status', tabId, phase, text }).catch(() => {}); // popup may be closed
}

// ---------------------------------------------------------------- content script

const sendToTab = (tabId, msg) => chrome.tabs.sendMessage(tabId, msg);

/** Make sure content.js is alive in the tab (not present on pre-install tabs). */
async function ensureContent(tabId) {
  try {
    return await sendToTab(tabId, { action: 'ping' });
  } catch {
    try {
      await chrome.scripting.executeScript({ target: { tabId }, files: ['content.js'] });
      return await sendToTab(tabId, { action: 'ping' });
    } catch {
      throw new Error("Fukidashi can't run on this page (browser pages and the Web Store are off limits).");
    }
  }
}

const toast = (tabId, text, kind = 'info', sticky = false) =>
  sendToTab(tabId, { action: 'show_status', text, kind, sticky }).catch(() => {});

// ---------------------------------------------------------------- translation

async function parseError(response) {
  try {
    const body = await response.json();
    if (body?.detail) return typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail);
  } catch { /* not JSON */ }
  return `Server returned ${response.status} ${response.statusText}`.trim();
}

async function requestTranslation(serverUrl, blob, sourceLang) {
  const form = new FormData();
  form.append('file', blob, 'screenshot.jpg');
  form.append('source_lang', sourceLang);

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(`${serverUrl}/translate`, {
      method: 'POST',
      body: form,
      headers: { 'ngrok-skip-browser-warning': '1' },
      signal: controller.signal,
    });
    if (!response.ok) throw new Error(await parseError(response));
    return await response.json();
  } catch (err) {
    if (err.name === 'AbortError') throw new Error('The server took too long to answer (60 s).');
    if (err instanceof TypeError) throw new Error(`Can't reach the server at ${serverUrl}. Is it running?`);
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

async function runTranslation(tabId, sourceLang) {
  if (inFlight.has(tabId)) return { ok: false, busy: true };
  inFlight.add(tabId);
  let capturing = false;
  try {
    const settings = await getSettings();
    const { serverUrl } = settings;
    sourceLang ||= settings.sourceLang;

    await setStatus(tabId, 'running', 'Translating…');
    await ensureContent(tabId);
    await toast(tabId, 'Translating…', 'info', true);

    // Hide our own overlay/toast (and snapshot scroller geometry) before capturing,
    // otherwise a re-run would read the previous English text.
    capturing = true;
    await sendToTab(tabId, { action: 'prepare_capture' });
    const tab = await chrome.tabs.get(tabId);
    const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, { format: 'jpeg', quality: 70 });
    capturing = false;
    await sendToTab(tabId, { action: 'end_capture' }).catch(() => {});
    await toast(tabId, 'Translating…', 'info', true);

    const blob = await (await fetch(dataUrl)).blob();
    const bitmap = await createImageBitmap(blob);
    const result = await requestTranslation(serverUrl, blob, sourceLang);

    const bubbles = result.data ?? [];
    const draw = await sendToTab(tabId, {
      action: 'draw_overlay',
      bubbles,
      originalWidth: result.width || bitmap.width,
      originalHeight: result.height || bitmap.height,
    });
    const text = draw?.count ? `Translated ${draw.count} bubble${draw.count === 1 ? '' : 's'}` : 'No text found on this view';
    await toast(tabId, text, 'success');
    await setStatus(tabId, 'done', text);
    return { ok: true, count: draw?.count ?? 0 };
  } catch (err) {
    console.error('Fukidashi: translation failed', err);
    if (capturing) await sendToTab(tabId, { action: 'end_capture' }).catch(() => {});
    await toast(tabId, err.message, 'error');
    await setStatus(tabId, 'error', err.message);
    return { ok: false, error: err.message };
  } finally {
    inFlight.delete(tabId);
  }
}

// ---------------------------------------------------------------- auto mode

function scheduleAuto(tabId) {
  clearTimeout(autoTimers.get(tabId));
  autoTimers.set(tabId, setTimeout(async () => {
    autoTimers.delete(tabId);
    const lang = await getAutoLang(tabId);
    if (lang) runTranslation(tabId, lang);
  }, AUTO_DELAY_MS));
}

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo) => {
  // URL changed (including pushState navigations): the old overlay is stale.
  if (changeInfo.url) sendToTab(tabId, { action: 'clear_overlay' }).catch(() => {});
  if (!changeInfo.url && changeInfo.status !== 'complete') return;
  if (await getAutoLang(tabId)) scheduleAuto(tabId);
});

chrome.tabs.onRemoved.addListener((tabId) => {
  clearTimeout(autoTimers.get(tabId));
  autoTimers.delete(tabId);
  inFlight.delete(tabId);
  chrome.storage.session.remove([autoKey(tabId), statusKey(tabId)]);
});

// ---------------------------------------------------------------- popup / shortcuts

async function overlayState(tabId) {
  try {
    const r = await sendToTab(tabId, { action: 'ping' });
    return { hasOverlay: r.hasOverlay, hidden: r.hidden };
  } catch {
    return { hasOverlay: false, hidden: false };
  }
}

async function toggleOverlay(tabId) {
  try {
    await ensureContent(tabId);
    return await sendToTab(tabId, { action: 'toggle_overlay' });
  } catch (err) {
    return { ok: false, error: err.message };
  }
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  const handlers = {
    async translate() {
      const busy = inFlight.has(msg.tabId);
      runTranslation(msg.tabId, msg.sourceLang); // progress arrives via 'status' broadcasts
      return { ok: true, busy };
    },
    async set_auto() {
      if (msg.enabled) {
        await chrome.storage.session.set({ [autoKey(msg.tabId)]: msg.sourceLang });
        if (msg.runNow) runTranslation(msg.tabId, msg.sourceLang);
      } else {
        await chrome.storage.session.remove(autoKey(msg.tabId));
        clearTimeout(autoTimers.get(msg.tabId));
      }
      return { ok: true };
    },
    toggle_overlay: () => toggleOverlay(msg.tabId),
    async get_state() {
      const [auto, st, overlay] = await Promise.all([
        getAutoLang(msg.tabId),
        chrome.storage.session.get(statusKey(msg.tabId)),
        overlayState(msg.tabId),
      ]);
      return { auto, running: inFlight.has(msg.tabId), status: st[statusKey(msg.tabId)] ?? null, overlay };
    },
  };
  const handler = handlers[msg?.action];
  if (!handler) return; // not ours (e.g. our own 'status' broadcast)
  handler().then(sendResponse);
  return true;
});

chrome.commands.onCommand.addListener(async (command) => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id) return;
  if (command === 'translate_page') runTranslation(tab.id);
  else if (command === 'toggle_overlay') toggleOverlay(tab.id);
});
