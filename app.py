# app.py
import os, logging
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
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # اختياري
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
        log.warning("TG %s: %s", r.status_code, r.text[:250])
    return r

def send(chat_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg("sendMessage", payload)

def reply_kb():
    # لوحة سفلية ثابتة
    return {
        "keyboard": [
            [{"text": "نوم"}, {"text": "حزن"}],
            [{"text": "تنفّس"}, {"text": "تواصل"}],
            [{"text": "اختبارات"}, {"text": "العلاج السلوكي"}],
            [{"text": "مساعدة"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
        "is_persistent": True
    }

def inline_rows(rows):
    return {"inline_keyboard": rows}

def is_cmd(txt, name): return txt.strip().startswith("/"+name)

# ======================
# اختبارات (GAD-7/PHQ-9)
# ======================
ANS = [("أبدًا",0), ("عدة أيام",1), ("أكثر من النصف",2), ("تقريبًا يوميًا",3)]
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
    "الحركة/الكلام ببطء شديد أو العكس (توتر زائد)",
    "أفكار بأنك ستكون أفضل حالًا لو لم تكن موجودًا"
]
TESTS = {"g7":{"name":"مقياس القلق GAD-7","q":G7},
         "phq":{"name":"مقياس الاكتئاب PHQ-9","q":PHQ9}}
SESS = {}  # {uid: {"key":, "i":, "score":}}

def tests_menu(chat_id):
    rows = [
        [{"text":"اختبار القلق (GAD-7)", "callback_data":"t:g7"}],
        [{"text":"اختبار الاكتئاب (PHQ-9)", "callback_data":"t:phq"}],
    ]
    send(chat_id, "اختر اختبارًا:", inline_rows(rows))

def start_test(chat_id, uid, key):
    data = TESTS[key]
    SESS[uid] = {"key":key, "i":0, "score":0}
    send(chat_id, f"سنبدأ: <b>{data['name']}</b>\nأجب حسب آخر أسبوعين.", reply_kb())
    ask_next(chat_id, uid)

def ask_next(chat_id, uid):
    st = SESS.get(uid);  0 if not st else None
    if not st: return
    key, i = st["key"], st["i"]; qs = TESTS[key]["q"]
    if i >= len(qs):
        score = st["score"]; total = len(qs)*3
        send(chat_id, f"النتيجة: <b>{score}</b> من {total}\n{interpret(key,score)}", reply_kb())
        SESS.pop(uid, None); return
    q = qs[i]
    row1 = [{"text":ANS[0][0], "callback_data":"a0"},
            {"text":ANS[1][0], "callback_data":"a1"}]
    row2 = [{"text":ANS[2][0], "callback_data":"a2"},
            {"text":ANS[3][0], "callback_data":"a3"}]
    send(chat_id, f"س{ i+1 }: {q}", inline_rows([row1,row2]))

def record_answer(chat_id, uid, a_idx):
    st = SESS.get(uid);  0 if not st else None
    if not st: return
    st["score"] += ANS[a_idx][1]; st["i"] += 1
    ask_next(chat_id, uid)

def interpret(key, score):
    if key=="g7":
        lvl = "قلق ضئيل" if score<=4 else ("قلق خفيف" if score<=9 else ("قلق متوسط" if score<=14 else "قلق شديد"))
        tips = "جرّب تمارين التنفّس، تقليل الكافيين، وروتين نوم ثابت."
        return f"<b>{lvl}</b>.\nنصيحة: {tips}"
    if key=="phq":
        if score<=4: lvl="ضئيل"
        elif score<=9: lvl="خفيف"
        elif score<=14: lvl="متوسط"
        elif score<=19: lvl="متوسط إلى شديد"
        else: lvl="شديد"
        tips = "نشّط يومك بمهام صغيرة ممتعة + تواصل + جدول نوم."
        return f"<b>اكتئاب {lvl}</b>.\nنصيحة: {tips}"
    return "تم."

# ======================
# قائمة CBT ومحتواها
# ======================
CBT_ITEMS = [
    ("أخطاء التفكير", "c:cd"),
    ("الاجترار والكبت", "c:rum"),
    ("الأسئلة العشرة", "c:q10"),
    ("الاسترخاء", "c:rlx"),
    ("التنشيط السلوكي", "c:ba"),
    ("اليقظة الذهنية", "c:mind"),
    ("حل المشكلات", "c:ps"),
    ("سلوكيات الأمان", "c:safe"),
]

def cbt_menu(chat_id):
    rows=[]
    for i in range(0, len(CBT_ITEMS), 2):
        row=[]
        for title, data in CBT_ITEMS[i:i+2]:
            row.append({"text": title, "callback_data": data})
        rows.append(row)
    send(chat_id, "اختر موضوع العلاج السلوكي:", inline_rows(rows))

def cbt_text(code):
    if code=="cd":
        t1 = ("<b>أخطاء التفكير (الانحيازات المعرفية)</b>\n"
              "أمثلة: التعميم المفرط، الأبيض/الأسود، قراءة الأفكار، التنبؤ بالمستقبل، التهويل، التصفية، يجبّات، التسمية، التخصيص.")
        t2 = ("<b>تمرين 3 خطوات:</b>\n"
              "١) التقط الفكرة السلبية.\n٢) قيّم الدليل معها/ضدها.\n٣) اكتب بديلًا متوازنًا.\n"
              "قاعدة: ليست كل الأفكار حقائق.")
        return [t1, t2]
    if code=="rum":
        return [
            "<b>الاجترار والكبت</b>\nالاجترار = تدوير نفس القلق؛ الكبت يزيده.",
            "خطوات: لاحظ ↙️ سمِّ الفكرة ↙️ حوّل الانتباه لنشاط بسيط (مشي/تنفّس/مهمة 5 دقائق) ↙️ خصّص وقتًا للقلق 15د يوميًا."
        ]
    if code=="q10":
        return [
            "<b>الأسئلة العشرة لتحدي الأفكار</b>",
            "هل لديّ دليل قوي؟ ماذا سأقول لصديقي؟ ما أسوأ/أفضل/أرجح سيناريو؟ ما البدائل؟ هل أعمّم؟ هل أقرأ الأفكار؟ ما تأثير تصديق الفكرة؟ ما الدليل ضدها؟ ما الإغفال؟ هل تفكيري أبيض/أسود؟"
        ]
    if code=="rlx":
        return [
            "<b>الاسترخاء</b>",
            "تنفّس 4-7-8: شهيق 4، حبس 7، زفير 8 × 6 مرات.\n"
            "استرخاء عضلي: شدّ/أرخِ كل مجموعة عضلية 5 ثوانٍ من القدمين حتى الوجه."
        ]
    if code=="ba":
        return [
            "<b>التنشيط السلوكي</b>",
            "اكتب 10 أنشطة صغيرة ممتعة/مفيدة، جدولة نشاطين يوميًا، قاعدة 5 دقائق للبدء، قيّم المزاج قبل/بعد (0-10)."
        ]
    if code=="mind":
        return [
            "<b>اليقظة الذهنية</b>",
            "تمرين 5-4-3-2-1: لاحظ 5 أشياء تراها، 4 تلمسها، 3 تسمعها، 2 تشمّها، 1 تتذوقها.\nتنفّس بانتباه، أعد انتباهك بلطف إذا تشتت."
        ]
    if code=="ps":
        return [
            "<b>حل المشكلات</b>",
            "عرّف المشكلة بدقة → فكّر بحلول متعددة → قيّم الإيجابيات/السلبيات → اختر خطة صغيرة → جرّب → راجع وعدّل."
        ]
    if code=="safe":
        return [
            "<b>سلوكيات الأمان</b>",
            "هي أشياء تقلل القلق مؤقتًا لكنها تُبقيه (تجنّب، اطمئنان متكرر...).\n"
            "جرّب تجارب سلوكية صغيرة لتقليلها تدريجيًا وملاحظة أن القلق يهبط ذاتيًا."
        ]
    return ["تم."]

def cbt_send(chat_id, code):
    for chunk in cbt_text(code):
        send(chat_id, chunk, reply_kb())

# ======================
# ردود مختصرة جاهزة
# ======================
def reply_sleep(chat_id):
    send(chat_id,
         "نصائح النوم:\n• ثبّت وقت النوم والاستيقاظ\n• قلّل الشاشات قبل النوم\n• تجنّب الكافيين مساءً\n• جرّب 4-7-8 قبل السرير.",
         reply_kb())
def reply_sad(chat_id):
    send(chat_id,
         "إذا حزِنْت:\n• نشاط صغير ممتع الآن\n• تواصل مع شخص مقرّب\n• اكتب 3 أشياء ممتنّ لها اليوم.",
         reply_kb())
def reply_breath(chat_id):
    send(chat_id,
         "تنفّس مهدّئ: شهيق 4 ث، احبس 4، زفير 6… كرر 6 مرات.",
         reply_kb())
def notify_contact(chat_id, message):
    user = message.get("from", {})
    username = user.get("username") or (user.get("first_name","")+" "+user.get("last_name","")).strip() or "مستخدم"
    send(chat_id, "تم تسجيل طلب تواصل ✅ سنرجع لك قريبًا.", reply_kb())
    if ADMIN_CHAT_ID:
        info = ("📩 طلب تواصل\n"
                f"الاسم: {username} (id={user.get('id')})\n"
                f"النص: {message.get('text') or ''}")
        tg("sendMessage", {"chat_id": ADMIN_CHAT_ID, "text": info})

# ======================
# ويبهوك
# ======================
@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "app":"Arabi Psycho Telegram Bot",
        "public_url": RENDER_EXTERNAL_URL,
        "status":"ok",
        "webhook": f"/webhook/{WEBHOOK_SECRET} (masked)"
    })

@app.route("/setwebhook", methods=["GET"])
def set_hook():
    if not RENDER_EXTERNAL_URL:
        return jsonify({"ok":False,"error":"RENDER_EXTERNAL_URL not set"}), 400
    url = f"{RENDER_EXTERNAL_URL}/webhook/{WEBHOOK_SECRET}"
    r = tg("setWebhook", {"url": url})
    return r.json(), r.status_code

@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    update = request.get_json(force=True, silent=True) or {}

    # ===== Callback buttons =====
    if "callback_query" in update:
        cq = update["callback_query"]
        data = cq.get("data","")
        chat_id = cq["message"]["chat"]["id"]
        uid = cq["from"]["id"]

        # اختبارات
        if data.startswith("t:"):
            key = data.split(":",1)[1]
            if key in TESTS: start_test(chat_id, uid, key)
            else: send(chat_id, "اختبار غير معروف.", reply_kb())
            return "ok", 200

        if data.startswith("a"):
            try:
                idx = int(data[1:])
                if 0 <= idx <= 3: record_answer(chat_id, uid, idx)
            except: send(chat_id, "إجابة غير صالحة.", reply_kb())
            return "ok", 200

        # CBT
        if data.startswith("c:"):
            code = data.split(":",1)[1]
            cbt_send(chat_id, code);  return "ok", 200

        return "ok", 200

    # ===== Plain messages =====
    if "message" in update:
        msg = update["message"]
        chat_id = msg["chat"]["id"]
        text = (msg.get("text") or "").strip()
        low = (text.replace("أ","ا").replace("إ","ا").replace("آ","ا")).lower()

        # أوامر أساسية
        if is_cmd(text,"start") or is_cmd(text,"menu"):
            send(chat_id,
                 "مرحبًا! أنا <b>عربي سايكو</b>.\n"
                 "عندي جلسات وأدوات سريعة + اختبارات + قائمة CBT.\n"
                 "ابدأ بـ /cbt أو /tests أو استخدم الأزرار بالأسفل.",
                 reply_kb());  return "ok", 200
        if is_cmd(text,"tests") or low=="اختبارات":
            tests_menu(chat_id);  return "ok", 200
        if is_cmd(text,"cbt") or low in ["العلاج السلوكي","العلاج السلوكي المعرفي","العلاج النفسي"]:
            cbt_menu(chat_id);  return "ok", 200
        if is_cmd(text,"whoami"):
            uid = msg.get("from",{}).get("id")
            send(chat_id, f"chat_id: {chat_id}\nuser_id: {uid}");  return "ok", 200

        # كلمات سريعة
        if low=="نوم":  reply_sleep(chat_id);  return "ok", 200
        if low=="حزن":  reply_sad(chat_id);    return "ok", 200
        if low in ["تنفس","تنفّس","تنفس"]: reply_breath(chat_id); return "ok", 200
        if low in ["تواصل","تواصل."]: notify_contact(chat_id, msg); return "ok", 200
        if low in ["مساعدة","help","/help"]:
            send(chat_id, "الأوامر: /menu /tests /cbt\nوجرّب الأزرار بالأسفل.", reply_kb()); return "ok", 200

        # مفاتيح نصية لعنواين CBT مباشرة
        CBT_TRIG = {
            "اخطاء التفكير":"cd","الاجترار":"rum","الكبت":"rum","الاسئلة العشرة":"q10",
            "الاسترخاء":"rlx","التنشيط السلوكي":"ba","اليقظة الذهنية":"mind","حل المشكلات":"ps","سلوكيات الامان":"safe"
        }
        for k, v in CBT_TRIG.items():
            if k in low:
                cbt_send(chat_id, v); return "ok", 200

        # افتراضي
        send(chat_id, f"تمام 👌 وصلتني: “{text}”", reply_kb());  return "ok", 200

    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
