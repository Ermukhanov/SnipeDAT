document.addEventListener("DOMContentLoaded", loadOptions);

function loadOptions() {
  chrome.storage.local.get(["telegramBotToken", "telegramChatId"], (result) => {
    if (result.telegramBotToken) document.getElementById("telegramBotToken").value = result.telegramBotToken;
    if (result.telegramChatId) document.getElementById("telegramChatId").value = result.telegramChatId;
  });
}

function saveOptions() {
  const token = document.getElementById("telegramBotToken").value;
  const chatId = document.getElementById("telegramChatId").value;
  
  if (!token || !chatId) {
    showStatus("Please fill in both fields", "error");
    return;
  }
  
  chrome.storage.local.set({ telegramBotToken: token, telegramChatId: chatId }, () => {
    showStatus("Settings saved successfully!", "success");
  });
}

function resetOptions() {
  chrome.storage.local.remove(["telegramBotToken", "telegramChatId"], () => {
    document.getElementById("telegramBotToken").value = "";
    document.getElementById("telegramChatId").value = "";
    showStatus("Settings reset", "success");
  });
}

function showStatus(message, type) {
  const status = document.getElementById("status");
  status.textContent = message;
  status.className = type;
  status.style.display = "block";
  setTimeout(() => { status.style.display = "none"; }, 3000);
}
