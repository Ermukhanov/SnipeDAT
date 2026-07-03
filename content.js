const MIN_POLL_DELAY_MS = 45000;
const MAX_POLL_DELAY_MS = 120000;
const SEEN_LOAD_IDS_LIMIT = 500;

const seenLoadIds = new Set();

function randomDelay(minMs, maxMs) {
  // Randomized polling keeps the stub from hammering dynamic load board pages.
  return Math.floor(Math.random() * (maxMs - minMs + 1)) + minMs;
}

function normalizeText(value) {
  return value?.replace(/\s+/g, " ").trim() || "";
}

function parseNumber(value) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }

  if (typeof value !== "string") {
    return "";
  }

  const parsed = Number.parseFloat(value.replace(/[$,]/g, ""));
  return Number.isFinite(parsed) ? parsed : "";
}

function firstNumericValue(...values) {
  return values.find((value) => value !== "" && value !== null && value !== undefined) ?? "";
}

function findNumberNearLabel(text, labels) {
  for (const label of labels) {
    const match = text.match(new RegExp(`\\b${label}\\b\\s*:?\\s*([\\d,.]+)`, "i"));

    if (match) {
      return parseNumber(match[1]);
    }
  }

  return "";
}

function findBrokerEmail(text) {
  const match = text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i);
  return match ? match[0] : "";
}

function getRowId(row, index) {
  return (
    row.getAttribute("data-load-id") ||
    row.getAttribute("data-test-load-id") ||
    `${normalizeText(row.textContent).slice(0, 160)}-${index}`
  );
}

function parseLoadRow(row, index) {
  const cells = Array.from(row.querySelectorAll("[role='cell'], td"));
  const values = cells.map((cell) => normalizeText(cell.textContent));
  const rawText = normalizeText(row.textContent);
  const miles = firstNumericValue(
    parseNumber(row.getAttribute("data-miles")),
    findNumberNearLabel(rawText, ["trip miles", "miles", "mi"]),
    parseNumber(values[5])
  );
  const deadhead_miles = firstNumericValue(
    parseNumber(row.getAttribute("data-deadhead-miles")),
    parseNumber(row.getAttribute("data-deadhead")),
    findNumberNearLabel(rawText, ["deadhead miles", "deadhead", "dh"]),
    parseNumber(values[6])
  );
  const broker_email =
    row.getAttribute("data-broker-email") ||
    findBrokerEmail(rawText);

  return {
    id: getRowId(row, index),
    origin: values[0] || "",
    destination: values[1] || "",
    pickup: values[2] || "",
    equipment: values[3] || "",
    rate: values[4] || "",
    miles,
    deadhead_miles,
    broker_email,
    rawText,
    scrapedAt: new Date().toISOString()
  };
}

function findLoadRows() {
  // TODO: Replace these generic selectors with confirmed DAT load board selectors.
  return Array.from(
    document.querySelectorAll("[role='row'], table tbody tr, [data-testid*='load']")
  ).filter((row) => normalizeText(row.textContent));
}

function rememberLoadId(loadId) {
  seenLoadIds.add(loadId);

  if (seenLoadIds.size <= SEEN_LOAD_IDS_LIMIT) {
    return;
  }

  const oldestLoadId = seenLoadIds.values().next().value;
  seenLoadIds.delete(oldestLoadId);
}

async function scrapeAndSendLoads() {
  // Stub scraper: parse visible row-like elements and send newly seen rows to the service worker.
  const newLoads = findLoadRows()
    .map(parseLoadRow)
    .filter((load) => {
      if (!load.id || seenLoadIds.has(load.id)) {
        return false;
      }

      rememberLoadId(load.id);
      return true;
    });

  if (newLoads.length === 0) {
    return;
  }

  chrome.runtime.sendMessage({
    type: "SNIPE_DAT_LOADS_SCRAPED",
    loads: newLoads
  });
}

function scheduleNextScrape() {
  const delayMs = randomDelay(MIN_POLL_DELAY_MS, MAX_POLL_DELAY_MS);

  // Re-schedule with a fresh random interval after every scrape attempt.
  window.setTimeout(async () => {
    if (document.visibilityState === "visible") {
      await scrapeAndSendLoads();
    }

    scheduleNextScrape();
  }, delayMs);
}

scheduleNextScrape();
