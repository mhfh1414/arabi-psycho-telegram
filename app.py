# app.py — Arabi Psycho Telegram Bot (CBT + Quick Protocols + Tests + Contact)

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

# رقم شات الأدمن (خاص/مجموعة). يقرأ من Environment أو يظل None.
_ADMIN_CHAT_ID_RAW = os.environ.get("ADMIN_CHAT_ID")
try:
    ADMIN_CHAT_ID = int(_ADMIN_CHAT_ID_RAW) if _ADMIN_CHAT_ID_RAW else None
except Exception:
    ADMIN_CHAT_ID = None

# نص يظهر للمستخدم عند طلب "تواصل" (ضع فيه رقمك/واتساب إن رغبت)
ADMIN_CONTACT = os.environ.get("ADMIN_CONTACT") or "تم استلام طلبك ✅ وسنتواصل معك قريبًا."

# =====================
# App & Logging
# =====================
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho-bot")

# جلسات CBT المؤقتة
SESSIONS = {}        # { chat_id: {stage: "...", ...} }

# =====================
# Telegram helpers
# =====================
def tg(method, payload):
    r = requests.post(f"{BOT_API}/{method}", json=payload, timeout=15)
    try:
        return r.json()
    except Exception:
        return {"status_code": r.status_code, "text": r.text}

def send(chat_id, text, reply_to=None, markup=None, parse_html=True):
    payload = {"chat_id": chat_id, "text": text}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if parse_html:
        payload["parse_mode"] = "HTML"
    if markup:
        payload["reply_markup"] = markup
    return tg("sendMessage", payload)

def set_webhook():
    if not RENDER_URL:
        return {"ok": False, "reason": "No public URL (RENDER_EXTERNAL_URL/PUBLIC_URL)"}
    url = f"{RENDER_URL.rstrip('/')}/webhook/{TELEGRAM_BOT_TOKEN}"
    payload = {"url": url}
    if WEBHOOK_SECRET:
        payload["secret_token"] = WEBHOOK_SECRET
    res = tg("setWebhook", payload)
    log.info("setWebhook -> %s", res)
    return res

# =====================
# Keyboards
# =====================
def kb_menu_inline():
    return {
        "inline_keyboard": [
            [{"text": "ابدأ جلسة CBT 🧠", "callback_data": "start_cbt"}],
            [{"text": "تعليمات ℹ️", "callback_data": "help"}],
            [{"text": "إنهاء الجلسة ✖️", "callback_data": "cancel"}],
        ]
    }

def kb_quick_reply():
    return {
        "keyboard": [
            [{"text": "نوم"}, {"text": "حزن"}],
            [{"text": "قلق"}, {"text": "تنفس"}],
            [{"text": "اختبارات"}, {"text": "تواصل"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False
    }

# =====================
# Quick protocols (نوم/حزن/قلق/تنفس)
# =====================
def msg_sleep_protocol():
    return (
        "😴 <b>بروتوكول النوم الليلة</b>\n"
        "1) أوقف الكافيين قبل النوم بـ 6–8 ساعات.\n"
        "2) خفّف الشاشات والإنارة قبل النوم بساعة.\n"
        "3) جرّب تنفّس <b>4-7-8</b> للتهدئة.\n"
        "4) غرفة باردة قليلًا ومظلمة.\n"
        "5) إن لم تنم خلال 20 دقيقة: انهض لنشاط بسيط ثم ارجع.\n"
        "\nاختر خطوة:"
    ), {
        "inline_keyboard": [
            [{"text": "ابدأ تنفّس 4-7-8", "callback_data": "sleep_breathe"}],
            [{"text": "روتين قبل النوم", "callback_data": "sleep_routine"}],
            [{"text": "خطة أسبوع للنوم", "callback_data": "sleep_week"}],
        ]
    }

def msg_sleep_breathe():
    return (
        "🫁 <b>تنفّس 4-7-8</b>\n"
        "ازفر كامل الهواء → شهيق 4 → حبس 7 → زفير 8 (كرّر 4 دورات)."
    )

def msg_sleep_routine():
    return (
        "🛏️ <b>روتين قبل النوم (20–30 دقيقة)</b>\n"
        "إضاءة خافتة، إغلاق الشاشات، وضوء/استحمام دافئ، تمدّد خفيف، كتابة أفكار، قراءة مهدّئة."
    )

def msg_sleep_week():
    return (
        "📆 <b>خطة أسبوع للنوم</b>\n"
        "استيقاظ ثابت + شمس صباحًا، رياضة خفيفة بعد العصر، كافيين قبل العصر فقط، "
        "عشاء خفيف، غرفة بلا شاشات، قيلولة 15–20 دقيقة فقط."
    )

def msg_sadness_protocol():
    return (
        "💙 <b>تفعيل سلوكي للحزن الآن</b>\n"
        "اختر نشاطًا بسيطًا 10–15 دقيقة يعيدك للحركة ثم قيّم مزاجك:\n"
        "• مشي قصير • شاور/وضوء • ترتيب ركن • اتصال بصديق • تنفّس 4×4"
    ), {
        "inline_keyboard": [
            [{"text": "مشي 10 دقائق", "callback_data": "sad_walk"}],
            [{"text": "شاور/وضوء", "callback_data": "sad_shower"}],
            [{"text": "اتصال بصديق", "callback_data": "sad_call"}],
            [{"text": "ترتيب 10 دقائق", "callback_data": "sad_clean"}],
            [{"text": "ابدأ CBT مختصر", "callback_data": "start_cbt"}],
        ]
    }

def msg_sad_action(tag):
    m = {
        "sad_walk": "🚶‍♂️ مشي خفيف 10 دقائق مع تنفّس بطيء.",
        "sad_shower": "🚿 شاور دافئ/وضوء ثم ملابس مريحة وإنارة هادئة.",
        "sad_call": "📞 اتصال 5–10 دقائق بشخص داعم.",
        "sad_clean": "🧹 رتب ركنًا صغيرًا 10 دقائق (سرير/مكتب).",
    }
    return m.get(tag, "تمام. خذ خطوة صغيرة الآن ثم قيّم مزاجك بعدها.")

def msg_anxiety_protocol():
    return (
        "🟡 <b>خطة القلق السريعة</b>\n"
        "1) 5-4-3-2-1: سمِّ 5 ترى/4 تلمس/3 تسمع/2 تشم/1 تتذوق.\n"
        "2) تنفّس 4×4: شهيق4/حبس4/زفير4/راحة4 لدقيقتين.\n"
        "3) اسأل: أسوأ/أفضل/أغلب احتمال؟ وما خطوتي الصغيرة الآن؟"
    )

def msg_breathing_box():
    return (
        "🫁 <b>تنفّس المربّع 4×4</b>\n"
        "شهيق 4 → حبس 4 → زفير 4 → راحة 4 (2–4 دقائق)."
    )

# =========================
# اختبارات نفسية (GAD-7, PHQ-9)
# =========================
TEST_SESSIONS = {}  # {chat_id: {"key": "...", "i": idx, "answers": []}}

def _digit_norm(s: str) -> str:
    trans = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    return s.translate(trans).strip()

TESTS = {
    "gad7": {
        "name": "مقياس القلق GAD-7",
        "questions": [
            "على مدى الأسبوعين الماضيين: كم مرة شعرت بالتوتر أو القلق أو التململ؟",
            "عدم القدرة على إيقاف القلق أو التحكم فيه؟",
            "القلق المفرط بشأن أمور مختلفة؟",
            "صعوبة الاسترخاء؟",
            "التململ بحيث يصعب الجلوس بهدوء؟",
            "الانفعال بسهولة أو العصبية؟",
            "الشعور بالخوف كأن شيئًا سيئًا قد يحدث؟"
        ],
        "options_text": "جاوب برقم: 0=أبدًا، 1=عدة أيام، 2=أكثر من نصف الأيام، 3=تقريبًا كل يوم.",
        "bands": [(0, 4, "خفيف"), (5, 9, "متوسط"), (10, 14, "متوسط إلى شديد"), (15, 21, "شديد")],
        "max": 21
    },
    "phq9": {
        "name": "مقياس الاكتئاب PHQ-9",
        "questions": [
            "قلة الاهتمام أو المتعة في عمل الأشياء؟",
            "الشعور بالإحباط أو الاكتئاب أو اليأس؟",
            "صعوبة في النوم أو النوم بكثرة؟",
            "الشعور بالتعب أو قلة الطاقة؟",
            "ضعف الشهية أو الأكل المفرط؟",
            "الشعور بسوء تجاه نفسك أو أنك فاشل؟",
            "صعوبة التركيز على الأمور (كالقراءة/التلفاز)؟",
            "الحركة أو الكلام ببطء شديد أو العكس بتململ زائد؟",
            "أفكار بأنك قد تؤذي نفسك؟ (إن كانت الإجابة >0 فالرجاء طلب مساعدة فورية)"
        ],
        "options_text": "جاوب برقم: 0=أبدًا، 1=عدة أيام، 2=أكثر من نصف الأيام، 3=تقريبًا كل يوم.",
        "bands": [(0, 4, "ضئيل/طبيعي"), (5, 9, "خفيف"), (10, 14, "متوسط"), (15, 19, "شديد نوعًا ما"), (20, 27, "شديد")],
        "max": 27
    }
}

def start_test(chat_id: int, key: str):
    t = TESTS[key]
    TEST_SESSIONS[chat_id] = {"key": key, "i": 0, "answers": []}
    send(chat_id, f"🧪 بدأنا: {t['name']}\n{t['options_text']}\n\nس1) {t['questions'][0]}\n\nاكتب 0/1/2/3.")

def continue_test(chat_id: int, text: str):
    sess = TEST_SESSIONS.get(chat_id)
    if not sess:
        return False

    key = sess["key"]
    t = TESTS[key]
    normalized = _digit_norm(text)
    if normalized not in {"0", "1", "2", "3"}:
        send(chat_id, f"رجاءً جاوب برقم 0 أو 1 أو 2 أو 3 فقط.\n{t['options_text']}")
        return True

    sess["answers"].append(int(normalized))
    sess["i"] += 1

    if sess["i"] >= len(t["questions"]):
        score = sum(sess["answers"])
        label = None
        for lo, hi, name in t["bands"]:
            if lo <= score <= hi:
                label = name
                break
        label = label or "—"

        msg = [f"📊 نتيجة {t['name']}: {score} / {t['max']} ({label})"]
        if key == "phq9" and sess["answers"][-1] > 0:
            msg.append("⚠️ لاحظت إجابة > 0 على سؤال الأفكار المؤذية. لو هذا ينطبق عليك الآن، فضلاً تواصل فوراً مع مختص/جهة طوارئ.")

        msg.append("\nهذه الأداة للتوعية وليست تشخيصًا. إن أثّرت الأعراض على حياتك اليومية، استشر مختصًا.")
        send(chat_id, "\n".join(msg))

        TEST_SESSIONS.pop(chat_id, None)
        send(chat_id, "تقدر تجرب اختبارات أخرى: /gad7 (قلق) أو /phq9 (اكتئاب) أو /menu")
        return True

    qn = sess["i"]
    send(chat_id, f"س{qn+1}) {t['questions'][qn]}\n\nاكتب 0/1/2/3.")
    return True

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
    # تحقق من توكن المسار
    if token != TELEGRAM_BOT_TOKEN:
        return "forbidden", 403

    # تحقق من السر (اختياري)
    if WEBHOOK_SECRET:
        incoming = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        if incoming != WEBHOOK_SECRET:
            return "forbidden", 403

    try:
        update = request.get_json(silent=True) or {}

        # ---------- Callback Query (أزرار) ----------
        cbq = update.get("callback_query")
        if cbq:
            chat_id = cbq["message"]["chat"]["id"]
            msg_id = cbq["message"]["message_id"]
            data = cbq.get("data", "")
            tg("answerCallbackQuery", {"callback_query_id": cbq["id"]})

            if data == "start_cbt":
                SESSIONS[chat_id] = {"stage": "mood"}
                send(chat_id, "نبدأ CBT 🧠\n١) قيّم مزاجك الآن من 0 إلى 10؟", reply_to=msg_id, parse_html=False)
                return "ok", 200

            if data == "help":
                send(chat_id,
                     "ℹ️ أوامر: /start /cbt /tests /gad7 /phq9 /menu /cancel\n"
                     "وأزرار: نوم/حزن/قلق/تنفس/تواصل.",
                     reply_to=msg_id)
                return "ok", 200

            if data == "cancel":
                SESSIONS.pop(chat_id, None)
                TEST_SESSIONS.pop(chat_id, None)
                send(chat_id, "تم إنهاء الجلسة. اكتب /cbt أو /tests للبدء من جديد.", reply_to=msg_id)
                return "ok", 200

            # نوم
            if data == "sleep_breathe":
                send(chat_id, msg_sleep_breathe(), reply_to=msg_id)
                return "ok", 200
            if data == "sleep_routine":
                send(chat_id, msg_sleep_routine(), reply_to=msg_id)
                return "ok", 200
            if data == "sleep_week":
                send(chat_id, msg_sleep_week(), reply_to=msg_id)
                return "ok", 200

            # حزن
            if data.startswith("sad_"):
                send(chat_id, msg_sad_action(data), reply_to=msg_id)
                return "ok", 200

            return "ok", 200

        # ---------- Message ----------
        message = update.get("message") or update.get("edited_message") or {}
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if not chat_id:
            return "ok", 200

        text = (message.get("text") or "").strip()
        msg_id = message.get("message_id")
        user = message.get("from", {})

        # فاحص أوامر يعمل في الخاص والمجموعات
        cmd = (text or "").split()[0].lower()
        def is_cmd(name):
            return cmd == f"/{name}" or cmd.startswith(f"/{name}@")

        # أداة مساعدة: معرفة رقم الشات/المستخدم
        if is_cmd("whoami"):
            uid = user.get("id")
            send(chat_id, f"chat_id: {chat_id}\nuser_id: {uid}")
            return "ok", 200

        # قائمة/إلغاء
        if is_cmd("menu"):
            send(chat_id, "القائمة الرئيسية:", markup=kb_menu_inline())
            return "ok", 200

        if is_cmd("cancel"):
            SESSIONS.pop(chat_id, None)
            TEST_SESSIONS.pop(chat_id, None)
            send(chat_id, "تم إنهاء أي جلسة نشطة. اكتب /cbt أو /tests للبدء.", reply_to=msg_id)
            return "ok", 200

        # ---------- اختبارات ----------
        if is_cmd("tests") or is_cmd("اختبارات"):
            send(chat_id, "اختر اختبارًا:\n- /gad7 (قلق)\n- /phq9 (اكتئاب)\n- /cancel لإلغاء")
            return "ok", 200

        if is_cmd("gad7"):
            start_test(chat_id, "gad7")
            return "ok", 200

        if is_cmd("phq9"):
            start_test(chat_id, "phq9")
            return "ok", 200

        # أثناء إجراء اختبار، التقاط إجابات 0/1/2/3
        if continue_test(chat_id, text):
            return "ok", 200

        # ---------- CBT Flow ----------
        sess = SESSIONS.get(chat_id)

        if is_cmd("cbt"):
            SESSIONS[chat_id] = {"stage": "mood"}
            send(chat_id, "نبدأ CBT 🧠\n١) قيّم مزاجك الآن من 0 إلى 10؟", reply_to=msg_id, parse_html=False)
            return "ok", 200

        if sess:
            stage = sess["stage"]

            if stage == "mood":
                try:
                    mood = int(text)
                    if not (0 <= mood <= 10):
                        raise ValueError
                    sess["mood_before"] = mood
                    sess["stage"] = "situation"
                    send(chat_id, "٢) صف الموقف باختصار:", reply_to=msg_id)
                except Exception:
                    send(chat_id, "أرسل رقمًا من 0 إلى 10 من فضلك.", reply_to=msg_id)
                return "ok", 200

            if stage == "situation":
                sess["situation"] = text
                sess["stage"] = "thoughts"
                send(chat_id, "٣) ما الأفكار التلقائية التي خطرت لك؟", reply_to=msg_id)
                return "ok", 200

            if stage == "thoughts":
                sess["thoughts"] = text
                sess["stage"] = "evidence_for"
                send(chat_id, "٤) دلائل تؤيد الفكرة:", reply_to=msg_id)
                return "ok", 200

            if stage == "evidence_for":
                sess["evidence_for"] = text
                sess["stage"] = "evidence_against"
                send(chat_id, "٥) دلائل تعارضها:", reply_to=msg_id)
                return "ok", 200

            if stage == "evidence_against":
                sess["evidence_against"] = text
                sess["stage"] = "balanced"
                send(chat_id, "٦) صياغة فكرة بديلة متوازنة:", reply_to=msg_id)
                return "ok", 200

            if stage == "balanced":
                sess["balanced"] = text
                sess["stage"] = "action"
                send(chat_id, "٧) خطوة عملية صغيرة ستقوم بها اليوم:", reply_to=msg_id)
                return "ok", 200

            if stage == "action":
                sess["action"] = text
                sess["stage"] = "wrapup"
                send(chat_id, "٨) قيّم مزاجك الآن (0–10) بعد إعادة التقييم:", reply_to=msg_id)
                return "ok", 200

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
                send(chat_id, "القائمة الرئيسية:", markup=kb_menu_inline())
                return "ok", 200

        # ---------- /start /help ----------
        if is_cmd("start"):
            send(
                chat_id,
                ("👋 أهلاً بك! أنا <b>عربي سايكو</b>.\n"
                 "اكتب: <code>/cbt</code> لبدء جلسة علاج سلوكي معرفي.\n"
                 "استخدم /tests للاختبارات (GAD-7, PHQ-9).\n"
                 "جرّب الأزرار: نوم/حزن/قلق/تنفس/تواصل."),
                markup=kb_quick_reply()
            )
            send(chat_id, "القائمة الرئيسية:", markup=kb_menu_inline())
            return "ok", 200

        if is_cmd("help"):
            send(
                chat_id,
                ("ℹ️ تعليمات سريعة:\n"
                 "• /start — بدء الاستخدام\n"
                 "• /cbt — جلسة علاج سلوكي معرفي\n"
                 "• /tests — قائمة الاختبارات (gad7/phq9)\n"
                 "• /menu — إظهار القائمة\n"
                 "• /cancel — إنهاء الجلسة الحالية")
            )
            return "ok", 200

        # ---------- كلمات سريعة ----------
        low = text.replace("أ", "ا").strip()

        if low in ["اختبارات", "tests"]:
            send(chat_id, "اختر اختبارًا:\n- /gad7 (قلق)\n- /phq9 (اكتئاب)\n- /cancel لإلغاء")
            return "ok", 200

        if low in ["نوم", "نوم."]:
            t, m = msg_sleep_protocol()
            send(chat_id, t, markup=m)
            return "ok", 200

        if low in ["حزن", "حزين", "زعلان"]:
            t, m = msg_sadness_protocol()
            send(chat_id, t, markup=m)
            return "ok", 200

        if low in ["قلق"]:
            send(chat_id, msg_anxiety_protocol())
            return "ok", 200

        if low in ["تنفس", "تنفّس", "تنفس 4x4"]:
            send(chat_id, msg_breathing_box())
            return "ok", 200

        if low in ["مساعدة", "help ar"]:
            send(chat_id, "أرسل: /cbt أو /tests، أو استخدم الأزرار: نوم/حزن/قلق/تنفس. لطلب تواصل اكتب: تواصل.")
            return "ok", 200

        # ---------- طلب تواصل ----------
        if low in ["تواصل", "تواصل."]:
            username = user.get("username") or (user.get("first_name","") + " " + user.get("last_name","")).strip() or "مستخدم"
            send(chat_id, f"تم تسجيل طلب تواصل ✅\n{ADMIN_CONTACT}")
            if ADMIN_CHAT_ID:
                info = (
                    f"📩 طلب تواصل\n"
                    f"من: {username} (user_id={user.get('id')}, chat_id={chat_id})\n"
                    f"النص: {text}"
                )
                send(ADMIN_CHAT_ID, info)
            return "ok", 200

        # ---------- رد افتراضي ----------
        intents = {
            "سلام": "وعليكم السلام ورحمة الله ✨",
            "مرحبا": "أهلًا وسهلًا! كيف أقدر أساعدك؟",
        }
        reply = next((v for k, v in intents.items() if k in text), None) or f"تمام 👌 وصلتني: “{text}”"
        send(chat_id, reply)

    except Exception as e:
        log.exception("webhook error: %s", e)

    return "ok", 200

# =====================
# Main (local dev)
# =====================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
