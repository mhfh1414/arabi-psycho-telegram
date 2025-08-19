# app.py — Arabi Psycho (Clean Menu: AI Chat inside 'Arabi Psycho' only)
import os, logging
from flask import Flask, request, jsonify
import requests

# -------- Config --------
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

WEBHOOK_SECRET      = os.environ.get("WEBHOOK_SECRET", "secret")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
ADMIN_CHAT_ID       = os.environ.get("ADMIN_CHAT_ID", "")
CONTACT_PHONE       = os.environ.get("CONTACT_PHONE", "")

# AI (OpenAI-compatible مثل OpenRouter) — اختياري
AI_BASE_URL = (os.environ.get("AI_BASE_URL","") or "").rstrip("/")
AI_API_KEY  = os.environ.get("AI_API_KEY","")
AI_MODEL    = os.environ.get("AI_MODEL","")
def ai_ready(): return bool(AI_BASE_URL and AI_API_KEY and AI_MODEL)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho")

# -------- Helpers --------
def tg(method, payload):
    r = requests.post(f"{BOT_API}/{method}", json=payload, timeout=20)
    if r.status_code != 200:
        log.warning("TG %s -> %s | %s", method, r.status_code, r.text[:300])
    return r

def send(cid, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": cid, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True}
    if reply_markup: payload["reply_markup"] = reply_markup
    return tg("sendMessage", payload)

def inline(rows): return {"inline_keyboard": rows}

def menu_kb():
    # ثلاث أزرار فقط — لا تكرار
    return {
        "keyboard": [
            [{"text": "🧠 عربي سايكو"}],
            [{"text": "💊 العلاج السلوكي المعرفي (CBT)"}],
            [{"text": "📝 الاختبارات النفسية"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

def is_cmd(txt, name): return (txt or "").strip().lower().startswith("/"+name)
def norm(s): return (s or "").replace("أ","ا").replace("إ","ا").replace("آ","ا").strip().lower()

# -------- Safety --------
CRISIS_WORDS = ["انتحار", "اذي نفسي", "قتل نفسي", "ما ابغى اعيش", "لا اريد العيش"]
def crisis_guard(text): return any(w in norm(text) for w in CRISIS_WORDS)

# -------- Intro --------
INTRO = (
    "مرحبًا! هذه قائمتك الرئيسية:\n"
    "• 🧠 <b>عربي سايكو</b>: تعريف سريع + المساعدة + التواصل، ثم <i>تفضل وابدأ شكواك الآن</i>.\n"
    "• 💊 <b>العلاج السلوكي المعرفي (CBT)</b>: بطاقات عملية قصيرة.\n"
    "• 📝 <b>الاختبارات النفسية</b>: قلق/اكتئاب/هلع.\n\n"
    "<b>تنبيه مهم:</b> لستُ بديلاً عن التشخيص أو العلاج لدى مختص. المشروع تحت إشراف "
    "<b>أخصائي نفسي مرخّص</b>."
)

# -------- CBT --------
CBT_INTRO = (
    "🧠 <b>العلاج السلوكي المعرفي (CBT)</b>\n"
    "يربط <b>الأفكار ↔ المشاعر ↔ السلوك</b> بخطوات عملية قصيرة. ابدأ ببطاقة وطبّق 5–10 دقائق."
)
CBT_CARDS = [
    ("سجلّ الأفكار",
     "١) الموقف والمشاعر.\n٢) الفكرة التلقائية.\n٣) أدلة مع/ضد.\n٤) صياغة متوازنة.\n٥) قيّم الانزعاج (0–10) قبل/بعد."),
    ("أخطاء التفكير",
     "الأبيض/الأسود، التعميم، قراءة الأفكار، التنبؤ، التهويل/التقليل… اسأل: ما البديل الواقعي المتوازن؟"),
    ("الأسئلة العشرة",
     "الدليل؟ البدائل؟ أسوأ/أفضل/أرجح؟ لو صديق مكاني؟ هل أتجاهل الإيجابي؟"),
    ("التعرّض التدريجي (قلق/هلع)",
     "اكتب سلّم 0–10. ابدأ من 3–4/10: تعرّض آمن بلا طمأنة/هروب حتى يهبط القلق، ثم اصعد درجة."),
    ("التنشيط السلوكي (مزاج)",
     "نشاط ممتع صغير + نافع صغير يوميًا. قاعدة 5 دقائق. سجّل المزاج قبل/بعد."),
    ("الاسترخاء والتنفس",
     "تنفّس 4–7–8 ×6. شد/إرخِ العضلات من القدم للرأس: 5 ثوان شد ثم 10 ثوان إرخاء."),
    ("اليقظة الذهنية",
     "تمرين 5–4–3–2–1 للحواس: ارجع للحاضر بلطف وبدون حكم."),
    ("حلّ المشكلات",
     "عرّف المشكلة بدقة → بدائل صغيرة → خطوة SMART → جرّب → قيّم وعدّل."),
    ("بروتوكول النوم",
     "ثبّت الاستيقاظ يوميًا، سرير=نوم فقط، طقوس تهدئة 30–45د، قلّل الكافيين مساءً."),
]
def cbt_menu(cid):
    send(cid, CBT_INTRO, menu_kb())
    rows = [[{"text": t, "callback_data": "cbt:"+t}] for (t,_) in CBT_CARDS]
    send(cid, "اختر بطاقة من العلاج السلوكي:", inline(rows))
def cbt_send(cid, title):
    for (t, body) in CBT_CARDS:
        if t == title:
            send(cid, f"<b>{t}</b>\n{body}", menu_kb()); break

# -------- Tests --------
ANS4 = [("أبدًا",0), ("عدة أيام",1), ("أكثر من النصف",2), ("تقريبًا يوميًا",3)]
ANS5 = [("0",0), ("1",1), ("2",2), ("3",3), ("4",4)]
GAD7 = ["التوتر/العصبية أو الشعور بالقلق","عدم القدرة على التوقف عن القلق أو السيطرة عليه",
        "الانشغال بالهموم بدرجة كبيرة","صعوبة الاسترخاء","تململ/صعوبة الجلوس بهدوء",
        "الانزعاج بسرعة أو العصبية","الخوف من حدوث شيء سيئ"]
PHQ9 = ["قلة الاهتمام أو المتعة","الحزن/اليأس","مشاكل النوم","قلة الطاقة",
        "الشهية (ضعف/زيادة)","الشعور بالذنب/عدم القيمة","صعوبة التركيز",
        "بطء/توتر بالحركة أو الكلام","أفكار أنك أفضل لو لم تكن موجودًا"]
PANIC7 = ["عدد نوبات الهلع","شدة أعراض النوبة","القلق الاستباقي","التجنّب",
          "التأثير على العمل/الدراسة","التأثير على العلاقات/الخروج","سلوكيات الأمان"]

TESTS = {
    "g7":   {"name":"اختبار القلق (GAD-7)","q":GAD7,   "ans":ANS4,"max":21},
    "phq":  {"name":"اختبار الاكتئاب (PHQ-9)","q":PHQ9,"ans":ANS4,"max":27},
    "panic":{"name":"مقياس الهلع (PDSS-SR مبسّط)","q":PANIC7,"ans":ANS5,"max":28},
}
SESS = {}  # {uid: {"key":, "i":, "score":}}

def tests_menu(cid):
    rows = [
        [{"text":"اختبار القلق (GAD-7)", "callback_data":"t:g7"}],
        [{"text":"اختبار الاكتئاب (PHQ-9)", "callback_data":"t:phq"}],
        [{"text":"مقياس الهلع (PDSS-SR)", "callback_data":"t:panic"}],
    ]
    send(cid, "اختر اختبارًا:", inline(rows))

def start_test(cid, uid, key):
    SESS[uid] = {"key":key, "i":0, "score":0}
    send(cid, f"سنبدأ: <b>{TESTS[key]['name']}</b>\nأجب بحسب آخر أسبوعين.", menu_kb())
    ask_next(cid, uid)

def ask_next(cid, uid):
    st = SESS.get(uid); 
    if not st: return
    key, i = st["key"], st["i"]; qs = TESTS[key]["q"]; ans = TESTS[key]["ans"]
    if i >= len(qs):
        score = st["score"]; total = TESTS[key]["max"]
        send(cid, f"النتيجة: <b>{score}</b> من {total}\n{interpret(key,score)}", menu_kb())
        SESS.pop(uid, None); return
    rows,row=[],[]
    for idx,(label,_) in enumerate(ans):
        row.append({"text":label,"callback_data":f"a{idx}"})
        if (ans is ANS4 and len(row)==2) or (ans is ANS5 and len(row)==3):
            rows.append(row); row=[]
    if row: rows.append(row)
    send(cid, f"س{ i+1 }: {qs[i]}", inline(rows))

def record_answer(cid, uid, idx):
    st = SESS.get(uid); 
    if not st: return
    key = st["key"]; st["score"] += TESTS[key]["ans"][idx][1]; st["i"] += 1
    ask_next(cid, uid)

def interpret(key, score):
    if key=="g7":
        lvl = "قلق ضئيل" if score<=4 else ("قلق خفيف" if score<=9 else ("قلق متوسط" if score<=14 else "قلق شديد"))
        return f"<b>{lvl}</b> — ابدأ ببطاقات الاسترخاء والتنشيط، ونظّم النوم."
    if key=="phq":
        if score<=4: lvl="ضئيل"
        elif score<=9: lvl="خفيف"
        elif score<=14: lvl="متوسط"
        elif score<=19: lvl="متوسط إلى شديد"
        else: lvl="شديد"
        return f"<b>اكتئاب {lvl}</b> — فعّل التنشيط السلوكي والدعم الاجتماعي، واستشر مختصًا عند الشدة."
    if key=="panic":
        if score<=7: lvl="خفيف"
        elif score<=14: lvl="متوسط"
        elif score<=21: lvl="متوسط إلى شديد"
        else: lvl="شديد"
        return f"<b>هلع {lvl}</b> — تنفّس ببطء، خفّف سلوكيات الأمان، وخطّة تعرّض تدريجي."
    return "تم."

# -------- AI Chat (robust with fallback) --------
AI_SESS = {}  # {uid: {"mode":"ai"|"manual","msgs":[...]}}
SYSTEM_PROMPT = (
    "أنت «عربي سايكو» مساعد نفسي تعليمي بالعربية. قدّم دعمًا عمليًا وتقنيات CBT "
    "بخطوات قصيرة. لا تشخّص طبيًا ولا تقدّم أدوية. عند مؤشرات خطر وجّه لطلب مساعدة فورية."
)

def ai_headers(): return {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type":"application/json"}

def ai_call(messages, max_tokens=150):
    url = AI_BASE_URL + "/v1/chat/completions"
    body = {"model": AI_MODEL, "messages": messages, "temperature": 0.4, "max_tokens": max_tokens}
    r = requests.post(url, headers=ai_headers(), json=body, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"AI {r.status_code}: {r.text[:200]}")
    return r.json()["choices"][0]["message"]["content"].strip()

def manual_reply(text):
    t = norm(text)
    if any(k in t for k in ["نوم","ارق","سهر"]):
        return ("خطة نوم:\n• ثبّت الاستيقاظ يوميًا\n• قلّل الشاشات بعد العشاء\n• طقوس تهدئة 30–45د\n• سرير=نوم فقط\n"
                "• إن لم تنم خلال 20د اخرج لنشاط هادئ وارجع.")
    if any(k in t for k in ["حزن","مزاج","اكتئاب"]):
        return ("تنشيط سلوكي اليوم:\n• نشاط ممتع صغير + نافع صغير\n• قاعدة 5 دقائق\n• قيّم المزاج قبل/بعد.")
    if any(k in t for k in ["قلق","توتر","هلع"]):
        return ("تهدئة القلق:\n• تنفّس 4–7–8 ×6\n• لاحظ الفكرة واسمها ثم ابحث عن بديل متوازن\n• قلّل سلوكيات الأمان وابدأ تعرّضًا تدريجيًا آمنًا.")
    return ("شكرًا لمشاركتك. اكتب الموقف والفكرة التلقائية وسنشتغل على صياغة متوازنة وخطوة سلوكية صغيرة.")

def ai_start(cid, uid):
    intro = (
        "مرحبًا 👋 أنا <b>عربي سايكو</b>.\n"
        "برنامج علاجي نفسي عملي بالذكاء الاصطناعي، تحت إشراف أخصائي نفسي مرخّص.\n\n"
        "أقدّم بطاقات CBT، واختبارات قياسية، ومحادثة داعمة.\n"
        f"{'وسيلة تواصل: <code>'+CONTACT_PHONE+'</code>\n' if CONTACT_PHONE else ''}"
        "تفضل وابدأ شكواك الآن ✍️"
    )
    send(cid, intro, menu_kb())
    AI_SESS[uid] = {"mode": "ai" if ai_ready() else "manual", "msgs": [{"role":"system","content":SYSTEM_PROMPT}] if ai_ready() else []}
    if ADMIN_CHAT_ID:
        try: tg("sendMessage", {"chat_id": int(ADMIN_CHAT_ID), "text": f"بدأ المستخدم {uid} جلسة عربي سايكو."})
        except: pass

def ai_handle(cid, uid, user_text):
    if crisis_guard(user_text):
        send(cid, "سلامتك أولًا. إن راودتك أفكار لإيذاء نفسك اتصل بالطوارئ فورًا وتواصل مع شخص موثوق.", menu_kb()); return
    sess = AI_SESS.get(uid)
    if not sess:
        ai_start(cid, uid); sess = AI_SESS.get(uid)
    if sess["mode"]=="manual":
        send(cid, manual_reply(user_text), menu_kb()); return
    msgs = (sess["msgs"] or [])[-14:]
    msgs.append({"role":"user","content": user_text})
    for mt in (150, 100, 70):
        try:
            reply = ai_call([*msgs], max_tokens=mt)
            msgs.append({"role":"assistant","content": reply})
            AI_SESS[uid]["msgs"] = msgs[-16:]
            send(cid, reply, menu_kb()); return
        except Exception as e:
            log.warning("AI error: %s", e)
            continue
    send(cid, manual_reply(user_text) + "\n\n(تم استخدام وضع بديل مؤقتًا.)", menu_kb())

def ai_end(cid, uid):
    AI_SESS.pop(uid, None)
    send(cid, "تم إنهاء الجلسة ✅", menu_kb())

# -------- Routes --------
@app.get("/")
def home():
    return jsonify({"app":"Arabi Psycho","public_url":RENDER_EXTERNAL_URL,
                    "webhook":f"/webhook/{WEBHOOK_SECRET[:3]}*****","ai_ready":ai_ready()})

@app.get("/setwebhook")
def set_hook():
    if not RENDER_EXTERNAL_URL: return {"ok":False,"error":"RENDER_EXTERNAL_URL not set"}, 400
    url = f"{RENDER_EXTERNAL_URL}/webhook/{WEBHOOK_SECRET}"
    res = requests.post(f"{BOT_API}/setWebhook", json={"url": url}, timeout=15)
    return res.json(), res.status_code

@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    upd = request.get_json(force=True, silent=True) or {}

    # Callbacks
    if "callback_query" in upd:
        cq = upd["callback_query"]; data = cq.get("data","")
        cid = cq["message"]["chat"]["id"]; uid = cq["from"]["id"]
        if data.startswith("t:"):
            key = data.split(":",1)[1]
            if key in TESTS: start_test(cid, uid, key)
            else: send(cid, "اختبار غير معروف.", menu_kb())
            return "ok", 200
        if data.startswith("a"):
            try: record_answer(cid, uid, int(data[1:]))
            except: send(cid, "إجابة غير صالحة.", menu_kb())
            return "ok", 200
        if data.startswith("cbt:"):
            cbt_send(cid, data.split(":",1)[1]); return "ok", 200
        return "ok", 200

    # Messages
    msg = upd.get("message") or upd.get("edited_message") or {}
    if not msg: return "ok", 200
    cid = msg["chat"]["id"]; text = (msg.get("text") or "").strip(); uid = msg.get("from",{}).get("id"); n = norm(text)

    # Commands / reset
    if is_cmd(text,"start") or is_cmd(text,"menu"):
        AI_SESS.pop(uid, None); SESS.pop(uid, None)
        send(cid, INTRO, menu_kb()); return "ok", 200
    if is_cmd(text,"reset"):
        AI_SESS.pop(uid, None); SESS.pop(uid, None)
        send(cid, "تمت إعادة الضبط. اختر من القائمة.", menu_kb()); return "ok", 200
    if n in ("انهاء","إنهاء","end","stop"):
        ai_end(cid, uid); return "ok", 200

    # Main buttons
    if text == "🧠 عربي سايكو": ai_start(cid, uid); return "ok", 200
    if text == "💊 العلاج السلوكي المعرفي (CBT)" or is_cmd(text,"cbt"): cbt_menu(cid); return "ok", 200
    if text == "📝 الاختبارات النفسية" or is_cmd(text,"tests"): tests_menu(cid); return "ok", 200

    # During sessions
    if uid in SESS:
        send(cid, "من فضلك أجب بالضغط على الأزرار المعروضة للاختبار.", menu_kb()); return "ok", 200
    if uid in AI_SESS:
        ai_handle(cid, uid, text); return "ok", 200

    # Default
    send(cid, "اختر من القائمة أو اكتب /start.", menu_kb()); return "ok", 200

# -------- Local run --------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
