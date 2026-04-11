document.addEventListener('DOMContentLoaded', async () => {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });

    // 1. Load Saved Language Preference (Optional but nice UX)
    chrome.storage.local.get(['sourceLang'], (result) => {
        if (result.sourceLang) {
            document.getElementById('languageSelect').value = result.sourceLang;
        }
    });

    const toggle = document.getElementById('autoToggle');

    // Auto-Translate Toggle Logic
    toggle.addEventListener('change', () => {
        const lang = document.getElementById('languageSelect').value;
        chrome.runtime.sendMessage({
            action: "toggle_auto",
            enabled: toggle.checked,
            tabId: tab.id,
            sourceLang: lang // Pass language to background worker too
        });
        document.getElementById('status').innerText = toggle.checked ? "Auto Mode: ON" : "Auto Mode: OFF";
    });

    // Manual Translate Button
    document.getElementById('translateBtn').addEventListener('click', () => {
        const lang = document.getElementById('languageSelect').value;

        // Save preference
        chrome.storage.local.set({ sourceLang: lang });

        document.getElementById('status').innerText = "Request Sent...";
        chrome.runtime.sendMessage({
            action: "start_translation",
            tabId: tab.id,
            sourceLang: lang // <--- SEND LANGUAGE HERE
        });
    });
});