# SnipeDAT

SnipeDAT is a Chrome extension MVP for monitoring DAT Power load board rows and sending load alerts to Telegram.

The extension includes:

- A Manifest V3 Chrome extension setup.
- A background service worker that receives parsed load data and sends Telegram bot messages.
- A content script stub that periodically scans DAT Power load board rows with randomized, rate-limited polling.

## Setup

1. Clone this repository.
2. Open `chrome://extensions`.
3. Enable Developer mode.
4. Click Load unpacked and select this repository directory.
5. Configure Telegram credentials in Chrome extension storage:
   - `telegramBotToken`
   - `telegramChatId`

## Notes

This is an MVP stub. DAT Power selectors and parsing should be validated against the current DAT Power UI before production use. Make sure your use complies with DAT's terms and all applicable laws.
