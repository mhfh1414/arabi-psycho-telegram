# app.py — Arabi Psycho Telegram Bot
# (Tests + CBT + Quick Therapy + Optional AI chat)
import os, logging
from flask import Flask, request, jsonify
import requests

# ========= Config =========
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN env var")

BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

WEBHOOK_SECRET      = os.environ.get("WEBHOOK_SECRET", "secret")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
ADMIN_CHAT_ID       = os.environ.get("ADMIN_CHAT_ID")      # اختياري: تنبيه طلبات تواصل
CONTACT_PHONE       = os.environ.get("CONTACT_PHONE")      # اختياري: رقمك لرسالة المساعدة

# ذكاء اصطناعي (API متوافق مع OpenAI) — اختياري
AI_BASE_URL = os.environ.get("AI_BASE_URL", "").rstrip("/")
AI_API_KEY  = os.environ.get("AI_API_KEY", "")
AI_MODEL    = os.environ.get("AI_MODEL", "")               # مثال: openrouter/auto أو gpt-4o-mini

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho-bot")

# ========= Telegram helpers =========
def tg(method, payload):
    r = requests.post(f"{BOT_API}/{method}", json=payload, timeout=20)
    if r.status_code != 200:
        log.warning("TG %s -> %s | %s", method, r.status_code, r.text[:300])
    return r

def send(chat_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {
        "chat_id": chat_id, "text": text, "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    return tg("sendMessage", payload)

def inline(rows):
    """Inline keyboard"""
    return {"inline_keyboard": rows}

def reply_kb():
    """القائمة السفلية الثابتة"""
    return {
        "keyboard": [
            [{"text":"العلاج السلوكي"}, {"text":"اختبارات"}],
            [{"text":"نوم"}, {"text":"حزن"}],
            [{"text":"تنفّس"}, {"text":"اكتئاب"}],
            [{"text":"ذكاء اصطناعي"}, {"text":"تواصل"}],
            [{"text":"مساعدة"}],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
        "is_persistent": True
    }

def is_cmd(txt, name):
    return (txt or "").strip().lower().startswith("/" + name)

def norm(s):
    return (s or "").replace("أ","ا").replace("إ","ا").replace("آ","ا").strip().lower()

# ========= Safety (بسيط) =========
CRISIS_WORDS = ["انتحار","اذي نفسي","ااذي نفسي","أؤذي نفسي","اوقتل نفسي","ما ابغى اعيش","ماابي اعيش"]
def crisis_guard(text):
    low = norm(text)
    return any(w in low for w in CRISIS_WORDS)

# ========= Tests (GAD-7 / PHQ-9) =========
ANS = [("أبدًا",0), ("عدة أيام",1), ("أكثر من النصف",2), ("تقريبًا يوميًا",3)]

G7 = [
    "التوتر/العصبية أو الشعور بالقلق",
    "عدم القدرة على إيقاف القلق أو السيطرة عليه",
    "الانشغال بالهموم بدرجة كبيرة",
    "صعوبة الاسترخاء",
    "تململ/صعوبة الجلوس بهدوء",
    "الانزعاج بسرعة أو العصبية",
    "الخوف من أن شيئًا سيئًا قد يحدث",
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

TESTS = {"g7":{"name":"مقياس القلق GAD-7","q":G7},
         "phq":{"name":"مقياس الاكتئاب PHQ-9","q":PHQ9}}

SESS = {}  # {uid: {"key":, "i":, "score":}}

def tests_menu(chat_id):
    send(chat_id, "اختر اختبارًا:", inline([
        [{"text":"اختبار القلق (GAD-7)",   "callback_data":"t:g7"}],
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
    key, i = st["key"], st["i"]
    qs = TESTS[key]["q"]
    if i >= len(qs):
        score = st["score"]
        total = len(qs)*3
        send(chat_id, f"النتيجة: <b>{score}</b> من {total}\n{interpret(key,score)}", reply_kb())
        SESS.pop(uid, None)
        return
    q = qs[i]
    send(chat_id, f"س{ i+1 }: {q}", inline([
        [{"text":ANS[0][0], "callback_data":"a0"},
         {"text":ANS[1][0], "callback_data":"a1"}],
        [{"text":ANS[2][0], "callback_data":"a2"},
         {"text":ANS[3][0], "callback_data":"a3"}],
    ]))

def record_answer(chat_id, uid, ans_idx):
    st = SESS.get(uid)
    if not st: return
    st["score"] += ANS[ans_idx][1]
    st["i"] += 1
    ask_next(chat_id, uid)

def interpret(key, score):
    if key == "g7":
        lvl = "قلق ضئيل" if score<=4 else ("قلق خفيف" if score<=9
              else ("قلق متوسط" if score<=14 else "قلق شديد"))
        return f"<b>{lvl}</b>.\nنصيحة: تنفّس ببطء، قلّل الكافيين، وثبّت مواعيد النوم."
    if key == "phq":
        if score<=4: lvl="ضئيل"
        elif score<=9: lvl="خفيف"
        elif score<=14: lvl="متوسط"
        elif score<=19: lvl="متوسط إلى شديد"
        else: lvl="شديد"
        return f"<b>اكتئاب {lvl}</b>.\nنصيحة: تنشيط سلوكي + تواصل اجتماعي + روتين نوم ثابت."
    return "تم."

# ========= CBT (inline) =========
CBT_ITEMS = [
    ("أخطاء التفكير",    "c:cd"),
    ("الاجترار والكبت",   "c:rum"),
    ("الأسئلة العشرة",    "c:q10"),
    ("الاسترخاء",        "c:rlx"),
    ("التنشيط السلوكي",  "c:ba"),
    ("اليقظة الذهنية",    "c:mind"),
    ("حل المشكلات",      "c:ps"),
    ("سلوكيات الأمان",   "c:safe"),
]

def cbt_menu(chat_id):
    rows = []
    for i in range(0, len(CBT_ITEMS), 2):
        pair = [{"text":t, "callback_data":d} for (t,d) in CBT_ITEMS[i:i+2]]
        rows.append(pair)
    send(chat_id, "اختر موضوع العلاج السلوكي:", inline(rows))

def cbt_text(code):
    if code=="cd":
        return [
            "<b>أخطاء التفكير</b>\nالأبيض/الأسود، التعميم، قراءة الأفكار، التنبؤ، التهويل…",
            "الخطوات: ١) التقط الفكرة ٢) الدليل معها/ضدها ٣) صياغة متوازنة واقعية."
        ]
    if code=="rum":
        return ["<b>الاجترار والكبت</b>",
                "لاحظ الفكرة وسمّها، خصّص «وقت قلق»، وحوّل انتباهك لنشاط بسيط حاضر."]
    if code=="q10":
        return ["<b>الأسئلة العشرة</b>",
                "ما الدليل؟ البدائل؟ لو صديق مكاني؟ أسوأ/أفضل/أرجح؟ هل أعمّم أو أقرأ أفكار؟ ماذا أتجاهل؟"]
    if code=="rlx":
        return ["<b>الاسترخاء</b>", "تنفّس 4-7-8 ×6. شدّ/إرخِ العضلات من القدم للرأس."]
    if code=="ba":
        return ["<b>التنشيط السلوكي</b>", "نشاطان صغيران يوميًا (ممتع/نافع) + قاعدة 5 دقائق + تقييم مزاج قبل/بعد."]
    if code=="mind":
        return ["<b>اليقظة الذهنية</b>", "تمرين 5-4-3-2-1 للحواس. ارجع للحاضر دون حكم."]
    if code=="ps":
        return ["<b>حل المشكلات</b>", "عرّف المشكلة → بدائل → خطة صغيرة SMART → جرّب → قيّم."]
    if code=="safe":
        return ["<b>سلوكيات الأمان</b>", "قلّل الطمأنة/التجنب تدريجيًا مع تعرّض آمن ومدروس."]
    return ["تم."]

def cbt_send(chat_id, code):
    for t in cbt_text(code):
        send(chat_id, t, reply_kb())

# ========= Therapy quick tips =========
THERAPY = {
    "نوم": (
        "<b>بروتوكول النوم (مختصر)</b>\n"
        "• ثبّت الاستيقاظ يوميًا\n"
        "• قلّل الشاشات مساءً\n"
        "• طقوس تهدئة 30–45د\n"
        "• سرير = نوم فقط\n"
        "• لو ما نمت خلال 20د: اخرج لنشاط هادئ وارجع."
    ),
    "حزن": (
        "<b>علاج الحزن (تنشيط سلوكي)</b>\n"
        "• 3 أنشطة صغيرة اليوم (ممتع/نافع/اجتماعي)\n"
        "• ابدأ بـ10–20د\n"
        "• قيّم المزاج قبل/بعد."
    ),
    "اكتئاب": (
        "<b>خطة يومية قصيرة للاكتئاب</b>\n"
        "• روتين صباحي بسيط + نور الشمس 10د\n"
        "• جدول نشاط ممتع/نافع\n"
        "• حركة خفيفة 10–15د."
    ),
    "تنفّس": (
        "<b>تمرين التنفّس 4-4-6</b>\n"
        "شهيق 4 ثوانٍ — ثبات 4 — زفير 6 ×10 مرات ببطء."
    ),
}

# ========= AI chat =========
AI_SESS = {}  # {uid: [messages...]}

SYSTEM_PROMPT = (
    "أنت مساعد نفسي تثقيفي بالعربية. قدّم دعمًا وتعليمات CBT بسيطة، "
    "وانصح بطلب مساعدة فورية عند وجود خطر إيذاء النفس أو الآخرين. لا تقدّم تشخيصًا."
)

def ai_ready():
    return bool(AI_BASE_URL and AI_API_KEY and AI_MODEL)

def ai_call(messages):
    """POST {AI_BASE_URL}/v1/chat/completions (شكل متوافق مع OpenAI)"""
    url = AI_BASE_URL + "/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    body = {"model": AI_MODEL, "messages": messages, "temperature": 0.4, "max_tokens": 600}
    r = requests.post(url, headers=headers, json=body, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

def ai_start(chat_id, uid):
    if not ai_ready():
        send(chat_id,
             "ميزة الذكاء الاصطناعي غير مفعّلة.\n"
             "أضف المتغيرات: AI_BASE_URL / AI_API_KEY / AI_MODEL ثم أعد النشر.",
             reply_kb())
        return
    AI_SESS[uid] = [{"role":"system","content": SYSTEM_PROMPT}]
    send(chat_id, "بدأنا جلسة <b>محادثة ذكية</b> 🤖\nاكتب سؤالك…\nلإنهائها: اكتب <code>انهاء</code>.",
         reply_kb())

def ai_handle(chat_id, uid, user_text):
    if crisis_guard(user_text):
        send(chat_id,
             "أقدّر شعورك، وسلامتك أهم شيء الآن.\n"
             "لو تراودك أفكار لإيذاء نفسك، اطلب مساعدة فورية من الطوارئ أو من تثق به.",
             reply_kb())
        return
    msgs = AI_SESS.get(uid) or [{"role":"system","content": SYSTEM_PROMPT}]
    msgs = msgs[-16:]
    msgs.append({"role":"user","content": user_text})
    try:
        reply = ai_call(msgs)
    except Exception as e:
        send(chat_id, f"تعذّر الاتصال بالذكاء الاصطناعي.\n{e}", reply_kb())
        return
    msgs.append({"role":"assistant","content": reply})
    AI_SESS[uid] = msgs[-18:]
    send(chat_id, reply, reply_kb())

def ai_end(chat_id, uid):
    AI_SESS.pop(uid, None)
    send(chat_id, "تم إنهاء جلسة الذكاء الاصطناعي ✅", reply_kb())

# ========= Routes =========
@app.get("/")
def home():
    return jsonify({
        "app": "Arabi Psycho Telegram Bot",
        "public_url": RENDER_EXTERNAL_URL or None,
        "webhook": f"/webhook/{WEBHOOK_SECRET[:3]}*****",
        "ai_ready": ai_ready()
    })

@app.get("/setwebhook")
def setwebhook():
    if not RENDER_EXTERNAL_URL:
        return jsonify({"ok": False, "error": "RENDER_EXTERNAL_URL not set"}), 400
    url = f"{RENDER_EXTERNAL_URL}/webhook/{WEBHOOK_SECRET}"
    res = requests.post(f"{BOT_API}/setWebhook", json={"url": url}, timeout=15)
    try:
        return res.json(), res.status_code
    except Exception:
        return {"ok": False, "status": res.status_code, "text": res.text[:300]}, 500

@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    upd = request.get_json(force=True, silent=True) or {}

    # ===== CallbackQuery =====
    if "callback_query" in upd:
        cq = upd["callback_query"]
        data = cq.get("data","")
        chat_id = cq["message"]["chat"]["id"]
        uid = cq["from"]["id"]

        if data.startswith("t:"):
            key = data.split(":",1)[1]
            if key in TESTS:
                start_test(chat_id, uid, key)
            else:
                send(chat_id, "اختبار غير معروف.", reply_kb())
            return "ok", 200

        if data.startswith("a"):
            try:
                idx = int(data[1:])
                if 0 <= idx <= 3:
                    record_answer(chat_id, uid, idx)
            except Exception:
                send(chat_id, "إجابة غير صالحة.", reply_kb())
            return "ok", 200

        if data.startswith("c:"):
            code = data.split(":",1)[1]
            cbt_send(chat_id, code)
            return "ok", 200

        return "ok", 200

    # ===== Messages =====
    msg = upd.get("message") or upd.get("edited_message") or {}
    if not msg:
        return "ok", 200

    chat_id = msg["chat"]["id"]
    text    = (msg.get("text") or "").strip()
    low     = norm(text)
    user    = msg.get("from", {})
    uid     = user.get("id")

    # جلسة ذكاء اصطناعي فعّالة؟
    if uid in AI_SESS and not (is_cmd(text,"start") or is_cmd(text,"help") or low=="انهاء"):
        ai_handle(chat_id, uid, text)
        return "ok", 200

    # أوامر
    if is_cmd(text, "start"):
        send(chat_id,
             "👋 أهلاً بك! أنا <b>عربي سايكو</b>.\n"
             "قائمة سفلية فيها: اختبارات، العلاج السلوكي، نوم، حزن، تنفّس، ذكاء اصطناعي…\n"
             "• /help للمساعدة • /menu لعرض الأزرار • /tests للاختبارات • /cbt للعلاج السلوكي",
             reply_kb())
        return "ok", 200

    if is_cmd(text, "help"):
        help_msg = (
            "<b>مساعدة ℹ️</b>\n"
            "• <b>اختبارات</b>: GAD-7 للقلق، PHQ-9 للاكتئاب.\n"
            "• <b>العلاج السلوكي</b>: مواضيع CBT مختصرة.\n"
            "• <b>نوم/حزن/اكتئاب/تنفّس</b>: نصائح سريعة.\n"
            "• <b>ذكاء اصطناعي</b>: محادثة تثقيفية (اختياري).\n"
            "• <b>تواصل</b>: لإرسال طلب تواصل للمشرف."
        )
        if CONTACT_PHONE:
            help_msg += f"\n\nللتواصل المباشر: <code>{CONTACT_PHONE}</code>"
        send(chat_id, help_msg, reply_kb());  return "ok", 200

    if is_cmd(text, "menu"):
        send(chat_id, "تم عرض الأزرار ✅", reply_kb());  return "ok", 200

    if is_cmd(text, "tests"):
        tests_menu(chat_id);  return "ok", 200

    if is_cmd(text, "cbt"):
        cbt_menu(chat_id);    return "ok", 200

    if is_cmd(text, "ai"):
        ai_start(chat_id, uid); return "ok", 200

    # إنهاء جلسة الذكاء الاصطناعي
    if low == "انهاء":
        ai_end(chat_id, uid); return "ok", 200

    # كلمات القائمة السفلية
    if low in ("اختبارات",):
        tests_menu(chat_id);  return "ok", 200

    if low in ("العلاج السلوكي","العلاج السلوكي المعرفي","cbt"):
        cbt_menu(chat_id);    return "ok", 200

    if low in THERAPY:
        send(chat_id, THERAPY[low], reply_kb());  return "ok", 200

    if low in ("ذكاء اصطناعي","ذكاءاصطناعي","ai"):
        ai_start(chat_id, uid); return "ok", 200

    # طلب تواصل (تنبيه للأدمن)
    if low in ("تواصل","تواصل."):
        username = user.get("username") or (user.get("first_name","")+" "+user.get("last_name","")).strip() or "مستخدم"
        send(chat_id, "تم تسجيل طلب تواصل ✅ سنرجع لك قريبًا.", reply_kb())
        if ADMIN_CHAT_ID:
            info = (f"📩 طلب تواصل\n"
                    f"👤 {username} (user_id={uid}, chat_id={chat_id})\n"
                    f"نصّه: {text}")
            tg("sendMessage", {"chat_id": int(ADMIN_CHAT_ID), "text": info})
        return "ok", 200

    # فحص أمان
    if crisis_guard(text):
        send(chat_id,
             "أقدّر شعورك، وسلامتك أهم شيء الآن.\n"
             "لو تراودك أفكار لإيذاء نفسك، تواصل فورًا مع الطوارئ أو شخص موثوق.",
             reply_kb())
        return "ok", 200

    # رد عام
    send(chat_id, f"تمام 👌 وصلتني: “{text}”. اكتب /menu لعرض الأزرار.", reply_kb())
    return "ok", 200


# ========= Main =========
if __name__ == "__main__":
    # للتجربة المحلية فقط
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
