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

  return {
    id: getRowId(row, index),
    origin: values[0] || "",
    destination: values[1] || "",
    pickup: values[2] || "",
    equipment: values[3] || "",
    rate: values[4] || "",
    rawText: normalizeText(row.textContent),
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
