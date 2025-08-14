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
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")  # اختياري

# =====================
# App & Logging
# =====================
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho-bot")

# جلسات CBT المؤقتة في الذاكرة
SESSIONS = {}  # { chat_id: {stage: "...", ...} }

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

# =====================
# Webhook
# =====================
@app.post("/webhook/<token>")
def webhook(token):
    # تحقّق من التوكن في عنوان المسار
    if token != TELEGRAM_BOT_TOKEN:
        return "forbidden", 403

    # تحقّق من السر (اختياري)
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

        # لو ما فيه نص، اكتفِ بـ 200 عادي
        if not chat_id:
            return "ok", 200

        # ---------- CBT FLOW ----------
        sess = SESSIONS.get(chat_id)

        # بدء جلسة CBT
        if text == "/cbt":
            SESSIONS[chat_id] = {"stage": "mood"}
            tg("sendMessage", {
                "chat_id": chat_id,
                "text": ("نبدأ جلسة علاج سلوكي معرفي قصيرة 🧠\n"
                         "١) قيّم مزاجك الآن من 0 إلى 10؟"),
                "reply_to_message_id": msg_id
            })
            return "ok", 200

        # متابعة الجلسة إن كانت فعّالة
        if sess:
            stage = sess["stage"]

            # ١) المزاج قبل
            if stage == "mood":
                try:
                    mood = int(text)
                    if not (0 <= mood <= 10):
                        raise ValueError
                    sess["mood_before"] = mood
                    sess["stage"] = "situation"
                    tg("sendMessage", {
                        "chat_id": chat_id,
                        "text": "٢) صف الموقف الذي حصل باختصار:",
                        "reply_to_message_id": msg_id
                    })
                except Exception:
                    tg("sendMessage", {
                        "chat_id": chat_id,
                        "text": "أرسل رقمًا من 0 إلى 10 من فضلك.",
                        "reply_to_message_id": msg_id
                    })
                return "ok", 200

            # ٢) الموقف
            if stage == "situation":
                sess["situation"] = text
                sess["stage"] = "thoughts"
                tg("sendMessage", {
                    "chat_id": chat_id,
                    "text": "٣) ما هي الأفكار التلقائية التي خطرت لك؟",
                    "reply_to_message_id": msg_id
                })
                return "ok", 200

            # ٣) الأفكار
            if stage == "thoughts":
                sess["thoughts"] = text
                sess["stage"] = "evidence_for"
                tg("sendMessage", {
                    "chat_id": chat_id,
                    "text": "٤) ما الدلائل التي تؤيد هذه الفكرة؟",
                    "reply_to_message_id": msg_id
                })
                return "ok", 200

            # ٤) أدلة مؤيدة
            if stage == "evidence_for":
                sess["evidence_for"] = text
                sess["stage"] = "evidence_against"
                tg("sendMessage", {
                    "chat_id": chat_id,
                    "text": "٥) وما الدلائل التي تعارضها؟",
                    "reply_to_message_id": msg_id
                })
                return "ok", 200

            # ٥) أدلة معارضة
            if stage == "evidence_against":
                sess["evidence_against"] = text
                sess["stage"] = "balanced"
                tg("sendMessage", {
                    "chat_id": chat_id,
                    "text": "٦) جرّب صياغة فكرة بديلة متوازنة:",
                    "reply_to_message_id": msg_id
                })
                return "ok", 200

            # ٦) الفكرة المتوازنة
            if stage == "balanced":
                sess["balanced"] = text
                sess["stage"] = "action"
                tg("sendMessage", {
                    "chat_id": chat_id,
                    "text": "٧) اختر خطوة عملية صغيرة ستقوم بها اليوم (Action):",
                    "reply_to_message_id": msg_id
                })
                return "ok", 200

            # ٧) الخطة
            if stage == "action":
                sess["action"] = text
                sess["stage"] = "wrapup"
                tg("sendMessage", {
                    "chat_id": chat_id,
                    "text": "٨) قيّم مزاجك الآن (0–10) بعد إعادة التقييم:",
                    "reply_to_message_id": msg_id
                })
                return "ok", 200

            # ٨) الختام + الملخص
            if stage == "wrapup":
                try:
                    mood_after = int(text)
                except Exception:
                    mood_after = None

                m_before = sess.get("mood_before")
                summary = (
                    "✅ <b>ملخص الجلسة</b>\n"
                    f"• الموقف: {sess.get('situation','-')}\n"
                    f"• الأفكار: {sess.get('thoughts','-')}\n"
                    f"• أدلة مؤيدة: {sess.get('evidence_for','-')}\n"
                    f"• أدلة معارضة: {sess.get('evidence_against','-')}\n"
                    f"• الفكرة البديلة: {sess.get('balanced','-')}\n"
                    f"• خطوة اليوم: {sess.get('action','-')}\n"
                )
                if m_before is not None and mood_after is not None:
                    diff = mood_after - m_before
                    summary += f"• المزاج: {m_before} ➜ {mood_after} (التغيّر: {diff})\n"

                tg("sendMessage", {
                    "chat_id": chat_id,
                    "text": summary + "\n📌 تقدر تعيد الجلسة بكتابة /cbt متى ما شئت.",
                    "parse_mode": "HTML"
                })
                SESSIONS.pop(chat_id, None)
                return "ok", 200
        # -------- END CBT FLOW --------

        # منطق الردود العام (intents)
        intents = {
            "سلام": "وعليكم السلام ورحمة الله ✨",
            "مرحبا": "أهلًا وسهلًا! كيف أقدر أساعدك؟",
            "تواصل": "تمام، تم تسجيل طلب تواصل ✅",
            "نوم": "جرّب تنام 7–8 ساعات، ونظّم وقت النوم 😴"
        }

        if text.startswith("/start"):
            reply = ("👋 أهلاً بك! أنا <b>عربي سايكو</b>.\n"
                     "اكتب: <code>/cbt</code> لبدء جلسة علاج سلوكي معرفي.\n"
                     "أو جرّب كلمات: نوم، تواصل، سلام… أو /help")
        elif text.startswith("/help"):
            reply = "أرسل كلمة مثل: نوم، تواصل، سلام — أو اكتب /cbt لبدء جلسة قصيرة."
        else:
            reply = next((v for k, v in intents.items() if k in text), None) or \
                    f"تمام 👌 وصلتني: “{text}”"

        # إرسال الرد
        if chat_id and reply:
            tg("sendMessage", {
                "chat_id": chat_id,
                "text": reply,
                "parse_mode": "HTML",
                "reply_to_message_id": msg_id
            })

    except Exception as e:
        log.exception("webhook error: %s", e)

    # نرجّع رد دائمًا
    return "ok", 200

# =====================
# Main (local dev)
# =====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
