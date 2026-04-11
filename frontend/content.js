chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "draw_overlay") {
        drawOverlay(
            request.bubbles,
            request.originalWidth,
            request.originalHeight,
            request.snapshotScrollX,
            request.snapshotScrollY,
            request.scrollerTopOnScreen
        );
    } else if (request.action === "clear_overlay") {
        clearOverlay();
    }
});

let lastUrl = location.href;
new MutationObserver(() => {
    if (location.href !== lastUrl) {
        lastUrl = location.href;
        clearOverlay();
    }
}).observe(document, {subtree: true, childList: true});

function clearOverlay() {
    const existing = document.getElementById('manga-translator-overlay');
    if (existing) existing.remove();
}

// --- HELPER: Find the exact same scroller popup.js found ---
function getLargestScroller() {
    // Try the document scrolling element first if it has a non-zero scroll top
    if (document.scrollingElement && document.scrollingElement.scrollTop > 0) {
        return document.scrollingElement;
    }

    const allElems = Array.from(document.querySelectorAll('*'));
    const candidates = allElems.filter(el => {
        const style = window.getComputedStyle(el);
        // An element is scrollable if it has overflow auto/scroll OR if it actually has scrollTop > 0
        const isScrollable = (style.overflowY === 'auto' || style.overflowY === 'scroll') || el.scrollTop > 0;
        const hasRoomToScroll = el.scrollHeight > el.clientHeight;
        // Ignore elements that are just visible overflow
        const isNotVisible = style.overflowY !== 'visible';
        
        return isScrollable && hasRoomToScroll && isNotVisible;
    });
    
    if (candidates.length === 0) return document.scrollingElement || document.documentElement;
    // Sort by how much they are scrolled first, then by size
    return candidates.sort((a, b) => {
        if (b.scrollTop !== a.scrollTop) return b.scrollTop - a.scrollTop;
        return b.scrollHeight - a.scrollHeight;
    })[0];
}

function drawOverlay(bubbles, originalWidth, originalHeight, snapshotScrollX, snapshotScrollY, scrollerTopOnScreen) {
    clearOverlay();

    // 1. Identify where to attach the overlay
    const scroller = getLargestScroller();

    // 2. Make the scroller 'relative' so our 'absolute' children stick to it
    // (Unless it's the body/html, then we don't touch it)
    if (scroller !== document.body && scroller !== document.documentElement) {
        const style = window.getComputedStyle(scroller);
        if (style.position === 'static') {
            scroller.style.position = 'relative';
        }
    }

    // 3. Calculate Scale
    const clientWidth = document.documentElement.clientWidth;
    const clientHeight = document.documentElement.clientHeight;
    const scaleX = clientWidth / originalWidth;
    const scaleY = clientHeight / originalHeight;

    // 4. Create Container
    const container = document.createElement('div');
    container.id = 'manga-translator-overlay';

    container.style.position = 'absolute';
    container.style.top = '0';
    container.style.left = '0';
    container.style.width = '100%';
    // Force height to match the SCROLLER'S full height
    container.style.height = scroller.scrollHeight + 'px';
    container.style.zIndex = '2147483647';
    container.style.pointerEvents = 'none';

    // --- ATTACH TO SCROLLER (Not Body!) ---
    // This is the magic fix. By appending to the scrolling div,
    // the text moves automatically when that div scrolls.
    if (scroller === document.documentElement) {
        document.body.appendChild(container);
    } else {
        scroller.appendChild(container);
    }

    // 5. Draw Bubbles
    bubbles.forEach(bubble => {
        const box = bubble.box;

        // Math: Box Position relative to Viewport + Scroller Position
        const absoluteX = (box[0] * scaleX) + snapshotScrollX;
        // CRITICAL FIX: We now subtract the scroller's position on the screen at the time of the snapshot.
        // This converts the bubble's absolute screen coordinate into a coordinate relative to the scroller.
        const absoluteY = (box[1] * scaleY) + snapshotScrollY - scrollerTopOnScreen;
        const w = (box[2] - box[0]) * scaleX;
        const h = (box[3] - box[1]) * scaleY;

        const div = document.createElement('div');
        div.style.position = 'absolute';
        div.style.left = `${absoluteX}px`;
        div.style.top = `${absoluteY}px`;
        div.style.width = `${w}px`;
        div.style.height = `${h}px`;

        // Styles
        div.style.background = 'radial-gradient(circle, rgba(255,255,255,1) 60%, rgba(255,255,255,0.8) 100%)';
        div.style.borderRadius = '50%';
        div.style.display = 'flex';
        div.style.alignItems = 'center';
        div.style.justifyContent = 'center';
        div.style.textAlign = 'center';
        div.style.padding = '5px';
        div.style.boxSizing = 'border-box';
        div.style.boxShadow = '0 0 5px rgba(255,255,255,0.5)';

        // Text
        const p = document.createElement('p');
        p.innerText = bubble.text;
        p.style.margin = '0';
        p.style.fontFamily = '"Comic Sans MS", "Chalkboard SE", sans-serif';
        p.style.color = '#000';
        p.style.fontWeight = 'bold';
        p.style.lineHeight = '1.1';
        p.style.wordBreak = 'break-word';
        p.style.textShadow = '2px 0 #fff, -2px 0 #fff, 0 2px #fff, 0 -2px #fff, 1px 1px #fff, -1px -1px #fff, 1px -1px #fff, -1px 1px #fff';

        let fontSize = 20;
        p.style.fontSize = fontSize + 'px';
        div.appendChild(p);
        container.appendChild(div);

        const minFontSize = 10;
        while ( (p.scrollHeight > h || p.scrollWidth > w) && fontSize > minFontSize ) {
            fontSize--;
            p.style.fontSize = fontSize + 'px';
        }
    });
}