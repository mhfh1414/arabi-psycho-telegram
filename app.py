# app.py — Arabi Psycho Telegram Bot (CBT + Tests + Educational Dx + AI Chat)
# -------------------------------------------
import os, json, logging
from flask import Flask, request, jsonify
import requests

# ========= الإعدادات =========
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

WEBHOOK_SECRET     = os.environ.get("WEBHOOK_SECRET", "secret")
RENDER_EXTERNAL_URL= os.environ.get("RENDER_EXTERNAL_URL", "")
ADMIN_CHAT_ID      = os.environ.get("ADMIN_CHAT_ID", "")
CONTACT_PHONE      = os.environ.get("CONTACT_PHONE", "")

# الذكاء الاصطناعي (OpenAI-compatible مثل OpenRouter)
AI_BASE_URL = (os.environ.get("AI_BASE_URL", "") or "").rstrip("/")
AI_API_KEY  = os.environ.get("AI_API_KEY", "")
AI_MODEL    = os.environ.get("AI_MODEL", "openai/gpt-4o-mini")

# ========= تحضير التطبيق =========
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho")

# ========= أدوات تيليجرام =========
def tg(method, payload):
    r = requests.post(f"{BOT_API}/{method}", json=payload, timeout=30)
    if r.status_code != 200:
        log.warning("TG %s -> %s %s", method, r.status_code, r.text[:300])
    return r

def send(chat_id, text, reply_markup=None, parse_mode="HTML"):
    data = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True}
    if reply_markup: data["reply_markup"] = reply_markup
    return tg("sendMessage", data)

def inline(rows):
    return {"inline_keyboard": rows}

def reply_kb():
    # لوحة أزرار سفلية دائمة
    return {
        "keyboard": [
            [{"text":"العلاج السلوكي"}, {"text":"اختبارات"}],
            [{"text":"التثقيف"}, {"text":"تشخيص تعليمي"}],
            [{"text":"نوم"}, {"text":"حزن"}],
            [{"text":"قلق"}, {"text":"اكتئاب"}],
            [{"text":"تنفّس"}, {"text":"عربي سايكو"}],
            [{"text":"عن عربي سايكو"}, {"text":"تواصل"}],
            [{"text":"مساعدة"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

def is_cmd(txt, name):
    return (txt or "").strip().startswith("/" + name)

# ========= فلاتر أمان بسيطة =========
CRISIS_WORDS = ["انتحار","ااذي نفسي","اذي نفسي","قتل نفسي","لم اعد اريد العيش","ما ابغى اعيش"]
def crisis_guard(text):
    low = (text or "").replace("أ","ا").replace("إ","ا").replace("آ","ا").lower()
    return any(w in low for w in CRISIS_WORDS)

# ========= التعليمات & نبذة =========
ABOUT = (
    "<b>عربي سايكو</b> 🤖 مساعد نفسي تعليمي باللغة العربية.\n"
    "يقدّم مواد تثقيفية وتمارين CBT بسيطة واختبارات قياسية ذاتيًا.\n"
    "<b>تنبيه مهم:</b> لستُ بديلًا عن التشخيص أو العلاج لدى مختص. "
    "المشروع تحت إشراف <b>أخصائي نفسي مرخّص</b>؛ المحتوى لأغراض التثقيف والدعم فقط.\n"
    f"{'هاتف للتواصل: ' + CONTACT_PHONE if CONTACT_PHONE else ''}"
)

HELP = (
    "الأوامر:\n"
    "• /start لبدء الاستخدام\n"
    "• /menu لعرض الأزرار\n"
    "• /tests لبدء الاختبارات\n"
    "• /cbt لبطاقات العلاج السلوكي\n"
    "• اكتب «عربي سايكو» لبدء محادثة ذكية\n"
    "• «تشخيص تعليمي» للحصول على مسارات ونصائح مبسطة"
)

# ========= اختبارات نفسية =========
ANS4 = [("أبدًا",0), ("عدة أيام",1), ("أكثر من النصف",2), ("تقريبًا يوميًا",3)]
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
    "الحركة/الكلام ببطء شديد أو على العكس بتوتر زائد",
    "أفكار بأنك ستكون أفضل حالًا لو لم تكن موجودًا"
]
# PDSS-SR مبسّط لنوبات الهلع (0-4)
ANS5 = [("0 لا شيء",0), ("1 خفيف",1), ("2 متوسط",2), ("3 شديد",3), ("4 شديد جدًا",4)]
PDSS = [
    "مدى شدة نوبات الهلع خلال الأسبوعين الماضيين",
    "مدى تكرار نوبات الهلع",
    "الخوف من حدوث نوبة أخرى",
    "تجنب الأماكن/المواقف خوفًا من الهلع",
    "الضيق الناجم عن القلق المتوقع (anticipatory)",
    "الأثر على العمل/الدراسة",
    "الأثر على العلاقات/الحياة الاجتماعية"
]

TESTS = {
    "g7":  {"name":"مقياس القلق GAD-7",     "q": G7,   "ans": ANS4},
    "phq": {"name":"مقياس الاكتئاب PHQ-9",  "q": PHQ9, "ans": ANS4},
    "pdss":{"name":"مقياس نوبات الهلع (PDSS-SR مبسّط)", "q": PDSS, "ans": ANS5},
}
SESS = {}  # {uid: {"key":..., "i":..., "score":...}}

def tests_menu(chat_id):
    send(chat_id, "اختر اختبارًا:", inline([
        [{"text":"اختبار القلق (GAD-7)", "callback_data":"t:g7"}],
        [{"text":"اختبار الاكتئاب (PHQ-9)", "callback_data":"t:phq"}],
        [{"text":"اختبار نوبات الهلع (PDSS-SR)", "callback_data":"t:pdss"}],
    ]))

def start_test(chat_id, uid, key):
    data = TESTS[key]
    SESS[uid] = {"key": key, "i": 0, "score": 0}
    send(chat_id, f"سنبدأ: <b>{data['name']}</b>\nأجب بحسب آخر أسبوعين.", reply_kb())
    ask_next(chat_id, uid)

def ask_next(chat_id, uid):
    st = SESS.get(uid)
    if not st: return
    key, i = st["key"], st["i"]; qs = TESTS[key]["q"]; ans = TESTS[key]["ans"]
    if i >= len(qs):
        score = st["score"]; SESS.pop(uid, None)
        txt = f"النتيجة: <b>{score}</b>\n{interpret_test(key, score)}"
        send(chat_id, txt, reply_kb()); return
    # بناء الأزرار بحسب عدد الخيارات
    rows = []
    row = []
    for idx, (label, _) in enumerate(ans):
        row.append({"text": label, "callback_data": f"a{idx}"})
        if len(row) == 2:
            rows.append(row); row=[]
    if row: rows.append(row)
    send(chat_id, f"س{ i+1 }: {qs[i]}", inline(rows))

def record_answer(chat_id, uid, ans_idx):
    st = SESS.get(uid)
    if not st: return
    key = st["key"]; ans = TESTS[key]["ans"]
    if 0 <= ans_idx < len(ans):
        st["score"] += ans[ans_idx][1]
        st["i"] += 1
    ask_next(chat_id, uid)

def interpret_test(key, score):
    if key == "g7":
        if score <= 4: lvl = "قلق ضئيل"
        elif score <= 9: lvl = "قلق خفيف"
        elif score <= 14: lvl = "قلق متوسط"
        else: lvl = "قلق شديد"
        return f"<b>{lvl}</b> — جرّب تمارين التنفّس، وثبّت مواعيد نومك. اطلب مساعدة مختص إذا أثر على حياتك."
    if key == "phq":
        if score <= 4: lvl="ضئيل"
        elif score <= 9: lvl="خفيف"
        elif score <= 14: lvl="متوسط"
        elif score <= 19: lvl="متوسط إلى شديد"
        else: lvl="شديد"
        return f"<b>اكتئاب {lvl}</b> — نوصي بالتنشيط السلوكي، والدعم الاجتماعي، ومراجعة مختص عند الارتفاع."
    if key == "pdss":
        if score <= 7: lvl="ضئيل"
        elif score <= 15: lvl="خفيف"
        elif score <= 23: lvl="متوسط"
        elif score <= 28: lvl="شديد"
        else: lvl="شديد جدًا"
        return f"<b>نوبات هلع: {lvl}</b> — التعرض التدريجي وتمارين التنفّس مفيدة. إن كانت النوبات متكررة، استشر مختصًا."
    return "تم."

# ========= بطاقات العلاج السلوكي (CBT) =========
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
        rows.append([{"text":CBT_ITEMS[i][0], "callback_data":CBT_ITEMS[i][1]},
                     {"text":CBT_ITEMS[i+1][0], "callback_data":CBT_ITEMS[i+1][1]}])
    send(chat_id, "اختر موضوع العلاج السلوكي:", inline(rows))

def cbt_text(code):
    if code=="cd":
        return ["<b>أخطاء التفكير</b>\nالأبيض/الأسود، التعميم، قراءة الأفكار، التنبؤ، التهويل…",
                "خطوات: ١) التقط الفكرة ٢) أدلة معها/ضدها ٣) صياغة متوازنة واقعية."]
    if code=="rum":
        return ["<b>الاجترار والكبت</b>",
                "سمِّ الفكرة، خصّص «وقت قلق»، حوّل انتباهك لنشاط بسيط (مشي/ترتيب)."]
    if code=="q10":
        return ["<b>الأسئلة العشرة</b>",
                "الدليل؟ البدائل؟ لو صديق مكاني؟ أسوأ/أفضل/أرجح؟ هل أعمّم؟ ماذا أتجاهل؟ الخ…"]
    if code=="rlx":
        return ["<b>الاسترخاء</b>", "تنفّس 4-7-8 ×6 مرات. شدّ/إرخِ العضلات من القدم للرأس ببطء."]
    if code=="ba":
        return ["<b>التنشيط السلوكي</b>", "نشاطان صغيران يوميًا (ممتع/نافع). قاعدة 5 دقائق. قيّم المزاج قبل/بعد."]
    if code=="mind":
        return ["<b>اليقظة الذهنية</b>", "تمرين 5-4-3-2-1 للحواس. لاحظ بلطف وارجع للحاضر دون حكم."]
    if code=="ps":
        return ["<b>حل المشكلات</b>", "عرّف المشكلة → بدائل → خطة صغيرة SMART → جرّب → قيّم."]
    if code=="safe":
        return ["<b>سلوكيات الأمان</b>", "قلّل الطمأنة والتجنب تدريجيًا مع تعرّض آمن."]
    return ["تم."]

def cbt_send(chat_id, code):
    for t in cbt_text(code):
        send(chat_id, t, reply_kb())

# ========= تثقيف (اضطرابات شائعة) =========
EDU = {
    "القلق الاجتماعي":
        "الخوف من التقييم السلبي. جرّب التعرض التدريجي + إعادة هيكلة الأفكار.",
    "الاكتئاب":
        "انخفاض المزاج وفقدان المتعة ≥ أسبوعين. التنشيط السلوكي مهم + دعم اجتماعي.",
    "الثقة بالنفس":
        "أعد صياغة الحوار الداخلي، راكم إنجازات صغيرة متدرجة.",
    "القلق على الصحة":
        "مبالغة في تفسير الأحاسيس الجسدية. دوّن الدليل مع/ضد واستشر طبيبًا عند الحاجة فقط.",
    "القلق":
        "قلق مفرط صعب السيطرة ≥ 6 أشهر مع أعراض توتر. ساعد نفسك بالتنفّس وتنظيم النوم.",
    "الوسواس القهري":
        "أفكار/دوافع متكررة مع أفعال قهرية. العلاج المفضل: التعرض ومنع الاستجابة (ERP).",
    "كرب ما بعد الصدمة":
        "ذكريات اقتحامية وتجنب وفرط يقظة بعد حدث صادم. يفضّل العلاج المعرفي المُعالج للصدمة.",
    "نوبات الهلع":
        "اندفاع مفاجئ من الخوف مع أعراض جسدية. التعرّف عليها + تنفّس بطيء + تعرّض تدريجي.",
}
def edu_menu(chat_id):
    rows=[]
    items=list(EDU.keys())
    for i in range(0,len(items),2):
        l=[{"text":items[i], "callback_data":"ed:"+items[i]}]
        if i+1<len(items): l.append({"text":items[i+1], "callback_data":"ed:"+items[i+1]})
        rows.append(l)
    send(chat_id, "التثقيف النفسي:", inline(rows))

# ========= جلسات سريعة (نوم/حزن/تنفّس) =========
THERAPY = {
    "sleep":
        "<b>بروتوكول النوم المختصر</b>\n• ثبّت الاستيقاظ يوميًا\n• قلّل الشاشات مساءً\n• طقوس تهدئة 30-45د\n"
        "• السرير = نوم فقط\n• لو ما نمت خلال 20د اخرج لنشاط هادئ وارجع.",
    "sad":
        "<b>علاج الحزن (تنشيط سلوكي)</b>\n• 3 أنشطة صغيرة اليوم (ممتع/نافع/اجتماعي)\n• ابدأ بـ10-20د\n• قيّم المزاج قبل/بعد.",
    "breath":
        "<b>تنفّس مهدّئ</b>\nاجلس وظهرك معتدل: شهيق 4 ثوانٍ، حبس 2، زفير 6 — كرر 10 مرات ببطء."
}

# ========= تشخيص تعليمي (مسار مبسّط) =========
DIAG = {}  # {uid: step}
def diag_start(chat_id, uid):
    DIAG[uid]=1
    send(chat_id,
         "تشخيص <b>تعليمي</b> مبسّط (ليس تشخيصًا طبيًا).\n"
         "س١) هل مررتَ بنوبات هلع مفاجئة متكررة آخر شهر؟",
         inline([[{"text":"نعم","callback_data":"dx:y1"},{"text":"لا","callback_data":"dx:n1"}]]))

def diag_next(chat_id, uid, step, yes):
    if step==1:
        DIAG[uid]=2
        msg = "س٢) خلال أسبوعين ماضيين: مزاج منخفض أو فقدان متعة معظم الأيام؟"
        send(chat_id, msg, inline([[{"text":"نعم","callback_data":"dx:y2"},{"text":"لا","callback_data":"dx:n2"}]])); return
    if step==2:
        DIAG[uid]=3
        msg = "س٣) قلق مفرط صعب السيطرة عليه معظم الأيام لستة أشهر مع توتر/أرق؟"
        send(chat_id, msg, inline([[{"text":"نعم","callback_data":"dx:y3"},{"text":"لا","callback_data":"dx:n3"}]])); return
    if step==3:
        # توصية
        DIAG.pop(uid, None)
        rec=[]
        if yes.get(1): rec.append("• خذ <b>اختبار نوبات الهلع (PDSS-SR)</b> ثم راجع التثقيف الخاص بالهلع.")
        if yes.get(2): rec.append("• خذ <b>PHQ-9</b> (اكتئاب) وابدأ بالتنشيط السلوكي.")
        if yes.get(3): rec.append("• خذ <b>GAD-7</b> (قلق) وجرّب تمارين التنفّس.")
        if not rec: rec.append("• نتيجتك لا تشير لنمط محدد هنا. استخدم قائمة <b>التثقيف</b> واختر ما يناسبك.")
        send(chat_id, "خلاصة تعليمية:\n" + "\n".join(rec), reply_kb())

# ========= الذكاء الاصطناعي =========
def ai_ready(): return bool(AI_BASE_URL and AI_API_KEY and AI_MODEL)
AI_SESS = {}  # {uid: messages}
SYSTEM_PROMPT = (
    "أنت «عربي سايكو»، مساعد نفسي تعليمي بالعربية. "
    "قدّم دعمًا عامًّا وتقنيات CBT البسيطة وتثقيفًا موجزًا. "
    "لا تُجري تشخيصًا طبيًا ولا تعطي تعليمات دوائية. "
    "إن ظهرت مؤشرات خطر (إيذاء النفس/الآخرين) فذكّر بطلب مساعدة فورية."
)

def ai_call(messages, max_tokens=220):
    url = AI_BASE_URL + "/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type":"application/json"}
    body = {"model": AI_MODEL, "messages": messages, "temperature": 0.4, "max_tokens": max_tokens}
    r = requests.post(url, headers=headers, json=body, timeout=30)
    if r.status_code == 402:
        # رصيد غير كافٍ
        raise RuntimeError("CREDITS:402")
    if r.status_code != 200:
        raise RuntimeError(f"AI {r.status_code}: {r.text[:300]}")
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

def ai_start(chat_id, uid):
    if not ai_ready():
        send(chat_id,
             "ميزة الذكاء الاصطناعي غير مفعّلة.\n"
             "أضف المفاتيح: AI_BASE_URL / AI_API_KEY / AI_MODEL ثم أعد النشر.",
             reply_kb()); return
    AI_SESS[uid] = [{"role":"system","content":SYSTEM_PROMPT}]
    send(chat_id,
         "بدأنا جلسة <b>عربي سايكو</b> 🤖\n"
         "اكتب سؤالك عن القلق/النوم/CBT…\n"
         "لإنهاء الجلسة: اكتب <code>انهاء</code>.",
         reply_kb())

def ai_handle(chat_id, uid, user_text):
    if crisis_guard(user_text):
        send(chat_id, "سلامتك أهم. إن راودتك أفكار لإيذاء نفسك فاتصل بالطوارئ فورًا أو تحدث لشخص موثوق.", reply_kb()); return
    msgs = AI_SESS.get(uid) or [{"role":"system","content":SYSTEM_PROMPT}]
    msgs = msgs[-16:]
    msgs.append({"role":"user","content": user_text})
    # محاولة مع تقليل المدى إن لزم
    for mt in (220, 140, 96, 64):
        try:
            reply = ai_call(msgs, max_tokens=mt)
            msgs.append({"role":"assistant","content":reply})
            AI_SESS[uid] = msgs[-18:]
            send(chat_id, reply, reply_kb())
            return
        except RuntimeError as e:
            if "CREDITS:402" in str(e):
                continue  # جرّب بمدى أصغر
            send(chat_id, f"تعذَّر الاتصال بالذكاء الاصطناعي.\n{e}", reply_kb())
            return
    send(chat_id,
         "يبدو أن الرصيد قليل، حاول رسالة أقصر أو اشحن رصيد OpenRouter.\n"
         "تم تقليل طول الردود تلقائيًا.", reply_kb())

def ai_end(chat_id, uid):
    AI_SESS.pop(uid, None)
    send(chat_id, "تم إنهاء جلسة عربي سايكو ✅", reply_kb())

# ========= المسارات =========
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

    # === أزرار كولباك ===
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

        if data.startswith("ed:"):
            topic = data.split(":",1)[1]
            send(chat_id, f"<b>{topic}</b>\n{EDU.get(topic,'')}", reply_kb()); return "ok", 200

        if data.startswith("dx:"):
            # تشخيص تعليمي
            ans = data.split(":",1)[1]
            step = int(ans[-1])
            yes = {"y":True,"n":False}[ans[0]]
            # خزّن الإجابات
            store = getattr(diag_next, "_ans", {})
            user = store.get(uid, {})
            user[step] = (ans[0]=="y")
            store[uid]=user
            setattr(diag_next, "_ans", store)
            diag_next(chat_id, uid, step, user)
            return "ok", 200

        return "ok", 200

    # === رسائل ===
    msg = upd.get("message") or upd.get("edited_message") or {}
    if not msg: return "ok", 200
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    norm = text.replace("أ","ا").replace("إ","ا").replace("آ","ا").lower()
    uid = msg.get("from",{}).get("id")

    # أوامر مساعدة
    if is_cmd(text,"start"):
        send(chat_id, "مرحبًا! كيف نبدأ اليوم؟ إليك بعض الخيارات:\n"
                      "1) <b>التعامل مع القلق:</b> ناقش موقفك وسنساعدك في تحليل الأفكار.\n"
                      "2) <b>تحسين المزاج:</b> تمارين سلوكية بسيطة.\n\n" + ABOUT,
             reply_kb()); return "ok", 200
    if is_cmd(text,"menu"):
        send(chat_id, "القائمة:", reply_kb()); return "ok", 200
    if is_cmd(text,"help"):
        send(chat_id, HELP, reply_kb()); return "ok", 200
    if is_cmd(text,"tests"):
        tests_menu(chat_id); return "ok", 200
    if is_cmd(text,"cbt"):
        cbt_menu(chat_id); return "ok", 200
    if is_cmd(text,"whoami"):
        uid2 = msg.get("from",{}).get("id")
        send(chat_id, f"chat_id: {chat_id}\nuser_id: {uid2}", reply_kb()); return "ok", 200

    # جلسة الذكاء الاصطناعي نشطة؟
    if uid in AI_SESS and norm != "انهاء":
        ai_handle(chat_id, uid, text); return "ok", 200
    if uid in AI_SESS and norm == "انهاء":
        ai_end(chat_id, uid); return "ok", 200

    # أزرار القاع بالنص
    if "اختبارات" in text:   tests_menu(chat_id); return "ok", 200
    if "العلاج السلوكي" in text: cbt_menu(chat_id); return "ok", 200
    if "التثقيف" in text:     edu_menu(chat_id); return "ok", 200
    if "نوم" == norm or text=="نوم":
        send(chat_id, THERAPY["sleep"], reply_kb()); return "ok", 200
    if "حزن" in text:
        send(chat_id, THERAPY["sad"], reply_kb()); return "ok", 200
    if "تنفس" in norm or "تنفّس" in text:
        send(chat_id, THERAPY["breath"], reply_kb()); return "ok", 200
    if text in ("قلق","اكتب قلق"):
        send(chat_id, "لإدارة القلق: جرّب تنفّس 4-7-8، ونظّم نومك. خذ <b>GAD-7</b> من «اختبارات».", reply_kb()); return "ok", 200
    if text in ("اكتئاب","اكتب اكتئاب"):
        send(chat_id, "لتحسين المزاج: التنشيط السلوكي + تواصل اجتماعي. خذ <b>PHQ-9</b> من «اختبارات».", reply_kb()); return "ok", 200
    if "عربي سايكو" in text and "عن" not in text:
        ai_start(chat_id, uid); return "ok", 200
    if "عن عربي سايكو" in text:
        send(chat_id, ABOUT, reply_kb()); return "ok", 200
    if "تشخيص تعليمي" in text:
        diag_start(chat_id, uid); return "ok", 200
    if "مساعدة" in text:
        send(chat_id, HELP + "\n\n" + ABOUT, reply_kb()); return "ok", 200
    if "تواصل" in text:
        send(chat_id, "تم تسجيل طلب تواصل ✅ سنرجع لك قريبًا." + (f"\nالهاتف: {CONTACT_PHONE}" if CONTACT_PHONE else ""), reply_kb())
        if ADMIN_CHAT_ID:
            user = msg.get("from", {})
            username = user.get("username") or (user.get("first_name","")+" "+user.get("last_name","")).strip() or "مستخدم"
            info = (f"📩 <b>طلب تواصل</b>\n"
                    f"👤 {username} (id={uid})\n"
                    f"💬 الرسالة: {text}")
            send(ADMIN_CHAT_ID, info, reply_kb())
        return "ok", 200

    # افتراضي: رد ترحيبي بسيط
    send(chat_id, "اكتب «القائمة» أو استخدم الأزرار بالأسفل.", reply_kb())
    return "ok", 200


# ====== تشغيل محلي (اختياري) ======
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
