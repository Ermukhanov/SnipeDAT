const TELEGRAM_API_BASE = "https://api.telegram.org";
const DIESEL_MPG = 6.5;
const DIESEL_PRICE_PER_GALLON = 4.00;
const OPERATING_COST_PER_MILE = 0.40;

async function getTelegramConfig() {
  // Credentials are saved by the options page in sync storage so they follow the user profile.
  const { token, chat_id, broker_email, default_miles, default_deadhead_miles } = await chrome.storage.sync.get([
    "token",
    "chat_id",
    "broker_email",
    "default_miles",
    "default_deadhead_miles"
  ]);

  return { token, chat_id, broker_email, default_miles, default_deadhead_miles };
}

function parseNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value !== "string") {
    return 0;
  }

  const parsed = Number.parseFloat(value.replace(/[$,]/g, ""));
  return Number.isFinite(parsed) ? parsed : 0;
}

function calculateFuelCost(miles) {
  return (parseNumber(miles) / DIESEL_MPG) * DIESEL_PRICE_PER_GALLON;
}

function calculateDeadheadImpact(deadheadMiles) {
  return calculateFuelCost(deadheadMiles);
}

function calculateOperatingCost(miles) {
  return parseNumber(miles) * OPERATING_COST_PER_MILE;
}

function calculateNetProfit(rate, miles) {
  const fuelCost = calculateFuelCost(miles);
  const operatingCost = calculateOperatingCost(miles);

  return parseNumber(rate) - (fuelCost + operatingCost);
}

function calculateTrueRpm(rate, miles) {
  const numericMiles = parseNumber(miles);

  if (numericMiles <= 0) {
    return 0;
  }

  return calculateNetProfit(rate, numericMiles) / numericMiles;
}

function calculatePremiumFields(load) {
  const miles = parseNumber(load.miles);
  const deadheadMiles = parseNumber(load.deadhead_miles);
  const rate = parseNumber(load.rate);
  const fuelCost = calculateFuelCost(miles);
  const deadheadImpact = calculateDeadheadImpact(deadheadMiles);
  const operatingCost = calculateOperatingCost(miles);
  const netProfit = calculateNetProfit(rate, miles);
  const trueRpm = calculateTrueRpm(rate, miles);

  return {
    miles,
    deadhead_miles: deadheadMiles,
    rate,
    fuel_cost: fuelCost,
    deadhead_impact: deadheadImpact,
    estimated_operating_cost: operatingCost,
    estimated_net_profit: netProfit,
    true_rpm: trueRpm
  };
}

function formatCurrency(value) {
  return `$${parseNumber(value).toFixed(2)}`;
}

function formatDecimal(value) {
  return parseNumber(value).toFixed(2);
}

function getBrokerEmail(load) {
  return (load.broker_email || "").trim();
}

function buildEmailBrokerMarkup(load) {
  const brokerEmail = getBrokerEmail(load);

  if (!brokerEmail) {
    return undefined;
  }

  return {
    inline_keyboard: [
      [
        {
          text: "Email Broker",
          url: `mailto:${brokerEmail}`
        }
      ]
    ]
  };
}

function formatLoadAlert(load) {
  const origin = load.origin || "Unknown origin";
  const destination = load.destination || "Unknown destination";
  const rate = load.rate ? `\nRate: ${load.rate}` : "";
  const pickup = load.pickup ? `\nPickup: ${load.pickup}` : "";
  const equipment = load.equipment ? `\nEquipment: ${load.equipment}` : "";
  const premium = calculatePremiumFields(load);

  return [
    "New DAT load alert",
    [
      `${origin} -> ${destination}${rate}${pickup}${equipment}`,
      `Miles: ${formatDecimal(premium.miles)}`,
      `Deadhead Miles: ${formatDecimal(premium.deadhead_miles)}`,
      `Fuel Cost: ${formatCurrency(premium.fuel_cost)}`,
      `Deadhead Impact: ${formatCurrency(premium.deadhead_impact)}`,
      `Estimated Operating Cost: ${formatCurrency(premium.estimated_operating_cost)}`,
      `Estimated Net Profit: ${formatCurrency(premium.estimated_net_profit)}`,
      `True RPM: ${formatCurrency(premium.true_rpm)}`
    ].join("\n")
  ].join("\n\n");
}

async function sendTelegramMessage(token, chatId, load) {
  const result = await sendTelegramAlert(
    token,
    chatId,
    formatLoadAlert(load),
    buildEmailBrokerMarkup(load)
  );

  if (!result.ok) {
    throw new Error(result.error || "Telegram API request failed");
  }

  return result;
}

async function sendTelegramAlert(token, chatId, message, replyMarkup) {
  try {
    const response = await fetch(`${TELEGRAM_API_BASE}/bot${token}/sendMessage`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        chat_id: chatId,
        text: message,
        disable_web_page_preview: true,
        ...(replyMarkup ? { reply_markup: replyMarkup } : {})
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
globalThis.calculateFuelCost = calculateFuelCost;
globalThis.calculateDeadheadImpact = calculateDeadheadImpact;
globalThis.calculateNetProfit = calculateNetProfit;
globalThis.calculateTrueRpm = calculateTrueRpm;
globalThis.calculatePremiumFields = calculatePremiumFields;
globalThis.formatLoadAlert = formatLoadAlert;
globalThis.buildEmailBrokerMarkup = buildEmailBrokerMarkup;

function applyLoadDefaults(load, config) {
  return {
    ...load,
    miles: load.miles ?? config.default_miles ?? "",
    deadhead_miles: load.deadhead_miles ?? config.default_deadhead_miles ?? "",
    broker_email: load.broker_email || config.broker_email || ""
  };
}

if (globalThis.chrome?.runtime?.onMessage) {
  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  // Content scripts send scraped load rows here; the service worker owns network I/O.
    if (message?.type !== "SNIPE_DAT_LOADS_SCRAPED") {
      return false;
    }

    const loads = Array.isArray(message.loads) ? message.loads : [];

    getTelegramConfig()
      .then((config) => {
        const { token, chat_id } = config;

        if (!token || !chat_id) {
          console.warn("SnipeDAT Telegram settings are missing. User needs to configure settings.");
          return [];
        }

        return Promise.all(
          loads.map((load) => sendTelegramMessage(token, chat_id, applyLoadDefaults(load, config)))
        );
      })
      .then((results) => sendResponse({ ok: true, sent: results.length }))
      .catch((error) => {
        console.error("Failed to send SnipeDAT alert.", error);
        sendResponse({ ok: false, error: error.message });
      });

    return true;
  });
}
