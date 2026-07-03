const TELEGRAM_API_BASE = "https://api.telegram.org";
const TELEGRAM_CHAT_ID = "6561112046";

async function getTelegramConfig() {
  const { telegramBotToken } = await chrome.storage.local.get([
    "telegramBotToken"
  ]);

  return { telegramBotToken };
}

function formatLoadAlert(load) {
  const origin = load.origin || "Unknown origin";
  const destination = load.destination || "Unknown destination";
  const rate = load.rate ? `\nRate: ${load.rate}` : "";
  const pickup = load.pickup ? `\nPickup: ${load.pickup}` : "";
  const equipment = load.equipment ? `\nEquipment: ${load.equipment}` : "";

  return [
    "New DAT load alert",
    `${origin} -> ${destination}${rate}${pickup}${equipment}`
  ].join("\n\n");
}

async function sendTelegramMessage(text) {
  const { telegramBotToken } = await getTelegramConfig();

  if (!telegramBotToken) {
    console.warn("SnipeDAT Telegram settings are missing.");
    return { ok: false, error: "Missing Telegram settings" };
  }

  const response = await fetch(`${TELEGRAM_API_BASE}/bot${telegramBotToken}/sendMessage`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      chat_id: TELEGRAM_CHAT_ID,
      text,
      disable_web_page_preview: true
    })
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Telegram API request failed: ${response.status} ${errorText}`);
  }

  return response.json();
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type !== "SNIPE_DAT_LOADS_SCRAPED") {
    return false;
  }

  const loads = Array.isArray(message.loads) ? message.loads : [];

  Promise.all(loads.map((load) => sendTelegramMessage(formatLoadAlert(load))))
    .then((results) => sendResponse({ ok: true, sent: results.length }))
    .catch((error) => {
      console.error("Failed to send SnipeDAT alert.", error);
      sendResponse({ ok: false, error: error.message });
    });

  return true;
});
