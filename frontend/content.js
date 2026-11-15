// Fukidashi content script.
// Owns everything that touches the page: scroller detection, hiding the overlay
// around screenshots, drawing translated bubbles and the status toast.
// The background worker drives it through messages (see the listener at the bottom).
(() => {
  // The script is declared in the manifest AND injected on demand by the background
  // worker, so guard against registering twice.
  if (window.__fukidashiLoaded) return;
  window.__fukidashiLoaded = true;

  const FONT_STACK = '"Anime Ace", "Comic Neue", "Comic Sans MS", "Chalkboard SE", sans-serif';
  const MIN_FONT = 9;
  const MAX_FONT = 28;

  let overlayHost = null;      // <div id="fukidashi-overlay"> holding a shadow root
  let overlayHidden = false;   // user asked to hide the translation
  let capturing = false;       // temporarily hidden while the screenshot is taken
  let snapshot = null;         // scroller geometry captured right before the screenshot
  let promotedScroller = null; // scroller we switched from static to relative
  let toast = null;            // { host, box, timer }

  // ---------------------------------------------------------------- scroller

  /**
   * Pick the element the user is actually reading in: either the document or a
   * large inner scroll container (common on reader sites).
   */
  function findScroller() {
    const root = document.scrollingElement || document.documentElement;
    const viewportArea = innerWidth * innerHeight;
    const docScrollable = root.scrollHeight > root.clientHeight + 1 || root.scrollWidth > root.clientWidth + 1;

    let best = null;
    let bestArea = 0;
    for (const el of document.querySelectorAll('body, body *')) {
      if (el === root) continue;
      // Cheap geometry test first; getComputedStyle only for plausible candidates.
      if (el.scrollHeight <= el.clientHeight + 1 && el.scrollWidth <= el.clientWidth + 1) continue;
      const style = getComputedStyle(el);
      const scrolls = /auto|scroll|overlay/.test(style.overflowY + style.overflowX);
      if (!scrolls) continue;
      const r = el.getBoundingClientRect();
      const w = Math.min(r.right, innerWidth) - Math.max(r.left, 0);
      const h = Math.min(r.bottom, innerHeight) - Math.max(r.top, 0);
      const area = Math.max(w, 0) * Math.max(h, 0);
      if (area > bestArea) { best = el; bestArea = area; }
    }

    const big = best && bestArea >= 0.25 * viewportArea;
    if (big && (!docScrollable || bestArea >= 0.6 * viewportArea)) return best;
    return root;
  }

  /** Detect the scroller and remember where it is right now. */
  function takeSnapshot() {
    const root = document.scrollingElement || document.documentElement;
    const scroller = findScroller();
    const isDoc = scroller === root;
    snapshot = {
      scroller,
      isDoc,
      scrollX: window.scrollX,
      scrollY: window.scrollY,
      scrollLeft: scroller.scrollLeft,
      scrollTop: scroller.scrollTop,
      rect: scroller.getBoundingClientRect(),
    };
    return { kind: isDoc ? 'document' : 'element', scrollX: snapshot.scrollX, scrollY: snapshot.scrollY };
  }

  // ----------------------------------------------------------------- overlay

  function applyVisibility() {
    if (overlayHost) overlayHost.style.visibility = overlayHidden || capturing ? 'hidden' : 'visible';
  }

  function clearOverlay() {
    overlayHost?.remove();
    overlayHost = null;
    if (promotedScroller) {
      promotedScroller.style.position = '';
      promotedScroller = null;
    }
  }

  const nextFrame = () => new Promise((r) => requestAnimationFrame(() => r()));

  /** Hide our UI and wait until the browser has actually painted without it. */
  async function prepareCapture() {
    capturing = true;
    applyVisibility();
    hideToast();
    // rAF doesn't fire in throttled tabs, so never wait on it unconditionally.
    await Promise.race([nextFrame().then(nextFrame), new Promise((r) => setTimeout(r, 200))]);
    return takeSnapshot();
  }

  function endCapture() {
    capturing = false;
    applyVisibility();
  }

  /**
   * Largest font (MIN..MAX) at which the text fits the available box.
   * Fit is monotonic in font size, so binary search beats a decrement loop.
   */
  function fitText(p, availW, availH) {
    const fits = (size) => {
      p.style.fontSize = size + 'px';
      return p.scrollHeight <= availH + 0.5 && p.scrollWidth <= availW + 0.5;
    };
    let lo = MIN_FONT;
    let hi = MAX_FONT;
    while (lo < hi) {
      const mid = Math.ceil((lo + hi) / 2);
      if (fits(mid)) lo = mid; else hi = mid - 1;
    }
    p.style.fontSize = lo + 'px';
  }

  const OVERLAY_CSS = `
    :host { all: initial; }
    .fukidashi-bubble {
      position: absolute; box-sizing: border-box; display: flex;
      align-items: center; justify-content: center; text-align: center;
      background: #fff; border-radius: 40%; overflow: hidden;
      box-shadow: 0 0 0 2px #fff;
    }
    .fukidashi-text {
      margin: 0; padding: 0; color: #111; font-family: ${FONT_STACK};
      font-weight: 700; line-height: 1.1; overflow-wrap: anywhere;
      white-space: pre-wrap;
    }`;

  function drawOverlay(bubbles, originalWidth, originalHeight) {
    clearOverlay();
    if (!snapshot) takeSnapshot();
    const snap = snapshot;
    const scroller = snap.scroller;

    // Screenshot pixels -> CSS pixels. innerWidth/Height is the area the screenshot
    // covers, so this also absorbs devicePixelRatio and browser zoom.
    const scaleX = innerWidth / originalWidth;
    const scaleY = innerHeight / originalHeight;

    // Document scroller: overlay lives at the document origin, so use page coordinates.
    // Inner scroller: overlay lives inside it, so use coordinates in its scrolled content.
    let offX, offY;
    if (snap.isDoc) {
      offX = snap.scrollX;
      offY = snap.scrollY;
    } else {
      offX = snap.scrollLeft - snap.rect.left - scroller.clientLeft;
      offY = snap.scrollTop - snap.rect.top - scroller.clientTop;
      if (getComputedStyle(scroller).position === 'static') {
        scroller.style.position = 'relative';
        promotedScroller = scroller;
      }
    }

    const host = document.createElement('div');
    host.id = 'fukidashi-overlay';
    host.style.cssText =
      'all:initial;position:absolute;top:0;left:0;width:0;height:0;overflow:visible;' +
      'z-index:2147483646;pointer-events:none;display:block;';
    const root = host.attachShadow({ mode: 'open' });
    const style = document.createElement('style');
    style.textContent = OVERLAY_CSS;
    root.appendChild(style);

    (snap.isDoc ? document.documentElement : scroller).appendChild(host);
    overlayHost = host;
    overlayHidden = false;
    capturing = false;
    applyVisibility();

    let drawn = 0;
    for (const bubble of bubbles) {
      const text = (bubble.text || '').trim();
      if (!text) continue;
      const [x1, y1, x2, y2] = bubble.box;
      const w = (x2 - x1) * scaleX;
      const h = (y2 - y1) * scaleY;

      const div = document.createElement('div');
      div.className = 'fukidashi-bubble';
      div.style.left = `${x1 * scaleX + offX}px`;
      div.style.top = `${y1 * scaleY + offY}px`;
      div.style.width = `${w}px`;
      div.style.height = `${h}px`;

      // Rounded corners eat into the usable area; keep text inside the inscribed box.
      const pad = Math.max(3, Math.min(w, h) * 0.12);
      div.style.padding = `${pad}px`;
      const availW = Math.max(w - 2 * pad, 1);
      const availH = Math.max(h - 2 * pad, 1);

      const p = document.createElement('p');
      p.className = 'fukidashi-text';
      p.style.width = `${availW}px`;
      p.innerText = text;
      div.appendChild(p);
      root.appendChild(div);   // must be attached to measure
      fitText(p, availW, availH);
      drawn++;
    }
    return drawn;
  }

  function toggleOverlay() {
    if (!overlayHost) return { hasOverlay: false, hidden: false };
    overlayHidden = !overlayHidden;
    applyVisibility();
    return { hasOverlay: true, hidden: overlayHidden };
  }

  // ------------------------------------------------------------------- toast

  const TOAST_CSS = `
    :host { all: initial; }
    .box {
      position: fixed; right: 16px; bottom: 16px; max-width: 320px;
      padding: 10px 14px; border: 1.5px solid #16130f; border-radius: 8px;
      background: #f6f1e7; color: #16130f; box-shadow: 3px 3px 0 #16130f;
      font: 600 13px/1.35 system-ui, -apple-system, "Segoe UI", sans-serif;
      opacity: 0; transform: translateY(6px);
      transition: opacity .18s ease, transform .18s ease;
    }
    .box.show { opacity: 1; transform: none; }
    .box.error { background: #e63b2e; color: #fff; }
    @media (prefers-reduced-motion: reduce) { .box { transition: none; } }`;

  function hideToast() {
    if (!toast) return;
    clearTimeout(toast.timer);
    toast.host.remove();
    toast = null;
  }

  /** kind: 'info' | 'success' | 'error'. Sticky toasts stay until replaced. */
  function showToast(text, kind = 'info', sticky = false) {
    if (capturing) return;
    hideToast();
    const host = document.createElement('div');
    host.id = 'fukidashi-toast';
    host.style.cssText = 'all:initial;position:fixed;z-index:2147483647;pointer-events:none;';
    const root = host.attachShadow({ mode: 'open' });
    const style = document.createElement('style');
    style.textContent = TOAST_CSS;
    const box = document.createElement('div');
    box.className = 'box ' + kind;
    box.setAttribute('role', kind === 'error' ? 'alert' : 'status');
    box.textContent = text;
    root.append(style, box);
    document.documentElement.appendChild(host);
    requestAnimationFrame(() => box.classList.add('show'));

    const ms = sticky ? 90000 : kind === 'error' ? 7000 : 3000; // sticky has a safety timeout
    toast = { host, timer: setTimeout(hideToast, ms) };
  }

  // ---------------------------------------------------------------- messages

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    switch (msg?.action) {
      case 'ping':
        sendResponse({ ok: true, hasOverlay: !!overlayHost, hidden: overlayHidden });
        break;
      case 'prepare_capture':
        prepareCapture().then((m) => sendResponse({ ok: true, metrics: m }));
        return true; // async response
      case 'end_capture':
        endCapture();
        sendResponse({ ok: true });
        break;
      case 'draw_overlay':
        sendResponse({ ok: true, count: drawOverlay(msg.bubbles || [], msg.originalWidth, msg.originalHeight) });
        break;
      case 'clear_overlay':
        clearOverlay();
        sendResponse({ ok: true });
        break;
      case 'toggle_overlay':
        sendResponse({ ok: true, ...toggleOverlay() });
        break;
      case 'show_status':
        showToast(msg.text, msg.kind, msg.sticky);
        sendResponse({ ok: true });
        break;
    }
  });

  // Cheap navigation detection; pushState-based SPA changes are reported by the
  // background worker through tabs.onUpdated (clear_overlay).
  addEventListener('popstate', clearOverlay);
  addEventListener('hashchange', clearOverlay);
})();
