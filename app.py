# app.py — Arabi Psycho Telegram Bot (Tests + CBT + Therapy + AI Chat)
import os, logging
from flask import Flask, request, jsonify
import requests

# =====================
# Config (بيئة التشغيل)
# =====================
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

WEBHOOK_SECRET      = os.environ.get("WEBHOOK_SECRET", "secret")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # اختياري: تنبيه الإدمن عند "تواصل"

# الذكاء الاصطناعي (متوافق OpenAI)
AI_BASE_URL = (os.environ.get("AI_BASE_URL") or "").rstrip("/")
AI_API_KEY  = os.environ.get("AI_API_KEY", "")
AI_MODEL    = os.environ.get("AI_MODEL", "")     # مثال: "gpt-3.5-turbo" أو "openrouter/auto"

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho-bot")

# ===============
# Telegram utils
# ===============
def tg(method, payload):
    r = requests.post(f"{BOT_API}/{method}", json=payload, timeout=15)
    if r.status_code != 200:
        log.warning("TG %s -> %s | %s", method, r.status_code, r.text[:300])
    return r

def send(chat_id, text, reply_markup=None, parse_mode="HTML"):
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True}
    if reply_markup:
        data["reply_markup"] = reply_markup
    return tg("sendMessage", data)

def inline(rows):
    return {"inline_keyboard": rows}

def reply_kb():
    # لوحة أزرار سفلية ثابتة
    return {
        "keyboard": [
            [{"text":"العلاج السلوكي"}, {"text":"اختبارات"}],
            [{"text":"نوم"}, {"text":"حزن"}],
            [{"text":"تنفّس"}, {"text":"عربي سايكو"}],  # ← الاسم الجديد
            [{"text":"مساعدة"}, {"text":"تواصل"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

def is_cmd(txt, name): return (txt or "").strip().lower().startswith("/"+name)

# =========
# Safety
# =========
CRISIS_WORDS = ["انتحار","اودي نفسي","أؤذي نفسي","اذي نفسي","قتل نفسي","ما ابغى اعيش","ابي اموت"]
def crisis_guard(text):
    low = (text or "")
    # توحيد همزات
    low = low.replace("أ","ا").replace("إ","ا").replace("آ","ا").lower()
    return any(w in low for w in CRISIS_WORDS)

# =============================
# Tests: GAD-7 (قلق) / PHQ-9
# =============================
ANS = [("أبدًا",0), ("عدة أيام",1), ("أكثر من النصف",2), ("تقريبًا يوميًا",3)]
G7 = [
    "التوتر/العصبية أو الشعور بالقلق",
    "عدم القدرة على التوقف عن القلق أو السيطرة عليه",
    "الانشغال بالهموم بدرجة كبيرة",
    "صعوبة الاسترخاء",
    "تململ/صعوبة الجلوس بهدوء",
    "الانزعاج بسرعة أو العصبية",
    "الخوف من حدوث شيء سيئ",
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
    "أفكار بأنك ستكون أفضل حالًا لو لم تكن موجودًا",
]
TESTS = {"g7":{"name":"مقياس القلق GAD-7","q":G7}, "phq":{"name":"مقياس الاكتئاب PHQ-9","q":PHQ9}}
SESS = {}  # اختبارات: {uid: {"key":..., "i":..., "score":...}}

def tests_menu(chat_id):
    send(chat_id, "اختر اختبارًا:", inline([
        [{"text":"اختبار القلق (GAD-7)", "callback_data":"t:g7"}],
        [{"text":"اختبار الاكتئاب (PHQ-9)", "callback_data":"t:phq"}],
    ]))

def start_test(chat_id, uid, key):
    data = TESTS[key]
    SESS[uid] = {"key": key, "i": 0, "score": 0}
    send(chat_id, f"سنبدأ: <b>{data['name']}</b>\nأجب حسب آخر أسبوعين.", reply_kb())
    ask_next(chat_id, uid)

def ask_next(chat_id, uid):
    st = SESS.get(uid)
    if not st: return
    key, i = st["key"], st["i"]; qs = TESTS[key]["q"]
    if i >= len(qs):
        score = st["score"]; total = len(qs)*3
        send(chat_id, f"النتيجة: <b>{score}</b> من {total}\n{interpret(key,score)}", reply_kb())
        SESS.pop(uid, None); return
    q = qs[i]
    send(chat_id, f"س{ i+1 }: {q}", inline([
        [{"text":ANS[0][0], "callback_data":"a0"}, {"text":ANS[1][0], "callback_data":"a1"}],
        [{"text":ANS[2][0], "callback_data":"a2"}, {"text":ANS[3][0], "callback_data":"a3"}],
    ]))

def record_answer(chat_id, uid, ans_idx):
    st = SESS.get(uid)
    if not st: return
    st["score"] += ANS[ans_idx][1]
    st["i"] += 1
    ask_next(chat_id, uid)

def interpret(key, score):
    if key=="g7":
        lvl = "قلق ضئيل" if score<=4 else ("قلق خفيف" if score<=9 else ("قلق متوسط" if score<=14 else "قلق شديد"))
        return f"<b>{lvl}</b>.\nنصيحة: تنفّس ببطء، قلّل الكافيين، وثبّت نومك."
    if key=="phq":
        if score<=4: lvl="ضئيل"
        elif score<=9: lvl="خفيف"
        elif score<=14: lvl="متوسط"
        elif score<=19: lvl="متوسط إلى شديد"
        else: lvl="شديد"
        return f"<b>اكتئاب {lvl}</b>.\nنصيحة: تنشيط سلوكي + تواصل اجتماعي + روتين نوم."
    return "تم."

# ==================
# CBT: بطاقة معلومات
# ==================
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
        pair = [{"text": t, "callback_data": d} for (t,d) in CBT_ITEMS[i:i+2]]
        rows.append(pair)
    send(chat_id, "اختر موضوع العلاج السلوكي:", inline(rows))

def cbt_text(code):
    if code=="cd":
        return [
            "<b>أخطاء التفكير</b>\nالأبيض/الأسود، التعميم، قراءة الأفكار، التنبؤ، التهويل…",
            "خطوات: ١) التقط الفكرة ٢) الدليل معها/ضدها ٣) صياغة متوازنة.",
        ]
    if code=="rum":
        return ["<b>الاجترار والكبت</b>", "لاحظ الفكرة واسمها، خصّص «وقت قلق»، وحوّل الانتباه لنشاط بسيط."]
    if code=="q10":
        return ["<b>الأسئلة العشرة</b>", "الدليل؟ البدائل؟ لو صديق مكاني؟ أسوأ/أفضل/أرجح؟ هل أعمّم/أقرأ أفكار؟ ماذا أتجاهل؟"]
    if code=="rlx":
        return ["<b>الاسترخاء</b>", "تنفّس 4-7-8 ×6. شدّ/إرخِ العضلات من القدم للرأس."]
    if code=="ba":
        return ["<b>التنشيط السلوكي</b>", "نشاطان صغيران يوميًا (ممتع/نافع) + قاعدة 5 دقائق + تقييم مزاج قبل/بعد."]
    if code=="mind":
        return ["<b>اليقظة الذهنية</b>", "تمرين 5-4-3-2-1 للحواس. ارجع للحاضر بدون حكم."]
    if code=="ps":
        return ["<b>حل المشكلات</b>", "عرّف المشكلة → بدائل → خطة صغيرة SMART → جرّب → قيّم."]
    if code=="safe":
        return ["<b>سلوكيات الأمان</b>", "قلّل الطمأنة/التجنب تدريجيًا مع تعرّض آمن."]
    return ["تم."]

def cbt_send(chat_id, code):
    for t in cbt_text(code):
        send(chat_id, t, reply_kb())

# ==========================
# Therapy quick suggestions
# ==========================
THERAPY = {
    "sleep": (
        "<b>بروتوكول النوم (مختصر)</b>\n"
        "• ثبّت الاستيقاظ يوميًا\n• قلّل الشاشات مساءً\n• طقوس تهدئة 30–45د\n"
        "• سرير=نوم فقط\n• إن لم تنم خلال 20د اخرج لنشاط هادئ وارجع."
    ),
    "sad": (
        "<b>علاج الحزن (تنشيط سلوكي)</b>\n"
        "• 3 أنشطة صغيرة اليوم (ممتع/نافع/اجتماعي)\n• ابدأ بـ10–20د\n• قيّم المزاج قبل/بعد."
    ),
    "dep": (
        "<b>إرشادات للاكتئاب الخفيف-المتوسط</b>\n"
        "تنشيط سلوكي + تواصل اجتماعي + نوم منتظم + تعرّض تدريجي لما تتجنّبه."
    ),
    "breath": (
        "<b>تمرين تنفّس سريع</b>\n"
        "شهيق 4 ثوانٍ – حبس 4 – زفير 6. كرّر 10 مرات ببطء."
    ),
    "help": (
        "### بعض النصائح العامة التي قد تساعدك:\n"
        "— **الالتزام بالعلاج**: الاستمرار مهم.\n"
        "— **المراقبة الذاتية**: راقب أفكارك ومشاعرك.\n"
        "— **الدعم الاجتماعي**: تحدّث مع شخص موثوق.\n"
        "— **الروتين الصحي**: نوم وغذاء ونشاط بسيط.\n"
        "لو ظهرت أفكار لإيذاء النفس: تواصل مع الطوارئ فورًا."
    ),
}

# ===========================
# AI Chat (OpenAI-compatible)
# ===========================
def ai_ready():
    return bool(AI_BASE_URL and AI_API_KEY and AI_MODEL)

AI_SESS = {}  # {uid: [messages]}

SYSTEM_PROMPT = (
    "أنت مساعد نفسي تعليمي باللغة العربية. قدّم دعمًا عامًّا وتقنيات CBT البسيطة، "
    "وتذكيرًا بأنك لست بديلاً عن مختص. لا تُصدر تشخيصًا. إن ظهر خطر على السلامة "
    "فوجّه للمساعدة الفورية."
)

def ai_call(messages):
    # POST {AI_BASE_URL}/v1/chat/completions
    url = AI_BASE_URL + "/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    body = {"model": AI_MODEL, "messages": messages, "temperature": 0.4, "max_tokens": 600}
    r = requests.post(url, headers=headers, json=body, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"AI {r.status_code}: {r.text[:300]}")
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

def ai_start(chat_id, uid):
    if not ai_ready():
        send(chat_id,
             "ميزة الذكاء الاصطناعي غير مفعّلة.\n"
             "أضف القيم في Render: AI_BASE_URL / AI_API_KEY / AI_MODEL ثم أعد النشر.",
             reply_kb()); return
    AI_SESS[uid] = [{"role":"system","content": SYSTEM_PROMPT}]
    send(chat_id,
         "بدأنا جلسة <b>عربي سايكو</b> 🤖\n"
         "اكتب سؤالك عن النوم/القلق/CBT…\n"
         "لإنهائها: اكتب <code>انهاء</code>.",
         reply_kb())

def ai_handle(chat_id, uid, user_text):
    if crisis_guard(user_text):
        send(chat_id,
             "أقدّر شعورك، وسلامتك أهم شيء الآن.\n"
             "لو تراودك أفكار لإيذاء نفسك، اطلب مساعدة فورية من الطوارئ/رقم بلدك.\n"
             "للتهدئة الآن: تنفّس 4-4-6 ×10 وابق مع شخص تثق به.",
             reply_kb()); return
    msgs = AI_SESS.get(uid) or [{"role":"system","content": SYSTEM_PROMPT}]
    msgs = msgs[-16:]
    msgs.append({"role":"user","content": user_text})
    try:
        reply = ai_call(msgs)
    except Exception as e:
        send(chat_id, f"تعذّر الاتصال بالذكاء الاصطناعي.\n{e}", reply_kb()); return
    msgs.append({"role":"assistant","content": reply})
    AI_SESS[uid] = msgs[-18:]
    send(chat_id, reply, reply_kb())

def ai_end(chat_id, uid):
    AI_SESS.pop(uid, None)
    send(chat_id, "تم إنهاء جلسة عربي سايكو ✅", reply_kb())

# =========
# Routes
# =========
@app.get("/")
def home():
    return jsonify({
        "app": "Arabi Psycho Telegram Bot",
        "public_url": RENDER_EXTERNAL_URL,
        "webhook": f"/webhook/{WEBHOOK_SECRET[:3]}*****",
        "ai_ready": ai_ready()
    })

@app.get("/setwebhook")
def set_hook():
    if not RENDER_EXTERNAL_URL:
        return jsonify({"ok": False, "error": "RENDER_EXTERNAL_URL not set"}), 400
    url = f"{RENDER_EXTERNAL_URL}/webhook/{WEBHOOK_SECRET}"
    res = requests.post(f"{BOT_API}/setWebhook", json={"url": url}, timeout=15)
    return res.json(), res.status_code

@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    upd = request.get_json(force=True, silent=True) or {}

    # ===== Callback buttons =====
    if "callback_query" in upd:
        cq = upd["callback_query"]; data = cq.get("data","")
        chat_id = cq["message"]["chat"]["id"]; uid = cq["from"]["id"]

        # اختبارات
        if data.startswith("t:"):
            key = data.split(":",1)[1]
            if key in TESTS: start_test(chat_id, uid, key)
            else: send(chat_id, "اختبار غير معروف.", reply_kb())
            return "ok", 200

        # إجابة اختبار
        if data.startswith("a"):
            try:
                idx = int(data[1:])
                if 0 <= idx <= 3: record_answer(chat_id, uid, idx)
            except: send(chat_id, "إجابة غير صالحة.", reply_kb())
            return "ok", 200

        # بطاقات CBT
        if data.startswith("c:"):
            code = data.split(":",1)[1]
            cbt_send(chat_id, code);  return "ok", 200

        return "ok", 200

    # ===== Messages =====
    msg = upd.get("message") or upd.get("edited_message") or {}
    if not msg: return "ok", 200

    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    low  = (text.replace("أ","ا").replace("إ","ا").replace("آ","ا")).lower()
    uid  = msg.get("from", {}).get("id")
    user = msg.get("from", {})
    username = user.get("username") or (user.get("first_name","") + " " + user.get("last_name","")).strip() or "مستخدم"

    # أزمة سلامة؟
    if crisis_guard(text):
        send(chat_id,
             "سلامتك أولًا. لو عندك أفكار لإيذاء نفسك فاتصل بالطوارئ فورًا أو تواصل مع شخص موثوق قريب منك.\n"
             "للتهدئة الآن: تنفّس ببطء (4-4-6) وابقَ مع أحد.",
             reply_kb());  return "ok", 200

    # أوامر أساسية
    if is_cmd(text, "start"):
        send(chat_id,
             "👋 أهلاً بك! أنا <b>عربي سايكو</b>.\n"
             "القائمة السفلية فيها: اختبارات، العلاج السلوكي، نوم، حزن، تنفّس، عربي سايكو…\n"
             "• /tests للاختبارات • /cbt للعلاج السلوكي • /menu لعرض الأزرار • /help للمساعدة",
             reply_kb()); return "ok", 200

    if is_cmd(text, "help"):
        send(chat_id,
             "اكتب كلمة مثل: <b>اختبارات</b>، <b>العلاج السلوكي</b>، <b>نوم</b>، <b>حزن</b>، <b>تنفّس</b>، "
             "<b>عربي سايكو</b> لبدء محادثة ذكية.\n"
             "أوامر: /start /help /menu /tests /cbt /whoami /ai_diag",
             reply_kb()); return "ok", 200

    if is_cmd(text, "menu"):
        send(chat_id, "القائمة:", reply_kb()); return "ok", 200

    if is_cmd(text, "tests"): tests_menu(chat_id); return "ok", 200
    if is_cmd(text, "cbt"):   cbt_menu(chat_id);   return "ok", 200

    if is_cmd(text, "whoami"):
        send(chat_id, f"chat_id: <code>{chat_id}</code>\nuser_id: <code>{uid}</code>", reply_kb())
        return "ok", 200

    if is_cmd(text, "ai_diag"):
        send(chat_id, f"ai_ready={ai_ready()}\nBASE={bool(AI_BASE_URL)} KEY={bool(AI_API_KEY)}\nMODEL={AI_MODEL or '-'}")
        return "ok", 200

    # جلسة الذكاء مفعلة؟
    if uid in AI_SESS and low not in ["/end","انهاء","انهائها","انهاء الجلسه","انهاء الجلسة"]:
        ai_handle(chat_id, uid, text); return "ok", 200
    if low in ["/end","انهاء","انهائها","انهاء الجلسه","انهاء الجلسة"]:
        ai_end(chat_id, uid); return "ok", 200

    # اختصارات الأزرار/الكلمات
    if low in ["اختبارات","اختبار","tests"]:
        tests_menu(chat_id); return "ok", 200

    if low in ["العلاج السلوكي","cbt","علاج سلوكي"]:
        cbt_menu(chat_id); return "ok", 200

    if low in ["نوم"]:
        send(chat_id, THERAPY["sleep"], reply_kb()); return "ok", 200

    if low in ["حزن"]:
        send(chat_id, THERAPY["sad"], reply_kb()); return "ok", 200

    if low in ["اكتئاب","اكتئاب؟","الاكتئاب"]:
        send(chat_id, THERAPY["dep"], reply_kb()); return "ok", 200

    if low in ["تنفس","تنفّس","تنفس؟"]:
        send(chat_id, THERAPY["breath"], reply_kb()); return "ok", 200

    # بدء عربي سايكو (الذكاء)
    if low in ["عربي سايكو","سايكو","روبوت","بوت","ذكاء","ذكاء اصطناعي","/ai","/chat"]:
        ai_start(chat_id, uid); return "ok", 200

    # طلب تواصل (تنبيه للإدمن)
    if low in ["تواصل","تواصل.","تواصل!"]:
        send(chat_id, "تم تسجيل طلب تواصل ✅ سنرجع لك قريبًا.", reply_kb())
        if ADMIN_CHAT_ID:
            info = (
                f"📩 طلب تواصل\n"
                f"من: {username} (user_id={uid})\n"
                f"chat_id: {chat_id}\n"
                f"نصّه: {text}"
            )
            send(ADMIN_CHAT_ID, info)
        return "ok", 200

    if low in ["مساعدة","help","/help"]:
        send(chat_id, THERAPY["help"], reply_kb()); return "ok", 200

    # افتراضي: رد بسيط/إيكو
    send(chat_id, f"تمام 👌 وصلتني: “{text}”\nاكتب: <b>عربي سايكو</b> لبدء محادثة ذكية، أو <b>العلاج السلوكي</b>، أو <b>اختبارات</b>.", reply_kb())
    return "ok", 200


# ==========
# Main (local)
# ==========
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
