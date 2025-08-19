# app.py — Arabi Psycho (Tests + CBT + Triage + Pricing + Contact)
# ─────────────────────────────────────────────────────────────────
import os, json, logging
from flask import Flask, request, jsonify
import requests

# ============ إعدادات عامة ============
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

WEBHOOK_SECRET     = os.environ.get("WEBHOOK_SECRET", "secret")
RENDER_EXTERNAL_URL= os.environ.get("RENDER_EXTERNAL_URL")
ADMIN_CHAT_ID      = os.environ.get("ADMIN_CHAT_ID", "")  # لإشعارات "تواصل"
CONTACT_PHONE      = os.environ.get("CONTACT_PHONE", "")  # رقم تواصل يظهر للعميل

# تسعير (اختياري للعرض فقط الآن)
PRICE_ENABLED      = os.environ.get("PRICE_ENABLED", "false").lower() == "true"
PRICE_GAD7         = os.environ.get("PRICE_GAD7", "15")   # ريال/… الخ
PRICE_PHQ9         = os.environ.get("PRICE_PHQ9", "15")
PRICE_PANIC        = os.environ.get("PRICE_PANIC", "20")
PAY_INSTRUCTIONS   = os.environ.get("PAY_INSTRUCTIONS",
    "للدفع: حوّل على الحساب المتفق عليه ثم أرسل الإيصال عبر زر تواصل.")

# أطباء/مشرفون (اختياري)
DOCTORS_JSON = os.environ.get("DOCTORS_JSON", '[]')  # مثال: [{"name":"د. سارة","license":"MOH-1234"}]
try:
    DOCTORS = json.loads(DOCTORS_JSON)
except Exception:
    DOCTORS = []

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho")

# ============ أدوات تيليجرام ============
def tg(method, payload):
    r = requests.post(f"{BOT_API}/{method}", json=payload, timeout=15)
    if r.status_code != 200:
        log.warning("TG %s -> %s | %s", method, r.status_code, r.text[:300])
    return r

def send(cid, text, reply_markup=None, parse_mode="HTML"):
    data = {"chat_id": cid, "text": text, "parse_mode": parse_mode, "disable_web_page_preview": True}
    if reply_markup:
        data["reply_markup"] = reply_markup
    return tg("sendMessage", data)

def inline(rows):  # لوحة أزرار داخلية
    return {"inline_keyboard": rows}

def menu_kb():     # لوحة سفلية مختصرة (6 أزرار)
    return {
        "keyboard": [
            [{"text":"🧪 اختبارات"}, {"text":"🧠 العلاج السلوكي"}],
            [{"text":"📊 تشخيص مبدئي"}, {"text":"📚 تثقيف نفسي"}],
            [{"text":"📞 تواصل"}, {"text":"❓ مساعدة"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True
    }

def is_cmd(txt, name): return (txt or "").strip().lower().startswith("/"+name)

# ============ نص المقدمة والتنبيه ============
INTRO = (
    "مرحبًا بك! كيف نبدأ اليوم؟ إليك بعض الخيارات:\n"
    "1) <b>التعامل مع القلق</b>: ناقش موقفك وسنساعدك في تحليل الأفكار.\n"
    "2) <b>تحسين المزاج</b>: تمارين سلوكية بسيطة لزيادة النشاط الآن.\n\n"
    "🤖 <b>عربي سايكو</b> مساعد نفسي <u>تعليمي</u> باللغة العربية.\n"
    "يقدم مواد تثقيفية وتمارين CBT بسيطة واختبارات قياسية لقياس الذات.\n"
    "<b>تنبيه مهم:</b> لستُ بديلاً عن التشخيص أو العلاج لدى مختص.\n"
    "المشروع تحت إشراف <b>أخصائي نفسي مرخّص</b>، والمحتوى لأغراض التثقيف والدعم فقط."
)

# ============ بنود CBT ============
CBT_CARDS = [
    ("أخطاء التفكير", 
     "الأبيض/الأسود، التعميم، قراءة الأفكار، التنبؤ، التهويل…\n"
     "الخطوات: ١) التقط الفكرة ٢) الدليل معها/ضدها ٣) صياغة متوازنة."),
    ("الأسئلة العشرة لتحدي الأفكار",
     "الدليل؟ البدائل؟ لو صديق مكاني؟ أسوأ/أفضل/أرجح؟ هل أعمّم/أقرأ أفكار؟\n"
     "ماذا أتجاهل؟ ماذا أنصح لو طال الأمر صديقًا لي؟"),
    ("الاسترخاء", 
     "تنفس 4-7-8 ×6 مرات. شد/إرخِ العضلات من القدم للرأس (PMR)."),
    ("التنشيط السلوكي", 
     "اختر نشاطين صغيرين اليوم (ممتع/نافع). قاعدة 5 دقائق. قيّم مزاجك قبل/بعد."),
    ("اليقظة الذهنية",
     "تمرين 5-4-3-2-1 للحواس. لاحظ بلا حكم. ارجع للحاضر."),
    ("حل المشكلات", 
     "عرّف المشكلة → فكّر ببدائل → خطة صغيرة SMART → جرّب → قيّم.")
]
def cbt_menu(cid):
    rows = []
    for title, _ in CBT_CARDS:
        rows.append([{"text": title, "callback_data": "cbt:"+title}])
    send(cid, "اختر بطاقة من العلاج السلوكي:", inline(rows))

def cbt_send(cid, title):
    for t, body in CBT_CARDS:
        if t == title:
            send(cid, f"<b>{t}</b>\n{body}", menu_kb())

# ============ الاختبارات ============
# خيارات الإجابة
ANS_4 = [("أبدًا",0), ("عدة أيام",1), ("أكثر من النصف",2), ("تقريبًا يوميًا",3)]
ANS_5 = [("0",0), ("1",1), ("2",2), ("3",3), ("4",4)]

GAD7 = [
    "التوتر/العصبية أو الشعور بالقلق",
    "عدم التمكن من إيقاف القلق أو السيطرة عليه",
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
    "الشعور بعدم القيمة أو الذنب",
    "صعوبة التركيز",
    "بطء/توتر بالحركة أو الكلام",
    "أفكار بأنك ستكون أفضل لو لم تكن موجودًا"
]
# PDSS-SR «مبسّط» 7 بنود (0–4)
PANIC7 = [
    "عدد نوبات الهلع خلال الأسبوعين الماضيين",
    "شدة أعراض النوبة عندما تحدث",
    "القلق anticipatory (الخوف من قدوم نوبة)",
    "تجنّب أماكن/مواقف خوفًا من النوبة",
    "تأثير الأعراض على العمل/الدراسة",
    "تأثير الأعراض على العلاقات/الخروج",
    "الاستعانة بسلوكيات أمان مفرطة (طمأنة/حمل ماء..)"
]

TESTS = {
    "g7":  {"name": "اختبار القلق (GAD-7)",  "q": GAD7,   "ans": ANS_4, "max": 21},
    "phq": {"name": "اختبار الاكتئاب (PHQ-9)","q": PHQ9,   "ans": ANS_4, "max": 27},
    "panic":{"name":"مقياس الهلع (PDSS-SR مبسّط)","q": PANIC7,"ans": ANS_5, "max": 28},
}
SESS = {}  # {uid: {"key":, "i":, "score":}}

def tests_menu(cid):
    rows = [
        [{"text":"اختبار القلق (GAD-7)",   "callback_data":"t:g7"}],
        [{"text":"اختبار الاكتئاب (PHQ-9)","callback_data":"t:phq"}],
        [{"text":"مقياس الهلع (PDSS-SR)",  "callback_data":"t:panic"}],
    ]
    if PRICE_ENABLED:
        price = (f"💳 التسعير — قلق: {PRICE_GAD7} • اكتئاب: {PRICE_PHQ9} • هلع: {PRICE_PANIC}\n"
                 f"{PAY_INSTRUCTIONS}")
        send(cid, price)
    send(cid, "اختر اختبارًا:", inline(rows))

def start_test(cid, uid, key):
    data = TESTS[key]
    SESS[uid] = {"key": key, "i": 0, "score": 0}
    send(cid, f"سنبدأ: <b>{data['name']}</b>\nأجب حسب آخر أسبوعين.", menu_kb())
    ask_next(cid, uid)

def ask_next(cid, uid):
    st = SESS.get(uid)
    if not st: return
    key, i = st["key"], st["i"]; qs = TESTS[key]["q"]; ans = TESTS[key]["ans"]
    if i >= len(qs):
        score = st["score"]; total = TESTS[key]["max"]
        send(cid, f"النتيجة: <b>{score}</b> من {total}\n{interpret(key,score)}", menu_kb())
        SESS.pop(uid, None); return
    q = qs[i]
    # ابنِ أزرار الإجابة
    row = []
    rows = []
    for idx, (label, _) in enumerate(ans):
        row.append({"text":label, "callback_data": f"a{idx}"})
        if len(row)==2 and ans is ANS_4:
            rows.append(row); row=[]
        if len(row)==3 and ans is ANS_5:
            rows.append(row); row=[]
    if row: rows.append(row)
    send(cid, f"س{ i+1 }: {q}", inline(rows))

def record_answer(cid, uid, ans_idx):
    st = SESS.get(uid)
    if not st: return
    key = st["key"]; ans = TESTS[key]["ans"]
    val = ans[ans_idx][1]
    st["score"] += val
    st["i"] += 1
    ask_next(cid, uid)

def interpret(key, score):
    if key=="g7":
        if score<=4:   lvl="قلق ضئيل"
        elif score<=9: lvl="قلق خفيف"
        elif score<=14:lvl="قلق متوسط"
        else:          lvl="قلق شديد"
        return f"<b>{lvl}</b> — ابدأ بتنظيم النوم وتقليل الكافيين وتمارين التنفس. جرّب بطاقات CBT."
    if key=="phq":
        if score<=4: lvl="ضئيل"
        elif score<=9: lvl="خفيف"
        elif score<=14:lvl="متوسط"
        elif score<=19:lvl="متوسط إلى شديد"
        else: lvl="شديد"
        return f"<b>اكتئاب {lvl}</b> — فعّل التنشيط السلوكي والتواصل الاجتماعي، واستشر مختصًا عند الشدة."
    if key=="panic":
        if score<=7:   lvl="أعراض هلع خفيفة"
        elif score<=14: lvl="متوسطة"
        elif score<=21: lvl="متوسطة إلى شديدة"
        else:           lvl="شديدة"
        return f"<b>{lvl}</b> — ابدأ بتدريبات التنفس، وقلّل سلوكيات الأمان، وفكّر ببرنامج تعرّض تدريجي آمن."
    return "تم."

# ============ تشخيص مبدئي ============
def triage_text():
    return (
        "📊 <b>تشخيص مبدئي (غير طبي)</b>\n"
        "• القياس يتم عبر اختبارات قياسية (GAD-7/PHQ-9/PDSS-SR) لقياس <u>شدة</u> الأعراض فقط.\n"
        "• النتيجة تساعدك على اختيار الخطة التعليمية (CBT) أو طلب استشارة مختص.\n"
        "• ليست بديلاً عن التشخيص الطبي. في حال الشدة العالية أو تدهور الوظائف اطلب مساعدة متخصصة."
    )

# ============ تثقيف ============
EDU = (
    "📚 <b>التثقيف النفسي المختصر</b>\n"
    "• القلق: يتضخم بالاجتناب والطمأنة؛ يقل بالتعرّض التدريجي.\n"
    "• الاكتئاب: ينخفض مع <i>التنشيط السلوكي</i> (نشاط ممتع/نافع يوميًا).\n"
    "• النوم: ثبّت وقت الاستيقاظ، وطقوس تهدئة 30-45 دقيقة، سرير=نوم فقط.\n"
    "• التنفس: 4-7-8 ×6 مرات عند التوتر."
)

# ============ تواصل ============
def contact_text():
    lines = ["📞 <b>التواصل</b>"]
    if CONTACT_PHONE:
        lines.append(f"الهاتف/واتساب: <code>{CONTACT_PHONE}</code>")
    if DOCTORS:
        lines.append("\n👩‍⚕️ <b>المشرفون/الأطباء</b>:")
        for d in DOCTORS:
            nm = d.get("name","")
            lic = d.get("license","")
            lines.append(f"• {nm}" + (f" — ترخيص: {lic}" if lic else ""))
    lines.append("\nهذا المشروع تحت إشراف أخصائي نفسي مرخّص. المحتوى تعليمي فقط.")
    return "\n".join(lines)

def notify_admin(msg):
    if not ADMIN_CHAT_ID: return
    try:
        tg("sendMessage", {"chat_id": int(ADMIN_CHAT_ID), "text": msg})
    except: pass

# ============ المسارات ============
@app.get("/")
def root():
    return jsonify({
        "app": "Arabi Psycho",
        "public_url": RENDER_EXTERNAL_URL,
        "webhook": f"/webhook/{WEBHOOK_SECRET[:3]}*****"
    })

@app.get("/setwebhook")
def setwebhook():
    if not RENDER_EXTERNAL_URL:
        return {"ok": False, "error":"RENDER_EXTERNAL_URL not set"}, 400
    url = f"{RENDER_EXTERNAL_URL}/webhook/{WEBHOOK_SECRET}"
    r = requests.post(f"{BOT_API}/setWebhook", json={"url": url}, timeout=15)
    return r.json(), r.status_code

@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    upd = request.get_json(force=True, silent=True) or {}

    # ــ أزرار داخلية
    if "callback_query" in upd:
        cq = upd["callback_query"]; data = cq.get("data","")
        cid = cq["message"]["chat"]["id"]; uid = cq["from"]["id"]

        if data.startswith("t:"):
            key = data.split(":",1)[1]
            if key in TESTS:
                start_test(cid, uid, key)
            else:
                send(cid, "اختبار غير معروف.", menu_kb())
            return "ok", 200

        if data.startswith("a"):
            try:
                idx = int(data[1:])
                record_answer(cid, uid, idx)
            except:
                send(cid, "إجابة غير صالحة.", menu_kb())
            return "ok", 200

        if data.startswith("cbt:"):
            title = data.split(":",1)[1]
            cbt_send(cid, title)
            return "ok", 200

        return "ok", 200

    # ــ رسائل عادية
    msg = upd.get("message") or upd.get("edited_message") or {}
    if not msg: return "ok", 200
    cid = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    low  = text.replace("أ","ا").replace("إ","ا").replace("آ","ا").lower()
    uid  = msg.get("from",{}).get("id")

    # أوامر
    if is_cmd(text, "start") or is_cmd(text, "menu") or text == "❓ مساعدة":
        send(cid, INTRO, menu_kb());  return "ok", 200
    if is_cmd(text, "tests") or text == "🧪 اختبارات":
        tests_menu(cid); return "ok", 200
    if is_cmd(text, "cbt") or text == "🧠 العلاج السلوكي":
        cbt_menu(cid); return "ok", 200
    if text == "📊 تشخيص مبدئي":
        send(cid, triage_text(), menu_kb()); return "ok", 200
    if text == "📚 تثقيف نفسي":
        send(cid, EDU, menu_kb()); return "ok", 200
    if text == "📞 تواصل":
        send(cid, contact_text(), menu_kb())
        notify_admin(f"طلب تواصل من user_id={uid} chat_id={cid}")
        return "ok", 200

    # جلسة اختبار نشطة؟
    if uid in SESS:
        send(cid, "استخدم الأزرار للإجابة على السؤال الحالي.", menu_kb()); return "ok", 200

    # افتراضي
    send(cid, "اكتب /menu لإظهار القائمة.", menu_kb())
    return "ok", 200

# ============ تشغيل محلي ============
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
