import asyncio
import websockets
import msgpack
import telebot
import threading
import time
import logging
import random
import string
import json
import os
from typing import Tuple, Optional, List, Dict, Any

CONFIG_FILE = "config.json"
if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"Config file {CONFIG_FILE} not found.")
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

TELEGRAM_TOKEN = config["telegram_token"]
CHANNEL_USERNAME = config["channel_username"]
ELEMSOCIAL_EMAIL = config["elemsocial_email"]
ELEMSOCIAL_PASSWORD = config["elemsocial_password"]
WS_URL = config.get("ws_url", "wss://ws.elemsocial.com/user_api_legacy")

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def generate_ray_id() -> str:
    timestamp = int(time.time() * 1000)
    chars = string.ascii_letters + string.digits
    random_part = ''.join(random.choices(chars, k=10))
    return f"{timestamp}{random_part}"

class ElemsocialClient:
    def __init__(self):
        self.socket: Optional[websockets.WebSocketClientProtocol] = None
        self.session_key: Optional[str] = None
        self.connected: bool = False
        self.reconnect_attempts: int = 0
        self.stop_flag: bool = False

    async def connect(self) -> bool:
        try:
            self.socket = await websockets.connect(WS_URL)
            logger.info("WebSocket (legacy) connected")
            self.reconnect_attempts = 0
            return True
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    async def send(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self.socket:
            logger.error("No active socket")
            return None
        if "ray_id" not in data:
            data["ray_id"] = generate_ray_id()
        try:
            packed = msgpack.packb(data)
            await self.socket.send(packed)
            response = await asyncio.wait_for(self.socket.recv(), timeout=30)
            return msgpack.unpackb(response, raw=False)
        except Exception as e:
            logger.error(f"Send/receive error: {e}")
            return None

    async def login(self) -> bool:
        resp = await self.send({
            "type": "social",
            "action": "auth/login",
            "email": ELEMSOCIAL_EMAIL,
            "password": ELEMSOCIAL_PASSWORD,
            "device_type": "browser",
            "device": "Telegram Bot (Media)"
        })
        if not resp or resp.get("status") != "success":
            logger.error(f"Login error: {resp}")
            return False
        self.session_key = resp.get("S_KEY")
        if not self.session_key:
            logger.error("S_KEY not received")
            return False
        resp2 = await self.send({
            "type": "authorization",
            "action": "connect",
            "S_KEY": self.session_key
        })
        if not resp2 or resp2.get("status") != "success":
            logger.error(f"Connect error: {resp2}")
            return False
        logger.info("Authorization successful")
        self.connected = True
        return True

    async def create_post(self, text: str) -> Tuple[bool, str]:
        if not self.connected:
            return False, "Not authorized"
        payload = {"text": text}
        resp = await self.send({
            "type": "social",
            "action": "posts/add",
            "payload": payload
        })
        if resp and resp.get("status") == "success":
            logger.info(f"Post published: {text[:50]}")
            return True, None
        else:
            error_msg = resp.get("message") if resp else "No response"
            logger.error(f"Publish error: {resp}")
            return False, error_msg

    async def ping_loop(self):
        while self.connected and not self.stop_flag:
            await asyncio.sleep(30)
            try:
                await self.send({"type": "ping"})
            except Exception as e:
                logger.warning(f"Ping failed: {e}")
                self.connected = False
                break

    async def maintain_connection(self):
        while not self.stop_flag:
            if not self.connected:
                delay = min(5 + self.reconnect_attempts * 2, 60)
                logger.info(f"Reconnecting in {delay} sec...")
                await asyncio.sleep(delay)
                self.reconnect_attempts += 1
                if await self.connect():
                    if await self.login():
                        asyncio.create_task(self.ping_loop())
                    else:
                        logger.error("Reconnect failed (login error)")
                else:
                    logger.error("Reconnect failed (socket error)")
            else:
                await asyncio.sleep(5)

    async def disconnect(self):
        self.stop_flag = True
        self.connected = False
        if self.socket:
            await self.socket.close()
            self.socket = None

bot = telebot.TeleBot(TELEGRAM_TOKEN)
client = ElemsocialClient()

def process_telegram_message(message) -> str:
    text = message.caption or message.text or ""
    return text

@bot.channel_post_handler(func=lambda msg: msg.chat.username == CHANNEL_USERNAME)
def handle_channel_post(message):
    text = process_telegram_message(message)
    if not text:
        logger.info("Message has no text, skipping")
        return
    logger.info(f"New post: {len(text)} chars")
    future = asyncio.run_coroutine_threadsafe(client.create_post(text), loop)
    try:
        success, err_msg = future.result(timeout=60)
        if not success:
            logger.error(f"Publish failed: {err_msg}")
    except Exception as e:
        logger.error(f"Exception during publish: {e}")

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

async def start_client():
    if await client.connect():
        if await client.login():
            asyncio.create_task(client.ping_loop())
            asyncio.create_task(client.maintain_connection())
            logger.info("Bot ready, listening to channel")
            return True
    logger.error("Failed to start client")
    return False

def run_async():
    loop.run_until_complete(start_client())
    loop.run_forever()

threading.Thread(target=run_async, daemon=True).start()
time.sleep(3)

logger.info(f"Listening to channel @{CHANNEL_USERNAME}")
bot.infinity_polling(skip_pending=True)