# Elemsocial Telegram Bot

A Python bot that automatically reposts messages from a specified Telegram channel to the **Elemsocial** social network via its legacy WebSocket API.

## Features

- Monitors new channel posts (including captions from media messages) in a public Telegram channel.
- Publishes the text content to Elemsocial using the `user_api_legacy` endpoint.
- Automatic reconnection with exponential backoff in case of WebSocket drops.
- Asynchronous design: Telegram polling and WebSocket client run in parallel without blocking each other.

## Requirements

- Python 3.8+
- Telegram Bot Token (obtain from [@BotFather](https://t.me/BotFather))
- A Telegram channel (you must add the bot as an administrator)
- Valid Elemsocial account credentials (email + password)

## Installation

1. Clone or download the repository:
   ```bash
   git clone https://github.com/yourusername/elemsocial-telegram-bot.git
   cd elemsocial-telegram-bot
```

1. (Optional but recommended) Create and activate a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate      # Linux/macOS
   venv\Scripts\activate         # Windows
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

Configuration

1. Copy the example config file and edit it:
   ```bash
   cp config.example.json config.json
   ```
2. Open config.json and fill in your actual credentials:
   ```json
   {
     "telegram_token": "1234567890:ABCdefGHIjklmNOPqrstUVWXYZ",
     "channel_username": "my_awesome_channel",
     "elemsocial_email": "your@email.com",
     "elemsocial_password": "YourSecretPass123",
     "admin_chat_id": null,
     "ws_url": "wss://ws.elemsocial.com/user_api_legacy"
   }
   ```
   · channel_username: the username of your Telegram channel without the @ symbol (e.g., my_channel).
   · admin_chat_id – optional, can be left null (reserved for future admin notifications).

⚠️ Never commit your real config.json to version control! It is already ignored in .gitignore.

Running the Bot

Simply execute:

```bash
python main.py
```

When started, the bot will:

· Connect to Elemsocial WebSocket and authenticate.
· Start polling your Telegram channel.
· Log every received post and attempt to republish it.

Logs are printed to the console with timestamps.
