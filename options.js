document.addEventListener("DOMContentLoaded", loadOptions);

const tokenInput = document.getElementById("token");
const chatIdInput = document.getElementById("chat_id");
const form = document.getElementById("options-form");
const resetButton = document.getElementById("reset");
const status = document.getElementById("status");

form.addEventListener("submit", (event) => {
  event.preventDefault();
  saveOptions();
});

resetButton.addEventListener("click", resetOptions);

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

function showStatus(message, type) {
  status.textContent = message;
  status.className = type;
  status.style.display = "block";
  setTimeout(() => {
    status.style.display = "none";
  }, 3000);
}
