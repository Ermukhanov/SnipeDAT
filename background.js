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

  const result = await sendTelegramAlert(telegramBotToken, TELEGRAM_CHAT_ID, text);

  if (!result.ok) {
    throw new Error(result.error || "Telegram API request failed");
  }

  return result;
}

async function sendTelegramAlert(token, chatId, message) {
  try {
    const response = await fetch(`${TELEGRAM_API_BASE}/bot${token}/sendMessage`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        chat_id: chatId,
        text: message,
        disable_web_page_preview: true
      })
    });

    const responseText = await response.text();
    let responseBody;

    try {
      responseBody = responseText ? JSON.parse(responseText) : {};
    } catch (_error) {
      responseBody = { description: responseText };
    }

    if (!response.ok) {
      return {
        ok: false,
        error: `Telegram API request failed: ${response.status} ${responseBody.description || ""}`.trim()
      };
    }

    return responseBody;
  } catch (error) {
    return { ok: false, error: error.message };
  }
}

globalThis.sendTelegramAlert = sendTelegramAlert;

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
