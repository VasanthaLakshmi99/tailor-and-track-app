// Passes badge lookups from job search pages to the Tailor&Track app on this laptop.
// (Pages themselves cannot talk to the app; only the extension can.)
const API = "http://127.0.0.1:8765";

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "lookup") {
    fetch(API + "/lookup", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-JobPilot": "1" },
      body: JSON.stringify({ items: msg.items }),
    })
      .then((r) => r.json())
      .then(sendResponse)
      .catch(() => sendResponse(null));   // app not running: simply no badges
    return true;  // answer comes later
  }
  return false;
});