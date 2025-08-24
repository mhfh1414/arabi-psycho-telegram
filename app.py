# app.py — عربي سايكو (AI + DSM5 إرشادي + CBT مطوّر + اختبارات نفسية + اختبارات شخصية + تحويل طبي)
# Python 3.10+ | python-telegram-bot v21.6

import os, re, asyncio, json, logging, time
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

import requests
from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

# ===== إعدادات عامة =====
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho")

VERSION = "2025-08-24.C"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("يرجى ضبط TELEGRAM_BOT_TOKEN")

# ذكاء اصطناعي
AI_BASE_URL = (os.getenv("AI_BASE_URL") or "").strip()
AI_API_KEY  = (os.getenv("AI_API_KEY") or "").strip()
AI_MODEL    = os.getenv("AI_MODEL", "gpt-4o-mini").strip()

# روابط تحويل (اختياري)
CONTACT_THERAPIST_URL    = os.getenv("CONTACT_THERAPIST_URL", "")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "")

# Webhook (Render) أو Polling
PUBLIC_URL = os.getenv("PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL")
PORT = int(os.getenv("PORT", "10000"))

# ===== أدوات =====
AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
EN_DIGITS = "0123456789"
TRANS = str.maketrans(AR_DIGITS, EN_DIGITS)
def normalize_num(s: str) -> str: return (s or "").translate(TRANS).strip()
def to_int(s: str) -> Optional[int]:
    try: return int(normalize_num(s))
    except: return None
def has(word: str, t: str) -> bool: return word in (t or "")

async def send_long(chat, text, kb=None):
    chunk = 3500
    for i in range(0, len(text), chunk):
        await chat.send_message(text[i:i+chunk], reply_markup=kb if i+chunk>=len(text) else None)

def yn(s: str) -> Optional[bool]:
    t = (s or "").strip().lower()
    return {"نعم":True,"ايوا":True,"ايوه":True,"ا":True,"yes":True,"y":True,
            "لا":False,"no":False,"n":False}.get(t)

# ===== قوائم =====
TOP_KB = ReplyKeyboardMarkup(
    [
        ["عربي سايكو 🧠"],
        ["العلاج السلوكي (CBT) 🧰", "الاختبارات النفسية 📝"],
        ["اختبارات الشخصية 🧩", "التحويل الطبي 👨‍⚕️"]
    ],
    resize_keyboard=True
)

CBT_KB = ReplyKeyboardMarkup(
    [
        ["علاج القلق (4 أسابيع)", "علاج الاكتئاب (تنشيط)"],
        ["إدارة الغضب", "التغلّب على الخوف"],
        ["سجلّ الأفكار 🧠", "تعرّض تدريجي (قلق/خوف)"],
        ["أدوات سريعة", "سجلّ المزاج"],
        ["◀️ رجوع"]
    ],
    resize_keyboard=True
)

TESTS_KB = ReplyKeyboardMarkup(
    [
        ["PHQ-9 اكتئاب", "GAD-7 قلق"],
        ["PC-PTSD-5 صدمة", "PCL-5 صدمة (20)"],
        ["Mini-SPIN رهاب اجتماعي", "فحص نوبات الهلع"],
        ["ISI-7 أرق", "PSS-10 ضغوط"],
        ["WHO-5 رفاه", "K10 ضيق نفسي"],
        ["◀️ رجوع"]
    ],
    resize_keyboard=True
)

PERSON_KB = ReplyKeyboardMarkup(
    [
        ["TIPI — الخمسة الكبار (10)"],
        ["SAPAS — فحص اضطراب شخصية"],
        ["MSI-BPD — فحص حدّية"],
        ["◀️ رجوع"]
    ],
    resize_keyboard=True
)

AI_CHAT_KB = ReplyKeyboardMarkup([["◀️ إنهاء جلسة عربي سايكو"]], resize_keyboard=True)

# ===== حالات المحادثة =====
MENU, CBT_MENU, TESTS_MENU, PERSON_MENU, AI_CHAT = range(5)
# سجلّ الأفكار
TH_SITU, TH_EMO, TH_AUTO, TH_FOR, TH_AGAINST, TH_ALT, TH_RERATE = range(10,17)
# التعرّض
EXPO_WAIT, EXPO_FLOW = range(20,22)
# اختبارات ثنائية/درجات
PANIC_Q, PTSD_Q, SURVEY = range(30,33)

# ===== أمان =====
CRISIS_WORDS = ["انتحار","قتل نفسي","اذي نفسي","سأؤذي نفسي","لا اريد العيش","ابي اموت","اريد اموت","فقدت الامل"]
def is_crisis(txt: str) -> bool:
    low = (txt or "").replace("أ","ا").replace("إ","ا").replace("آ","ا").lower()
    return any(w in low for w in CRISIS_WORDS)

# ===== ذكاء اصطناعي =====
AI_SYSTEM_GENERAL = (
    "أنت «عربي سايكو» — معالج نفسي افتراضي عربي يعتمد مبادئ CBT "
    "وتحت إشراف أخصائي نفسي مرخّص. لست بديلاً عن الطوارئ/التشخيص الطبي.\n"
    "قدّم أسئلة استكشافية قصيرة وخطوات سلوكية عملية وختم بنقاط تنفيذ بسيطة."
)
AI_SYSTEM_DSM = (
    "أنت «عربي سايكو» بوضع **تشخيص استرشادي DSM-5** (غير تشخيص طبي). "
    "رتّب الأعراض مع (المدة/الشدة/التأثير الوظيفي/الضغوط/العوامل)، وقدّم مسارات تقييم "
    "واحتمالات تعليمية، وتنبيهات أمان، وتمارين CBT مناسبة. تجنّب الجزم بالتشخيص."
)

def ai_call(user_content: str, history: List[Dict[str,str]], dsm_mode: bool) -> str:
    if not (AI_BASE_URL and AI_API_KEY and AI_MODEL):
        return "تعذّر استخدام الذكاء الاصطناعي (تحقق من المفتاح/النموذج/العنوان)."
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type":"application/json"}
    sys = AI_SYSTEM_DSM if dsm_mode else AI_SYSTEM_GENERAL
    payload = {
        "model": AI_MODEL,
        "messages": [{"role":"system","content":sys}] + history + [{"role":"user","content":user_content}],
        "temperature": 0.4,
        "max_tokens": 800
    }
    try:
        r = requests.post(f"{AI_BASE_URL.rstrip('/')}/chat/completions", data=json.dumps(payload), headers=headers, timeout=35)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"تعذّر الاتصال بالذكاء الاصطناعي: {e}"

async def ai_respond(text: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    if is_crisis(text):
        return ("⚠️ لو كان لديك خطر فوري على نفسك/غيرك اتصل بالطوارئ. "
                "جرّب الآن تنفس 4-7-8 لعشر مرات واطلب الدعم من شخص موثوق وحدد موعدًا مع مختص.")
    hist: List[Dict[str,str]] = context.user_data.get("ai_hist", [])[-20:]
    dsm_mode = (context.user_data.get("ai_mode") == "dsm")
    reply = await asyncio.to_thread(ai_call, text, hist, dsm_mode)
    hist += [{"role":"user","content":text},{"role":"assistant","content":reply}]
    context.user_data["ai_hist"] = hist[-20:]
    return reply

# ===== نصوص CBT مطوّرة =====
CBT_TXT = {
"anx": (
"🧭 **خطة علاج القلق (4 أسابيع)**\n"
"أ) تثبيت روتين: نوم/صحوة ثابتة، كافيين أقل، حركة يومية 20د.\n"
"ب) أدوات يومية: تنفس 4-7-8 ×3 مرات/اليوم، تمرين تأريض 5-4-3-2-1، كتابة فكرة ↔ بديل.\n"
"ج) تعرّض تدريجي: سلّم مواقف 0–10 وابدأ 3–4/10، ابقَ حتى يهبط القلق ≥ النصف.\n"
"د) تواصل: صديق/مجتمع داعم 2–3 مرات بالأسبوع.\n"
"هـ) تقييم أسبوعي: سجل تقدّمك 0–10 واضبط الخطة."
),
"dep": (
"🌱 **تنشيط سلوكي للاكتئاب**\n"
"١) أنشطة رعاية ذاتية يومية (أكل/دش/مشية قصيرة).\n"
"٢) نشاط ممتع صغير 10–20د (موسيقى/هواية بسيطة).\n"
"٣) مهمة ذات معنى (5–15د) نحو قيمة مهمة لك.\n"
"٤) تتبّع المزاج قبل/بعد (0–10) لملاحظة التحسّن التدريجي."
),
"anger": (
"🔥 **إدارة الغضب (خطوات سريعة)**\n"
"• لاحظ إشارات الجسد (شدّ/سخونة). خذ مهلة 20 دقيقة.\n"
"• تنفّس 4-7-8؛ اكتب أفكارك ثم صحّح التعميم/التهويل.\n"
"• اختر سلوكًا آمنًا (مغادرة/ماء/مشي)، ثم عُد للنقاش باتفاق: وقت/دور لكل طرف/ملخّص."
),
"fear": (
"🧗 **التغلّب على الخوف (تعرّض + منع الطمأنة)**\n"
"1) اكتب هرم المواقف 0–10.\n"
"2) ابدأ من 3–4/10، ابقَ حتى يهبط القلق للنصف دون طمأنة.\n"
"3) كرّر الموقف حتى يصبح 1–2/10 ثم اصعد للدرجة التالية."
),
"quick": (
"🧰 **أدوات سريعة**\n"
"• تنفّس 4-7-8 ×4.\n"
"• شد/إرخاء عضلي تدريجي من القدم للرأس.\n"
"• تأريض 5-4-3-2-1 للحظة الحالية.\n"
"• حل المشكلات: تعريف دقيق → بدائل → مزايا/عيوب → خطة → تجربة → تقييم."
),
"mood": (
"📒 **سجل المزاج (يومي)**\n"
"– قيّم مزاجك 0–10 الآن.\n"
"– ماذا حدث اليوم؟ ومن حولك؟\n"
"– الفكرة السائدة؟ والسلوك الذي فعلته؟\n"
"– خطوة صغيرة لتحسين نقطة واحدة؟"
)
}

# ===== تمارين CBT التفاعلية =====
@dataclass
class ThoughtRecord:
    situation: str = ""
    emotion: str = ""
    auto: str = ""
    ev_for: str = ""
    ev_against: str = ""
    alternative: str = ""
    start: Optional[int] = None
    end: Optional[int] = None

@dataclass
class ExposureState:
    suds: Optional[int] = None
    plan: Optional[str] = None

# ===== الاستبيانات =====
@dataclass
class Survey:
    id: str
    title: str
    items: List[str]
    scale: str
    min_v: int
    max_v: int
    reverse: List[int] = field(default_factory=list)
    ans: List[int] = field(default_factory=list)

def survey_prompt(s: Survey, i: int) -> str:
    return f"({i+1}/{len(s.items)}) {s.items[i]}\n{ s.scale }"

# --- بنوك أسئلة (مختصرات عربية) ---
PHQ9 = Survey("phq9","PHQ-9 — الاكتئاب",
["قلة الاهتمام/المتعة","الإحباط/اليأس","مشاكل النوم","التعب/قلة الطاقة","تغير الشهية",
 "الشعور بالسوء عن النفس","صعوبة التركيز","بطء/توتر ملحوظ","أفكار بإيذاء النفس"],
"0=أبدًا،1=عدة أيام،2=أكثر من نصف الأيام،3=تقريبًا كل يوم",0,3)

GAD7 = Survey("gad7","GAD-7 — القلق",
["توتر/قلق/عصبية","صعوبة إيقاف القلق","الانشغال بالهموم","صعوبة الاسترخاء",
 "تململ","العصبية/الانزعاج بسهولة","الخوف من حدوث أمر سيئ"],
"0=أبدًا،1=عدة أيام،2=أكثر من نصف الأيام،3=تقريبًا كل يوم",0,3)

MINISPIN = Survey("minispin","Mini-SPIN — الرهاب الاجتماعي",
["أتجنب مواقف اجتماعية خوف الإحراج","أقلق أن يلاحظ الآخرون ارتباكي","أخاف التحدث أمام الآخرين"],
"0=أبدًا،1=قليلًا،2=إلى حد ما،3=كثيرًا،4=جداً",0,4)

TIPI = Survey("tipi","TIPI — الخمسة الكبار (10)",
["منفتح/اجتماعي","ناقد قليل المودة (عكسي)","منظم/موثوق","يتوتر بسهولة",
 "منفتح على الخبرة","انطوائي/خجول (عكسي)","ودود/متعاون","مهمل/عشوائي (عكسي)",
 "هادئ وثابت (عكسي)","تقليدي/غير خيالي (عكسي)"],
"قيّم 1–7 (1=لا تنطبق…7=تنطبق تمامًا)",1,7,reverse=[1,5,7,8,9])

ISI7 = Survey("isi7","ISI-7 — الأرق",
["صعوبة بدء النوم","صعوبة الاستمرار بالنوم","الاستيقاظ المبكر","الرضا عن النوم",
 "تأثير الأرق على الأداء بالنهار","ملاحظة الآخرين للمشكلة","القلق/الانزعاج من نومك"],
"0=لا،1=خفيف،2=متوسط،3=شديد،4=شديد جدًا",0,4)

PSS10 = Survey("pss10","PSS-10 — الضغوط المُدركة",
["كم شعرت بأن الأمور خرجت عن سيطرتك؟","كم انزعجت من أمر غير متوقع؟","كم شعرت بالتوتر؟",
 "كم شعرت بأنك تتحكم بالأمور؟ (عكسي)","كم شعرت بالثقة في التعامل مع مشكلاتك؟ (عكسي)",
 "كم شعرت أن الأمور تسير كما ترغب؟ (عكسي)","كم لم تستطع التأقلم مع كل ما عليك؟",
 "كم سيطرت على الانفعالات؟ (عكسي)","كم شعرت بأن المشاكل تتراكم؟","كم وجدت وقتًا للأشياء المهمة؟ (عكسي)"],
"0=أبدًا،1=نادرًا،2=أحيانًا،3=كثيرًا،4=دائمًا",0,4,reverse=[3,4,5,7,9])

WHO5 = Survey("who5","WHO-5 — الرفاه",
["شعرتُ بالمزاج الجيد","شعرتُ بالهدوء والسكينة","شعرتُ بالنشاط","كنتُ أستيقظ مرتاحًا","كان يومي ذا معنى"],
"0=أبدًا…5=طوال الوقت",0,5)

K10 = Survey("k10","K10 — الضيق النفسي (آخر 4 أسابيع)",
["كم مرة شعرت بالتعب من غير سبب؟","عصبي/متوتر؟","ميؤوس؟","قلق شديد؟","كل شيء جهد عليك؟",
 "لا تستطيع الهدوء؟","حزين بشدة؟","لا شيء يفرحك؟","لا تحتمل التأخير؟","شعور بلا قيمة؟"],
"1=أبدًا،2=قليلًا،3=أحيانًا،4=غالبًا،5=دائمًا",1,5)

PC_PTSD5_Q = [
"آخر شهر: كوابيس/ذكريات مزعجة للحدث؟ (نعم/لا)",
"تجنّبت التفكير/الأماكن المرتبطة؟ (نعم/لا)",
"كنت على أعصابك/سريع الفزع؟ (نعم/لا)",
"شعرت بالخدر/الانفصال عن الناس/الأنشطة؟ (نعم/لا)",
"شعرت بالذنب/اللوم بسبب الحدث؟ (نعم/لا)"
]

# PCL-5 (20 بند، 0-4)
PCL5 = Survey("pcl5","PCL-5 — أعراض الصدمة (20)",
[
"ذكريات مزعجة متكررة عن الحدث","أحلام مزعجة عن الحدث","تصرفات/شعور كأن الحدث يعاد",
"انزعاج شديد عند التذكير","تفاعلات جسدية قوية عند التذكير","تجنب الأفكار/المشاعر المرتبطة",
"تجنب الأماكن/الناس المرتبطة","ثغرات في الذاكرة حول الحدث","معتقدات سلبية عن الذات/العالم",
"لوم نفسك/الآخرين بشكل مبالغ فيه","حالة سلبية مستمرة (خوف/غضب/ذنب...)",
"فقدان الاهتمام بالأنشطة","شعور بالانفصال عن الآخرين","صعوبة الشعور بالمشاعر الإيجابية",
"تهيّج/نوبات غضب","سلوك متهوّر/مفرط المخاطرة","فرط يقظة","تركيز صعب",
"زيادة الفزع/الارتباك","مشاكل نوم"
],
"0=أبدًا،1=قليلًا،2=متوسطًا،3=كثيرًا،4=شديدًا",0,4)

SAPAS_Q = [
"هل علاقاتك القريبة غير مستقرة؟ (نعم/لا)","هل تتصرف اندفاعيًا؟ (نعم/لا)","خلافات متكررة؟ (نعم/لا)",
"يراك الناس «غريب الأطوار»؟ (نعم/لا)","صعوبة الثقة بالناس؟ (نعم/لا)","تتجنب الاختلاط خوف الإحراج؟ (نعم/لا)",
"تقلق كثيرًا على أشياء صغيرة؟ (نعم/لا)","كمالية/صرامة تؤثر على حياتك؟ (نعم/لا)"
]
MSI_BPD_Q = [
"علاقات شديدة التقلب؟ (نعم/لا)","صورة ذات متقلبة جدًا؟ (نعم/لا)","اندفاع مؤذٍ أحيانًا؟ (نعم/لا)",
"تهديدات/محاولات إيذاء؟ (نعم/لا)","تقلبات مشاعر شديدة؟ (نعم/لا)","فراغ داخلي مستمر؟ (نعم/لا)",
"غضب شديد يصعب تهدئته؟ (نعم/لا)","خوف قوي من الهجر؟ (نعم/لا)","توتر شديد/أفكار غريبة؟ (نعم/لا)","تجنّب/اختبارات للآخرين خوف الهجر؟ (نعم/لا)"
]

# حالات ثنائية
@dataclass
class BinState:
    i: int = 0
    yes: int = 0
    qs: List[str] = field(default_factory=list)

# ===== الأوامر =====
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        "مرحبًا! أنا **عربي سايكو**.\n"
        "— معك معالج نفسي افتراضي بالذكاء الاصطناعي تحت إشراف أخصائي نفسي مرخّص.\n"
        "اختر من الأزرار:", reply_markup=TOP_KB
    )
    return MENU

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/start — القائمة\n/help — مساعدة\n/version — رقم النسخة\n/ai_diag — فحص إعدادات الذكاء")

async def cmd_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"ArabiPsycho v{VERSION}")

async def cmd_ai_diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"AI_BASE_URL set={bool(AI_BASE_URL)} | KEY set={bool(AI_API_KEY)} | MODEL={AI_MODEL}")

# ===== تحويل طبي =====
def referral_keyboard():
    rows = []
    if CONTACT_THERAPIST_URL:
        rows.append([InlineKeyboardButton("👨‍⚕️ تحويل إلى أخصائي نفسي", url=CONTACT_THERAPIST_URL)])
    if CONTACT_PSYCHIATRIST_URL:
        rows.append([InlineKeyboardButton("👨‍⚕️ تحويل إلى طبيب نفسي", url=CONTACT_PSYCHIATRIST_URL)])
    if not rows:
        rows.append([InlineKeyboardButton("تواصل عبر تيليجرام", url="https://t.me/")])
    return InlineKeyboardMarkup(rows)

# ===== المستوى الأعلى =====
async def top_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if has("عربي سايكو", t):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("ابدأ جلسة عربي سايكو 🤖", callback_data="start_ai")],
            [InlineKeyboardButton("تشخيص استرشادي DSM-5", callback_data="start_dsm")]
        ])
        await update.message.reply_text(
            "معك عربي سايكو — معالج نفسي افتراضي بالذكاء الاصطناعي (ليس بديلاً للطوارئ/التشخيص الطبي).",
            reply_markup=kb
        ); return MENU

    if has("العلاج السلوكي", t):
        await update.message.reply_text("اختر أداة/خطة:", reply_markup=CBT_KB); return CBT_MENU

    if has("الاختبارات النفسية", t):
        await update.message.reply_text("اختر اختبارًا:", reply_markup=TESTS_KB); return TESTS_MENU

    if has("اختبارات الشخصية", t):
        await update.message.reply_text("اختر اختبار شخصية:", reply_markup=PERSON_KB); return PERSON_MENU

    if has("التحويل الطبي", t):
        await update.message.reply_text("خيارات التحويل:", reply_markup=referral_keyboard()); return MENU

    await update.message.reply_text("اختر من الأزرار أو اكتب /help.", reply_markup=TOP_KB); return MENU

# ===== AI =====
async def ai_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["ai_mode"] = "free"; context.user_data["ai_hist"] = []
    await q.message.chat.send_message(
        "✅ بدأت جلسة **عربي سايكو** (ذكاء اصطناعي). اكتب شكواك الآن.\n"
        "تذكير: هذا دعم تعليمي/سلوكي وليس تشخيصًا طبيًا.\n"
        "لإنهاء الجلسة: «◀️ إنهاء جلسة عربي سايكو».",
        reply_markup=AI_CHAT_KB
    ); return AI_CHAT

async def dsm_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["ai_mode"] = "dsm"; context.user_data["ai_hist"] = []
    await q.message.chat.send_message(
        "✅ دخلت وضع **DSM-5 الاسترشادي** (غير تشخيص). صف الأعراض بالمدة/الشدة/الأثر.",
        reply_markup=AI_CHAT_KB
    ); return AI_CHAT

async def ai_chat_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text in ("◀️ إنهاء جلسة عربي سايكو","خروج","/خروج"):
        await update.message.reply_text("انتهت الجلسة. رجعناك للقائمة.", reply_markup=TOP_KB); return MENU
    await update.effective_chat.send_action(ChatAction.TYPING)
    reply = await ai_respond(text, context)
    await update.message.reply_text(reply, reply_markup=AI_CHAT_KB); return AI_CHAT

# ===== CBT Router =====
async def cbt_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if t == "◀️ رجوع":
        await update.message.reply_text("رجعناك للقائمة.", reply_markup=TOP_KB); return MENU
    if has("علاج القلق", t):   await send_long(update.effective_chat, CBT_TXT["anx"], CBT_KB); return CBT_MENU
    if has("علاج الاكتئاب", t): await send_long(update.effective_chat, CBT_TXT["dep"], CBT_KB); return CBT_MENU
    if has("إدارة الغضب", t):   await send_long(update.effective_chat, CBT_TXT["anger"], CBT_KB); return CBT_MENU
    if has("الخوف", t):         await send_long(update.effective_chat, CBT_TXT["fear"], CBT_KB); return CBT_MENU
    if has("أدوات سريعة", t):   await send_long(update.effective_chat, CBT_TXT["quick"], CBT_KB); return CBT_MENU
    if has("سجلّ المزاج", t):   await send_long(update.effective_chat, CBT_TXT["mood"], CBT_KB); return CBT_MENU

    if has("سجلّ الأفكار", t):
        context.user_data["tr"] = ThoughtRecord()
        await update.message.reply_text("📝 اكتب **الموقف** (متى/أين/مع من؟).", reply_markup=ReplyKeyboardRemove()); return TH_SITU

    if has("تعرّض تدريجي", t):
        context.user_data["expo"] = ExposureState()
        await update.message.reply_text("أرسل درجة قلقك الحالية 0–10.", reply_markup=ReplyKeyboardRemove()); return EXPO_WAIT

    await update.message.reply_text("اختر أداة من القائمة:", reply_markup=CBT_KB); return CBT_MENU

async def cbt_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # حالياً لا حاجة لالتقاط نص حر إضافي هنا
    return CBT_MENU

# سجل الأفكار
async def tr_situ(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tr: ThoughtRecord = context.user_data["tr"]; tr.situation = update.message.text.strip()
    await update.message.reply_text("ما الشعور الآن؟ اكتب الاسم وقيمته (مثال: قلق 7/10).");  return TH_EMO
async def tr_emo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tr: ThoughtRecord = context.user_data["tr"]; tr.emotion = update.message.text.strip()
    m = re.search(r"(\d+)", normalize_num(tr.emotion)); tr.start = int(m.group(1)) if m else None
    await update.message.reply_text("ما **الفكرة التلقائية**؟");  return TH_AUTO
async def tr_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tr: ThoughtRecord = context.user_data["tr"]; tr.auto = update.message.text.strip()
    await update.message.reply_text("اكتب **أدلة تؤيد** الفكرة.");  return TH_FOR
async def tr_for(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tr: ThoughtRecord = context.user_data["tr"]; tr.ev_for = update.message.text.strip()
    await update.message.reply_text("اكتب **أدلة تنفي** الفكرة.");  return TH_AGAINST
async def tr_against(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tr: ThoughtRecord = context.user_data["tr"]; tr.ev_against = update.message.text.strip()
    await update.message.reply_text("اكتب **فكرة بديلة متوازنة**.");  return TH_ALT
async def tr_alt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tr: ThoughtRecord = context.user_data["tr"]; tr.alternative = update.message.text.strip()
    await update.message.reply_text("أعد تقييم الشعور 0–10.");  return TH_RERATE
async def tr_rerate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tr: ThoughtRecord = context.user_data["tr"]; tr.end = to_int(update.message.text)
    txt = (
        "✅ **ملخّص سجلّ الأفكار**\n"
        f"• الموقف: {tr.situation}\n• الشعور قبل: {tr.emotion}\n• الفكرة: {tr.auto}\n"
        f"• أدلة تؤيد: {tr.ev_for}\n• أدلة تنفي: {tr.ev_against}\n• البديل: {tr.alternative}\n"
        f"• التقييم بعد: {tr.end if tr.end is not None else '—'}\nاستمر يوميًا."
    )
    await send_long(update.effective_chat, txt, CBT_KB); return CBT_MENU

# التعرّض
async def expo_wait(update: Update, context: ContextTypes.DEFAULT_TYPE):
    n = to_int(update.message.text); 
    if n is None or not (0 <= n <= 10):
        await update.message.reply_text("أرسل رقمًا من 0 إلى 10.");  return EXPO_WAIT
    st: ExposureState = context.user_data["expo"]; st.suds = n
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("أمثلة 3–4/10", callback_data="expo_suggest")],
        [InlineKeyboardButton("شرح سريع", callback_data="expo_help")]
    ])
    await update.message.reply_text(f"درجتك = {n}/10. اكتب موقفًا مناسبًا 3–4/10 أو استخدم الأزرار.", reply_markup=kb); return EXPO_FLOW

async def expo_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "expo_suggest":
        await q.edit_message_text("أمثلة: ركوب المصعد لطابقين، انتظار صف قصير، الجلوس بمقهى 10 دقائق قرب المخرج.\nاكتب موقفك.")
    else:
        await q.edit_message_text("القاعدة: تعرّض آمن + منع طمأنة + البقاء حتى يهبط القلق ≥ النصف ثم كرّر.")
    return EXPO_FLOW

async def expo_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st: ExposureState = context.user_data["expo"]; st.plan = (update.message.text or "").strip()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ابدأ الآن", callback_data="expo_start")],
        [InlineKeyboardButton("تم — قيّم الدرجة", callback_data="expo_rate")]
    ])
    await update.message.reply_text(f"خطة التعرض:\n• {st.plan}\nابدأ وابقَ حتى يهبط القلق ≥ النصف.", reply_markup=kb); return EXPO_FLOW

async def expo_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "expo_start": await q.edit_message_text("بالتوفيق! عند الانتهاء أرسل الدرجة الجديدة 0–10.");  return EXPO_WAIT
    if q.data == "expo_rate":  await q.edit_message_text("أرسل الدرجة الجديدة 0–10.");  return EXPO_WAIT
    return EXPO_FLOW

# ===== Router الاختبارات =====
async def tests_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if t == "◀️ رجوع":
        await update.message.reply_text("رجعناك للقائمة.", reply_markup=TOP_KB);  return MENU

    key = {
        "PHQ-9 اكتئاب":"phq9","GAD-7 قلق":"gad7","Mini-SPIN رهاب اجتماعي":"minispin",
        "PC-PTSD-5 صدمة":"pcptsd5","PCL-5 صدمة (20)":"pcl5","فحص نوبات الهلع":"panic",
        "ISI-7 أرق":"isi7","PSS-10 ضغوط":"pss10","WHO-5 رفاه":"who5","K10 ضيق نفسي":"k10"
    }.get(t)

    if key is None:
        await update.message.reply_text("اختر اختبارًا:", reply_markup=TESTS_KB);  return TESTS_MENU

    # فحص الهلع
    if key == "panic":
        context.user_data["panic"] = BinState(i=0, yes=0, qs=[
            "آخر 4 أسابيع: هل حدثت لديك نوبات هلع مفاجئة؟ (نعم/لا)",
            "هل تخاف من حدوث نوبة أخرى أو تتجنب أماكن بسببها؟ (نعم/لا)"
        ])
        await update.message.reply_text(context.user_data["panic"].qs[0], reply_markup=ReplyKeyboardRemove());  return PANIC_Q

    # PC-PTSD-5
    if key == "pcptsd5":
        context.user_data["pc"] = BinState(i=0, yes=0, qs=PC_PTSD5_Q)
        await update.message.reply_text(PC_PTSD5_Q[0], reply_markup=ReplyKeyboardRemove());  return PTSD_Q

    # PCL-5
    if key == "pcl5":
        s = Survey(PCL5.id, PCL5.title, list(PCL5.items), PCL5.scale, PCL5.min_v, PCL5.max_v)
        context.user_data["s"] = s; context.user_data["s_i"] = 0
        await update.message.reply_text(f"بدء **{s.title}**.\n{survey_prompt(s,0)}", reply_markup=ReplyKeyboardRemove())
        return SURVEY

    # بقية المقاييس الرقمية
    s_map = {"phq9":PHQ9,"gad7":GAD7,"minispin":MINISPIN,"isi7":ISI7,"pss10":PSS10,"who5":WHO5,"k10":K10}
    s0 = s_map[key]
    s = Survey(s0.id, s0.title, list(s0.items), s0.scale, s0.min_v, s0.max_v, list(s0.reverse))
    context.user_data["s"] = s; context.user_data["s_i"] = 0
    await update.message.reply_text(f"بدء **{s.title}**.\n{survey_prompt(s,0)}", reply_markup=ReplyKeyboardRemove())
    return SURVEY

# ===== Router اختبارات الشخصية =====
async def person_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if t == "◀️ رجوع":
        await update.message.reply_text("رجعناك للقائمة.", reply_markup=TOP_KB);  return MENU

    key = {"TIPI — الخمسة الكبار (10)":"tipi","SAPAS — فحص اضطراب شخصية":"sapas","MSI-BPD — فحص حدّية":"msi"}.get(t)
    if key is None:
        await update.message.reply_text("اختر اختبار شخصية:", reply_markup=PERSON_KB);  return PERSON_MENU

    if key in ("sapas","msi"):
        qs = SAPAS_Q if key=="sapas" else MSI_BPD_Q
        context.user_data["bin"] = BinState(i=0, yes=0, qs=qs)
        await update.message.reply_text(qs[0], reply_markup=ReplyKeyboardRemove());  return SURVEY

    if key == "tipi":
        s = Survey(TIPI.id, TIPI.title, list(TIPI.items), TIPI.scale, TIPI.min_v, TIPI.max_v, list(TIPI.reverse))
        context.user_data["s"] = s; context.user_data["s_i"] = 0
        await update.message.reply_text(f"بدء **{s.title}**.\n{survey_prompt(s,0)}", reply_markup=ReplyKeyboardRemove());  return SURVEY

# ===== تدفقات الاختبارات =====
async def panic_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st: BinState = context.user_data["panic"]; ans = yn(update.message.text)
    if ans is None: await update.message.reply_text("أجب بـ نعم/لا.");  return PANIC_Q
    st.yes += 1 if ans else 0; st.i += 1
    if st.i < len(st.qs): await update.message.reply_text(st.qs[st.i]);  return PANIC_Q
    msg = "إيجابي — يحتمل وجود نوبات هلع" if st.yes==2 else "سلبي — لا مؤشر قوي الآن"
    await update.message.reply_text(f"**نتيجة فحص الهلع:** {msg}", reply_markup=TESTS_KB);  return TESTS_MENU

async def ptsd_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st: BinState = context.user_data["pc"]; ans = yn(update.message.text)
    if ans is None: await update.message.reply_text("أجب بـ نعم/لا.");  return PTSD_Q
    st.yes += 1 if ans else 0; st.i += 1
    if st.i < len(st.qs): await update.message.reply_text(st.qs[st.i]);  return PTSD_Q
    result = "إيجابي (≥3 «نعم») — يُستحسن التقييم." if st.yes>=3 else "سلبي."
    await update.message.reply_text(f"**PC-PTSD-5:** {st.yes}/5 — {result}", reply_markup=TESTS_KB);  return TESTS_MENU

async def survey_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ثنائي (SAPAS/MSI)
    if "bin" in context.user_data:
        st: BinState = context.user_data["bin"]; ans = yn(update.message.text)
        if ans is None: await update.message.reply_text("أجب بـ نعم/لا.");  return SURVEY
        st.yes += 1 if ans else 0; st.i += 1
        if st.i < len(st.qs): await update.message.reply_text(st.qs[st.i]);  return SURVEY
        if len(st.qs)==8:
            msg = f"**SAPAS:** {st.yes}/8 — " + ("إيجابي (≥3) يُستحسن التقييم." if st.yes>=3 else "سلبي.")
        else:
            msg = f"**MSI-BPD:** {st.yes}/10 — " + ("إيجابي (≥7) يُستحسن التقييم." if st.yes>=7 else "سلبي.")
        context.user_data.pop("bin", None)
        await update.message.reply_text(msg, reply_markup=PERSON_KB);  return PERSON_MENU

    # درجات (باقي المقاييس)
    s: Survey = context.user_data["s"]; i = context.user_data["s_i"]
    n = to_int(update.message.text)
    if n is None or not (s.min_v <= n <= s.max_v):
        await update.message.reply_text(f"أدخل رقمًا بين {s.min_v} و{s.max_v}.");  return SURVEY
    s.ans.append(n); i += 1

    if i >= len(s.items):
        # تفسير
        if s.id=="gad7":
            total=sum(s.ans); lvl = "طبيعي/خفيف جدًا" if total<=4 else "خفيف" if total<=9 else "متوسط" if total<=14 else "شديد"
            await update.message.reply_text(f"**GAD-7:** {total}/21 — قلق {lvl}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="phq9":
            total=sum(s.ans)
            lvl = "لا/خفيف جدًا" if total<=4 else "خفيف" if total<=9 else "متوسط" if total<=14 else "متوسط-شديد" if total<=19 else "شديد"
            warn = "\n⚠️ بند أفكار الإيذاء >0 — اطلب مساعدة عاجلة." if s.ans[8]>0 else ""
            await update.message.reply_text(f"**PHQ-9:** {total}/27 — {lvl}{warn}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="minispin":
            total=sum(s.ans); msg="مؤشر رهاب اجتماعي محتمل" if total>=6 else "أقل من حد الإشارة"
            await update.message.reply_text(f"**Mini-SPIN:** {total}/12 — {msg}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="isi7":
            total=sum(s.ans); lvl="ضئيل" if total<=7 else "خفيف" if total<=14 else "متوسط" if total<=21 else "شديد"
            await update.message.reply_text(f"**ISI-7:** {total}/28 — أرق {lvl}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="pss10":
            vals=s.ans[:]
            for idx in s.reverse: vals[idx] = s.max_v - vals[idx]
            total=sum(vals); lvl="منخفض" if total<=13 else "متوسط" if total<=26 else "عالٍ"
            await update.message.reply_text(f"**PSS-10:** {total}/40 — ضغط {lvl}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="who5":
            score=sum(s.ans)*4; note="منخفض (≤50) — حسّن الروتين وتواصل مع مختص عند الحاجة." if score<=50 else "جيد."
            await update.message.reply_text(f"**WHO-5:** {score}/100 — {note}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="k10":
            total=sum(s.ans); lvl="خفيف" if total<=19 else "متوسط" if total<=24 else "شديد" if total<=29 else "شديد جدًا"
            await update.message.reply_text(f"**K10:** {total}/50 — ضيق {lvl}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="tipi":
            vals=s.ans[:]
            for idx in s.reverse: vals[idx] = 8 - vals[idx]
            extr=(vals[0]+vals[5])/2; agre=(vals[1]+vals[6])/2; cons=(vals[2]+vals[7])/2; emot=(vals[3]+vals[8])/2; open_=(vals[4]+vals[9])/2
            def lab(x): return "عالٍ" if x>=5.5 else "منخفض" if x<=2.5 else "متوسط"
            msg=(f"**TIPI (1–7):**\n"
                 f"• الانبساط: {extr:.1f} ({lab(extr)})\n• التوافق: {agre:.1f} ({lab(agre)})\n"
                 f"• الانضباط: {cons:.1f} ({lab(cons)})\n• الاستقرار الانفعالي: {emot:.1f} ({lab(emot)})\n"
                 f"• الانفتاح: {open_:.1f} ({lab(open_)})")
            await update.message.reply_text(msg, reply_markup=PERSON_KB);  return PERSON_MENU
        if s.id=="pcl5":
            total=sum(s.ans); note="إشارة مرتفعة (≥31–33) — يُستحسن تقييم مختص." if total>=31 else "أقل من حد الإشارة."
            await update.message.reply_text(f"**PCL-5:** {total}/80 — {note}", reply_markup=TESTS_KB);  return TESTS_MENU

        await update.message.reply_text("تم الحساب.", reply_markup=TESTS_KB);  return TESTS_MENU

    context.user_data["s_i"] = i
    await update.message.reply_text(survey_prompt(s, i));  return SURVEY

# ===== سقوط عام =====
async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اختر من الأزرار أو اكتب /start.", reply_markup=TOP_KB)
    return MENU

# ===== ربط وتشغيل =====
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            MENU:       [MessageHandler(filters.TEXT & ~filters.COMMAND, top_router)],

            CBT_MENU:   [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cbt_free_text),
                MessageHandler(filters.TEXT & ~filters.COMMAND, cbt_router),
            ],

            TH_SITU:    [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_situ)],
            TH_EMO:     [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_emo)],
            TH_AUTO:    [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_auto)],
            TH_FOR:     [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_for)],
            TH_AGAINST: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_against)],
            TH_ALT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_alt)],
            TH_RERATE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_rerate)],

            EXPO_WAIT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, expo_wait)],
            EXPO_FLOW:  [
                CallbackQueryHandler(expo_cb, pattern="^expo_(suggest|help)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, expo_flow),
                CallbackQueryHandler(expo_actions, pattern="^expo_(start|rate)$"),
            ],

            TESTS_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, tests_router)],
            PERSON_MENU:[MessageHandler(filters.TEXT & ~filters.COMMAND, person_router)],

            PANIC_Q:    [MessageHandler(filters.TEXT & ~filters.COMMAND, panic_flow)],
            PTSD_Q:     [MessageHandler(filters.TEXT & ~filters.COMMAND, ptsd_flow)],
            SURVEY:     [MessageHandler(filters.TEXT & ~filters.COMMAND, survey_flow)],

            AI_CHAT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat_flow)],
        },
        fallbacks=[MessageHandler(filters.ALL, fallback)],
        allow_reentry=True
    )

    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("version", cmd_version))
    app.add_handler(CommandHandler("ai_diag", cmd_ai_diag))
    app.add_handler(CallbackQueryHandler(ai_start_cb, pattern="^start_ai$"))
    app.add_handler(CallbackQueryHandler(dsm_start_cb, pattern="^start_dsm$"))
    app.add_handler(conv)

    if PUBLIC_URL:
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=f"{BOT_TOKEN}",
            webhook_url=f"{(PUBLIC_URL or '').rstrip('/')}/{BOT_TOKEN}",
            drop_pending_updates=True
        )
    else:
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
