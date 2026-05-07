Elemsocial Telegram Bot

A Telegram bot that publishes text posts and photos to Elemsocial via WebSocket API.

Features

· Publish text posts to Elemsocial
· Upload photos with captions
· Automatic WebSocket connection management with reconnection logic
· Single-user access control
· Secure SSL handling (bypasses certificate validation)
· MessagePack API communication

Requirements

· Python 3.7+
· Telegram Bot Token (from @BotFather)
· Valid Elemsocial account credentials

Installation

1. Clone the repository:

```bash
git clone https://github.com/yourusername/elemsocial-telegram-bot.git
cd elemsocial-telegram-bot
```

1. Install dependencies:

```bash
pip install websockets msgpack telebot requests urllib3
```

1. Edit config.json with your credentials:

```json
{
    "telegram_token": "YOUR_TELEGRAM_BOT_TOKEN",
    "allowed_user_id": YOUR_TELEGRAM_USER_ID,
    "elemsocial_email": "your@email.com",
    "elemsocial_password": "your_password",
    "ws_url": "wss://ws.elemsocial.com/user_api_legacy"
}
```

Usage

Run the bot:

```bash
python main.py
```

Commands

Command Description
/start Show welcome message and connection status
/status Check WebSocket connection status

Publishing Content

· Text post: Send any text message (except commands)
· Photo post: Send a photo with optional caption

The bot will confirm successful publication or report errors.

Configuration

Edit config.json with the following parameters:

Parameter Description
telegram_token Telegram Bot API token
allowed_user_id Numeric Telegram user ID (only this user can use the bot)
elemsocial_email Your Elemsocial login email
elemsocial_password Your Elemsocial password
ws_url WebSocket API endpoint (default is provided)

How It Works

1. Establishes WebSocket connection to Elemsocial API
2. Authenticates using email/password
3. Maintains connection with periodic pings and auto-reconnect
4. Listens for Telegram messages from authorized user
5. Forwards text or photo content to Elemsocial using MessagePack format

Limitations

· Only one authorized user is supported
· SSL certificate validation is disabled (use only with trusted networks)
· Requires stable internet connection

Error Handling

· Automatic reconnection on connection loss (exponential backoff: 5s → 60s max)
· Timeout protection for long photo uploads (90 seconds)
· User-friendly error messages in Telegram

Files

File Description
main.py Main bot script
config.json Configuration file (contains your credentials)

License

MIT
