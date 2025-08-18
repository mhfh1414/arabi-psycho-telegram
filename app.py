# app.py — Arabi Psycho Telegram Bot (Tests + CBT + Therapy + "Arabi Saiko" AI)
import os, logging, json
from flask import Flask, request, jsonify
import requests

# ========= الإعدادات (Environment) =========
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")

BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

WEBHOOK_SECRET      = os.environ.get("WEBHOOK_SECRET", "secret")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
ADMIN_CHAT_ID       = os.environ.get("ADMIN_CHAT_ID")              # اختياري: تنبيه طلبات التواصل

# الذكاء الاصطناعي (متوافق مع OpenAI / OpenRouter)
AI_BASE_URL = os.environ.get("AI_BASE_URL", "").rstrip("/")        # مثال OpenRouter: https://openrouter.ai/api
AI_API_KEY  = os.environ.get("AI_API_KEY", "")
AI_MODEL    = os.environ.get("AI_MODEL", "openrouter/auto")        # اختر موديل مدعوم في مزودك

# ========= تطبيق Flask =========
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho-bot")

# ========= توابع تيليجرام =========
def tg(method, payload):
    r = requests.post(f"{BOT_API}/{method}", json=payload, timeout=15)
    if r.status_code != 200:
        log.warning("TG %s -> %s | %s", method, r.status_code, r.text[:350])
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
    return {"inline_keyboard": rows}

def reply_kb():
    # لوحة سفلية دائمة
    return {
        "keyboard": [
            [{"text": "العلاج السلوكي"}, {"text": "اختبارات"}],
            [{"text": "نوم"}, {"text": "حزن"}],
            [{"text": "تثقيف"}, {"text": "عربي سايكو"}],
            [{"text": "مساعدة"}, {"text": "تواصل"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

def show_menu(chat_id, note="القائمة السفلية جاهزة ✅"):
    send(chat_id, note, reply_kb())

def is_cmd(txt, name): return (txt or "").strip().lower().startswith("/"+name)

def norm_ar(s):
    return (s or "").replace("أ","ا").replace("إ","ا").replace("آ","ا").strip().lower()

# ========= أمان بسيط =========
CRISIS_WORDS = ["انتحار", "اؤذي نفسي", "اذي نفسي", "قتل نفسي", "ما ابغى اعيش", "اريد اموت", "افكر اذ"]
def crisis_guard(text):
    low = norm_ar(text)
    return any(w in low for w in CRISIS_WORDS)

# ========= الاختبارات النفسية (GAD-7 / PHQ-9) =========
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
TESTS = {"g7":{"name":"مقياس القلق GAD-7","q":G7}, "phq":{"name":"مقياس الاكتئاب PHQ-9","q":PHQ9}}
SESS = {}  # {uid: {"key":, "i":, "score":}}

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
        SESS.pop(uid, None)
        return
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
        return f"<b>{lvl}</b>.\nنصيحة: تنفّس ببطء، قلّل الكافيين، وثبّت النوم."
    if key=="phq":
        if score<=4: lvl="ضئيل"
        elif score<=9: lvl="خفيف"
        elif score<=14: lvl="متوسط"
        elif score<=19: lvl="متوسط إلى شديد"
        else: lvl="شديد"
        return f"<b>اكتئاب {lvl}</b>.\nنصيحة: تنشيط سلوكي + تواصل اجتماعي + روتين نوم."
    return "تم."

# ========= CBT =========
CBT_ITEMS = [
    ("أخطاء التفكير",     "c:cd"),
    ("الاجترار والكبت",    "c:rum"),
    ("الأسئلة العشرة",     "c:q10"),
    ("الاسترخاء",          "c:rlx"),
    ("التنشيط السلوكي",    "c:ba"),
    ("اليقظة الذهنية",     "c:mind"),
    ("حل المشكلات",        "c:ps"),
    ("سلوكيات الأمان",     "c:safe"),
]
def cbt_menu(chat_id):
    rows=[]
    for i in range(0, len(CBT_ITEMS), 2):
        pair = [{"text": t, "callback_data": d} for (t,d) in CBT_ITEMS[i:i+2]]
        rows.append(pair)
    send(chat_id, "اختر موضوع العلاج السلوكي (CBT):", inline(rows))

def cbt_text(code):
    if code=="cd":
        return [
            "<b>أخطاء التفكير</b>\nالأبيض/الأسود، التعميم، قراءة الأفكار، التنبؤ، التهويل…",
            "خطوات: ١) التقط الفكرة ٢) الدليل معها/ضدها ٣) صياغة متوازنة."
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
        return ["<b>حل المشكلات</b>", "عرّف المشكلة → بدائل → خطة SMART صغيرة → جرّب → قيّم."]
    if code=="safe":
        return ["<b>سلوكيات الأمان</b>", "قلّل الطمأنة/التجنب تدريجيًا مع تعرّض آمن."]
    return ["تم."]

def cbt_send(chat_id, code):
    for t in cbt_text(code):
        send(chat_id, t, reply_kb())

# ========= علاج سريع (مختصر) =========
THERAPY = {
    "sleep":
        "<b>بروتوكول النوم (مختصر)</b>\n• ثبّت الاستيقاظ يوميًا\n• قلّل الشاشات مساءً\n• طقوس تهدئة 30–45د\n• سرير=نوم فقط\n• لو ما نمت خلال 20د اخرج لنشاط هادئ وارجع.",
    "sad":
        "<b>علاج الحزن (تنشيط سلوكي)</b>\n• 3 أنشطة صغيرة اليوم (ممتع/نافع/اجتماعي)\n• ابدأ بـ10–20د\n• قيّم المزاج قبل/بعد.",
}

# ========= جلسة الذكاء الاصطناعي (عربي سايكو) =========
AI_SESS = {}  # {uid: [{"role":"system"/"user"/"assistant","content":...}, ...]}
SYSTEM_PROMPT = (
    "أنت «عربي سايكو» مساعد نفسي تعليمي بالعربية. قدّم دعمًا عامًّا وتقنيات CBT البسيطة، "
    "وتذكيرًا أنك لست بديلاً عن مختص. لا تُعطِ تشخيصًا. عند وجود خطر على السلامة "
    "(إيذاء النفس/الآخرين)، وجّه لطلب مساعدة فورية."
)

def ai_ready():
    return bool(AI_BASE_URL and AI_API_KEY and AI_MODEL)

def ai_call(messages):
    """
    POST {AI_BASE_URL}/v1/chat/completions — متوافق مع OpenAI.
    لتقليل أخطاء الرصيد 402 نستخدم max_tokens صغير.
    """
    url = AI_BASE_URL + "/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    body = {"model": AI_MODEL, "messages": messages, "temperature": 0.4, "max_tokens": 220}
    r = requests.post(url, headers=headers, json=body, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code}: {r.text[:400]}")
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

def ai_start(chat_id, uid):
    if not ai_ready():
        send(chat_id,
             "ميزة «عربي سايكو» غير مفعّلة.\n"
             "أضف المتغيرات: AI_BASE_URL / AI_API_KEY / AI_MODEL ثم أعد النشر.",
             reply_kb()); return
    AI_SESS[uid] = [{"role":"system","content": SYSTEM_PROMPT}]
    send(chat_id,
         "بدأنا جلسة <b>عربي سايكو</b> 🤖\n"
         "اكتب سؤالك عن النوم/القلق/CBT…\n"
         "لإنهاء الجلسة اكتب: <code>انهاء</code>.",
         reply_kb())

def ai_handle(chat_id, uid, user_text):
    if crisis_guard(user_text):
        send(chat_id,
             "أقدّر شعورك، وسلامتك أهم شيء الآن.\n"
             "لو تراودك أفكار لإيذاء نفسك، اطلب مساعدة فورية من الطوارئ/رقم بلدك.\n"
             "كخطوة سريعة: تنفّس 4-4-6 ×10 وابق مع شخص تثق به.",
             reply_kb())
        return
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
    send(chat_id, "تم إنهاء جلسة «عربي سايكو» ✅", reply_kb())

# ========= مسارات الويب =========
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

    # === Callback query (inline buttons) ===
    if "callback_query" in upd:
        cq = upd["callback_query"]; data = cq.get("data","")
        chat_id = cq["message"]["chat"]["id"]; uid = cq["from"]["id"]

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

        if data.startswith("c:"):
            code = data.split(":",1)[1]
            cbt_send(chat_id, code);  return "ok", 200

        return "ok", 200

    # === Messages ===
    msg = upd.get("message") or upd.get("edited_message") or {}
    if not msg:
        return "ok", 200

    chat_id = msg["chat"]["id"]
    text    = (msg.get("text") or "").strip()
    low     = norm_ar(text)
    uid     = msg.get("from", {}).get("id")
    user    = msg.get("from", {})
    username = user.get("username") or (user.get("first_name","")+" "+user.get("last_name","")).strip() or "مستخدم"

    # أوامر مساعدة/تشخيص
    if is_cmd(text, "ai_diag"):
        send(chat_id, f"ai_ready={ai_ready()}\nBASE={bool(AI_BASE_URL)} KEY={bool(AI_API_KEY)}\nMODEL={AI_MODEL or '-'}")
        return "ok", 200
    if is_cmd(text, "whoami"):
        send(chat_id, f"chat_id: {chat_id}\nuser_id: {uid}")
        return "ok", 200

    # القائمة / البداية
    if is_cmd(text, "start"):
        send(chat_id,
             "أهلًا بك، أنا <b>عربي سايكو</b>.\n"
             "القائمة السفلية: اختبارات، العلاج السلوكي، نوم، حزن، تنفّس، عربي سايكو…\n"
             "• /menu لعرض الأزرار • /tests للاختبارات • /cbt للعلاج السلوكي • /help للمساعدة",
             reply_kb())
        return "ok", 200
    if is_cmd(text, "menu") or low in ["قائمة","القائمة","menu"]:
        show_menu(chat_id, "هذه هي القائمة:")
        return "ok", 200
    if is_cmd(text, "help") or "مساعدة" in low:
        send(chat_id,
             "استخدم الأزرار أو الأوامر:\n"
             "• /menu لعرض الأزرار\n• /tests للاختبارات (GAD-7 / PHQ-9)\n"
             "• /cbt لعرض مواضيع العلاج السلوكي\n• أرسل «عربي سايكو» لبدء محادثة ذكية\n"
             "• «انهاء» لإنهاء الجلسة الذكية.", reply_kb())
        return "ok", 200

    # اختبارات
    if is_cmd(text, "tests") or any(w in low for w in ["اختبار","اختبارات","مقياس","قياس"]):
        tests_menu(chat_id);  return "ok", 200

    # CBT
    if is_cmd(text, "cbt") or ("العلاج السلوكي" in low) or "cbt" in low:
        cbt_menu(chat_id);    return "ok", 200

    # العلاج السريع
    if "نوم" in low:
        send(chat_id, THERAPY["sleep"], reply_kb()); return "ok", 200
    if "حزن" in low:
        send(chat_id, THERAPY["sad"], reply_kb());   return "ok", 200
    if "تثقيف" in low:
        send(chat_id, "للتثقيف: اختر من <b>العلاج السلوكي (CBT)</b> أو اطلب موضوعًا محددًا.", reply_kb())
        return "ok", 200

    # طلب تواصل (ينبه الأدمن)
    if "تواصل" in low:
        send(chat_id, "تم تسجيل طلب تواصل ✅ سنرجع لك قريبًا.", reply_kb())
        if ADMIN_CHAT_ID:
            info = (f"📩 طلب تواصل\n"
                    f"اسم: @{username} (user_id={uid})\n"
                    f"نصّه: {text}")
            send(ADMIN_CHAT_ID, info)
        return "ok", 200

    # عربي سايكو (بدء/إنهاء/استمرار)
    if "عربي سايكو" in low:
        ai_start(chat_id, uid); return "ok", 200
    if low == "انهاء":
        ai_end(chat_id, uid);   return "ok", 200
    if uid in AI_SESS:
        ai_handle(chat_id, uid, text); return "ok", 200

    # إصلاح اللوحة عند التعلّق
    if is_cmd(text, "fixkb"):
        tg("sendMessage", {"chat_id": chat_id, "text": "إعادة ضبط اللوحة…",
                           "reply_markup": {"remove_keyboard": True}})
        show_menu(chat_id)
        return "ok", 200

    # رد افتراضي
    send(chat_id, "اكتب /menu لعرض الأزرار أو «عربي سايكو» لبدء محادثة.", reply_kb())
    return "ok", 200


# ========= تشغيل محلّي (اختياري) =========
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
