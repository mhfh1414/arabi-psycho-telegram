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
# Helpers
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

def kb_menu():
    return {
        "inline_keyboard": [
            [{"text": "ابدأ جلسة CBT 🧠", "callback_data": "start_cbt"}],
            [{"text": "تعليمات ℹ️", "callback_data": "help"}],
            [{"text": "إنهاء الجلسة ✖️", "callback_data": "cancel"}],
        ]
    }

def send(chat_id, text, reply_to=None, markup=None, parse_html=True):
    payload = {"chat_id": chat_id, "text": text}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if parse_html:
        payload["parse_mode"] = "HTML"
    if markup:
        payload["reply_markup"] = markup
    return tg("sendMessage", payload)

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
    # تحقق من التوكن في عنوان المسار
    if token != TELEGRAM_BOT_TOKEN:
        return "forbidden", 403

    # تحقق من السر (اختياري)
    if WEBHOOK_SECRET:
        incoming = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if incoming != WEBHOOK_SECRET:
            return "forbidden", 403

    try:
        update = request.get_json(silent=True) or {}

        # ========= Callback Query (أزرار) =========
        cbq = update.get("callback_query")
        if cbq:
            chat_id = cbq["message"]["chat"]["id"]
            msg_id = cbq["message"]["message_id"]
            data = cbq.get("data")
            tg("answerCallbackQuery", {"callback_query_id": cbq["id"]})

            if data == "start_cbt":
                SESSIONS[chat_id] = {"stage": "mood"}
                send(chat_id,
                     "نبدأ جلسة علاج سلوكي معرفي قصيرة 🧠\n"
                     "١) قيّم مزاجك الآن من 0 إلى 10؟",
                     reply_to=msg_id, parse_html=False)
                return "ok", 200

            if data == "help":
                send(chat_id,
                     "ℹ️ تعليمات سريعة:\n"
                     "• /start — بدء الاستخدام\n"
                     "• /cbt — جلسة علاج سلوكي معرفي قصيرة\n"
                     "• /menu — إظهار القائمة\n"
                     "• /cancel — إنهاء الجلسة الحالية\n"
                     "• كلمات مفيدة: سلام، نوم، تواصل",
                     reply_to=msg_id)
                return "ok", 200

            if data == "cancel":
                SESSIONS.pop(chat_id, None)
                send(chat_id, "تم إنهاء الجلسة الحالية. تقدر تبدأ من جديد بـ /cbt أو من القائمة.", reply_to=msg_id)
                return "ok", 200

            return "ok", 200

        # ========= Message =========
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        text = (message.get("text") or "").strip()
        msg_id = message.get("message_id")

        if not chat_id:
            return "ok", 200

        # ---------- أوامر سريعة ----------
        if text == "/menu":
            send(chat_id, "القائمة الرئيسية:", markup=kb_menu())
            return "ok", 200

        if text == "/cancel":
            SESSIONS.pop(chat_id, None)
            send(chat_id, "تم إنهاء الجلسة الحالية. اكتب /cbt للبدء من جديد.", reply_to=msg_id)
            return "ok", 200

        # ---------- CBT FLOW ----------
        sess = SESSIONS.get(chat_id)

        # بدء جلسة CBT
        if text == "/cbt":
            SESSIONS[chat_id] = {"stage": "mood"}
            send(chat_id,
                 "نبدأ جلسة علاج سلوكي معرفي قصيرة 🧠\n"
                 "١) قيّم مزاجك الآن من 0 إلى 10؟",
                 reply_to=msg_id, parse_html=False)
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
                    send(chat_id, "٢) صف الموقف الذي حصل باختصار:", reply_to=msg_id)
                except Exception:
                    send(chat_id, "أرسل رقمًا من 0 إلى 10 من فضلك.", reply_to=msg_id)
                return "ok", 200

            # ٢) الموقف
            if stage == "situation":
                sess["situation"] = text
                sess["stage"] = "thoughts"
                send(chat_id, "٣) ما هي الأفكار التلقائية التي خطرت لك؟", reply_to=msg_id)
                return "ok", 200

            # ٣) الأفكار
            if stage == "thoughts":
                sess["thoughts"] = text
                sess["stage"] = "evidence_for"
                send(chat_id, "٤) ما الدلائل التي تؤيد هذه الفكرة؟", reply_to=msg_id)
                return "ok", 200

            # ٤) أدلة مؤيدة
            if stage == "evidence_for":
                sess["evidence_for"] = text
                sess["stage"] = "evidence_against"
                send(chat_id, "٥) وما الدلائل التي تعارضها؟", reply_to=msg_id)
                return "ok", 200

            # ٥) أدلة معارضة
            if stage == "evidence_against":
                sess["evidence_against"] = text
                sess["stage"] = "balanced"
                send(chat_id, "٦) جرّب صياغة فكرة بديلة متوازنة:", reply_to=msg_id)
                return "ok", 200

            # ٦) الفكرة المتوازنة
            if stage == "balanced":
                sess["balanced"] = text
                sess["stage"] = "action"
                send(chat_id, "٧) اختر خطوة عملية صغيرة ستقوم بها اليوم (Action):", reply_to=msg_id)
                return "ok", 200

            # ٧) الخطة
            if stage == "action":
                sess["action"] = text
                sess["stage"] = "wrapup"
                send(chat_id, "٨) قيّم مزاجك الآن (0–10) بعد إعادة التقييم:", reply_to=msg_id)
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

                send(chat_id, summary + "\n📌 تقدر تعيد الجلسة بكتابة /cbt متى ما شئت.")
                SESSIONS.pop(chat_id, None)
                send(chat_id, "القائمة الرئيسية:", markup=kb_menu())
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
            send(
                chat_id,
                ("👋 أهلاً بك! أنا <b>عربي سايكو</b>.\n"
                 "اكتب: <code>/cbt</code> لبدء جلسة علاج سلوكي معرفي.\n"
                 "جرّب أيضًا /help أو اضغط الأزرار بالأسفل."),
                markup=kb_menu()
            )
        elif text.startswith("/help"):
            send(
                chat_id,
                ("ℹ️ تعليمات سريعة:\n"
                 "• /start — بدء الاستخدام\n"
                 "• /cbt — جلسة علاج سلوكي معرفي قصيرة\n"
                 "• /menu — إظهار القائمة\n"
                 "• /cancel — إنهاء الجلسة الحالية\n"
                 "• كلمات مفيدة: سلام، نوم، تواصل")
            )
        else:
            reply = next((v for k, v in intents.items() if k in text), None) or \
                    f"تمام 👌 وصلتني: “{text}”"
            send(chat_id, reply)

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
