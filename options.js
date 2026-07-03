document.addEventListener("DOMContentLoaded", loadOptions);

const TELEGRAM_API_BASE = "https://api.telegram.org";
const TEST_MESSAGE = "TEST LOAD: Chicago, IL -> Dallas, TX | $2500";

const tokenInput = document.getElementById("token");
const chatIdInput = document.getElementById("chat_id");
const form = document.getElementById("options-form");
const resetButton = document.getElementById("reset");
const testConnectionButton = document.getElementById("test-connection");
const status = document.getElementById("status");

form.addEventListener("submit", (event) => {
  event.preventDefault();
  saveOptions();
});

resetButton.addEventListener("click", resetOptions);
testConnectionButton.addEventListener("click", testConnection);

function loadOptions() {
  // Load saved Telegram credentials from Chrome profile sync storage.
  chrome.storage.sync.get(["token", "chat_id"], (result) => {
    tokenInput.value = result.token || "";
    chatIdInput.value = result.chat_id || "";
  });
}

function saveOptions() {
  const token = tokenInput.value.trim();
  const chat_id = chatIdInput.value.trim();

  if (!token || !chat_id) {
    showStatus("Please fill in both fields", "error");
    return;
  }

  chrome.storage.sync.set({ token, chat_id }, () => {
    showStatus("Settings saved.", "success");
  });
}

function resetOptions() {
  chrome.storage.sync.remove(["token", "chat_id"], () => {
    tokenInput.value = "";
    chatIdInput.value = "";
    showStatus("Settings reset.", "success");
  });
}

async function testConnection() {
  testConnectionButton.disabled = true;

  try {
    const { token, chat_id } = await chrome.storage.sync.get([
      "token",
      "chat_id"
    ]);

    if (!token || !chat_id) {
      showStatus("Please save both Telegram credentials before testing.", "error");
      return;
    }

    const response = await fetch(`${TELEGRAM_API_BASE}/bot${token}/sendMessage`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        chat_id,
        text: TEST_MESSAGE,
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

    if (!response.ok || responseBody.ok === false) {
      throw new Error(responseBody.description || `Telegram API request failed: ${response.status}`);
    }

    showStatus("Test message sent successfully.", "success");
  } catch (error) {
    showStatus(`Test connection failed: ${error.message}`, "error");
  } finally {
    testConnectionButton.disabled = false;
  }
}

function showStatus(message, type) {
  status.textContent = message;
  status.className = type;
  status.style.display = "block";
  setTimeout(() => {
    status.style.display = "none";
  }, 3000);
}
