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

function findEmail(text) {
  return text.match(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i)?.[0] || "";
}

function findValueByLabel(text, labels) {
  const labelPattern = labels.join("|");
  const match = text.match(
    new RegExp(`(?:${labelPattern})\\s*:?\\s*\\$?([\\d,]+(?:\\.\\d+)?)\\s*(?:mi|mile|miles)?`, "i")
  );

  return match?.[1] || "";
}

function getOptionalLoadFields(values, rawText) {
  const miles =
    values[5] ||
    findValueByLabel(rawText, ["loaded miles", "trip miles", "miles", "mi"]);
  const deadheadMiles =
    values[6] ||
    findValueByLabel(rawText, ["deadhead", "dh", "origin deadhead"]);
  const brokerEmail = findEmail(values.find(findEmail) || rawText);

  return { miles, deadheadMiles, brokerEmail };
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
  const optionalFields = getOptionalLoadFields(values, rawText);

  return {
    id: getRowId(row, index),
    origin: values[0] || "",
    destination: values[1] || "",
    pickup: values[2] || "",
    equipment: values[3] || "",
    rate: values[4] || "",
    miles: optionalFields.miles,
    deadheadMiles: optionalFields.deadheadMiles,
    brokerEmail: optionalFields.brokerEmail,
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
