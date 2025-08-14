import os
import logging
from flask import Flask, request, jsonify
import requests

# =====================
# Config
# =====================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN env var")

BOT_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
RENDER_URL = os.environ.get("RENDER_EXTERNAL_URL") or os.environ.get("PUBLIC_URL")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")

# =====================
# App & Logging
# =====================
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho-bot")

# =====================
# Telegram helpers
# =====================
def tg(method, payload):
    r = requests.post(f"{BOT_API}/{method}", json=payload, timeout=15)
    try:
        return r.json()
    except Exception:
        return {"status_code": r.status_code, "text": r.text}

def set_webhook():
    if not RENDER_URL:
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
        "public_url": RENDER_URL,
        "webhook": f"/webhook/{TELEGRAM_BOT_TOKEN[-8:]}...(masked)",
    })

@app.get("/health")
def health():
    return "ok", 200

@app.get("/setwebhook")
def setwebhook_route():
    return jsonify(set_webhook())

@app.get("/getwebhook")
def getwebhook_route():
    return jsonify(tg("getWebhookInfo", {}))

@app.post("/webhook/<token>")
def webhook(token):
    if token != TELEGRAM_BOT_TOKEN:
        return "forbidden", 403

    if WEBHOOK_SECRET:
        incoming = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if incoming != WEBHOOK_SECRET:
            return "forbidden", 403

    try:
        update = request.get_json(silent=True) or {}
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = (message.get("text") or "").strip()
        msg_id = message.get("message_id")

        if text.startswith("/start"):
            reply = ("👋 أهلاً بك! أنا <b>عربي سايكو</b> على تيليجرام.\n"
                     "• /help — التعليمات\n"
                     "• اكتب أي رسالة وسأرد عليك الآن (نموذج تجريبي).")
        elif text.startswith("/help"):
            reply = ("🔧 تعليمات سريعة:\n"
                     "- أرسل رسالة نصية وسأرد عليك.\n"
                     "- هذا نموذج أولي سنطوّره لاحقًا.")
        elif text:
            reply = f"تمام 👌 وصلتني:\n“{text}”"
        else:
            reply = "أرسل نصًا من فضلك."

        if chat_id and reply:
            tg("sendMessage", {
                "chat_id": chat_id,
                "text": reply,
                "parse_mode": "HTML",
                "reply_to_message_id": msg_id
            })
    except Exception as e:
        log.exception("webhook error: %s", e)

    # ارجع رد دائمًا حتى لا ترمي Flask خطأ
    return "ok", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
