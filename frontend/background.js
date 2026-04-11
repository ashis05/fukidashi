// --- CONFIGURATION ---
const SERVER_URL = "https://unrevealingly-unstammering-jessika.ngrok-free.dev";

// Track which tabs have Auto-Translate enabled AND their language
// Format: Map<TabID, LanguageCode>
const autoTabs = new Map();

// --- 1. LISTEN FOR MESSAGES FROM POPUP ---
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
    if (request.action === "start_translation") {
        // Manual run: use the language sent from popup
        runTranslationPipeline(request.tabId, request.sourceLang);
    }
    else if (request.action === "toggle_auto") {
        if (request.enabled) {
            // Store the language preference for this tab
            autoTabs.set(request.tabId, request.sourceLang);
            // Run immediately
            runTranslationPipeline(request.tabId, request.sourceLang);
        } else {
            autoTabs.delete(request.tabId);
        }
    }
});

// --- 2. LISTEN FOR PAGE NAVIGATION ---
chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
    // Check if this tab is in our "Auto-Translate" list
    if (changeInfo.status === 'complete' && autoTabs.has(tabId)) {

        // Retrieve the saved language for this tab
        const savedLang = autoTabs.get(tabId);
        console.log(`Auto-Translating Tab ${tabId} in ${savedLang}...`);

        setTimeout(() => {
            runTranslationPipeline(tabId, savedLang);
        }, 2000);
    }
});

// --- 3. THE TRANSLATION LOGIC ---
async function runTranslationPipeline(tabId, sourceLang = 'ja') {
    try {
        chrome.tabs.sendMessage(tabId, { action: "show_status", text: `Translating (${sourceLang})...` }).catch(() => {});

        // A. Find Scroller
        const metrics = await chrome.scripting.executeScript({
            target: { tabId: tabId },
            func: () => {
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
                const scroller = getLargestScroller();
                // Get the bounding rect so we know where this scroller is on the screen
                const rect = scroller.getBoundingClientRect();
                return { 
                    x: scroller.scrollLeft, 
                    y: scroller.scrollTop,
                    scrollerTopOnScreen: rect.top
                };
            }
        });
        const pageMetrics = metrics[0].result;

        // B. Capture
        const dataUrl = await chrome.tabs.captureVisibleTab(null, { format: 'jpeg', quality: 50 });
        const dimensions = await getBitmapDimensions(dataUrl);

        // C. Send to Python Server
        const blob = await (await fetch(dataUrl)).blob();
        const formData = new FormData();
        formData.append("file", blob, "screenshot.jpg");

        // --- KEY CHANGE: Send the language choice ---
        formData.append("source_lang", sourceLang);

        const response = await fetch(`${SERVER_URL}/translate`, {
            method: 'POST',
            body: formData
        });
        const result = await response.json();

        // D. Draw
        chrome.tabs.sendMessage(tabId, {
            action: "draw_overlay",
            bubbles: result.data,
            originalWidth: dimensions.width,
            originalHeight: dimensions.height,
            snapshotScrollX: pageMetrics.x,
            snapshotScrollY: pageMetrics.y,
            scrollerTopOnScreen: pageMetrics.scrollerTopOnScreen
        });

    } catch (err) {
        console.error("Translation Failed:", err);
        chrome.tabs.sendMessage(tabId, { action: "show_status", text: "Error: " + err.message }).catch(() => {});
    }
}

async function getBitmapDimensions(dataUrl) {
    const response = await fetch(dataUrl);
    const blob = await response.blob();
    const bitmap = await createImageBitmap(blob);
    return { width: bitmap.width, height: bitmap.height };
}
