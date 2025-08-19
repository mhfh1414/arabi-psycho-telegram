# app.py — Arabi Psycho (CBT + Tests + Triage + AI Chat)
import os, json, logging, requests
from flask import Flask, request, jsonify

# ── Config
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN: raise RuntimeError("Missing TELEGRAM_BOT_TOKEN")
BOT_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

WEBHOOK_SECRET      = os.environ.get("WEBHOOK_SECRET", "secret")
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
ADMIN_CHAT_ID       = os.environ.get("ADMIN_CHAT_ID", "")
CONTACT_PHONE       = os.environ.get("CONTACT_PHONE", "")

# Pricing (display only)
PRICE_ENABLED = os.environ.get("PRICE_ENABLED","false").lower()=="true"
PRICE_GAD7    = os.environ.get("PRICE_GAD7","15")
PRICE_PHQ9    = os.environ.get("PRICE_PHQ9","15")
PRICE_PANIC   = os.environ.get("PRICE_PANIC","20")
PAY_INSTRUCTIONS = os.environ.get("PAY_INSTRUCTIONS","للدفع: حول ثم أرسل الإيصال عبر زر تواصل.")

# Doctors (optional)
DOCTORS = []
try: DOCTORS = json.loads(os.environ.get("DOCTORS_JSON","[]"))
except: pass

# AI (optional, OpenAI-compatible)
AI_BASE_URL = (os.environ.get("AI_BASE_URL","") or "").rstrip("/")
AI_API_KEY  = os.environ.get("AI_API_KEY","")
AI_MODEL    = os.environ.get("AI_MODEL","")
def ai_ready(): return bool(AI_BASE_URL and AI_API_KEY and AI_MODEL)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho")

# ── Telegram helpers
def tg(m, p): 
    r = requests.post(f"{BOT_API}/{m}", json=p, timeout=15)
    if r.status_code!=200: log.warning("TG %s -> %s %s", m, r.status_code, r.text[:200])
    return r
def send(cid, txt, kb=None, parse_mode="HTML"):
    d={"chat_id":cid,"text":txt,"parse_mode":parse_mode,"disable_web_page_preview":True}
    if kb: d["reply_markup"]=kb
    return tg("sendMessage", d)
def inline(rows): return {"inline_keyboard": rows}
def menu_kb(): 
    return {
        "keyboard":[
            [{"text":"🧪 اختبارات"}, {"text":"🧠 العلاج السلوكي"}],
            [{"text":"📊 تشخيص مبدئي"}, {"text":"🤖 عربي سايكو"}],
            [{"text":"📞 تواصل"}, {"text":"❓ مساعدة"}],
        ],
        "resize_keyboard":True, "is_persistent":True
    }
def is_cmd(t, name): return (t or "").strip().lower().startswith("/"+name)

# ── Intro
INTRO = (
    "مرحبًا بك! أنا <b>عربي سايكو</b>.\n"
    "القائمة: اختبارات • العلاج السلوكي • تشخيص مبدئي • عربي سايكو • تواصل • مساعدة.\n\n"
    "<b>تنبيه مهم:</b> لستُ بديلاً عن التشخيص أو العلاج لدى مختص. "
    "المشروع تحت إشراف <b>أخصائي نفسي مرخّص</b>، والمحتوى للدعم والتعليم العملي فقط."
)

# ── CBT Cards
CBT_CARDS = [
    ("أخطاء التفكير","الأبيض/الأسود، التعميم، قراءة الأفكار، التنبؤ، التهويل…\nالخطوات: ١) التقط الفكرة ٢) الدليل معها/ضدها ٣) صياغة متوازنة."),
    ("الأسئلة العشرة","الدليل؟ البدائل؟ لو صديق مكاني؟ أسوأ/أفضل/أرجح؟ هل أعمّم/أقرأ أفكار؟ ماذا أتجاهل؟"),
    ("الاسترخاء","تنفّس 4-7-8 ×6. شد/إرخِ العضلات من القدم للرأس."),
    ("التنشيط السلوكي","نشاطان صغيران اليوم (ممتع/نافع). قاعدة 5 دقائق. قيّم مزاجك قبل/بعد."),
    ("اليقظة الذهنية","تمرين 5-4-3-2-1 للحواس. لاحظ بلا حكم وارجع للحاضر."),
    ("حل المشكلات","عرّف المشكلة → بدائل → خطة SMART صغيرة → جرّب → قيّم."),
]
def cbt_menu(cid):
    rows=[[{"text":t,"callback_data":"cbt:"+t}] for (t,_) in CBT_CARDS]
    send(cid,"اختر بطاقة من العلاج السلوكي:", inline(rows))
def cbt_send(cid, title):
    for t,body in CBT_CARDS:
        if t==title: send(cid, f"<b>{t}</b>\n{body}", menu_kb())

# ── Tests (GAD7/PHQ9/PANIC)
ANS_4=[("أبدًا",0),("عدة أيام",1),("أكثر من النصف",2),("تقريبًا يوميًا",3)]
ANS_5=[("0",0),("1",1),("2",2),("3",3),("4",4)]
GAD7=[ "التوتر/العصبية أو الشعور بالقلق","عدم التمكن من إيقاف القلق","الانشغال بالهموم بدرجة كبيرة",
       "صعوبة الاسترخاء","تململ/صعوبة الجلوس بهدوء","الانزعاج بسرعة","الخوف من حدوث شيء سيئ" ]
PHQ9=[ "قلة الاهتمام بالأشياء","الشعور بالحزن/اليأس","مشاكل بالنوم","إرهاق/قلة طاقة","ضعف شهية/إفراط بالأكل",
       "شعور بعدم القيمة أو بالذنب","صعوبة التركيز","بطء/توتر في الحركة","أفكار أنك ستكون أفضل لو لم تكن موجودًا" ]
PANIC7=[ "عدد نوبات الهلع خلال أسبوعين","شدة أعراض النوبة","القلق الاستباقي","التجنّب خوفًا من النوبة",
         "تأثير الأعراض على العمل/الدراسة","تأثيرها على العلاقات/الخروج","سلوكيات الأمان (طمأنة/حمل ماء..)" ]
TESTS={"g7":{"name":"اختبار القلق (GAD-7)","q":GAD7,"ans":ANS_4,"max":21},
       "phq":{"name":"اختبار الاكتئاب (PHQ-9)","q":PHQ9,"ans":ANS_4,"max":27},
       "panic":{"name":"مقياس الهلع (PDSS-SR مبسّط)","q":PANIC7,"ans":ANS_5,"max":28}}
SESS={}
def tests_menu(cid):
    if PRICE_ENABLED:
        send(cid, f"💳 التسعير: قلق {PRICE_GAD7} • اكتئاب {PRICE_PHQ9} • هلع {PRICE_PANIC}\n{PAY_INSTRUCTIONS}")
    rows=[[{"text":"اختبار القلق (GAD-7)","callback_data":"t:g7"}],
          [{"text":"اختبار الاكتئاب (PHQ-9)","callback_data":"t:phq"}],
          [{"text":"مقياس الهلع (PDSS-SR)","callback_data":"t:panic"}]]
    send(cid,"اختر اختبارًا:", inline(rows))
def start_test(cid, uid, key):
    SESS[uid]={"key":key,"i":0,"score":0}
    send(cid, f"سنبدأ: <b>{TESTS[key]['name']}</b>\nأجب حسب آخر أسبوعين.", menu_kb()); ask_next(cid,uid)
def ask_next(cid, uid):
    st=SESS.get(uid); 
    if not st: return
    key, i = st["key"], st["i"]; qs=TESTS[key]["q"]; ans=TESTS[key]["ans"]
    if i>=len(qs):
        score=st["score"]; total=TESTS[key]["max"]
        send(cid, f"النتيجة: <b>{score}</b> من {total}\n{interpret(key,score)}", menu_kb())
        SESS.pop(uid,None); return
    # build answers rows
    rows=[]; row=[]
    for idx,(label,_) in enumerate(ans):
        row.append({"text":label,"callback_data":f"a{idx}"})
        if (ans is ANS_4 and len(row)==2) or (ans is ANS_5 and len(row)==3):
            rows.append(row); row=[]
    if row: rows.append(row)
    send(cid, f"س{ i+1 }: {qs[i]}", inline(rows))
def record_answer(cid, uid, idx):
    st=SESS.get(uid); 
    if not st: return
    key=st["key"]; st["score"] += TESTS[key]["ans"][idx][1]; st["i"]+=1; ask_next(cid,uid)
def interpret(key, score):
    if key=="g7":
        lvl = "قلق ضئيل" if score<=4 else ("قلق خفيف" if score<=9 else ("قلق متوسط" if score<=14 else "قلق شديد"))
        return f"<b>{lvl}</b> — ابدأ بتنظيم النوم، قلّل الكافيين، جرّب بطاقات CBT والتنفس."
    if key=="phq":
        if score<=4:lvl="ضئيل"
        elif score<=9:lvl="خفيف"
        elif score<=14:lvl="متوسط"
        elif score<=19:lvl="متوسط إلى شديد"
        else:lvl="شديد"
        return f"<b>اكتئاب {lvl}</b> — فعّل التنشيط السلوكي وتواصل اجتماعيًا، واستشر مختصًا عند الشدة."
    if key=="panic":
        if score<=7:lvl="خفيف"
        elif score<=14:lvl="متوسط"
        elif score<=21:lvl="متوسط إلى شديد"
        else:lvl="شديد"
        return f"<b>هلع {lvl}</b> — تنفّس ببطء، خفّف سلوكيات الأمان، خطّة تعرّض تدريجي آمن."
    return "تم."

# ── Triage & Contact
def triage_text():
    return ("📊 <b>تشخيص مبدئي (غير طبي)</b>\n"
            "القياس يتم عبر GAD-7/PHQ-9/PDSS-SR لتقدير شدة الأعراض واختيار الخطة التعليمية (CBT) "
            "أو طلب استشارة مختص. ليست بديلاً عن التشخيص الطبي.")

def contact_text():
    lines=["📞 <b>التواصل</b>"]
    if CONTACT_PHONE: lines.append(f"الهاتف/واتساب: <code>{CONTACT_PHONE}</code>")
    if DOCTORS:
        lines.append("\n👩‍⚕️ <b>المشرفون</b>:")
        for d in DOCTORS:
            nm, lic = d.get("name",""), d.get("license","")
            lines.append("• "+nm + (f" — ترخيص: {lic}" if lic else ""))
    lines.append("\nالمشروع تحت إشراف أخصائي نفسي مرخّص. المحتوى تعليمي/داعم.")
    return "\n".join(lines)
def notify_admin(msg):
    if not ADMIN_CHAT_ID: return
    try: tg("sendMessage", {"chat_id": int(ADMIN_CHAT_ID), "text": msg})
    except: pass

# ── AI Chat
AI_SESS = {}  # {uid: [msgs]}
SYSTEM_PROMPT = (
    "أنت «عربي سايكو» مساعد نفسي تعليمي بالعربية. قدّم دعمًا عامًّا وتقنيات CBT "
    "بخطوات قصيرة، وذكّر بأنك لست بديلاً عن مختص. تجنّب التشخيص الطبي المباشر."
)
CRISIS_WORDS=["انتحار","اذي نفسي","قتل نفسي","ما ابغى اعيش"]
def crisis(text):
    t=text.replace("أ","ا").replace("إ","ا").replace("آ","ا").lower()
    return any(w in t for w in CRISIS_WORDS)

def ai_call(messages, max_tokens=120):
    url=AI_BASE_URL+"/v1/chat/completions"
    headers={"Authorization":f"Bearer {AI_API_KEY}","Content-Type":"application/json"}
    body={"model":AI_MODEL,"messages":messages,"temperature":0.4,"max_tokens":max_tokens}
    r=requests.post(url,headers=headers,json=body,timeout=30)
    if r.status_code!=200: raise RuntimeError(r.text[:300])
    return r.json()["choices"][0]["message"]["content"].strip()

def ai_start(cid, uid):
    if not ai_ready():
        send(cid, "ميزة عربي سايكو (الذكاء الاصطناعي) غير مفعّلة. أضف AI_BASE_URL / AI_API_KEY / AI_MODEL.", menu_kb()); return
    AI_SESS[uid]=[{"role":"system","content":SYSTEM_PROMPT}]
    send(cid, "بدأنا جلسة <b>عربي سايكو</b> 🤖\nاكتب سؤالك عن القلق/النوم/CBT…\nلإنهاء الجلسة: اكتب <code>انهاء</code>.", menu_kb())

def ai_handle(cid, uid, text):
    if crisis(text):
        send(cid,"سلامتك أهم. لو تراودك أفكار لإيذاء نفسك، اطلب مساعدة فورية من الطوارئ/رقم بلدك وتواصل مع من تثق به.", menu_kb()); return
    msgs=AI_SESS.get(uid)
    if not msgs: return
    msgs = msgs[-16:]; msgs.append({"role":"user","content":text})
    try:
        reply=ai_call(msgs, max_tokens=110)
    except Exception as e:
        send(cid, f"تعذّر الاتصال بالذكاء الاصطناعي.\n{e}\nتم تقليل طول الردود تلقائيًا، جرّب لاحقًا أو اشحن رصيد OpenRouter.", menu_kb()); return
    msgs.append({"role":"assistant","content":reply}); AI_SESS[uid]=msgs[-18:]
    send(cid, reply, menu_kb())

def ai_end(cid, uid):
    AI_SESS.pop(uid, None)
    send(cid,"تم إنهاء جلسة عربي سايكو ✅", menu_kb())

# ── Routes
@app.get("/")
def home():
    return jsonify({"app":"Arabi Psycho","public_url":RENDER_EXTERNAL_URL,"webhook":f"/webhook/{WEBHOOK_SECRET[:3]}*****","ai_ready":ai_ready()})

@app.get("/setwebhook")
def sethook():
    if not RENDER_EXTERNAL_URL: return {"ok":False,"error":"RENDER_EXTERNAL_URL not set"},400
    url=f"{RENDER_EXTERNAL_URL}/webhook/{WEBHOOK_SECRET}"
    r=requests.post(f"{BOT_API}/setWebhook", json={"url":url}, timeout=15)
    return r.json(), r.status_code

@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    upd=request.get_json(force=True,silent=True) or {}

    # callbacks
    if "callback_query" in upd:
        cq=upd["callback_query"]; data=cq.get("data",""); cid=cq["message"]["chat"]["id"]; uid=cq["from"]["id"]
        if data.startswith("t:"):
            key=data.split(":",1)[1]; 
            if key in TESTS: start_test(cid, uid, key)
            else: send(cid,"اختبار غير معروف.", menu_kb())
            return "ok",200
        if data.startswith("a"):
            try: record_answer(cid, uid, int(data[1:]))
            except: send(cid,"إجابة غير صالحة.", menu_kb())
            return "ok",200
        if data.startswith("cbt:"):
            cbt_send(cid, data.split(":",1)[1]); return "ok",200
        return "ok",200

    # messages
    msg=upd.get("message") or upd.get("edited_message") or {}
    if not msg: return "ok",200
    cid=msg["chat"]["id"]; text=(msg.get("text") or "").strip(); low=text.replace("أ","ا").replace("إ","ا").replace("آ","ا").lower()
    uid=msg.get("from",{}).get("id")

    # Commands / buttons
    if is_cmd(text,"start") or is_cmd(text,"menu") or text=="❓ مساعدة":
        send(cid, INTRO, menu_kb()); return "ok",200
    if is_cmd(text,"tests") or text=="🧪 اختبارات": tests_menu(cid); return "ok",200
    if is_cmd(text,"cbt") or text=="🧠 العلاج السلوكي": cbt_menu(cid); return "ok",200
    if text=="📊 تشخيص مبدئي": send(cid, triage_text(), menu_kb()); return "ok",200
    if text=="📞 تواصل":
        send(cid, contact_text(), menu_kb()); notify_admin(f"طلب تواصل من user_id={uid} chat_id={cid}"); return "ok",200
    if text=="🤖 عربي سايكو": ai_start(cid, uid); return "ok",200
    if text=="انهاء": ai_end(cid, uid); return "ok",200

    # During test
    if uid in SESS:
        send(cid,"استخدم الأزرار للإجابة على السؤال الحالي.", menu_kb()); return "ok",200

    # AI session?
    if uid in AI_SESS: 
        ai_handle(cid, uid, text); return "ok",200

    # default
    send(cid,"اكتب /menu لإظهار القائمة.", menu_kb()); return "ok",200

if __name__=="__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT",5000)))
