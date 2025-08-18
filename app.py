# app.py — Arabi Psycho Telegram Bot (Tests + DSM Educational + CBT + Psychoeducation + AI Chat)
import os, logging, json
from flask import Flask, request, jsonify
import requests

# =============== إعدادات عامة ===============
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

WEBHOOK_SECRET      = os.environ.get("WEBHOOK_SECRET", "secret")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")

# إشراف وترخيص
SUPERVISOR_NAME  = os.environ.get("SUPERVISOR_NAME",  "المشرف")
SUPERVISOR_TITLE = os.environ.get("SUPERVISOR_TITLE", "أخصائي نفسي")
LICENSE_NO       = os.environ.get("LICENSE_NO",       "—")
LICENSE_ISSUER   = os.environ.get("LICENSE_ISSUER",   "—")
CLINIC_URL       = os.environ.get("CLINIC_URL",       "")
CONTACT_PHONE    = os.environ.get("CONTACT_PHONE",    "")

# إشعارات “تواصل” (اختياري)
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

# مزود الذكاء الاصطناعي (متوافق مع OpenAI)
AI_BASE_URL = (os.environ.get("AI_BASE_URL", "") or "").rstrip("/")
AI_API_KEY  = os.environ.get("AI_API_KEY",  "")
AI_MODEL    = os.environ.get("AI_MODEL",    "")   # مثال: openrouter/anthropic/claude-3-haiku

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho-bot")


# =============== توابع تيليجرام ===============
def tg(method, payload):
    r = requests.post(f"{BOT_API}/{method}", json=payload, timeout=15)
    if r.status_code != 200:
        log.warning("TG %s -> %s | %s", method, r.status_code, r.text[:300])
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

def inline(rows):
    return {"inline_keyboard": rows}

def reply_kb():
    # لوحة أزرار سفلية ثابتة
    return {
        "keyboard": [
            [{"text":"العلاج السلوكي"}, {"text":"اختبارات"}],
            [{"text":"التثقيف"}, {"text":"تشخيص تعليمي"}],
            [{"text":"نوم"}, {"text":"حزن"}],
            [{"text":"قلق"}, {"text":"اكتئاب"}],
            [{"text":"تنفّس"}, {"text":"عربي سايكو"}],
            [{"text":"تواصل"}, {"text":"عن عربي سايكو"}],
            [{"text":"مساعدة"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

def is_cmd(txt, name): 
    return (txt or "").strip().lower().startswith("/"+name.lower())

def norm_ar(s):
    return (s or "").replace("أ","ا").replace("إ","ا").replace("آ","ا").strip().lower()


# =============== سلامة وأزمات ===============
CRISIS_WORDS = ["انتحار","اذي نفسي","اودي نفسي","اودي ذاتي","قتل نفسي","ما ابغى اعيش"]
def crisis_guard(text):
    t = norm_ar(text)
    return any(w in t for w in CRISIS_WORDS)


# =============== نص النظام للذكاء الاصطناعي ===============
SYSTEM_PROMPT = (
    "أنت مساعد نفسي عربي يقدم تثقيفًا ودعمًا عامًّا وتقنيات CBT البسيطة."
    " تعمل بإشراف {name} ({title})، ترخيص {lic_no} – {lic_issuer}."
    " هذا البوت ليس بديلًا عن التشخيص أو وصف الأدوية. كن دقيقًا، متعاطفًا، ومختصرًا."
    " في حال خطر على السلامة وجّه فورًا لطلب مساعدة طبية عاجلة."
).format(
    name=SUPERVISOR_NAME, title=SUPERVISOR_TITLE,
    lic_no=LICENSE_NO, lic_issuer=LICENSE_ISSUER
)

def ai_ready():
    return bool(AI_BASE_URL and AI_API_KEY and AI_MODEL)

def ai_call(messages):
    """POST {AI_BASE_URL}/v1/chat/completions (واجهة متوافقة مع OpenAI)"""
    url = AI_BASE_URL + "/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 220  # أقل للاقتصاد بالرصد
    }
    r = requests.post(url, headers=headers, json=body, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"AI {r.status_code}: {r.text[:300]}")
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

AI_SESS = {}  # {uid: [messages...]}

def ai_start(chat_id, uid):
    if not ai_ready():
        send(chat_id, "ميزة <b>عربي سايكو</b> غير مفعّلة (أكمل إعدادات AI).", reply_kb()); return
    AI_SESS[uid] = [{"role":"system","content": SYSTEM_PROMPT}]
    send(chat_id,
         f"بدأنا جلسة <b>عربي سايكو</b> 🤖 بإشراف {SUPERVISOR_NAME} ({SUPERVISOR_TITLE}).\n"
         "اكتب سؤالك عن النوم/القلق/CBT…\n"
         "لإنهاء الجلسة: اكتب <code>انهاء</code>.",
         reply_kb())

def ai_end(chat_id, uid):
    AI_SESS.pop(uid, None)
    send(chat_id, "تم إنهاء جلسة عربي سايكو ✅", reply_kb())

def ai_handle(chat_id, uid, user_text):
    if crisis_guard(user_text):
        send(chat_id,
             "أقدّر شعورك، وسلامتك أهم شيء الآن.\n"
             "إن وُجدت أفكار لإيذاء النفس فاتصل بالطوارئ فورًا أو توجّه لأقرب طوارئ.",
             reply_kb()); return
    msgs = AI_SESS.get(uid) or [{"role":"system","content": SYSTEM_PROMPT}]
    msgs = msgs[-16:]
    msgs.append({"role":"user","content": user_text})
    try:
        reply = ai_call(msgs)
    except Exception as e:
        send(chat_id,
             "يتعذّر الاتصال بالذكاء الاصطناعي.\n"
             f"{e}\nتم تقليل طول الردود تلقائيًا. جرّب لاحقًا أو اشحن رصيد OpenRouter.",
             reply_kb()); return
    msgs.append({"role":"assistant","content": reply})
    AI_SESS[uid] = msgs[-18:]
    send(chat_id, reply, reply_kb())


# =============== اختبارات نفسية (GAD-7 / PHQ-9) ===============
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
    "الشعور بتدنّي تقدير الذات أو الذنب",
    "صعوبة التركيز",
    "الحركة/الكلام ببطء شديد أو بعصبية زائدة",
    "أفكار بأنك ستكون أفضل حالًا لو لم تكن موجودًا"
]
TESTS = {"g7":{"name":"مقياس القلق GAD-7","q":G7}, "phq":{"name":"مقياس الاكتئاب PHQ-9","q":PHQ9}}

SESS_TEST = {}  # {uid: {"key":, "i":, "score":}}

def tests_menu(chat_id):
    send(chat_id, "اختر اختبارًا:", inline([
        [{"text":"اختبار القلق (GAD-7)","callback_data":"t:g7"}],
        [{"text":"اختبار الاكتئاب (PHQ-9)","callback_data":"t:phq"}],
    ]))

def test_start(chat_id, uid, key):
    data = TESTS[key]
    SESS_TEST[uid] = {"key":key, "i":0, "score":0}
    send(chat_id, f"سنبدأ: <b>{data['name']}</b>\nأجب حسب آخر أسبوعين.", reply_kb())
    test_ask(chat_id, uid)

def test_ask(chat_id, uid):
    st = SESS_TEST.get(uid)
    if not st: return
    key, i = st["key"], st["i"]; qs = TESTS[key]["q"]
    if i >= len(qs):
        score = st["score"]; total = len(qs)*3
        send(chat_id, f"النتيجة: <b>{score}</b> من {total}\n{test_interpret(key,score)}", reply_kb())
        SESS_TEST.pop(uid, None); return
    q = qs[i]
    send(chat_id, f"س{ i+1 }: {q}", inline([
        [{"text":ANS[0][0],"callback_data":"qa0"}, {"text":ANS[1][0],"callback_data":"qa1"}],
        [{"text":ANS[2][0],"callback_data":"qa2"}, {"text":ANS[3][0],"callback_data":"qa3"}],
    ]))

def test_record(chat_id, uid, idx):
    st = SESS_TEST.get(uid)
    if not st: return
    st["score"] += ANS[idx][1]
    st["i"] += 1
    test_ask(chat_id, uid)

def test_interpret(key, score):
    if key=="g7":
        lvl = "ضئيل" if score<=4 else ("خفيف" if score<=9 else ("متوسط" if score<=14 else "شديد"))
        return f"<b>مؤشرات قلق {lvl}</b> (تعليمي).\nنصيحة: تنفّس ببطء، قلّل الكافيين، وثبّت نومك."
    if key=="phq":
        if score<=4: lvl="ضئيل"
        elif score<=9: lvl="خفيف"
        elif score<=14: lvl="متوسط"
        elif score<=19: lvl="متوسط إلى شديد"
        else: lvl="شديد"
        return f"<b>مؤشرات اكتئاب {lvl}</b> (تعليمي).\nنصيحة: تنشيط سلوكي + روتين نوم + تواصل اجتماعي."
    return "تم."


# =============== “تشخيص تعليمي” DSM-5 (مبسّط) ===============
# — تنبيه: النتائج تعليمية وليست تشخيصًا طبيًا —
DSM_SESS = {}  # {uid: {"key":, "i":, "hits":, "flags":{...}}}

MDD_SYMPTOMS = [
    ("مزاج مكتئب معظم اليوم", "mood"),
    ("فقدان الاهتمام أو المتعة بمعظم الأنشطة", "anhedonia"),
    ("تغير ملحوظ في الوزن/الشهية", "appetite"),
    ("أرق أو نوم مفرط تقريبًا يوميًا", "sleep"),
    ("تباطؤ حركي أو توتر زائد ملحوظ", "psychomotor"),
    ("إرهاق أو فقدان الطاقة", "fatigue"),
    ("مشاعر ذنب مفرطة أو عديمة القيمة", "guilt"),
    ("ضعف التركيز أو التردد", "concentration"),
    ("أفكار متكررة عن الموت/إيذاء النفس", "si"),
]
GAD_SYMPTOMS = [
    ("توتر/استثارة بسهولة", "irritable"),
    ("إجهاد/إرهاق سريع", "fatigue"),
    ("صعوبة التركيز أو شرود الذهن", "focus"),
    ("شدّ عضلي", "muscle"),
    ("اضطراب النوم", "sleep"),
    ("تململ/شعور داخلي بعدم الارتياح", "restless"),
]

def dsm_menu(chat_id):
    send(chat_id, "اختر فحصًا تعليميًا (DSM-5 مبسّط):", inline([
        [{"text":"اكتئاب (تعليمي)","callback_data":"d:mdd"}],
        [{"text":"قلق عام (تعليمي)","callback_data":"d:gad"}],
        [{"text":"تنبيه هام","callback_data":"d:note"}],
    ]))

def dsm_note(chat_id):
    send(chat_id,
         "هذه الفحوصات <b>تعليمية</b> لمساعدتك على فهم المعايير ولا تُعد تشخيصًا.\n"
         "إن تنطبق عليك مؤشرات كثيرة، فاستشر مختصًا مرخّصًا لتقييم مهني.", reply_kb())

def dsm_start(chat_id, uid, key):
    if key=="mdd":
        DSM_SESS[uid] = {"key":"mdd","i":0,"hits":0,"flags":{"mood":False,"anhedonia":False}}
        send(chat_id, "خلال <b>آخر أسبوعين</b> تقريبًا كل يوم… أجب بـ نعم/لا:", reply_kb())
        dsm_ask(chat_id, uid)
    elif key=="gad":
        DSM_SESS[uid] = {"key":"gad","i":0,"hits":0,"flags":{"duration6m":False}}
        # سؤال مدة القلق أولًا
        send(chat_id, "هل كنت تعاني من قلق وقلقٍ زائد <b>أغلب الأيام لمدة 6 أشهر+</b>؟", inline([
            [{"text":"نعم","callback_data":"dy"}, {"text":"لا","callback_data":"dn"}]
        ]))
    else:
        dsm_note(chat_id)

def dsm_ask(chat_id, uid):
    st = DSM_SESS.get(uid)
    if not st: return
    if st["key"]=="mdd":
        i = st["i"]
        if i >= len(MDD_SYMPTOMS):
            # تفسير تعليمي
            hits = st["hits"]
            mood_ok = st["flags"].get("mood",False) or st["flags"].get("anhedonia",False)
            msg = ["<b>نتيجة تعليمية لا تُعد تشخيصًا:</b>"]
            if hits >= 5 and mood_ok:
                msg.append("قد تنطبق <b>بعض</b> معايير نوبة اكتئاب جسيمة. يُستحسن طلب تقييم مهني.")
            else:
                msg.append("لا تكفي المؤشرات الحالية لمطابقة المعايير بشكل تعليمي.")
            msg.append("لو لديك أفكار إيذاء النفس فاتصل بالطوارئ فورًا.")
            send(chat_id, "\n".join(msg), reply_kb()); DSM_SESS.pop(uid,None); return
        text, code = MDD_SYMPTOMS[i]
        send(chat_id, text, inline([
            [{"text":"نعم","callback_data":"dy"}, {"text":"لا","callback_data":"dn"}]
        ]))
    elif st["key"]=="gad":
        # بعد سؤال المدة، نسأل الأعراض الستة
        i = st["i"]
        if i >= len(GAD_SYMPTOMS):
            hits = st["hits"]; dur = st["flags"].get("duration6m",False)
            msg = ["<b>نتيجة تعليمية لا تُعد تشخيصًا:</b>"]
            if dur and hits >= 3:
                msg.append("قد تنطبق <b>بعض</b> مؤشرات اضطراب القلق العام. يُستحسن طلب تقييم مهني.")
            else:
                msg.append("لا تكفي المؤشرات الحالية لمطابقة المعايير بشكل تعليمي.")
            send(chat_id, "\n".join(msg), reply_kb()); DSM_SESS.pop(uid,None); return
        text, code = GAD_SYMPTOMS[i]
        send(chat_id, text, inline([
            [{"text":"نعم","callback_data":"dy"}, {"text":"لا","callback_data":"dn"}]
        ]))

def dsm_record(chat_id, uid, yes):
    st = DSM_SESS.get(uid)
    if not st: return
    k = st["key"]
    if k=="gad" and st["i"]==0 and "duration6m" in st["flags"] and st["flags"]["duration6m"] is False:
        # هذا حدث لو ضغط قبل أن نهيئ، نتجاهل
        pass
    if k=="gad" and st["flags"].get("duration6m") is False and st["i"]==0 and "asked_duration" not in st["flags"]:
        # أول كبسة بعد سؤال المدة
        st["flags"]["asked_duration"] = True
        st["flags"]["duration6m"] = bool(yes)
        # لا نزيد i هنا؛ نبدأ الأعراض الآن من 0
        dsm_ask(chat_id, uid); return

    if k=="mdd":
        i = st["i"]; text, code = MDD_SYMPTOMS[i]
        if yes:
            st["hits"] += 1
            if code in ("mood","anhedonia"):
                st["flags"][code] = True
        st["i"] += 1
        dsm_ask(chat_id, uid); return

    if k=="gad":
        i = st["i"]; text, code = GAD_SYMPTOMS[i]
        if yes: st["hits"] += 1
        st["i"] += 1
        dsm_ask(chat_id, uid); return


# =============== CBT + تثقيف + بروتوكولات سريعة ===============
CBT_ITEMS = [
    ("أخطاء التفكير", "cd"),
    ("الاجترار والكبت", "rum"),
    ("الأسئلة العشرة", "q10"),
    ("الاسترخاء", "rlx"),
    ("التنشيط السلوكي", "ba"),
    ("اليقظة الذهنية", "mind"),
    ("حل المشكلات", "ps"),
    ("سلوكيات الأمان", "safe"),
]
def cbt_menu(chat_id):
    rows=[]
    for i in range(0,len(CBT_ITEMS),2):
        pair = [{"text":t,"callback_data":"c:"+d} for (t,d) in CBT_ITEMS[i:i+2]]
        rows.append(pair)
    send(chat_id, "اختر موضوع العلاج السلوكي:", inline(rows))

def cbt_text(code):
    if code=="cd":
        return [
            "<b>أخطاء التفكير</b>: الأبيض/الأسود، التعميم، قراءة الأفكار، التنبؤ، التهويل…",
            "الخطوات: ١) التقط الفكرة ٢) الدليل معها/ضدها ٣) صياغة متوازنة."
        ]
    if code=="rum":
        return ["<b>الاجترار والكبت</b>", "سمِّ الفكرة، حدّد «وقت قلق»، حوّل لنشاط بسيط."]
    if code=="q10":
        return ["<b>الأسئلة العشرة</b>", "الدليل؟ البدائل؟ لو صديق مكاني؟ أسوأ/أفضل/أرجح؟ هل أعمّم؟"]
    if code=="rlx":
        return ["<b>الاسترخاء</b>", "تنفّس 4-7-8 ×6. شدّ/إرخ العضلات من القدم للرأس."]
    if code=="ba":
        return ["<b>التنشيط السلوكي</b>", "نشاطان صغيران يوميًا (ممتع/نافع) + قاعدة 5 دقائق + تقييم مزاج قبل/بعد."]
    if code=="mind":
        return ["<b>اليقظة الذهنية</b>", "تمرين 5-4-3-2-1 للحواس. لاحظ من دون حكم."]
    if code=="ps":
        return ["<b>حل المشكلات</b>", "عرّف المشكلة → بدائل → خطة صغيرة SMART → جرّب → قيّم."]
    if code=="safe":
        return ["<b>سلوكيات الأمان</b>", "قلّل الطمأنة/التجنب تدريجيًا مع تعرّض آمن."]
    return ["تم."]

def cbt_send(chat_id, code):
    for t in cbt_text(code):
        send(chat_id, t, reply_kb())

PSYCHOEDU = {
    "anx": [
        "<b>عن القلق</b>",
        "مفيد بقدرٍ معتدل، ويصبح مشكلة عند الاستمرار والشدّة.",
        "عوامل مساعدة: تقليل كافيين، نشاط بدني، نوم منتظم، تعرّض تدريجي للمواقف."
    ],
    "dep": [
        "<b>عن الاكتئاب</b>",
        "يمسّ المزاج والطاقة والنوم والشهية.",
        "المفيد: تنشيط سلوكي، تواصل اجتماعي، هيكلة اليوم، طلب دعم مهني عند الشدة."
    ],
    "sleep": [
        "<b>نظافة النوم</b>",
        "ثبّت الاستيقاظ يوميًا، قلّل الشاشات ليلًا، سرير=نوم فقط، طقوس تهدئة 30–45د."
    ],
    "panic": [
        "<b>نوبات الهلع</b>",
        "غير خطرة عادة لكنها مُخيفة. تعلّم التنفس البطيء ومواجهة الأحاسيس تدريجيًا."
    ],
}
def edu_menu(chat_id):
    send(chat_id, "مواضيع التثقيف:", inline([
        [{"text":"القلق","callback_data":"e:anx"}, {"text":"الاكتئاب","callback_data":"e:dep"}],
        [{"text":"نوم","callback_data":"e:sleep"}, {"text":"نوبات الهلع","callback_data":"e:panic"}],
    ]))
def edu_send(chat_id, key):
    for p in PSYCHOEDU.get(key,["تم."]):
        send(chat_id, p, reply_kb())

THERAPY = {
    "sleep":
        "<b>بروتوكول النوم (مختصر)</b>\n• ثبّت الاستيقاظ يوميًا\n• قلّل الشاشات مساءً\n• طقوس تهدئة 30–45د\n• سرير=نوم فقط\n• لو ما نمت خلال 20د اخرج لنشاط هادئ وارجع.",
    "sad":
        "<b>علاج الحزن (تنشيط سلوكي)</b>\n• 3 أنشطة صغيرة اليوم (ممتع/نافع/اجتماعي)\n• ابدأ بـ10–20د\n• قيّم المزاج قبل/بعد.",
    "anx":
        "<b>قلق (سريع)</b>\n• تنفّس 4-4-6 ×10\n• قائمة مواقف مخيفة → تدرّج\n• قلّل الطمأنة والقهوة."
}


# =============== صفحات وويبهوك ===============
@app.get("/")
def home():
    return jsonify({
        "app": "Arabi Psycho Telegram Bot",
        "public_url": RENDER_EXTERNAL_URL,
        "webhook": f"/webhook/{WEBHOOK_SECRET[:3]}*****",
        "ai_ready": ai_ready(),
        "supervisor": {
            "name": SUPERVISOR_NAME, "title": SUPERVISOR_TITLE,
            "license": f"{LICENSE_NO} – {LICENSE_ISSUER}"
        }
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

    # ==== Callback ====
    if "callback_query" in upd:
        cq   = upd["callback_query"]
        data = cq.get("data","")
        chat_id = cq["message"]["chat"]["id"]
        uid     = cq["from"]["id"]

        # اختبارات
        if data.startswith("t:"):
            key = data.split(":",1)[1]
            if key in TESTS: test_start(chat_id, uid, key)
            else: send(chat_id, "اختبار غير معروف.", reply_kb())
            return "ok", 200
        if data.startswith("qa"):
            try:
                idx = int(data[2:])
                if 0 <= idx <= 3: test_record(chat_id, uid, idx)
            except: send(chat_id, "إجابة غير صالحة.", reply_kb())
            return "ok", 200

        # CBT
        if data.startswith("c:"):
            c = data.split(":",1)[1]
            cbt_send(chat_id, c);  return "ok", 200

        # تثقيف
        if data.startswith("e:"):
            k = data.split(":",1)[1]
            edu_send(chat_id, k); return "ok", 200

        # DSM تعليمي
        if data.startswith("d:"):
            k = data.split(":",1)[1]
            if k=="note": dsm_note(chat_id)
            else: dsm_start(chat_id, uid, k)
            return "ok", 200
        if data in ("dy","dn"):
            dsm_record(chat_id, uid, data=="dy"); return "ok", 200

        return "ok", 200

    # ==== Messages ====
    msg = upd.get("message") or upd.get("edited_message") or {}
    if not msg: return "ok", 200
    chat_id = msg["chat"]["id"]
    text    = (msg.get("text") or "").strip()
    low     = norm_ar(text)
    uid     = msg.get("from",{}).get("id")

    # جلسة AI فعّالة؟
    if uid in AI_SESS and low != "انهاء":
        ai_handle(chat_id, uid, text);  return "ok", 200
    if low == "انهاء":
        ai_end(chat_id, uid); return "ok", 200

    # أوامر
    if is_cmd(text, "start"):
        start_msg(chat_id); return "ok", 200
    if is_cmd(text, "menu"):
        send(chat_id, "القائمة:", reply_kb()); return "ok", 200
    if is_cmd(text, "help"):
        send(chat_id,
             "الأوامر: /menu للأزرار • /tests للاختبارات • /cbt للعلاج السلوكي • /about للمعلومات.\n"
             "اكتب: عربي سايكو لبدء محادثة الذكاء الاصطناعي.",
             reply_kb()); return "ok", 200
    if is_cmd(text, "tests"):
        tests_menu(chat_id); return "ok", 200
    if is_cmd(text, "cbt"):
        cbt_menu(chat_id); return "ok", 200
    if is_cmd(text, "about"):
        about_msg(chat_id); return "ok", 200
    # فحص إعدادات AI (للاختبار)
    if is_cmd(text, "ai_diag"):
        send(chat_id, f"ai_ready={ai_ready()} | BASE={bool(AI_BASE_URL)} | KEY={bool(AI_API_KEY)} | MODEL={AI_MODEL or '-'}")
        return "ok", 200

    # تواصل
    if low in ("تواصل","تواصل.","طلب تواصل"):
        user = msg.get("from",{})
        username = user.get("username") or (user.get("first_name","")+" "+user.get("last_name","")).strip() or "مستخدم"
        send(chat_id, "تم تسجيل طلب تواصل ✅ سنرجع لك قريبًا.", reply_kb())
        if ADMIN_CHAT_ID:
            info = (f"📩 طلب تواصل\n"
                    f"اسم: {username} (user_id={user.get('id')})\n"
                    f"نص: {(text or '')}")
            tg("sendMessage", {"chat_id": ADMIN_CHAT_ID, "text": info})
        return "ok", 200

    # أزرار سريعة بالنص
    if low in ("اختبارات",):
        tests_menu(chat_id); return "ok", 200
    if low in ("العلاج السلوكي","علاج سلوكي"):
        cbt_menu(chat_id); return "ok", 200
    if low in ("التثقيف",):
        edu_menu(chat_id); return "ok", 200
    if low in ("تشخيص تعليمي","التشخيص التعليمي","تشخيص"):
        dsm_menu(chat_id); return "ok", 200

    if low in ("نوم",):
        send(chat_id, THERAPY["sleep"], reply_kb()); return "ok", 200
    if low in ("حزن",):
        send(chat_id, THERAPY["sad"], reply_kb()); return "ok", 200
    if low in ("قلق",):
        send(chat_id, THERAPY["anx"], reply_kb()); return "ok", 200
    if low in ("اكتئاب",):
        send(chat_id, "للاكتئاب: جرّب التنشيط السلوكي وتواصلًا اجتماعيًا خفيفًا. ويمكنك إجراء PHQ-9 من زر «اختبارات».", reply_kb()); return "ok", 200
    if low in ("تنفس","تنفّس"):
        send(chat_id, "تنفّس 4-4-6 ×10: شهيق 4، حبس 4، زفير 6. كرّر ببطء.", reply_kb()); return "ok", 200

    if low in ("عربي سايكو","ذكاء اصطناعي","ايه اي","arabipsycho","arabi psycho"):
        ai_start(chat_id, uid); return "ok", 200

    if low in ("عن عربي سايكو","عن","about arabi"):
        about_msg(chat_id); return "ok", 200

    if low in ("مساعدة","help","?"):
        send(chat_id,
             "أنا مساعد نفسي للتثقيف والدعم العام.\n"
             "جرّب: «اختبارات»، «العلاج السلوكي»، «التثقيف»، «تشخيص تعليمي»، أو «عربي سايكو».",
             reply_kb()); return "ok", 200

    # افتراضي: ردّ موجّه
    if ai_ready():
        send(chat_id, "أكتب «عربي سايكو» لبدء محادثة ذكية، أو /menu لعرض الأزرار.", reply_kb())
    else:
        send(chat_id, "اكتب /menu لعرض الأزرار.", reply_kb())
    return "ok", 200


# =============== رسائل ثابتة ===============
def start_msg(chat_id):
    about_msg(chat_id)
    send(chat_id,
         "أوامر سريعة: /menu • /tests • /cbt • /about\n"
         "زر «عربي سايكو» لبدء محادثة بالذكاء الاصطناعي.",
         reply_kb())

def about_msg(chat_id):
    lines = [
        "<b>عربي سايكو</b> 🤖",
        f"يشغَّل بإشراف {SUPERVISOR_NAME} ({SUPERVISOR_TITLE})",
        f"الترخيص: {LICENSE_NO} – {LICENSE_ISSUER}",
        "الغرض: تثقيف ودعم عام (CBT) — ليس بديلًا عن تشخيص أو وصفة دوائية.",
        "للطوارئ: تواصل مع الجهات المختصة فورًا."
    ]
    if CONTACT_PHONE: lines.append(f"رقم التواصل: {CONTACT_PHONE}")
    if CLINIC_URL:    lines.append(f"الموقع: {CLINIC_URL}")
    send(chat_id, "\n".join(lines), reply_kb())


# =============== تشغيل محلي ===============
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
