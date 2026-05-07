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
import ssl
import requests
from typing import Tuple, Optional, Dict, Any, List
from telebot.types import Message
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

CONFIG_FILE = "config.json"
if not os.path.exists(CONFIG_FILE):
    raise FileNotFoundError(f"Config file {CONFIG_FILE} not found.")
with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config = json.load(f)

TELEGRAM_TOKEN = config["telegram_token"]
ALLOWED_USER_ID = config["allowed_user_id"]
ELEMSOCIAL_EMAIL = config["elemsocial_email"]
ELEMSOCIAL_PASSWORD = config["elemsocial_password"]
WS_URL = config.get("ws_url", "wss://ws.elemsocial.com/user_api_legacy")

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Настройка сессии с отключенной проверкой SSL
class SSLAdapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)

session = requests.Session()
session.mount('https://', SSLAdapter())
session.verify = False
telebot.apihelper._get_req_session = lambda: session

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
        self._lock = asyncio.Lock()

    async def connect(self) -> bool:
        try:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            self.socket = await websockets.connect(WS_URL, ssl=ssl_context)
            logger.info("WebSocket connected")
            self.reconnect_attempts = 0
            return True
        except Exception as e:
            logger.error(f"Connection error: {e}")
            return False

    async def send_and_receive(self, data: Dict[str, Any], timeout: int = 30) -> Optional[Dict[str, Any]]:
        if not self.socket:
            logger.error("No active socket")
            return None
            
        if "ray_id" not in data:
            data["ray_id"] = generate_ray_id()
            
        try:
            async with self._lock:
                packed = msgpack.packb(data)
                await self.socket.send(packed)
                response = await asyncio.wait_for(self.socket.recv(), timeout=timeout)
                return msgpack.unpackb(response, raw=False)
        except asyncio.TimeoutError:
            logger.error(f"Timeout error")
            return None
        except Exception as e:
            logger.error(f"Send/receive error: {e}")
            return None

    async def login(self) -> bool:
        resp = await self.send_and_receive({
            "type": "social",
            "action": "auth/login",
            "email": ELEMSOCIAL_EMAIL,
            "password": ELEMSOCIAL_PASSWORD,
            "device_type": "browser",
            "device": "Telegram Bot"
        })
        if not resp or resp.get("status") != "success":
            logger.error(f"Login error: {resp}")
            return False
        self.session_key = resp.get("S_KEY")
        if not self.session_key:
            logger.error("S_KEY not received")
            return False
            
        resp2 = await self.send_and_receive({
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

    async def create_post_with_photo(self, text: str, photo_data: bytes, filename: str = "photo.jpg") -> Tuple[bool, str]:
        """Публикация поста с фото - отправляем файл прямо в posts/add"""
        if not self.connected:
            return False, "Not authorized"
        
        # Формируем payload с файлом как в примере разработчика
        files = [
            {
                "name": filename,
                "buffer": photo_data
            }
        ]
        
        payload = {
            "text": text,
            "files": files  # Отправляем файлы прямо в payload
        }
        
        logger.info(f"Sending post with photo, payload size: {len(photo_data)} bytes")
        
        resp = await self.send_and_receive({
            "type": "social",
            "action": "posts/add",
            "payload": payload
        }, timeout=120)  # Увеличиваем таймаут для фото
        
        if resp and resp.get("status") == "success":
            logger.info(f"Post with photo published successfully!")
            return True, None
        else:
            error_msg = resp.get("message") if resp else "No response"
            logger.error(f"Publish error: {resp}")
            return False, error_msg

    async def create_post(self, text: str) -> Tuple[bool, str]:
        """Публикация текстового поста"""
        if not self.connected:
            return False, "Not authorized"
            
        payload = {"text": text}
        resp = await self.send_and_receive({
            "type": "social",
            "action": "posts/add",
            "payload": payload
        }, timeout=60)
        
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
                if self.connected and self.socket:
                    await self.send_and_receive({"type": "ping"})
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
                        logger.info("Reconnected successfully")
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

def safe_send_message(chat_id: int, text: str):
    """Безопасная отправка сообщения"""
    try:
        bot.send_message(chat_id, text, parse_mode=None)
    except Exception as e:
        logger.error(f"Failed to send message: {e}")

def is_allowed_user(message: Message) -> bool:
    user_id = message.from_user.id
    if user_id != ALLOWED_USER_ID:
        logger.warning(f"Unauthorized access attempt from user {user_id}")
        safe_send_message(message.chat.id, "❌ Нет доступа")
        return False
    return True

def download_telegram_photo(file_id: str) -> Tuple[Optional[bytes], Optional[str]]:
    """Скачивает фото из Telegram, возвращает (данные, расширение)"""
    try:
        file_info = bot.get_file(file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        # Определяем расширение файла
        ext = file_info.file_path.split('.')[-1] if '.' in file_info.file_path else 'jpg'
        
        return downloaded_file, ext
    except Exception as e:
        logger.error(f"Failed to download photo: {e}")
        return None, None

@bot.message_handler(commands=['start'])
def handle_start(message: Message):
    if not is_allowed_user(message):
        return
    
    safe_send_message(
        message.chat.id,
        "🤖 Elemsocial Bot\n\n"
        "Отправьте текст или фото для публикации в Elemsocial.\n\n"
        f"Статус: {'✅ Connected' if client.connected else '🔄 Connecting...'}"
    )

@bot.message_handler(commands=['status'])
def handle_status(message: Message):
    if not is_allowed_user(message):
        return
    
    status_text = f"WebSocket: {'✅ Connected' if client.connected else '❌ Disconnected'}"
    safe_send_message(message.chat.id, status_text)

@bot.message_handler(content_types=['photo'])
def handle_photo(message: Message):
    if not is_allowed_user(message):
        return
    
    caption = message.caption or ""
    photo = message.photo[-1]  # Берём фото в максимальном качестве
    
    safe_send_message(message.chat.id, "📸 Получил фото, публикую в Elemsocial...")
    
    photo_data, ext = download_telegram_photo(photo.file_id)
    if not photo_data:
        safe_send_message(message.chat.id, "❌ Не удалось скачать фото")
        return
    
    try:
        future = asyncio.run_coroutine_threadsafe(
            client.create_post_with_photo(caption, photo_data, f"photo.{ext}"), 
            loop
        )
        success, err_msg = future.result(timeout=90)  # Больше времени для фото
        
        if success:
            safe_send_message(message.chat.id, "✅ Фото опубликовано в Elemsocial!")
        else:
            safe_send_message(message.chat.id, f"❌ Ошибка: {err_msg}")
    except Exception as e:
        logger.error(f"Exception: {e}")
        safe_send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

@bot.message_handler(content_types=['text'])
def handle_text(message: Message):
    if not is_allowed_user(message):
        return
    
    text = message.text.strip()
    if not text or text.startswith('/'):
        return
    
    safe_send_message(message.chat.id, "📝 Публикую текст в Elemsocial...")
    
    try:
        future = asyncio.run_coroutine_threadsafe(client.create_post(text), loop)
        success, err_msg = future.result(timeout=60)
        
        if success:
            safe_send_message(message.chat.id, "✅ Текст опубликован в Elemsocial!")
        else:
            safe_send_message(message.chat.id, f"❌ Ошибка: {err_msg}")
    except Exception as e:
        logger.error(f"Exception: {e}")
        safe_send_message(message.chat.id, f"❌ Ошибка: {str(e)[:100]}")

# Асинхронный цикл
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

async def start_client():
    if await client.connect():
        if await client.login():
            asyncio.create_task(client.ping_loop())
            asyncio.create_task(client.maintain_connection())
            logger.info("Bot ready")
            return True
    logger.error("Failed to start client")
    return False

def run_async():
    loop.run_until_complete(start_client())
    loop.run_forever()

threading.Thread(target=run_async, daemon=True).start()
time.sleep(3)

logger.info(f"Bot started for user ID: {ALLOWED_USER_ID}")
bot.infinity_polling(skip_pending=True, timeout=60)
