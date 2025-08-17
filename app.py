# app.py — Arabi Psycho Telegram Bot (Psychoeducation + CBT + Tests + AI)
import os, logging
from flask import Flask, request, jsonify
import requests

# ============== Config ==============
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "secret")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")  # Optional

# AI (OpenAI-compatible / OpenRouter)
AI_BASE_URL = (os.environ.get("AI_BASE_URL") or "").rstrip("/")
AI_API_KEY  = os.environ.get("AI_API_KEY", "")
AI_MODEL    = os.environ.get("AI_MODEL", "")  # e.g. openai/gpt-4o-mini

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho-bot")

# ============ Telegram helpers ============
def tg(method, payload):
    r = requests.post(f"{BOT_API}/{method}", json=payload, timeout=15)
    if r.status_code != 200:
        log.warning("TG %s -> %s | %s", method, r.status_code, r.text[:300])
    return r

def send(chat_id, text, reply_markup=None, parse_mode="HTML"):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True}
    if reply_markup: payload["reply_markup"] = reply_markup
    return tg("sendMessage", payload)

def inline(rows):  # inline keyboard
    return {"inline_keyboard": rows}

def reply_kb():    # bottom persistent keyboard
    return {
        "keyboard": [
            [{"text":"العلاج السلوكي"}, {"text":"اختبارات"}],
            [{"text":"التثقيف"}, {"text":"نوم"}],
            [{"text":"حزن"}, {"text":"قلق"}],
            [{"text":"تنفّس"}, {"text":"عربي سايكو"}],
            [{"text":"تواصل"}, {"text":"مساعدة"}],
            [{"text":"اكتئاب"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

def is_cmd(txt, name): return (txt or "").strip().lower().startswith("/"+name)
def norm(s: str) -> str:
    if not s: return ""
    return (s.replace("أ","ا").replace("إ","ا").replace("آ","ا").replace("ة","ه").strip().lower())

# ============== Safety بسيط ==============
CRISIS_WORDS = ["انتحار","اذي نفسي","اؤذي نفسي","قتل نفسي","ما ابغى اعيش"]
def crisis_guard(text):
    low = norm(text)
    return any(w in low for w in CRISIS_WORDS)

# ============== Tests ==============
# إجابات موحّدة (0..3)
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
# مختصرات إضافية (بنفس سلم 0..3 خلال الأسبوعين الماضيين)
SA3 = [  # Social Anxiety (قصير)
    "أقلق كثيرًا من الإحراج أو الحكم عليّ في المواقف الاجتماعية",
    "أتجنب أو أتضايق من التجمعات/التعارف/التقديم أمام الآخرين",
    "أفكر لفترات طويلة بما قد يظنه الناس عنّي"
]
OCI4 = [  # OCD (قصير)
    "تراودني أفكار مزعجة ومتكررة يصعب تجاهلها",
    "أفحص/أتحقق كثيرًا (الأبواب، الهاتف، الغاز…)",
    "أغسل/أنظّف بإفراط أو بطقوس محددة",
    "أرتّب/أعدّل الأشياء حتى «تشعر» بالكمال"
]
PTSD5 = [
    "ذكريات مزعجة متكررة أو كوابيس عن حدث صادم",
    "تجنّب تذكّره أو أماكن/أشخاص يذكّرون به",
    "يقظة مفرطة/استنفار (توتر، قلق، صعوبة نوم)",
    "أفكار أو مشاعر سلبية مستمرة منذ الحدث",
    "تأثير واضح على العمل أو العلاقات"
]
PANIC4 = [
    "نوبات مفاجئة من خوف شديد مع أعراض جسدية (خفقان، ضيق نفس…)",
    "قلق مستمر من حدوث نوبة أخرى",
    "تجنّب أماكن/أنشطة خوفًا من النوبات",
    "تأثير ذلك على حياتي اليومية"
]
HEALTH5 = [
    "قلق شديد حول الصحة حتى مع طمأنة الأطباء",
    "أفسّر الأعراض البسيطة كدلائل مرض خطير",
    "أبحث كثيرًا في الإنترنت أو أطلب فحوصات متكررة",
    "أراقب جسمي باستمرار وأفحصه",
    "هذا القلق يؤثر على يومي"
]

TESTS = {
    "g7":   {"name":"مقياس القلق GAD-7","q":G7},
    "phq":  {"name":"مقياس الاكتئاب PHQ-9","q":PHQ9},
    "sa3":  {"name":"قلق اجتماعي (مختصر)","q":SA3},
    "oci4": {"name":"وسواس قهري (مختصر)","q":OCI4},
    "ptsd5":{"name":"كرب ما بعد الصدمة (مختصر)","q":PTSD5},
    "panic4":{"name":"نوبات الهلع (مختصر)","q":PANIC4},
    "health5":{"name":"قلق صحي (مختصر)","q":HEALTH5},
}
SESS = {}  # {uid: {"key":, "i":, "score":}}

def tests_menu(chat_id):
    send(chat_id, "اختر اختبارًا:", inline([
        [{"text":"القلق GAD-7", "callback_data":"t:g7"}],
        [{"text":"الاكتئاب PHQ-9", "callback_data":"t:phq"}],
        [{"text":"قلق اجتماعي (قصير)", "callback_data":"t:sa3"}],
        [{"text":"وسواس قهري (قصير)", "callback_data":"t:oci4"}],
        [{"text":"كرب ما بعد الصدمة (قصير)", "callback_data":"t:ptsd5"}],
        [{"text":"نوبات هلع (قصير)", "callback_data":"t:panic4"}],
        [{"text":"قلق صحي (قصير)", "callback_data":"t:health5"}],
    ]))

def start_test(chat_id, uid, key):
    data = TESTS[key]
    SESS[uid] = {"key": key, "i": 0, "score": 0}
    send(chat_id, f"سنبدأ: <b>{data['name']}</b>\nأجب حسب آخر أسبوعين. (المقياس إرشادي وليس تشخيصًا).", reply_kb())
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
    # إرشادات تقريبية مبسطة
    if key=="g7":
        lvl = "قلق ضئيل" if score<=4 else ("قلق خفيف" if score<=9 else ("قلق متوسط" if score<=14 else "قلق شديد"))
        return f"<b>{lvl}</b>.\nنصيحة: تنفّس ببطء، قلّل الكافيين، وثبّت نومك."
    if key=="phq":
        if score<=4: lvl="ضئيل"
        elif score<=9: lvl="خفيف"
        elif score<=14: lvl="متوسط"
        elif score<=19: lvl="متوسط إلى شديد"
        else: lvl="شديد"
        return f"<b>اكتئاب {lvl}</b>.\nتنشيط سلوكي + تواصل اجتماعي + روتين نوم."
    if key=="sa3":
        lvl = "منخفض" if score<=3 else ("محتمل" if score<=6 else "مرتفع")
        return f"قلق اجتماعي <b>{lvl}</b>. جرّب التعرض التدريجي + تحدي الأفكار."
    if key=="oci4":
        lvl = "منخفض" if score<=3 else ("خفيف" if score<=7 else ("متوسط" if score<=11 else "مرتفع"))
        return f"أعراض وسواس <b>{lvl}</b>. التعرض مع منع الاستجابة (ERP) يفيد."
    if key=="ptsd5":
        lvl = "منخفض" if score<=4 else ("متوسط" if score<=9 else "مرتفع")
        return f"أعراض صدمة <b>{lvl}</b>. لو مرتفع أو مزعج بشدة، راجع مختص."
    if key=="panic4":
        lvl = "منخفض" if score<=3 else ("متوسط" if score<=7 else "مرتفع")
        return f"أعراض هلع <b>{lvl}</b>. جرّب التعرض للأحاسيس + تنظيم التنفس."
    if key=="health5":
        lvl = "منخفض" if score<=4 else ("متوسط" if score<=9 else "مرتفع")
        return f"قلق صحي <b>{lvl}</b>. قلّل الفحص/الطمأنة ودرّب الانتباه المرن."
    return "تم."

# ============== CBT (inline) ==============
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
    rows=[]; 
    for i in range(0, len(CBT_ITEMS), 2):
        rows.append([{"text": t, "callback_data": d} for (t,d) in CBT_ITEMS[i:i+2]])
    send(chat_id, "اختر موضوع العلاج السلوكي:", inline(rows))

def cbt_text(code):
    if code=="cd":
        return ["<b>أخطاء التفكير</b>\nالأبيض/الأسود، التعميم، قراءة الأفكار، التنبؤ، التهويل…",
                "خطوات: ١) التقط الفكرة ٢) الدليل معها/ضدها ٣) صياغة متوازنة."]
    if code=="rum":
        return ["<b>الاجترار والكبت</b>", "لاحظ الفكرة واسمها، خصّص «وقت قلق»، وحوّل الانتباه لنشاط بسيط."]
    if code=="q10":
        return ["<b>الأسئلة العشرة</b>", "الدليل؟ البدائل؟ لو صديق مكاني؟ أسوأ/أفضل/أرجح؟ هل أعمّم/أقرأ أفكار؟ ماذا أتجاهل؟"]
    if code=="rlx":
        return ["<b>الاسترخاء</b>", "تنفّس 4-7-8 ×6. شدّ/إرخِ العضلات من القدم للرأس."]
    if code=="ba":
        return ["<b>التنشيط السلوكي</b>", "نشاطان صغيران يوميًا (ممتع/نافع) + قاعدة 5 دقائق + تقييم مزاج."]
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

# ============== Psychoeducation Cards ==============
PE_CARDS = {
    "sa":  ["<b>القلق الاجتماعي</b>",
            "• أفكار: «سيضحكون عليّ» → تحدّاها بالأدلة.",
            "• سلوك: تعرّض تدريجي + تقليل التجنّب.",
            "• تمرين: سرد مراتب مواقف من الأسهل للأصعب والتدرّج."],
    "dep": ["<b>الاكتئاب</b>",
            "• التنشيط السلوكي: مهام صغيرة ممتعة/نافعة يوميًا.",
            "• نوم منتظم + تعريض للشمس/حركة خفيفة.",
            "• راقب أفكار جلد الذات واستبدلها بواقعية رحيمة."],
    "self":["<b>الثقة بالنفس</b>",
            "• سجل إنجازات صغيرة يوميًا.",
            "• حوار ذاتي داعم بدل النقد القاسي.",
            "• تعلّم مهارات تدريجية (عرض، تعارف، تفاوض)."],
    "health":["<b>القلق الصحي</b>",
              "• قلّل الفحص والبحث الطبي المتكرر.",
              "• مرّن تقبّل عدم اليقين مع تركيز على الأنشطة.",
              "• استخدم «نافذة طمأنة» محدودة بدل الطمأنة المستمرة."],
    "anx":["<b>القلق العام</b>",
           "• جدول «وقت القلق» + تمارين تنفّس.",
           "• أوقف الاجترار بخطوة سلوكية قصيرة.",
           "• قلّل الكافيين ونظّم النوم."],
    "ocd":["<b>الوسواس القهري</b>",
           "• ERP: تعرّض تدريجي ومنع استجابة.",
           "• اكتب هرم المثيرات وتدرّب خطوة خطوة.",
           "• تقبّل القلق بدل محاولة التخلص الفوري منه."],
    "ptsd":["<b>كرب ما بعد الصدمة</b>",
            "• أمان وتنظيم جسدي (أرض نفسك بحواسّك).",
            "• تعرّض آمن وتدريجي للذكريات مع مختص.",
            "• شبكة دعم اجتماعي."],
    "panic":["<b>نوبات الهلع</b>",
             "• تعرّض داخلي للأحاسيس (دوخة/لهاث) بشكل آمن.",
             "• تنفّس بطيء، وتفسير بديل للأعراض.",
             "• قلّل التجنّب واطلب دعمًا تدريجيًا."]
}
PE_TO_TEST = {  # زر "ابدأ اختبار"
    "sa":"sa3", "dep":"phq", "health":"health5", "anx":"g7",
    "ocd":"oci4", "ptsd":"ptsd5", "panic":"panic4"
}

def pe_menu(chat_id):
    rows = [
        [{"text":"القلق الاجتماعي","callback_data":"pe:sa"},
         {"text":"الاكتئاب","callback_data":"pe:dep"}],
        [{"text":"الثقة بالنفس","callback_data":"pe:self"},
         {"text":"القلق الصحي","callback_data":"pe:health"}],
        [{"text":"القلق العام","callback_data":"pe:anx"},
         {"text":"الوسواس القهري","callback_data":"pe:ocd"}],
        [{"text":"كرب ما بعد الصدمة","callback_data":"pe:ptsd"},
         {"text":"نوبات الهلع","callback_data":"pe:panic"}],
    ]
    send(chat_id, "التثقيف النفسي — اختر موضوعًا:", inline(rows))

def pe_send(chat_id, code):
    for t in PE_CARDS.get(code, ["تم."]):
        send(chat_id, t, reply_kb())
    test_key = PE_TO_TEST.get(code)
    if test_key:
        send(chat_id, "تحب تعمل فحصًا سريعًا؟", inline([[{"text":"ابدأ الاختبار","callback_data":f"t:{test_key}"}]]))

# ============ Therapy quick tips ============
THERAPY = {
    "sleep":
        "<b>بروتوكول النوم (مختصر)</b>\n• ثبّت الاستيقاظ يوميًا\n• قلّل الشاشات مساءً\n• طقوس تهدئة 30–45د\n• سرير=نوم فقط\n• لو ما نمت خلال 20د اخرج لنشاط هادئ وارجع.",
    "sad":
        "<b>علاج الحزن (تنشيط سلوكي)</b>\n• 3 أنشطة صغيرة اليوم (ممتع/نافع/اجتماعي)\n• ابدأ بـ10–20د\n• قيّم المزاج قبل/بعد.",
    "anx":
        "<b>قواعد سريعة للقلق</b>\n• تنفّس 4-4-6 ×10\n• قلّل الكافيين\n• قاعدة 5 دقائق لبدء المهمة\n• راقب الاجترار وبدّله بخطوة عملية.",
    "breath":
        "<b>تنفّس مهدّئ</b>\nتنفّس 4-4-6 × 10 مرات: شهيق 4، احتفاظ 4، زفير 6."
}

# ============ AI Chat ============
def ai_ready(): return bool(AI_BASE_URL and AI_API_KEY and AI_MODEL)
AI_SESS = {}  # {uid: [...messages]}
SYSTEM_PROMPT = ("أنت «عربي سايكو» مساعد نفسي تعليمي بالعربية. استخدم تقنيات CBT البسيطة، "
                 "وتذكيرًا بأنك لست بديلاً عن مختص. لا تقدّم تشخيصًا. في حال خطر على السلامة، "
                 "وجّه لطلب مساعدة فورية.")

def ai_call(messages):
    url = AI_BASE_URL + "/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    body = {"model": AI_MODEL, "messages": messages, "temperature": 0.4, "max_tokens": 256}
    r = requests.post(url, headers=headers, json=body, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"AI {r.status_code}: {r.text[:300]}")
    data = r.json()
    return data["choices"][0]["message"]["content"].strip()

def ai_start(chat_id, uid):
    if not ai_ready():
        send(chat_id, "ميزة الذكاء الاصطناعي غير مفعّلة.\nأضف: AI_BASE_URL / AI_API_KEY / AI_MODEL ثم أعد النشر.", reply_kb()); return
    AI_SESS[uid] = [{"role":"system","content": SYSTEM_PROMPT}]
    send(chat_id, "بدأنا جلسة <b>عربي سايكو</b> 🤖\nاكتب سؤالك…\nلإنهاء الجلسة: اكتب <code>انهاء</code>.", reply_kb())

def ai_handle(chat_id, uid, user_text):
    if crisis_guard(user_text):
        send(chat_id, "سلامتك أهم شيء الآن. لو عندك أفكار لإيذاء نفسك، اطلب مساعدة فورية من الطوارئ/رقم بلدك.\nجرّب الآن تنفّس 4-4-6 ×10 وابْقَ قريبًا من شخص تثق به.", reply_kb()); return
    msgs = AI_SESS.get(uid) or [{"role":"system","content": SYSTEM_PROMPT}]
    msgs = msgs[-16:] + [{"role":"user","content": user_text}]
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

# ============== Routes ==============
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
            cbt_send(chat_id, data.split(":",1)[1]); return "ok", 200

        if data.startswith("pe:"):
            pe_send(chat_id, data.split(":",1)[1]); return "ok", 200

        return "ok", 200

    # ===== Messages =====
    msg = upd.get("message") or upd.get("edited_message") or {}
    if not msg: return "ok", 200
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    low = norm(text)
    uid = msg.get("from", {}).get("id")
    user = msg.get("from", {})
    username = user.get("username") or (user.get("first_name","") + " " + user.get("last_name","")).strip() or "مستخدم"

    # أوامر
    if is_cmd(text, "start"):
        send(chat_id,
             "أهلًا بك! أنا <b>عربي سايكو</b>.\nالقائمة: التثقيف، الاختبارات، العلاج السلوكي، نوم، حزن، قلق، تنفّس…\n"
             "• /menu لعرض الأزرار • /cbt للعلاج السلوكي • /tests للاختبارات • /help للمساعدة.",
             reply_kb()); return "ok", 200
    if is_cmd(text, "help"):
        send(chat_id, "اكتب: التثقيف، اختبارات، العلاج السلوكي، نوم، حزن، قلق، تنفّس، عربي سايكو، تواصل.\nلإنهاء الذكاء: اكتب «انهاء».", reply_kb()); return "ok", 200
    if is_cmd(text, "menu"):
        send(chat_id, "القائمة:", reply_kb()); return "ok", 200
    if is_cmd(text, "tests"):
        tests_menu(chat_id); return "ok", 200
    if is_cmd(text, "cbt"):
        cbt_menu(chat_id); return "ok", 200
    if is_cmd(text, "ai_diag"):
        send(chat_id, f"ai_ready={ai_ready()}\nBASE={bool(AI_BASE_URL)} KEY={bool(AI_API_KEY)}\nMODEL={AI_MODEL or '-'}"); return "ok", 200

    # إنهاء جلسة الذكاء (أولوية)
    if low in ["انهاء","انهائها","انهاء الجلسه","انهاء الجلسة","/end"]:
        ai_end(chat_id, uid); return "ok", 200

    # كلمات القوائم (أولوية أعلى من الذكاء)
    if low in ["التثقيف","اضطرابات","التعليم النفسي","تثقيف"]:
        pe_menu(chat_id); return "ok", 200
    if low in ["اختبارات","اختبار","test","tests"]:
        tests_menu(chat_id); return "ok", 200
    if low in ["العلاج السلوكي","cbt","علاج سلوكي"]:
        cbt_menu(chat_id); return "ok", 200
    if low in ["نوم","sleep"]:
        send(chat_id, THERAPY["sleep"], reply_kb()); return "ok", 200
    if low in ["حزن","زعل"]:
        send(chat_id, THERAPY["sad"], reply_kb()); return "ok", 200
    if low in ["قلق","قلق عام"]:
        send(chat_id, THERAPY["anx"], reply_kb()); return "ok", 200
    if "تنفس" in low or "تنف" in low:
        send(chat_id, THERAPY["breath"], reply_kb()); return "ok", 200
    if low in ["اكتئاب"]:
        send(chat_id, "لو تحب فحصًا: اضغط «الاكتئاب PHQ-9» من /tests.\nوإليك خطة مختصرة:\n" + THERAPY["sad"], reply_kb()); return "ok", 200

    # طلب تواصل → تنبيه إدمن
    if "تواصل" in low:
        send(chat_id, "تم تسجيل طلب تواصل ✅ سنرجع لك قريبًا.", reply_kb())
        if ADMIN_CHAT_ID:
            info = (f"📩 طلب تواصل\nاسم: {username} (user_id={uid})\nchat_id: {chat_id}\nنصّه: {text}")
            send(ADMIN_CHAT_ID, info)
        return "ok", 200

    # بدء جلسة الذكاء
    if low in ["عربي سايكو","ذكاء","ذكاء اصطناعي","ai","/ai","سايكو"]:
        ai_start(chat_id, uid); return "ok", 200

    # لو جلسة الذكاء نشطة
    if uid in AI_SESS:
        ai_handle(chat_id, uid, text); return "ok", 200

    # رد افتراضي
    send(chat_id, f"تمام 👌 وصلتني: “{text}”.\nاكتب <b>/menu</b> لعرض الأزرار.", reply_kb())
    return "ok", 200

# ============== Main ==============
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
