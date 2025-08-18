# app.py — Arabi Psycho Telegram Bot (CBT + Education + Tests + AI)
import os, logging, json
from flask import Flask, request, jsonify
import requests

# ========= Config =========
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

WEBHOOK_SECRET     = os.environ.get("WEBHOOK_SECRET", "secret")
RENDER_EXTERNAL_URL= os.environ.get("RENDER_EXTERNAL_URL", "")

# Contact/Admin
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")
CONTACT_PHONE = os.environ.get("CONTACT_PHONE")  # مثل: +9665xxxxxxxx

# Supervision (يظهر في /help)
SUPERVISOR_NAME  = os.environ.get("SUPERVISOR_NAME", "أخصائي نفسي مرخّص")
SUPERVISOR_TITLE = os.environ.get("SUPERVISOR_TITLE", "MS, CBT")
LICENSE_NO       = os.environ.get("LICENSE_NO", "—")
LICENSE_ISSUER   = os.environ.get("LICENSE_ISSUER", "وزارة الصحة")

# AI (OpenAI-compatible • يفضّل OpenRouter)
AI_BASE_URL = os.environ.get("AI_BASE_URL", "").rstrip("/") or "https://openrouter.ai/api"
AI_API_KEY  = os.environ.get("AI_API_KEY", "")
AI_MODEL    = os.environ.get("AI_MODEL", "openrouter/auto")

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho")

# ========= Telegram helpers =========
def tg(method, payload):
    r = requests.post(f"{BOT_API}/{method}", json=payload, timeout=20)
    if r.status_code != 200:
        log.warning("TG %s -> %s | %s", method, r.status_code, r.text[:300])
    return r

def send(chat_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True}
    if reply_markup: payload["reply_markup"] = reply_markup
    return tg("sendMessage", payload)

def inline(rows):
    return {"inline_keyboard": rows}

def reply_kb():
    return {
        "keyboard": [
            [{"text":"العلاج السلوكي"}, {"text":"اختبارات"}],
            [{"text":"التثقيف"}, {"text":"تشخيص تعليمي"}],
            [{"text":"نوم"}, {"text":"حزن"}],
            [{"text":"قلق"}, {"text":"اكتئاب"}],
            [{"text":"تنفّس"}, {"text":"عربي سايكو"}],
            [{"text":"تواصل"}, {"text":"مساعدة"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

def is_cmd(txt, name):
    return (txt or "").strip().startswith("/"+name)

# ========= Safety (بسيط) =========
CRISIS_WORDS = ["انتحار","اودي نفسي","اذي نفسي","قتل نفسي","ما ابغى اعيش","أؤذي نفسي","اايذاء"]
def crisis_guard(text):
    low = (text or "")
    for a,b in (("أ","ا"),("إ","ا"),("آ","ا")): low = low.replace(a,b)
    low = low.lower()
    return any(w in low for w in CRISIS_WORDS)

# ========= HELP / ABOUT =========
def help_msg(chat_id):
    lines = [
        "📘 <b>التعليمات</b>",
        f"يعمل <b>عربي سايكو</b> تحت إشراف {SUPERVISOR_NAME} ({SUPERVISOR_TITLE})، ترخيص <b>{LICENSE_NO}</b> – {LICENSE_ISSUER}.",
        "الغرض: تثقيف ودعم عام بتقنيات CBT — ليس بديلاً عن التشخيص الطبي أو وصف الأدوية.",
        "",
        "الأزرار:",
        "• <b>اختبارات</b>: GAD-7 (قلق) + PHQ-9 (اكتئاب) + PDSS-SR (نوبات هلع).",
        "• <b>العلاج السلوكي</b>: أدوات وتطبيقات CBT.",
        "• <b>التثقيف</b>: معلومات مبسّطة عن القلق/الاكتئاب/النوم/الهلع.",
        "• <b>تشخيص تعليمي</b>: مؤشرات DSM-5 للتثقيف فقط.",
        "• <b>عربي سايكو</b>: محادثة بالذكاء الاصطناعي.",
        "",
        "أوامر: /menu • /tests • /cbt • /about",
        "إنهاء جلسة الذكاء الاصطناعي: اكتب <code>انهاء</code>.",
        "للأزمات: اتصل بالطوارئ في بلدك أو الجأ لأقرب غرفة طوارئ."
    ]
    send(chat_id, "\n".join(lines), reply_kb())

def about_msg():
    return (
        "ℹ️ <b>عن عربي سايكو</b>\n"
        "مساعد نفسي تعليمي بالعربية يقدم أدوات CBT واختبارات مقننة قصيرة ودعمًا عامًا.\n"
        "ليس بديلاً عن العلاج الطبي. لطلب تواصل أو موعد: استخدم زر <b>تواصل</b>."
    )

# ========= AI (OpenRouter/OpenAI-compatible) =========
def ai_ready():
    return bool(AI_BASE_URL and AI_API_KEY and AI_MODEL)

AI_SESS = {}  # {uid: [messages]}
SYSTEM_PROMPT = (
    "أنت مساعد نفسي عربي. قدّم دعمًا عامًّا وتقنيات CBT المختصرة، دون تشخيص طبي أو وصف دواء. "
    "ذكّر دائماً بطلب مساعدة مباشرة عند وجود خطر على السلامة. اجعل ردودك موجزة وعملية."
)

def ai_call(messages):
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
             "ميزة الذكاء الاصطناعي غير مفعّلة.\n"
             "أضف AI_BASE_URL / AI_API_KEY / AI_MODEL ثم أعد النشر.",
             reply_kb()); return
    AI_SESS[uid] = [{"role":"system","content": SYSTEM_PROMPT}]
    send(chat_id, "🤖 بدأنا جلسة <b>عربي سايكو</b>…\nاكتب سؤالك عن النوم/القلق/CBT…\nلإنهاء الجلسة: اكتب <code>انهاء</code>.", reply_kb())

def ai_handle(chat_id, uid, user_text):
    if crisis_guard(user_text):
        send(chat_id,
             "سلامتك أهم شيء الآن.\nلو تراودك أفكار لإيذاء نفسك فاتصل بالطوارئ أو تواصل مع قريب موثوق فورًا.\n"
             "للمساعدة الفورية: تنفّس 4-4-6 لعشر مرات، وابقَ مع شخص تثق به.",
             reply_kb()); return
    msgs = AI_SESS.get(uid) or [{"role":"system","content": SYSTEM_PROMPT}]
    msgs = msgs[-16:] + [{"role":"user","content": user_text}]
    try:
        reply = ai_call(msgs)
    except Exception as e:
        send(chat_id,
             "يتعذّر الاتصال بالذكاء الاصطناعي.\n"
             "يبدو أن الرصيد قليل أو المفاتيح غير صالحة في OpenRouter.\n"
             f"<code>{e}</code>",
             reply_kb()); return
    msgs.append({"role":"assistant","content": reply})
    AI_SESS[uid] = msgs[-18:]
    send(chat_id, reply, reply_kb())

def ai_end(chat_id, uid):
    AI_SESS.pop(uid, None)
    send(chat_id, "تم إنهاء جلسة عربي سايكو ✅", reply_kb())

# ========= Psychoeducation =========
EDU_TOPICS = [
    ("القلق", "edu:anx"),
    ("الاكتئاب", "edu:dep"),
    ("النوم", "edu:sleep"),
    ("نوبات الهلع", "edu:panic"),
]
def edu_menu(chat_id):
    rows=[]
    for i in range(0,len(EDU_TOPICS),2):
        rows.append([{"text":t,"callback_data":d} for (t,d) in EDU_TOPICS[i:i+2]])
    send(chat_id, "اختر موضوعًا للتثقيف:", inline(rows))

def edu_text(code):
    if code=="anx":
        return ("<b>القلق</b>\n"
                "مفيد بقدرٍ صغير لكنه يزداد مع الاجتناب والطمأنة الزائدة.\n"
                "جرب: التعرّض التدريجي، تقليل الكافيين، تنفّس 4-7-8، تنظيم النوم.")
    if code=="dep":
        return ("<b>الاكتئاب</b>\n"
                "يُبقيك في حلقة (انسحاب ← خمول ← مزاج أسوأ).\n"
                "العلاج: تنشيط سلوكي (مهام صغيرة ممتعة/نافعة)، روتين نهاري، تواصل.")
    if code=="sleep":
        return ("<b>النوم</b>\n"
                "ثبّت الاستيقاظ يوميًا، قلّل الشاشات مساءً، اجعل السرير للنوم فقط، طقوس تهدئة 30-45د.")
    if code=="panic":
        return ("<b>نوبات الهلع</b>\n"
                "غير خطِرة لكنها مزعجة. لا تقاوم الأعراض؛ راقبها واسمِّها وابقَ في الموقف حتى تهدأ.\n"
                "تعرّض + تقليل سلوكيات الأمان (ماء/مخرج قريب…).")
    return "."

def edu_send(chat_id, code):
    send(chat_id, edu_text(code), reply_kb())

# ========= CBT (inline) =========
CBT_ITEMS = [
    ("أخطاء التفكير","c:cd"),
    ("الاجترار والكبت","c:rum"),
    ("الأسئلة العشرة","c:q10"),
    ("الاسترخاء","c:rlx"),
    ("التنشيط السلوكي","c:ba"),
    ("اليقظة الذهنية","c:mind"),
    ("حل المشكلات","c:ps"),
    ("سلوكيات الأمان","c:safe"),
]
def cbt_menu(chat_id):
    rows=[]; 
    for i in range(0,len(CBT_ITEMS),2):
        rows.append([{"text":t,"callback_data":d} for (t,d) in CBT_ITEMS[i:i+2]])
    send(chat_id, "اختر موضوع العلاج السلوكي:", inline(rows))

def cbt_text(code):
    if code=="cd":
        return [
            "<b>أخطاء التفكير</b>: الأبيض/الأسود، التعميم، قراءة الأفكار، التنبؤ، التهويل…",
            "٣ خطوات: ١) التقط الفكرة ٢) الدليل معها/ضدها ٣) صياغة متوازنة."
        ]
    if code=="rum":  return ["<b>الاجترار والكبت</b>", "سمِّ الفكرة وعدها. خصّص «وقت قلق». حوّل الانتباه لنشاط بسيط."]
    if code=="q10":  return ["<b>الأسئلة العشرة</b>", "الدليل؟ البدائل؟ أسوأ/أفضل/أرجح؟ لو صديقي مكاني؟ هل أعمّم؟…"]
    if code=="rlx":  return ["<b>الاسترخاء</b>", "تنفّس 4-7-8 ×6. شد/إرخِ العضلات من القدم للرأس."]
    if code=="ba":   return ["<b>التنشيط السلوكي</b>", "نشاطان صغيران يوميًا (ممتع/نافع) + قاعدة 5 دقائق."]
    if code=="mind": return ["<b>اليقظة الذهنية</b>", "تمرين 5-4-3-2-1 للحواس. ارجع للحاضر بدون حكم."]
    if code=="ps":   return ["<b>حل المشكلات</b>", "عرِّف المشكلة → بدائل → خطة صغيرة SMART → جرّب → قيّم."]
    if code=="safe": return ["<b>سلوكيات الأمان</b>", "قلّل الطمأنة/التجنب تدريجيًا مع تعرّض آمن."]
    return ["تم."]

def cbt_send(chat_id, code):
    for t in cbt_text(code):
        send(chat_id, t, reply_kb())

# ========= Therapy quick cards =========
THERAPY = {
    "sleep": "<b>بروتوكول النوم (مختصر)</b>\n• ثبّت الاستيقاظ يوميًا\n• طقوس تهدئة 30–45د\n• سرير=نوم فقط\n• لو ما نمت خلال 20د اخرج لنشاط هادئ وارجع.",
    "sad":   "<b>علاج الحزن (تنشيط سلوكي)</b>\n• 3 أنشطة صغيرة اليوم (ممتع/نافع/اجتماعي)\n• قيّم المزاج قبل/بعد.",
    "anx":   "<b>القلق</b>\n• تعرّض تدريجي للمواقف المخيفة\n• قلّل الطمأنة والتجنب\n• تنفّس ببطء.",
    "dep":   "<b>الاكتئاب</b>\n• مهام 5 دقائق\n• حركة خفيفة\n• تواصل مع صديق.",
    "panic": "<b>نوبة الهلع</b>\n• لاحظ الأعراض كـ «موجة» واسمِّها\n• ابقَ في الموقف حتى تنخفض 50% على الأقل\n• امتنع عن الهروب.",
}

# ========= Educational Diagnostic (DSM-like, not medical) =========
def dx_intro(chat_id):
    rows = [[{"text":"قلق","callback_data":"dx:anx"},{"text":"اكتئاب","callback_data":"dx:dep"}],
            [{"text":"نوبات هلع","callback_data":"dx:panic"}]]
    send(chat_id,
         "🧭 <b>تشخيص تعليمي</b> (للتثقيف فقط)\n"
         "اختر مجالًا لعرض مؤشرات DSM-5 الشائعة وروابط الاختبارات المناسبة.",
         inline(rows))

def dx_text(code):
    if code=="anx":
        return ("<b>قلق (تعليمي)</b>\nمؤشرات شائعة ≥6 أشهر: قلق زائد صعب السيطرة، توتر/تعب، صعوبة التركيز، اضطراب النوم…\n"
                "اختبر نفسك بمقياس <b>GAD-7</b> من «اختبارات».")
    if code=="dep":
        return ("<b>اكتئاب (تعليمي)</b>\nمزاج منخفض أو فقد المتعة معظم الأيام + ٤ أعراض (نوم/شهية/طاقة/تركز/ذنب/أفكار موت…) لمدة ≥ أسبوعين.\n"
                "اختبر نفسك بمقياس <b>PHQ-9</b> من «اختبارات».")
    if code=="panic":
        return ("<b>نوبات هلع (تعليمي)</b>\nهجمات فجائية مع خفقان/ضيـق نفس/دوخة… يليها قلق توقعي أو تجنب ≥ شهر.\n"
                "للتقدير الذاتي جرّب <b>PDSS-SR</b> من «اختبارات».")
    return "."

# ========= Tests =========
# كل اختبار يحدد: الاسم، الأسئلة، خيارات الإجابة (label,score)
ANS_0_3 = [("أبدًا",0),("عدة أيام",1),("أكثر من النصف",2),("تقريبًا يوميًا",3)]
GAD7_Q = [
    "التوتر/العصبية أو الشعور بالقلق",
    "عدم القدرة على التوقف عن القلق أو السيطرة عليه",
    "الانشغال بالهموم بدرجة كبيرة",
    "صعوبة الاسترخاء",
    "تململ/صعوبة الجلوس بهدوء",
    "الانزعاج بسرعة أو العصبية",
    "الخوف من حدوث شيء سيئ",
]
PHQ9_Q = [
    "قلة الاهتمام أو المتعة بالقيام بالأشياء",
    "الشعور بالحزن أو الاكتئاب أو اليأس",
    "مشاكل في النوم أو النوم كثيرًا",
    "الإرهاق أو قلة الطاقة",
    "ضعف الشهية أو الإفراط في الأكل",
    "الشعور بتدني تقدير الذات أو الذنب",
    "صعوبة التركيز",
    "الحركة/الكلام ببطء شديد أو توتر زائد",
    "أفكار بأنك ستكون أفضل حالًا لو لم تكن موجودًا",
]
# PDSS-SR (مبسّط 7 بنود 0-4)
PDSS_Q = [
    "شدّة نوبات الهلع خلال الأسبوع الماضي",
    "الضيق أثناء النوبة",
    "القلق التوقعي من حدوث نوبة",
    "تجنّب المواقف خوفًا من النوبة",
    "تأثير الأعراض الجسدية (قلب/نفس) على حياتك",
    "التأثير على العمل/الدراسة",
    "التأثير على العلاقات/الخروج",
]
ANS_0_4 = [("لا شيء",0),("خفيف",1),("متوسط",2),("شديد",3),("شديد جدًا",4)]

TESTS = {
    "g7":   {"name":"مقياس القلق GAD-7","q":GAD7_Q,"ans":ANS_0_3},
    "phq":  {"name":"مقياس الاكتئاب PHQ-9","q":PHQ9_Q,"ans":ANS_0_3},
    "pdss": {"name":"مقياس نوبات الهلع PDSS-SR","q":PDSS_Q,"ans":ANS_0_4},
}

SESS = {}  # {uid: {"key":, "i":, "score":}}

def tests_menu(chat_id):
    rows = [
        [{"text":"اختبار القلق (GAD-7)","callback_data":"t:g7"}],
        [{"text":"اختبار الاكتئاب (PHQ-9)","callback_data":"t:phq"}],
        [{"text":"اختبار نوبات الهلع (PDSS-SR)","callback_data":"t:pdss"}],
    ]
    send(chat_id, "اختر اختبارًا:", inline(rows))

def start_test(chat_id, uid, key):
    d = TESTS[key]
    SESS[uid] = {"key":key,"i":0,"score":0}
    send(chat_id, f"سنبدأ: <b>{d['name']}</b>\nأجب حسب آخر أسبوعين.", reply_kb())
    ask_next(chat_id, uid)

def ask_next(chat_id, uid):
    st = SESS.get(uid)
    if not st: return
    d = TESTS[st["key"]]; qs = d["q"]; answers = d["ans"]; i = st["i"]
    if i >= len(qs):
        score = st["score"]; max_sc = (answers[-1][1]) * len(qs)
        send(chat_id, f"النتيجة: <b>{score}</b> من {max_sc}\n{interpret(st['key'], score)}", reply_kb())
        SESS.pop(uid, None); return
    # ابنِ لوحة إجابات صفين/ثلاثة
    cells = [{"text":lbl, "callback_data":f"a{idx}"} for idx,(lbl,_) in enumerate(answers)]
    rows = []
    step = 2
    for k in range(0,len(cells),step):
        rows.append(cells[k:k+step])
    send(chat_id, f"س{ i+1 }: {qs[i]}", inline(rows))

def record_answer(chat_id, uid, ans_idx):
    st = SESS.get(uid)
    if not st: return
    d = TESTS[st["key"]]
    answers = d["ans"]
    if 0 <= ans_idx < len(answers):
        st["score"] += answers[ans_idx][1]
        st["i"] += 1
    ask_next(chat_id, uid)

def interpret(key, score):
    if key=="g7":
        # 0-21
        lvl = "قلق ضئيل" if score<=4 else ("قلق خفيف" if score<=9 else ("قلق متوسط" if score<=14 else "قلق شديد"))
        tip = "تنفّس ببطء، قلّل الكافيين، تعرّض تدريجيًا للمخاوف."
        return f"<b>{lvl}</b>.\n{tip}"
    if key=="phq":
        # 0-27
        lvl = "ضئيل" if score<=4 else ("خفيف" if score<=9 else ("متوسط" if score<=14 else ("متوسط إلى شديد" if score<=19 else "شديد")))
        tip = "التنشيط السلوكي + تواصل اجتماعي + روتين نوم."
        return f"<b>اكتئاب {lvl}</b>.\n{tip}"
    if key=="pdss":
        # 0-28
        lvl = "خفيف" if score<=7 else ("متوسط" if score<=14 else ("ملحوظ" if score<=21 else "شديد"))
        tip = "يساعد التعرض التدريجي وتقليل سلوكيات الأمان. راجع مختصًا لو كانت النوبات مقيّدة لحياتك."
        return f"<b>نوبات هلع – شدة {lvl}</b>.\n{tip}"
    return "."

# ========= Routes =========
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
    r = requests.post(f"{BOT_API}/setWebhook", json={"url": url}, timeout=15)
    try: data = r.json()
    except: data = {"ok": False, "text": r.text}
    return data, r.status_code

@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    upd = request.get_json(force=True, silent=True) or {}

    # --- Callbacks ---
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
                record_answer(chat_id, uid, idx)
            except: send(chat_id, "إجابة غير صالحة.", reply_kb())
            return "ok", 200

        if data.startswith("c:"):
            code = data.split(":",1)[1]
            cbt_send(chat_id, code); return "ok", 200

        if data.startswith("edu:"):
            code = data.split(":",1)[1]
            edu_send(chat_id, code); return "ok", 200

        if data.startswith("dx:"):
            code = data.split(":",1)[1]
            send(chat_id, dx_text(code), reply_kb()); return "ok", 200

        return "ok", 200

    # --- Messages ---
    msg = upd.get("message") or upd.get("edited_message") or {}
    if not msg: return "ok", 200
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    low  = text
    for a,b in (("أ","ا"),("إ","ا"),("آ","ا")): low = low.replace(a,b)
    low = low.lower()
    uid = msg.get("from", {}).get("id")
    user = msg.get("from", {})
    username = user.get("username") or (user.get("first_name","")+" "+user.get("last_name","")).strip() or "مستخدم"

    # AI session?
    if uid in AI_SESS and low not in ("انهاء","انهاء."):
        ai_handle(chat_id, uid, text); return "ok", 200
    if low in ("انهاء","انهاء."):
        ai_end(chat_id, uid); return "ok", 200

    # Commands
    if is_cmd(text,"start"):
        send(chat_id,
             "أهلًا بك! أنا <b>عربي سايكو</b>.\n"
             "القائمة السفلية: اختبارات، العلاج السلوكي، نوم، حزن، قلق، اكتئاب، تنفّس، عربي سايكو…\n"
             "• /tests للاختبارات • /cbt للعلاج السلوكي • /menu لعرض الأزرار • /help للمساعدة.",
             reply_kb()); return "ok", 200
    if is_cmd(text,"menu"):
        send(chat_id, "القائمة:", reply_kb()); return "ok", 200
    if is_cmd(text,"help"):
        help_msg(chat_id); return "ok", 200
    if is_cmd(text,"about"):
        send(chat_id, about_msg(), reply_kb()); return "ok", 200
    if is_cmd(text,"tests"):
        tests_menu(chat_id); return "ok", 200
    if is_cmd(text,"cbt"):
        cbt_menu(chat_id); return "ok", 200

    # Buttons / keywords
    if low == "اختبارات":
        tests_menu(chat_id); return "ok", 200
    if low == "العلاج السلوكي":
        cbt_menu(chat_id); return "ok", 200
    if low == "التثقيف":
        edu_menu(chat_id); return "ok", 200
    if low == "تشخيص تعليمي":
        dx_intro(chat_id); return "ok", 200

    if low == "نوم":
        send(chat_id, THERAPY["sleep"], reply_kb()); return "ok", 200
    if low == "حزن":
        send(chat_id, THERAPY["sad"], reply_kb()); return "ok", 200
    if low == "قلق":
        send(chat_id, THERAPY["anx"], reply_kb()); return "ok", 200
    if low == "اكتئاب":
        send(chat_id, THERAPY["dep"], reply_kb()); return "ok", 200
    if low in ("هلع","نوبات الهلع","نوبه","هلع "):
        send(chat_id, THERAPY["panic"], reply_kb()); return "ok", 200

    if low in ("تنفس","تنفّس","تنفس "):
        send(chat_id, "✨ تمرين تنفّس 4-7-8: شهيق 4 ثوانٍ، حبس 7، زفير 8. كرر 6 مرات.", reply_kb()); return "ok", 200

    if low in ("عربي سايكو","ذكاء اصطناعي","الذكاء الاصطناعي"):
        ai_start(chat_id, uid); return "ok", 200

    if low in ("مساعدة","التعليمات"):
        help_msg(chat_id); return "ok", 200

    if low in ("تواصل","تواصل "):
        send(chat_id, "تم تسجيل طلب تواصل ✅ سنرجع لك قريبًا.", reply_kb())
        if ADMIN_CHAT_ID:
            info = (f"📩 طلب تواصل\n"
                    f"من: {username} (id={uid}, chat_id={chat_id})\n"
                    f"نصّه: {text}")
            tg("sendMessage", {"chat_id": int(ADMIN_CHAT_ID), "text": info})
        if CONTACT_PHONE:
            send(chat_id, f"📞 بإمكانك التواصل المباشر على الرقم: {CONTACT_PHONE}", reply_kb())
        return "ok", 200

    # fallback
    if ai_ready():
        ai_start(chat_id, uid)
        send(chat_id, "اكتب سؤالك…", reply_kb())
    else:
        send(chat_id, "اكتب /menu لعرض الأزرار أو /help للمساعدة.", reply_kb())
    return "ok", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
