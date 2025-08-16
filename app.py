# app.py
import os, logging, json
from flask import Flask, request, jsonify
import requests

# ======================
# إعدادات
# ======================
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN env var")

BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "secret")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # اختياري: رقم شاتك للإشعارات
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")  # اختياري

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho-bot")

# ======================
# مساعدات تيليجرام
# ======================
def tg(method, payload):
    url = f"{BOT_API}/{method}"
    r = requests.post(url, json=payload, timeout=15)
    if r.status_code != 200:
        log.warning("TG error %s: %s", r.status_code, r.text[:200])
    return r

def send(chat_id, text, reply_markup=None, parse_mode="HTML"):
    return tg("sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
        **({"reply_markup": reply_markup} if reply_markup else {})
    })

def reply_kb():
    # لوحة أزرار سفلية دائمة
    return {
        "keyboard": [
            [{"text": "نوم"}, {"text": "حزن"}],
            [{"text": "تنفّس"}, {"text": "تواصل"}],
            [{"text": "مساعدة"}, {"text": "اختبارات"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
        "is_persistent": True
    }

def inline_rows(rows):
    return {"inline_keyboard": rows}

def is_cmd(text, name):
    return text.strip().startswith("/" + name)

# ======================
# بيانات الاختبارات (GAD-7، PHQ-9)
# ======================
ANS = [("أبدًا", 0), ("عدة أيام", 1), ("أكثر من النصف", 2), ("تقريبًا يوميًا", 3)]

G7 = [
    "التوتر/العصبية أو الشعور بالقلق",
    "عدم القدرة على التوقف عن القلق أو السيطرة عليه",
    "الانشغال بالهموم بدرجة كبيرة",
    "صعوبة الاسترخاء",
    "تململ/صعوبة الجلوس بهدوء",
    "الانزعاج بسرعة أو العصبية",
    "الخوف من حدوث شيء سيئ"
]
PHQ9 = [
    "قلة الاهتمام أو المتعة بالقيام بالأشياء",
    "الشعور بالحزن أو الاكتئاب أو اليأس",
    "مشاكل في النوم أو النوم كثيرًا",
    "الإرهاق أو قلة الطاقة",
    "ضعف الشهية أو الإفراط في الأكل",
    "الشعور بتدني تقدير الذات أو الذنب",
    "صعوبة التركيز",
    "الحركة أو الكلام ببطء شديد أو العكس (توتر زائد)",
    "أفكار بأنك ستكون أفضل حالًا لو لم تكن موجودًا"
]

TESTS = {
    "g7": {"name": "مقياس القلق GAD-7", "q": G7},
    "phq": {"name": "مقياس الاكتئاب PHQ-9", "q": PHQ9},
}

# حالة الجلسات البسيطة بالذاكرة
SESS = {}   # { user_id: {"key":"g7","i":0,"score":0} }

def start_test(chat_id, user_id, key):
    data = TESTS[key]
    SESS[user_id] = {"key": key, "i": 0, "score": 0}
    send(chat_id, f"سنبدأ: <b>{data['name']}</b>\nأجب حسب آخر أسبوعين.", reply_markup=reply_kb())
    ask_next(chat_id, user_id)

def ask_next(chat_id, user_id):
    st = SESS.get(user_id)
    if not st: 
        return
    key, i = st["key"], st["i"]
    qs = TESTS[key]["q"]
    if i >= len(qs):
        # انهاء وحساب النتيجة
        score = st["score"]
        total = len(qs)*3
        interpretation = interpret(key, score)
        send(chat_id, f"النتيجة: <b>{score}</b> من {total}\n{interpretation}", reply_markup=reply_kb())
        # تنظيف
        SESS.pop(user_id, None)
        return
    q = qs[i]
    # أزرار قصيرة لتفادي مشكلة طول callback_data
    row1 = [{"text": f"{ANS[0][0]}", "callback_data": f"a0"},
            {"text": f"{ANS[1][0]}", "callback_data": f"a1"}]
    row2 = [{"text": f"{ANS[2][0]}", "callback_data": f"a2"},
            {"text": f"{ANS[3][0]}", "callback_data": f"a3"}]
    send(chat_id, f"س{ i+1 }: {q}", reply_markup=inline_rows([row1, row2]))

def record_answer(chat_id, user_id, a_idx):
    st = SESS.get(user_id)
    if not st:
        return
    score_add = ANS[a_idx][1]
    st["score"] += score_add
    st["i"] += 1
    ask_next(chat_id, user_id)

def interpret(key, score):
    if key == "g7":
        if score <= 4: lvl = "قلق ضئيل"
        elif score <= 9: lvl = "قلق خفيف"
        elif score <= 14: lvl = "قلق متوسط"
        else: lvl = "قلق شديد"
        tips = "جرّب تمارين التنفّس، تقليل الكافيين، وروتين نوم ثابت."
        return f"<b>{lvl}</b>.\nنصيحة: {tips}"
    if key == "phq":
        if score <= 4: lvl = "اكتئاب ضئيل"
        elif score <= 9: lvl = "خفيف"
        elif score <= 14: lvl = "متوسط"
        elif score <= 19: lvl = "متوسط إلى شديد"
        else: lvl = "شديد"
        tips = "نشّط يومك بمهام صغيرة ممتعة + تواصل اجتماعي + جدول نوم."
        return f"<b>{lvl}</b>.\nنصيحة: {tips}"
    return "تم."

def tests_menu(chat_id):
    rows = [
        [{"text": "اختبار القلق (GAD-7)", "callback_data": "t:g7"}],
        [{"text": "اختبار الاكتئاب (PHQ-9)", "callback_data": "t:phq"}],
    ]
    send(chat_id, "اختر اختبارًا:", reply_markup=inline_rows(rows))

# ======================
# محتوى علاجي مبسّط
# ======================
def reply_cbt(chat_id):
    send(chat_id,
         "العلاج السلوكي المعرفي (CBT):\n"
         "1) راقب الفكرة المزعجة.\n2) قيّم الدليل معها/ضدها.\n3) استبدلها بفكرة متوازنة.\n"
         "اكتب لي كلمة: <b>تفكير</b> أو <b>تنفّس</b> لأعطيك خطوات سريعة.",
         reply_markup=reply_kb())

def reply_sleep(chat_id):
    send(chat_id,
         "نصائح النوم:\n• ثبّت وقت النوم والاستيقاظ\n• قلّل من الشاشات قبل النوم\n• تجنّب الكافيين مساءً\n• جرّب تنفّس 4-7-8 قبل السرير.",
         reply_markup=reply_kb())

def reply_sad(chat_id):
    send(chat_id,
         "إذا كنت تشعر بالحزن:\n• افعل نشاطًا صغيرًا ممتعًا الآن\n• تواصل مع شخص مقرّب\n• اكتب 3 أشياء ممتنّ لها اليوم.",
         reply_markup=reply_kb())

def reply_breath(chat_id):
    send(chat_id,
         "تنفّس هدّئ أعصابك الآن:\nاستنشق 4 ثوانٍ – احبس 4 – ازفر 6… كرّر 6 مرات.",
         reply_markup=reply_kb())

def notify_contact(chat_id, message):
    user = message.get("from", {})
    username = user.get("username") or (user.get("first_name","") + " " + user.get("last_name","")).strip() or "مستخدم"
    send(chat_id, "تم تسجيل طلب تواصل ✅ سنرجع لك قريبًا.", reply_markup=reply_kb())
    if ADMIN_CHAT_ID:
        info = (
            "📩 طلب تواصل\n"
            f"الاسم: {username} (id={user.get('id')})\n"
            f"النص: {message.get('text') or ''}"
        )
        tg("sendMessage", {"chat_id": ADMIN_CHAT_ID, "text": info})

# ======================
# ويبهوك
# ======================
@app.route("/", methods=["GET"])
def home():
    data = {
        "app": "Arabi Psycho Telegram Bot",
        "public_url": RENDER_EXTERNAL_URL,
        "status": "ok",
        "webhook": f"/webhook/{WEBHOOK_SECRET} (masked)"
    }
    return jsonify(data)

@app.route("/setwebhook", methods=["GET"])
def set_hook():
    if not RENDER_EXTERNAL_URL:
        return jsonify({"ok": False, "error": "RENDER_EXTERNAL_URL not set"}), 400
    url = f"{RENDER_EXTERNAL_URL}/webhook/{WEBHOOK_SECRET}"
    r = tg("setWebhook", {"url": url})
    return r.json(), r.status_code

@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    update = request.get_json(force=True, silent=True) or {}
    # callback query
    if "callback_query" in update:
        cq = update["callback_query"]
        data = cq.get("data") or ""
        chat_id = cq["message"]["chat"]["id"]
        user_id = cq["from"]["id"]

        # بدء اختبار
        if data.startswith("t:"):
            key = data.split(":",1)[1]
            if key in TESTS:
                start_test(chat_id, user_id, key)
            else:
                send(chat_id, "اختيار غير معروف.", reply_markup=reply_kb())
            return "ok", 200

        # إجابة سؤال (a0..a3)
        if data.startswith("a"):
            try:
                a_idx = int(data[1:])
                if 0 <= a_idx <= 3:
                    record_answer(chat_id, user_id, a_idx)
            except:
                send(chat_id, "إجابة غير صالحة.", reply_markup=reply_kb())
            return "ok", 200

        # غير ذلك
        send(chat_id, "تم.", reply_markup=reply_kb())
        return "ok", 200

    # رسالة عادية
    if "message" in update:
        message = update["message"]
        chat_id = message["chat"]["id"]
        text = (message.get("text") or "").strip()
        low = text.replace("أ", "ا").replace("إ", "ا").replace("آ","ا").strip().lower()

        # أوامر
        if is_cmd(text, "start") or is_cmd(text, "menu"):
            send(chat_id,
                 "مرحبًا! أنا <b>عربي سايكو</b>.\n"
                 "عندي جلسات وأدوات سريعة + اختبارات نفسية.\n"
                 "اكتب /tests لفتح الاختبارات.",
                 reply_markup=reply_kb())
            return "ok", 200

        if is_cmd(text, "tests") or low == "اختبارات":
            tests_menu(chat_id);  return "ok", 200

        if is_cmd(text, "cbt"):
            reply_cbt(chat_id);  return "ok", 200

        if is_cmd(text, "whoami"):
            uid = message.get("from", {}).get("id")
            send(chat_id, f"chat_id: {chat_id}\nuser_id: {uid}")
            return "ok", 200

        # كلمات سريعة
        if low == "نوم":
            reply_sleep(chat_id);  return "ok", 200
        if low == "حزن":
            reply_sad(chat_id);    return "ok", 200
        if low in ["تنفس","تنفّس","تنفس"]:
            reply_breath(chat_id); return "ok", 200
        if low in ["تواصل","تواصل."]:
            notify_contact(chat_id, message);  return "ok", 200
        if low in ["مساعدة","help","/help"]:
            send(chat_id, "الأوامر: /menu /tests /cbt\nوجرّب الأزرار بالأسفل.", reply_markup=reply_kb()); return "ok", 200

        # تلقائي
        send(chat_id, f"تمام 👌 وصلتني: “{text}”", reply_markup=reply_kb())
        return "ok", 200

    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
