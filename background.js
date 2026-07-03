const TELEGRAM_API_BASE = "https://api.telegram.org";
const TRUCK_MPG = 6.5;
const DIESEL_PRICE_PER_GALLON = 4;

async function getTelegramConfig() {
  // Credentials are saved by the options page in sync storage so they follow the user profile.
  const { token, chat_id } = await chrome.storage.sync.get([
    "token",
    "chat_id"
  ]);

  return { token, chat_id };
}

function parseCurrency(value) {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }

  const match = String(value || "").match(/\$?\s*([\d,]+(?:\.\d{1,2})?)/);
  return match ? Number(match[1].replace(/,/g, "")) : null;
}

function parseMiles(value) {
  if (typeof value === "number") {
    return Number.isFinite(value) ? value : null;
  }

  const match = String(value || "").match(/([\d,]+(?:\.\d+)?)\s*(?:mi|mile|miles)?/i);
  return match ? Number(match[1].replace(/,/g, "")) : null;
}

function formatCurrency(value) {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  return `$${value.toLocaleString(undefined, {
    maximumFractionDigits: 2,
    minimumFractionDigits: 2
  })}`;
}

function formatRatePerMile(value) {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  return `$${value.toFixed(2)}/mi`;
}

function calculateLoadMetrics(load) {
  const rate = parseCurrency(load.rate);
  const loadedMiles = parseMiles(load.miles);
  const deadheadMiles = parseMiles(load.deadheadMiles);
  const totalMiles =
    loadedMiles === null && deadheadMiles === null
      ? null
      : (loadedMiles || 0) + (deadheadMiles || 0);
  const fuelCost = totalMiles === null ? null : (totalMiles / TRUCK_MPG) * DIESEL_PRICE_PER_GALLON;
  const deadheadFuelCost =
    deadheadMiles === null ? null : (deadheadMiles / TRUCK_MPG) * DIESEL_PRICE_PER_GALLON;
  const netProfit = rate === null || fuelCost === null ? null : rate - fuelCost;
  const trueRpm = rate === null || !totalMiles ? null : rate / totalMiles;

  return {
    loadedMiles,
    deadheadMiles,
    totalMiles,
    fuelCost,
    deadheadFuelCost,
    netProfit,
    trueRpm
  };
}

function formatMiles(value) {
  if (value === null || !Number.isFinite(value)) {
    return "N/A";
  }

  return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })} mi`;
}

function formatLoadAlert(load) {
  const origin = load.origin || "Unknown origin";
  const destination = load.destination || "Unknown destination";
  const rate = load.rate ? `\nRate: ${load.rate}` : "";
  const pickup = load.pickup ? `\nPickup: ${load.pickup}` : "";
  const equipment = load.equipment ? `\nEquipment: ${load.equipment}` : "";
  const metrics = calculateLoadMetrics(load);

  return [
    "New DAT load alert",
    [
      `${origin} -> ${destination}`,
      rate.trim(),
      pickup.trim(),
      equipment.trim(),
      `Loaded miles: ${formatMiles(metrics.loadedMiles)}`,
      `Deadhead miles: ${formatMiles(metrics.deadheadMiles)}`,
      `Total miles: ${formatMiles(metrics.totalMiles)}`,
      `Deadhead fuel impact: ${formatCurrency(metrics.deadheadFuelCost)}`,
      `Fuel cost: ${formatCurrency(metrics.fuelCost)} (${TRUCK_MPG} mpg @ ${formatCurrency(DIESEL_PRICE_PER_GALLON)}/gal)`,
      `Estimated net profit: ${formatCurrency(metrics.netProfit)}`,
      `True RPM: ${formatRatePerMile(metrics.trueRpm)}`
    ].filter(Boolean).join("\n")
  ].join("\n\n");
}

function buildBrokerEmailUrl(load) {
  const brokerEmail = load.brokerEmail || "";
  const recipient = brokerEmail ? brokerEmail : "";
  const subject = `DAT load inquiry: ${load.origin || "Origin"} to ${load.destination || "Destination"}`;
  const body = [
    "Hello,",
    "",
    "I am interested in this DAT load.",
    `Lane: ${load.origin || "Unknown origin"} to ${load.destination || "Unknown destination"}`,
    load.pickup ? `Pickup: ${load.pickup}` : "",
    load.rate ? `Rate: ${load.rate}` : "",
    "",
    "Please send more details."
  ].filter(Boolean).join("\n");

  return `mailto:${recipient}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

function buildTelegramReplyMarkup(load) {
  return {
    inline_keyboard: [
      [
        {
          text: "Email Broker",
          url: buildBrokerEmailUrl(load)
        }
      ]
    ]
  };
}

async function sendTelegramMessage(token, chatId, load) {
  const result = await sendTelegramAlert(
    token,
    chatId,
    formatLoadAlert(load),
    buildTelegramReplyMarkup(load)
  );

  if (!result.ok) {
    throw new Error(result.error || "Telegram API request failed");
  }

  return result;
}

async function sendTelegramAlert(token, chatId, message, replyMarkup) {
  try {
    const payload = {
      chat_id: chatId,
      text: message,
      disable_web_page_preview: true
    };

    if (replyMarkup) {
      payload.reply_markup = replyMarkup;
    }

    const response = await fetch(`${TELEGRAM_API_BASE}/bot${token}/sendMessage`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
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
  // Content scripts send scraped load rows here; the service worker owns network I/O.
  if (message?.type !== "SNIPE_DAT_LOADS_SCRAPED") {
    return false;
  }

  const loads = Array.isArray(message.loads) ? message.loads : [];

  getTelegramConfig()
    .then(({ token, chat_id }) => {
      if (!token || !chat_id) {
        console.warn("SnipeDAT Telegram settings are missing. User needs to configure settings.");
        return [];
      }

      return Promise.all(
        loads.map((load) =>
          sendTelegramMessage(token, chat_id, load)
        )
      );
    })
    .then((results) => sendResponse({ ok: true, sent: results.length }))
    .catch((error) => {
      console.error("Failed to send SnipeDAT alert.", error);
      sendResponse({ ok: false, error: error.message });
    });

  return true;
});
