# app.py — Arabi Psycho Telegram Bot (Tests + DSM Educational + CBT + Psychoeducation + AI Chat)
import os, logging, json, sqlite3, re
from flask import Flask, request, jsonify, g
import requests
from datetime import datetime

# =============== إعدادات عامة ===============
# التحقق من المتغيرات البيئية المطلوبة
required_env_vars = ["TELEGRAM_BOT_TOKEN", "AI_API_KEY", "AI_MODEL"]
for var in required_env_vars:
    if not os.environ.get(var):
        raise RuntimeError(f"Missing required environment variable: {var}")

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
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

# إشعارات "تواصل" (اختياري)
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID")

# مزود الذكاء الاصطناعي (متوافق مع OpenAI)
AI_BASE_URL = (os.environ.get("AI_BASE_URL", "") or "").rstrip("/")
AI_API_KEY  = os.environ.get("AI_API_KEY",  "")
AI_MODEL    = os.environ.get("AI_MODEL",    "")

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho-bot")

# =============== إدارة قاعدة البيانات ===============
DATABASE = 'sessions.db'

def get_db():
    """الحصول على اتصال قاعدة البيانات"""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE, check_same_thread=False)
        g.db.row_factory = sqlite3.Row
    return g.db

def init_db():
    """تهيئة جداول قاعدة البيانات"""
    db = get_db()
    
    # جدول جلسات الذكاء الاصطناعي
    db.execute('''
        CREATE TABLE IF NOT EXISTS ai_sessions (
            user_id INTEGER PRIMARY KEY,
            messages TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # جدول جلسات الاختبارات
    db.execute('''
        CREATE TABLE IF NOT EXISTS test_sessions (
            user_id INTEGER,
            test_key TEXT,
            current_index INTEGER,
            score INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, test_key)
        )
    ''')
    
    # جدول جلسات التشخيص التعليمي
    db.execute('''
        CREATE TABLE IF NOT EXISTS dsm_sessions (
            user_id INTEGER,
            session_key TEXT,
            data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, session_key)
        )
    ''')
    
    db.commit()

@app.teardown_appcontext
def close_db(error):
    """إغلاق اتصال قاعدة البيانات"""
    if hasattr(g, 'db'):
        g.db.close()

# =============== توابع تيليجرام محسنة ===============
def tg(method, payload):
    """إرسال طلب إلى تيليجرام مع معالجة الأخطاء"""
    try:
        r = requests.post(f"{BOT_API}/{method}", json=payload, timeout=15)
        r.raise_for_status()
        return r
    except requests.exceptions.RequestException as e:
        log.error("Telegram API error for %s: %s", method, e)
        return None

def send(chat_id, text, reply_markup=None, parse_mode="HTML"):
    """إرسال رسالة مع معالجة الأخطاء"""
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    
    response = tg("sendMessage", payload)
    if not response or response.status_code != 200:
        log.error("Failed to send message to chat %s", chat_id)
    return response

def inline(rows):
    return {"inline_keyboard": rows}

def reply_kb():
    """لوحة أزرار سفلية ثابتة"""
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

def is_valid_user_input(text):
    """التحقق من صحة المدخلات"""
    if not text or len(text) > 1000:
        return False
    # منع حقن الأكواد الضارة
    if any(char in text for char in ['<script>', '<?php', '<?']):
        return False
    return True

# =============== سلامة وأزمات ===============
CRISIS_WORDS = ["انتحار","اذي نفسي","اودي نفسي","اودي ذاتي","قتل نفسي","ما ابغى اعيش"]
def crisis_guard(text):
    if not is_valid_user_input(text):
        return False
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
    """الاتصال بالذكاء الاصطناعي مع معالجة الأخطاء"""
    if not is_valid_user_input(json.dumps(messages)):
        raise ValueError("Invalid input for AI call")
    
    url = AI_BASE_URL + "/v1/chat/completions"
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    body = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 220
    }
    
    try:
        r = requests.post(url, headers=headers, json=body, timeout=30)
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except requests.exceptions.RequestException as e:
        log.error("AI API error: %s", e)
        raise RuntimeError(f"AI API error: {e}")

def ai_start(chat_id, uid):
    """بدء جلسة الذكاء الاصطناعي"""
    if not ai_ready():
        send(chat_id, "ميزة <b>عربي سايكو</b> غير مفعّلة (أكمل إعدادات AI).", reply_kb())
        return
    
    db = get_db()
    initial_messages = [{"role":"system","content": SYSTEM_PROMPT}]
    db.execute(
        "INSERT OR REPLACE INTO ai_sessions (user_id, messages) VALUES (?, ?)",
        (uid, json.dumps(initial_messages))
    )
    db.commit()
    
    send(chat_id,
         f"بدأنا جلسة <b>عربي سايكو</b> 🤖 بإشراف {SUPERVISOR_NAME} ({SUPERVISOR_TITLE}).\n"
         "اكتب سؤالك عن النوم/القلق/CBT…\n"
         "لإنهاء الجلسة: اكتب <code>انهاء</code>.",
         reply_kb())

def ai_end(chat_id, uid):
    """إنهاء جلسة الذكاء الاصطناعي"""
    db = get_db()
    db.execute("DELETE FROM ai_sessions WHERE user_id = ?", (uid,))
    db.commit()
    send(chat_id, "تم إنهاء جلسة عربي سايكو ✅", reply_kb())

def ai_handle(chat_id, uid, user_text):
    """معالجة رسالة المستخدم في جلسة الذكاء الاصطناعي"""
    if not is_valid_user_input(user_text):
        send(chat_id, "الرسالة طويلة جدًا أو تحتوي على محتوى غير صالح.", reply_kb())
        return
    
    if crisis_guard(user_text):
        send(chat_id,
             "أقدّر شعورك، وسلامتك أهم شيء الآن.\n"
             "إن وُجدت أفكار لإيذاء النفس فاتصل بالطوارئ فورًا أو توجّه لأقرب طوارئ.",
             reply_kb())
        return
    
    db = get_db()
    row = db.execute("SELECT messages FROM ai_sessions WHERE user_id = ?", (uid,)).fetchone()
    
    if not row:
        ai_start(chat_id, uid)
        return
    
    try:
        msgs = json.loads(row['messages'])
        msgs = msgs[-16:]  # حفظ الذاكرة
        msgs.append({"role":"user","content": user_text})
        
        reply = ai_call(msgs)
        msgs.append({"role":"assistant","content": reply})
        
        # حفظ الرسائل المحدثة
        db.execute(
            "UPDATE ai_sessions SET messages = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
            (json.dumps(msgs[-18:]), uid)
        )
        db.commit()
        
        send(chat_id, reply, reply_kb())
    except Exception as e:
        log.error("AI handling error: %s", e)
        send(chat_id,
             "حدث خطأ أثناء معالجة طلبك. يرجى المحاولة لاحقًا.",
             reply_kb())

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

def tests_menu(chat_id):
    send(chat_id, "اختر اختبارًا:", inline([
        [{"text":"اختبار القلق (GAD-7)","callback_data":"t:g7"}],
        [{"text":"اختبار الاكتئاب (PHQ-9)","callback_data":"t:phq"}],
    ]))

def test_start(chat_id, uid, key):
    """بدء اختبار جديد"""
    if key not in TESTS:
        send(chat_id, "اختبار غير معروف.", reply_kb())
        return
    
    data = TESTS[key]
    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO test_sessions (user_id, test_key, current_index, score) VALUES (?, ?, ?, ?)",
        (uid, key, 0, 0)
    )
    db.commit()
    
    send(chat_id, f"سنبدأ: <b>{data['name']}</b>\nأجب حسب آخر أسبوعين.", reply_kb())
    test_ask(chat_id, uid)

def test_ask(chat_id, uid):
    """عرض سؤال الاختبار الحالي"""
    db = get_db()
    row = db.execute(
        "SELECT test_key, current_index, score FROM test_sessions WHERE user_id = ?",
        (uid,)
    ).fetchone()
    
    if not row:
        return
    
    key, i, score = row['test_key'], row['current_index'], row['score']
    qs = TESTS[key]["q"]
    
    if i >= len(qs):
        total = len(qs) * 3
        send(chat_id, f"النتيجة: <b>{score}</b> من {total}\n{test_interpret(key, score)}", reply_kb())
        db.execute("DELETE FROM test_sessions WHERE user_id = ?", (uid,))
        db.commit()
        return
    
    q = qs[i]
    send(chat_id, f"س{ i+1 }: {q}", inline([
        [{"text":ANS[0][0],"callback_data":"qa0"}, {"text":ANS[1][0],"callback_data":"qa1"}],
        [{"text":ANS[2][0],"callback_data":"qa2"}, {"text":ANS[3][0],"callback_data":"qa3"}],
    ]))

def test_record(chat_id, uid, idx):
    """تسجيل إجابة الاختبار"""
    if idx < 0 or idx > 3:
        send(chat_id, "إجابة غير صالحة.", reply_kb())
        return
    
    db = get_db()
    row = db.execute(
        "SELECT test_key, current_index, score FROM test_sessions WHERE user_id = ?",
        (uid,)
    ).fetchone()
    
    if not row:
        return
    
    key, i, score = row['test_key'], row['current_index'], row['score']
    new_score = score + ANS[idx][1]
    new_index = i + 1
    
    db.execute(
        "UPDATE test_sessions SET current_index = ?, score = ? WHERE user_id = ?",
        (new_index, new_score, uid)
    )
    db.commit()
    
    test_ask(chat_id, uid)

def test_interpret(key, score):
    """تفسير نتائج الاختبار"""
    if key == "g7":
        if score <= 4: lvl = "ضئيل"
        elif score <= 9: lvl = "خفيف"
        elif score <= 14: lvl = "متوسط"
        else: lvl = "شديد"
        return f"<b>مؤشرات قلق {lvl}</b> (تعليمي).\nنصيحة: تنفّس ببطء، قلّل الكافيين، وثبّت نومك."
    
    if key == "phq":
        if score <= 4: lvl = "ضئيل"
        elif score <= 9: lvl = "خفيف"
        elif score <= 14: lvl = "متوسط"
        elif score <= 19: lvl = "متوسط إلى شديد"
        else: lvl = "شديد"
        return f"<b>مؤشرات اكتئاب {lvl}</b> (تعليمي).\nنصيحة: تنشيط سلوكي + روتين نوم + تواصل اجتماعي."
    
    return "تم."

# =============== باقي الكود (CBT، التثقيف، التشخيص التعليمي) ===============
# [يتبع بنفس نمط التعديلات السابقة مع استخدام قاعدة البيانات]

# =============== صفحات وويبهوك ===============
@app.before_first_request
def before_first_request():
    """تهيئة قاعدة البيانات قبل أول طلب"""
    init_db()

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
        },
        "database": "SQLite with session persistence"
    })

@app.get("/setwebhook")
def set_hook():
    if not RENDER_EXTERNAL_URL:
        return jsonify({"ok": False, "error": "RENDER_EXTERNAL_URL not set"}), 400
    
    url = f"{RENDER_EXTERNAL_URL}/webhook/{WEBHOOK_SECRET}"
    try:
        res = requests.post(f"{BOT_API}/setWebhook", json={"url": url}, timeout=15)
        return res.json(), res.status_code
    except requests.exceptions.RequestException as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    try:
        upd = request.get_json(force=True, silent=True) or {}
        
        # [معالجة الرسائل والكولباك بنفس المنطق السابق مع استخدام الدوال المحسنة]
        
        return "ok", 200
    except Exception as e:
        log.error("Webhook error: %s", e)
        return "error", 500

# =============== تشغيل التطبيق ===============
if __name__ == "__main__":
    # تهيئة قاعدة البيانات
    with app.app_context():
        init_db()
    
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
