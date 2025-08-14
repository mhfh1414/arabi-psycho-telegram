import os
import logging
from flask import Flask, request, jsonify
import requests

# =====================
# Config (بيئة التشغيل)
# =====================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # مطلوب
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN env var")

BOT_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("PUBLIC_URL")  # يضبطه Render تلقائيًا
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")  # اختياري لكنه مستحسن

# =====================
# App & Logging
# =====================
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho-bot")

# =====================
# Telegram helpers
# =====================
def tg(method: str, payload: dict):
    url = f"{BOT_API}/{method}"
    r = requests.post(url, json=payload, timeout=15)
    try:
        return r.json()
    except Exception:
        return {"status_code": r.status_code, "text": r.text}

def send_message(chat_id: int, text: str, reply_to_message_id: int | None = None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    return tg("sendMessage", payload)

def set_webhook():
    if not RENDER_URL:
        log.warning("No PUBLIC URL (RENDER_EXTERNAL_URL) yet. Skipping setWebhook.")
        return {"ok": False, "reason": "No public URL"}
    url = f"{RENDER_URL.rstrip('/')}/webhook/{TELEGRAM_BOT_TOKEN}"
    payload = {"url": url}
    if WEBHOOK_SECRET:
        payload["secret_token"] = WEBHOOK_SECRET
    res = tg("setWebhook", payload)
    log.info("setWebhook -> %s", res)
    return res

# =====================
# Routes
# =====================
@app.get("/")
def index():
    return jsonify({
        "app": "Arabi Psycho Telegram Bot",
        "status": "ok",
        "webhook": f"/webhook/{TELEGRAM_BOT_TOKEN[-8:]}... (masked)",
        "public_url": RENDER_URL,
    })

@app.get("/health")
def health():
    return "ok", 200

@app.get("/setwebhook")
def setwebhook_route():
    res = set_webhook()
    return jsonify(res)

@app.get("/getwebhook")
def getwebhook_route():
    return tg("getWebhookInfo", {})

@app.post("/webhook/<token>")
def webhook(token):
    if token != TELEGRAM_BOT_TOKEN:
        return "forbidden", 403

    # Optional: تحقق من الهيدر الس
