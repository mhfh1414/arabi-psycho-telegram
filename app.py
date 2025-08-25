# app.py — عربي سايكو (بوت تيليجرام)
# Python 3.10+ | python-telegram-bot v21.6

import os, re, json, asyncio, logging, time
from dataclasses import dataclass, field
from typing import List, Dict, Optional

import requests
from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

# ========= إعداد عام =========
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho")
VERSION = "2025-08-26.1"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("يرجى ضبط TELEGRAM_BOT_TOKEN")

# AI (OpenAI أو OpenRouter بصيغة متوافقة مع /v1/chat/completions)
AI_BASE_URL = (os.getenv("AI_BASE_URL") or "").strip()
AI_API_KEY  = (os.getenv("AI_API_KEY") or "").strip()
AI_MODEL    = (os.getenv("AI_MODEL") or "gpt-4o-mini").strip()

# روابط تحويل (اختياري)
CONTACT_THERAPIST_URL    = os.getenv("CONTACT_THERAPIST_URL", "")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "")

# Webhook (Render) وإلا Polling
PUBLIC_URL = os.getenv("PUBLIC_URL") or os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", "10000"))

# ========= أدوات مساعدة =========
AR_DIG = "٠١٢٣٤٥٦٧٨٩"
EN_DIG = "0123456789"
TRANS  = str.maketrans(AR_DIG, EN_DIG)

def normalize_num(s: str) -> str:
    return (s or "").translate(TRANS).strip()

def to_int(s: str) -> Optional[int]:
    try: return int(normalize_num(s))
    except: return None

async def send_long(chat, text: str, kb=None):
    chunk = 3500
    for i in range(0, len(text), chunk):
        await chat.send_message(text[i:i+chunk], reply_markup=kb if i+chunk>=len(text) else None)

def has(word: str, t: str) -> bool:
    return word in (t or "")

# ========= أمان: كلمات أزمة =========
CRISIS = ["انتحار","سأؤذي نفسي","اذي نفسي","قتل نفسي","ابي اموت","اريد اموت","ما ابغى اعيش","فقدت الامل"]
def is_crisis(txt: str) -> bool:
    low = (txt or "").replace("أ","ا").replace("إ","ا").replace("آ","ا").lower()
    return any(w in low for w in CRISIS)

# ========= لوحات مفاتيح =========
TOP_KB = ReplyKeyboardMarkup(
    [
        ["🧠 عربي سايكو"],
        ["العلاج السلوكي المعرفي (CBT) 💊", "📝 الاختبارات النفسية"],
        ["🧩 اختبارات الشخصية", "التحويل الطبي 👨‍⚕️"],
    ], resize_keyboard=True
)

CBT_KB = ReplyKeyboardMarkup(
    [
        ["ما هو CBT؟", "أخطاء التفكير"],
        ["طرق علاج القلق", "طرق علاج الاكتئاب"],
        ["إدارة الغضب", "التخلّص من الخوف"],
        ["سجلّ الأفكار (تمرين)", "التعرّض التدريجي"],
        ["التنشيط السلوكي", "الاسترخاء والتنفس"],
        ["اليقظة الذهنية", "حل المشكلات"],
        ["بروتوكول النوم", "◀️ رجوع"]
    ], resize_keyboard=True
)

TESTS_KB = ReplyKeyboardMarkup(
    [
        ["PHQ-9 (اكتئاب)", "GAD-7 (قلق)"],
        ["PC-PTSD-5 (صدمة)", "Mini-SPIN (رهاب اجتماعي)"],
        ["ISI-7 (أرق)", "PSS-10 (ضغوط)"],
        ["WHO-5 (رفاه)", "K10 (ضيق نفسي)"],
        ["◀️ رجوع"]
    ], resize_keyboard=True
)

PERSONALITY_KB = ReplyKeyboardMarkup(
    [
        ["TIPI (الخمسة الكبار)", "SAPAS (فرز شخصية)"],
        ["MSI-BPD (مؤشر حدّية)"],
        ["◀️ رجوع"]
    ], resize_keyboard=True
)

AI_CHAT_KB = ReplyKeyboardMarkup([["◀️ إنهاء جلسة عربي سايكو"]], resize_keyboard=True)

# ========= حالات =========
MENU, CBT_MENU, TESTS_MENU, AI_CHAT, PERS_MENU = range(5)
TH_SITU, TH_EMO, TH_AUTO, TH_FOR, TH_AGAINST, TH_ALT, TH_RERATE = range(10,17)
EXPO_WAIT, EXPO_FLOW = range(20,22)
PANIC_Q, PTSD_Q, SURVEY = range(30,33)
BIN_YN = range(40,41)

# ========= الذكاء الاصطناعي =========
AI_SYSTEM_GENERAL = (
    "أنت «عربي سايكو»، معالج نفسي افتراضي بالعربية يعتمد مبادئ CBT.\n"
    "- لست بديلاً للطوارئ/التشخيص الطبي أو وصف الدواء.\n"
    "- قدّم أسئلة استكشافية وخطوات سلوكية بسيطة ونقاط عمل عملية."
)
AI_SYSTEM_DSM = (
    "أنت «عربي سايكو»، وضع DSM-5 الاسترشادي (غير تشخيصي).\n"
    "- رتّب الأعراض حسب المدة/الشدة/الأثر الوظيفي واقترح مسارات تقييم وتمارين CBT مبسطة.\n"
    "- اختتم بنقاط عمل + متى يُفضّل إحالة لطبيب/أخصائي."
)

def ai_call(user_content: str, history: List[Dict[str,str]], dsm_mode: bool) -> str:
    if not (AI_BASE_URL and AI_API_KEY and AI_MODEL):
        return "تعذّر استخدام الذكاء الاصطناعي حاليًا (تحقّق من المفاتيح/النموذج)."
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    sys = AI_SYSTEM_DSM if dsm_mode else AI_SYSTEM_GENERAL
    payload = {
        "model": AI_MODEL,
        "messages": [{"role":"system","content":sys}] + history + [{"role":"user","content":user_content}],
        "temperature": 0.4, "max_tokens": 700,
    }
    try:
        r = requests.post(f"{AI_BASE_URL.rstrip('/')}/chat/completions", headers=headers, data=json.dumps(payload), timeout=30)
        r.raise_for_status()
        j = r.json()
        return j["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"تعذّر الاتصال بالذكاء الاصطناعي: {e}"

async def ai_respond(text: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    if is_crisis(text):
        return ("⚠️ لو لديك خطر فوري على نفسك/غيرك اتصل بالطوارئ فورًا.\n"
                "جرّب الآن تنفّس 4-7-8 عشر مرات وابقَ مع شخص موثوق وحدّد موعدًا عاجلًا مع مختص.")
    hist: List[Dict[str,str]] = context.user_data.get("ai_hist", [])[-20:]
    dsm = (context.user_data.get("ai_mode") == "dsm")
    reply = await asyncio.to_thread(ai_call, text, hist, dsm)
    hist += [{"role":"user","content":text},{"role":"assistant","content":reply}]
    context.user_data["ai_hist"] = hist[-20:]
    return reply

# ========= نصوص CBT =========
CBT_TXT = {
"about": "CBT يربط بين الفكر↔الشعور↔السلوك… خطوات التطبيق: سمِّ الشعور 0-10 → اكتب الموقف والفكرة → أدلة معها/ضدها → فكرة بديلة → خطوة صغيرة 5-15د الآن.",
"dist": "تشوّهات شائعة: تعميم، تهويل، قراءة أفكار، تنبؤ سلبي، أبيض/أسود، لازم/يجب… اسأل: ما الدليل؟ ما البديل؟ ماذا أنصح صديقًا مكاني؟",
"anxiety":"علاج القلق (مختصر):\n• التعرّض التدريجي مع منع الطمأنة.\n• ضبط التنفّس والاسترخاء العضلي.\n• تحدّي الأفكار الكارثية بسجلّ أفكار.\n• تنشيط سلوكي يومي (حركة/تواصل/مهام صغيرة).\n• كافيين وشاشات مساءً: تقليل واضح.\n• نوم ثابت واستيقاظ بوقت محدد.",
"depr":"علاج الاكتئاب (مختصر):\n• تنشيط سلوكي (3 أنشطة قصيرة يوميًا).\n• تعرّف أنماط التفكير السلبي واستبدالها.\n• روتين نوم/أكل/شمس/حركة.\n• تواصل داعم ومهام قابلة للإنجاز.\n• اطلب تقييم مختص إذا استمر الحزن/فقدان المتعة ≥ أسبوعين أو ظهرت أفكار إيذاء.",
"anger":"إدارة الغضب:\n1) إشارة توقف (تنفّس 4-7-8 ×4).\n2) مؤقت 20 دقيقة قبل الرد.\n3) وصف المشكلة بلا اتهام (أنا أشعر… عندما… أحتاج …).\n4) خطّة بدائل: مغادرة قصيرة، ماء بارد، مشي 10د.\n5) تقييم بعدي: ماذا تعلّمت؟",
"fear":"التخلّص من الخوف: قائمة هرمية من 0-10، ابدأ 3-4/10، تعرّض متكرر حتى يهبط القلق ≥ النصف، ثم اصعد درجة. امنع سلوكيات الأمان (الاطمئنان الزائد/الهروب).",
"relax":"الاسترخاء: تنفّس 4-7-8 (شهيق4 حبس7 زفير8 ×4) + شد/إرخاء عضلي تدريجي من القدم للرأس.",
"mind":"اليقظة الذهنية: تمرين 5-4-3-2-1 (حواس) وعودة للحاضر بلا حكم، تسمية الأفكار «مجرّد فِكرة».",
"prob":"حل المشكلات: عرّف بدقة → أفكار بلا حكم → مزايا/عيوب → اختر خطة متى/أين/كيف → جرّب → قيّم.",
"sleep":"بروتوكول النوم: استيقاظ ثابت، السرير للنوم فقط، إيقاف الشاشات ساعة قبل النوم، تجنّب البقاء بالسرير >20 دقيقة بدون نوم."
}

# ========= تمارين تفاعلية =========
@dataclass
class ThoughtRecord:
    situation: str = ""; emotion: str = ""; auto: str = ""
    ev_for: str = ""; ev_against: str = ""; alternative: str = ""
    start: Optional[int] = None; end: Optional[int] = None

@dataclass
class ExposureState:
    suds: Optional[int] = None
    plan: Optional[str] = None

# ========= محرك استبيانات =========
@dataclass
class Survey:
    id: str; title: str; items: List[str]; scale: str; min_v: int; max_v: int
    reverse: List[int] = field(default_factory=list)
    ans: List[int] = field(default_factory=list)

def survey_prompt(s: Survey, i: int) -> str:
    return f"({i+1}/{len(s.items)}) {s.items[i]}\n{ s.scale }"

# بنوك أسئلة
PHQ9 = Survey("phq9","PHQ-9 — الاكتئاب",
 ["قلة الاهتمام/المتعة","الإحباط/اليأس","مشاكل النوم","التعب/قلة الطاقة","تغيّر الشهية",
  "الشعور بالسوء عن النفس","صعوبة التركيز","بطء/توتر ملحوظ","أفكار بإيذاء النفس"],
 "0=أبدًا،1=عدة أيام،2=أكثر من نصف الأيام،3=تقريبًا كل يوم",0,3)

GAD7 = Survey("gad7","GAD-7 — القلق",
 ["توتر/قلق/عصبية","عدم القدرة على إيقاف القلق","الانشغال بالهموم","صعوبة الاسترخاء",
  "تململ/صعوبة الهدوء","العصبية بسهولة","الخوف من حدوث أمر سيئ"],
 "0=أبدًا…3=تقريبًا كل يوم",0,3)

MINISPIN = Survey("minispin","Mini-SPIN — الرهاب الاجتماعي",
 ["أتجنب مواقف اجتماعية خوف الإحراج","أقلق أن يلاحظ الآخرون ارتباكي","أخاف التحدث أمام الآخرين"],
 "0=أبدًا…4=جداً",0,4)

TIPI = Survey("tipi","TIPI — الخمسة الكبار (10)",
 ["منفتح/اجتماعي","ناقد قليل المودة (عكسي)","منظم/موثوق","يتوتر بسهولة",
  "منفتح على الخبرة","انطوائي/خجول (عكسي)","ودود/متعاون","مهمل/عشوائي (عكسي)",
  "هادئ وثابت (عكسي)","تقليدي/غير خيالي (عكسي)"],
 "قيّم 1–7",1,7,reverse=[1,5,7,8,9])

ISI7 = Survey("isi7","ISI-7 — الأرق",
 ["صعوبة بدء النوم","صعوبة الاستمرار","الاستيقاظ المبكر","الرضا عن النوم",
  "تأثير الأرق نهارًا","ملاحظة الآخرين للمشكلة","القلق من نومك"],
 "0=لا…4=شديد جدًا",0,4)

PSS10 = Survey("pss10","PSS-10 — الضغوط المدركة",
 ["الأمور خرجت عن سيطرتك؟","انزعجت من أمر غير متوقع؟","شعرت بالتوتر؟",
  "تتحكم بالأمور؟ (عكسي)","واثق بالتعامل مع مشكلاتك؟ (عكسي)","الأمور تسير كما ترغب؟ (عكسي)",
  "لم تستطع التأقلم مع كل ما عليك؟","سيطرت على غضبك/انفعالك؟ (عكسي)","المشاكل تتراكم؟","وجدت وقتًا للمهم؟ (عكسي)"],
 "0=أبدًا…4=دائمًا",0,4,reverse=[3,4,5,7,9])

WHO5 = Survey("who5","WHO-5 — الرفاه",
 ["كنتُ مبتهجًا","شعرتُ بالسكينة","نشِطًا وحيويًا","أستيقظ مرتاحًا","يومي مليء بما يهمّني"],
 "0=لم يحصل…5=طوال الوقت",0,5)

K10 = Survey("k10","K10 — الضيق النفسي (4 أسابيع)",
 ["تعب بلا سبب؟","عصبي/متوتر؟","ميؤوس؟","قلق شديد؟","كل شيء جهد؟","لا تستطيع الهدوء؟",
  "حزين جدًا؟","لا شيء يفرحك؟","لا تحتمل التأخير؟","شعور بلا قيمة؟"],
 "1=أبدًا…5=دائمًا",1,5)

PC_PTSD5 = [
 "آخر شهر: كوابيس/ذكريات مزعجة لحدث صادم؟ (نعم/لا)",
 "تجنّبت التفكير/الأماكن المرتبطة؟ (نعم/لا)",
 "كنت على أعصابك/سريع الفزع؟ (نعم/لا)",
 "شعرت بالخدر/الابتعاد عن الناس/الأنشطة؟ (نعم/لا)",
 "شعرت بالذنب/اللوم بسبب الحدث؟ (نعم/لا)"
]

SAPAS = [
 "هل علاقاتك القريبة غير مستقرة أو قصيرة؟ (نعم/لا)",
 "هل تتصرف اندفاعيًا بلا تفكير كافٍ؟ (نعم/لا)",
 "خلافات متكررة؟ (نعم/لا)",
 "يراكا الناس «غريب الأطوار»؟ (نعم/لا)",
 "صعوبة الثقة وتشكّ بالآخرين؟ (نعم/لا)",
 "تتجنب الاختلاط خوف الإحراج/الرفض؟ (نعم/لا)",
 "تقلق كثيرًا على أشياء صغيرة؟ (نعم/لا)",
 "كمالية/صرامة تؤثر على حياتك؟ (نعم/لا)",
]
MSI_BPD = [
 "علاقات شديدة التقلب؟ (نعم/لا)","صورتك الذاتية تتبدّل جدًا؟ (نعم/لا)",
 "اندفاع مؤذٍ أحيانًا؟ (نعم/لا)","محاولات/تهديدات إيذاء النفس؟ (نعم/لا)",
 "تقلب انفعالي سريع؟ (نعم/لا)","فراغ داخلي دائم؟ (نعم/لا)",
 "غضب شديد يصعب تهدئته؟ (نعم/لا)","خوف قوي من الهجر؟ (نعم/لا)",
 "توتر شديد/أفكار غريبة تحت الضغط؟ (نعم/لا)","اختبارات/تجنّب خوف الهجر؟ (نعم/لا)"
]

# ========= اضطرابات الشخصية (نص إرشادي) =========
PD_TEXT = (
"🧩 اضطرابات الشخصية — DSM-5 (عناقيد A/B/C)\n\n"
"A: الزورية، الفُصامية الانعزالية، الفُصامية الشكل.\n"
"B: المعادية للمجتمع، الحدّية، الهستيرية، النرجسية.\n"
"C: التجنبية، الاتكالية، الوسواسية القهرية للشخصية.\n\n"
"النمط يكون مستمرًا ويؤثر على الوظيفة. للاسترشاد استخدم SAPAS وMSI-BPD.\n"
"⚠️ النتائج ليست تشخيصًا."
)

# ========= تحويل طبي =========
def referral_keyboard():
    rows = []
    if CONTACT_THERAPIST_URL:
        rows.append([InlineKeyboardButton("تحويل إلى أخصائي نفسي 👨‍⚕️", url=CONTACT_THERAPIST_URL)])
    if CONTACT_PSYCHIATRIST_URL:
        rows.append([InlineKeyboardButton("تحويل إلى طبيب نفسي 👨‍⚕️", url=CONTACT_PSYCHIATRIST_URL)])
    if not rows:
        rows.append([InlineKeyboardButton("أرسل وسيلة التواصل الخاصة بك", url="https://t.me/")])
    return InlineKeyboardMarkup(rows)

# ========= أوامر =========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("ابدأ جلسة عربي سايكو 🤖", callback_data="start_ai")],
        [InlineKeyboardButton("DSM-5 تشخيص استرشادي",   callback_data="start_dsm")],
    ])
    await update.effective_chat.send_message(
        "معك **عربي سايكو** — معالج نفسي افتراضي بالذكاء الاصطناعي **تحت إشراف أخصائي نفسي مرخّص** "
        "و(ليس بديلاً للطوارئ/التشخيص الطبي).\n\n"
        "اختر من القائمة أو ابدأ جلسة:",
        reply_markup=TOP_KB
    )
    await update.effective_chat.send_message("—", reply_markup=kb)
    return MENU

async def cmd_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"عربي سايكو — النسخة: {VERSION}")

async def cmd_ai_diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"AI_BASE_URL set={bool(AI_BASE_URL)} | KEY set={bool(AI_API_KEY)} | MODEL={AI_MODEL}"
    )

# ========= توجيه المستوى الأعلى =========
async def top_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if has("عربي سايكو", t) or has("🧠", t):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("ابدأ جلسة عربي سايكو 🤖", callback_data="start_ai")],
            [InlineKeyboardButton("DSM-5 تشخيص استرشادي",   callback_data="start_dsm")],
        ])
        await update.message.reply_text(
            "أنا «عربي سايكو». الردود تعليمية/سلوكية وليست تشخيصًا طبيًا.", reply_markup=kb
        )
        return MENU

    if has("العلاج السلوكي", t):
        await update.message.reply_text("اختر وحدة من CBT:", reply_markup=CBT_KB);  return CBT_MENU

    if has("الاختبارات النفسية", t):
        await update.message.reply_text("اختر اختبارًا:", reply_markup=TESTS_KB);   return TESTS_MENU

    if has("اختبارات الشخصية", t) or has("الشخصية", t):
        await update.message.reply_text("اختبارات الشخصية:", reply_markup=PERSONALITY_KB); return PERS_MENU

    if has("التحويل الطبي", t):
        await update.message.reply_text("خيارات التحويل:", reply_markup=referral_keyboard()); return MENU

    await update.message.reply_text("اختر من الأزرار أو اكتب /help.", reply_markup=TOP_KB); return MENU

# ========= بدء جلسة AI عبر الأزرار =========
async def ai_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["ai_hist"] = []; context.user_data["ai_mode"] = "free"
    await q.message.chat.send_message(
        "بدأت جلسة **عربي سايكو**. اكتب ما يضايقك الآن وسأساعدك بخطوات عملية.\n"
        "لإنهاء الجلسة: «◀️ إنهاء جلسة عربي سايكو».", reply_markup=AI_CHAT_KB
    )
    return AI_CHAT

async def dsm_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["ai_hist"] = []; context.user_data["ai_mode"] = "dsm"
    await q.message.chat.send_message(
        "✅ دخلت وضع **DSM-5 الاسترشادي** (غير تشخيصي).\n"
        "صف الأعراض بالمدة/الشدة/الأثر، وسأقترح مسارات تقييم وتمارين مناسبة.",
        reply_markup=AI_CHAT_KB
    )
    return AI_CHAT

async def ai_chat_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text in ("◀️ إنهاء جلسة عربي سايكو","خروج","/خروج"):
        await update.message.reply_text("انتهت الجلسة. رجعناك للقائمة.", reply_markup=TOP_KB); return MENU
    await update.effective_chat.send_action(ChatAction.TYPING)
    reply = await ai_respond(text, context)
    await update.message.reply_text(reply, reply_markup=AI_CHAT_KB)
    return AI_CHAT

# ========= CBT Router =========
async def cbt_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if t == "◀️ رجوع":
        await update.message.reply_text("رجعناك للقائمة.", reply_markup=TOP_KB); return MENU

    m = {
        "ما هو CBT؟":"about", "أخطاء التفكير":"dist", "طرق علاج القلق":"anxiety",
        "طرق علاج الاكتئاب":"depr", "إدارة الغضب":"anger", "التخلّص من الخوف":"fear",
        "الاسترخاء والتنفس":"relax", "اليقظة الذهنية":"mind", "حل المشكلات":"prob", "بروتوكول النوم":"sleep"
    }
    if t in m:
        await send_long(update.effective_chat, CBT_TXT[m[t]], CBT_KB); return CBT_MENU

    if t == "التنشيط السلوكي":
        context.user_data["ba_wait"] = True
        await update.message.reply_text("أرسل 3 أنشطة صغيرة اليوم (10–20د) مفصولة بفواصل/أسطر.", reply_markup=ReplyKeyboardRemove())
        return CBT_MENU

    if t == "سجلّ الأفكار (تمرين)":
        context.user_data["tr"] = ThoughtRecord()
        await update.message.reply_text("📝 اكتب **الموقف** باختصار (متى/أين/مع من؟).", reply_markup=ReplyKeyboardRemove())
        return TH_SITU

    if t == "التعرّض التدريجي":
        context.user_data["expo"] = ExposureState()
        await update.message.reply_text("أرسل درجة قلقك الحالية 0–10.", reply_markup=ReplyKeyboardRemove())
        return EXPO_WAIT

    await update.message.reply_text("اختر من القائمة:", reply_markup=CBT_KB); return CBT_MENU

async def cbt_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("ba_wait"):
        context.user_data["ba_wait"] = False
        parts = [s.strip() for s in re.split(r"[,\n،]+", update.message.text or "") if s.strip()]
        plan = "خطة اليوم:\n• " + "\n• ".join(parts[:3] or ["نشاط بسيط 10–20 دقيقة الآن."])
        await update.message.reply_text(plan + "\nقيّم مزاجك قبل/بعد 0–10.")
        await update.message.reply_text("رجوع لقائمة CBT:", reply_markup=CBT_KB)
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
        "✅ ملخص سجلّ الأفكار\n"
        f"• الموقف: {tr.situation}\n• الشعور قبل: {tr.emotion}\n• الفكرة: {tr.auto}\n"
        f"• أدلة تؤيد: {tr.ev_for}\n• أدلة تنفي: {tr.ev_against}\n• البديل: {tr.alternative}\n"
        f"• التقييم بعد: {tr.end if tr.end is not None else '—'}\n"
        "استمر بالتدريب يوميًا."
    )
    await send_long(update.effective_chat, txt)
    await update.message.reply_text("اختر من قائمة CBT:", reply_markup=CBT_KB);  return CBT_MENU

# التعرّض
async def expo_wait(update: Update, context: ContextTypes.DEFAULT_TYPE):
    n = to_int(update.message.text or "")
    if n is None or not (0<=n<=10):
        await update.message.reply_text("أرسل رقمًا من 0 إلى 10."); return EXPO_WAIT
    st: ExposureState = context.user_data["expo"]; st.suds = n
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("أمثلة 3–4/10", callback_data="expo_suggest")],
        [InlineKeyboardButton("شرح سريع",    callback_data="expo_help")],
    ])
    await update.message.reply_text(f"درجتك = {n}/10. اكتب موقفًا مناسبًا 3–4/10 أو استخدم الأزرار.", reply_markup=kb)
    return EXPO_FLOW

async def expo_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "expo_suggest":
        await q.edit_message_text("أمثلة: ركوب المصعد لطابقين، الانتظار بدقائق، الجلوس بمقهى قرب المخرج 10د.\nاكتب موقفك.")
    else:
        await q.edit_message_text("القاعدة: تعرّض آمن + منع الطمأنة + البقاء حتى يهبط القلق للنصف ثم كرّر.")
    return EXPO_FLOW

async def expo_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st: ExposureState = context.user_data["expo"]; st.plan = (update.message.text or "").strip()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ابدأ الآن",    callback_data="expo_start")],
        [InlineKeyboardButton("تم — قيّم الدرجة", callback_data="expo_rate")],
    ])
    await update.message.reply_text(f"خطة التعرض:\n• {st.plan}\nابدأ والبقاء حتى يهبط القلق ≥ النصف.", reply_markup=kb)
    return EXPO_FLOW

async def expo_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "expo_start":
        await q.edit_message_text("بالتوفيق! عند الانتهاء أرسل الدرجة الجديدة 0–10."); return EXPO_WAIT
    if q.data == "expo_rate":
        await q.edit_message_text("أرسل الدرجة الجديدة 0–10."); return EXPO_WAIT
    return EXPO_FLOW

# ========= اختبارات نعم/لا عامة =========
@dataclass
class BinState:
    i: int = 0; yes: int = 0; qs: List[str] = field(default_factory=list)

# ========= Routers للاختبارات =========
async def tests_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if t == "◀️ رجوع":
        await update.message.reply_text("رجعناك للقائمة.", reply_markup=TOP_KB); return MENU

    key = {
        "PHQ-9 (اكتئاب)":"phq9","GAD-7 (قلق)":"gad7","PC-PTSD-5 (صدمة)":"pcptsd5",
        "Mini-SPIN (رهاب اجتماعي)":"minispin","ISI-7 (أرق)":"isi7","PSS-10 (ضغوط)":"pss10",
        "WHO-5 (رفاه)":"who5","K10 (ضيق نفسي)":"k10"
    }.get(t)

    if key is None:
        await update.message.reply_text("اختر اختبارًا:", reply_markup=TESTS_KB); return TESTS_MENU

    # ثنائي: PTSD
    if key == "pcptsd5":
        context.user_data["pc"] = BinState(i=0, yes=0, qs=PC_PTSD5)
        await update.message.reply_text(PC_PTSD5[0], reply_markup=ReplyKeyboardRemove()); return PTSD_Q

    # درجات
    s_map = {"phq9":PHQ9,"gad7":GAD7,"minispin":MINISPIN,"isi7":ISI7,"pss10":PSS10,"who5":WHO5,"k10":K10}
    s0 = s_map[key]; s = Survey(s0.id, s0.title, list(s0.items), s0.scale, s0.min_v, s0.max_v, list(s0.reverse))
    context.user_data["s"]=s; context.user_data["s_i"]=0
    await update.message.reply_text(f"بدء **{s.title}**.\n{survey_prompt(s,0)}", reply_markup=ReplyKeyboardRemove())
    return SURVEY

async def pers_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if t == "◀️ رجوع":
        await update.message.reply_text("رجعناك للقائمة.", reply_markup=TOP_KB); return MENU

    key = {"TIPI (الخمسة الكبار)":"tipi","SAPAS (فرز شخصية)":"sapas","MSI-BPD (مؤشر حدّية)":"msi"}.get(t)
    if key is None:
        await update.message.reply_text("اختر اختبارًا:", reply_markup=PERSONALITY_KB); return PERS_MENU

    if key in ("sapas","msi"):
        qs = SAPAS if key=="sapas" else MSI_BPD
        context.user_data["bin"] = BinState(i=0, yes=0, qs=qs)
        await update.message.reply_text(qs[0], reply_markup=ReplyKeyboardRemove()); return BIN_YN

    if key=="tipi":
        s0=TIPI; s = Survey(s0.id, s0.title, list(s0.items), s0.scale, s0.min_v, s0.max_v, list(s0.reverse))
        context.user_data["s"]=s; context.user_data["s_i"]=0
        await update.message.reply_text(f"بدء **{s.title}**.\n{survey_prompt(s,0)}", reply_markup=ReplyKeyboardRemove())
        return SURVEY

# تدفّق PTSD
async def ptsd_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st: BinState = context.user_data["pc"]
    ans = (update.message.text or "").strip().replace("أ","ا").lower()
    if ans not in ("نعم","لا"): await update.message.reply_text("أجب بـ نعم/لا."); return PTSD_Q
    st.yes += 1 if ans=="نعم" else 0; st.i += 1
    if st.i < len(st.qs): await update.message.reply_text(st.qs[st.i]); return PTSD_Q
    result = "إيجابي (≥3 «نعم»)" if st.yes>=3 else "سلبي"
    await update.message.reply_text(f"**PC-PTSD-5:** {st.yes}/5 — {result}", reply_markup=TESTS_KB); return TESTS_MENU

# ثنائي للشخصية
async def bin_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st: BinState = context.user_data["bin"]
    ans = (update.message.text or "").strip().replace("أ","ا").lower()
    if ans not in ("نعم","لا"): await update.message.reply_text("أجب بـ نعم/لا."); return BIN_YN
    st.yes += 1 if ans=="نعم" else 0; st.i += 1
    if st.i < len(st.qs): await update.message.reply_text(st.qs[st.i]); return BIN_YN
    if len(st.qs)==8:
        cut=3; msg = f"**SAPAS:** {st.yes}/8 — " + ("إيجابي (≥3) يُستحسن التقييم." if st.yes>=cut else "سلبي.")
    else:
        cut=7; msg = f"**MSI-BPD:** {st.yes}/10 — " + ("إيجابي (≥7) يُستحسن التقييم." if st.yes>=cut else "سلبي.")
    await update.message.reply_text(msg, reply_markup=PERSONALITY_KB); context.user_data.pop("bin",None); return PERS_MENU

# تدفّق الدرجات العام
async def survey_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s: Survey = context.user_data["s"]; i = context.user_data["s_i"]
    n = to_int(update.message.text)
    if n is None or not (s.min_v<=n<=s.max_v):
        await update.message.reply_text(f"أدخل رقمًا بين {s.min_v} و{s.max_v}."); return SURVEY
    s.ans.append(n); i += 1
    if i >= len(s.items):
        if s.id=="gad7":
            total=sum(s.ans); lvl= "طبيعي/خفيف جدًا" if total<=4 else "خفيف" if total<=9 else "متوسط" if total<=14 else "شديد"
            await update.message.reply_text(f"**GAD-7:** {total}/21 — قلق {lvl}", reply_markup=TESTS_KB); return TESTS_MENU
        if s.id=="phq9":
            total=sum(s.ans)
            lvl = "لا/خفيف جدًا" if total<=4 else "خفيف" if total<=9 else "متوسط" if total<=14 else "متوسط-شديد" if total<=19 else "شديد"
            warn = "\n⚠️ بند أفكار الإيذاء >0 — اطلب مساعدة عاجلة." if s.ans[8]>0 else ""
            await update.message.reply_text(f"**PHQ-9:** {total}/27 — {lvl}{warn}", reply_markup=TESTS_KB); return TESTS_MENU
        if s.id=="minispin":
            total=sum(s.ans); msg="مؤشر رهاب اجتماعي محتمل" if total>=6 else "أقل من حد الإشارة"
            await update.message.reply_text(f"**Mini-SPIN:** {total}/12 — {msg}", reply_markup=TESTS_KB); return TESTS_MENU
        if s.id=="isi7":
            total=sum(s.ans); lvl="ضئيل" if total<=7 else "خفيف" if total<=14 else "متوسط" if total<=21 else "شديد"
            await update.message.reply_text(f"**ISI-7:** {total}/28 — أرق {lvl}", reply_markup=TESTS_KB); return TESTS_MENU
        if s.id=="pss10":
            vals=s.ans[:]
            for idx in s.reverse: vals[idx] = s.max_v - vals[idx]
            total=sum(vals); lvl="منخفض" if total<=13 else "متوسط" if total<=26 else "عالٍ"
            await update.message.reply_text(f"**PSS-10:** {total}/40 — ضغط {lvl}", reply_markup=TESTS_KB); return TESTS_MENU
        if s.id=="who5":
            total=sum(s.ans)*4; note="منخفض (≤50) يُستحسن التقييم." if total<=50 else "جيد."
            await update.message.reply_text(f"**WHO-5:** {total}/100 — {note}", reply_markup=TESTS_KB); return TESTS_MENU
        if s.id=="k10":
            total=sum(s.ans); lvl="خفيف" if total<=19 else "متوسط" if total<=24 else "شديد" if total<=29 else "شديد جدًا"
            await update.message.reply_text(f"**K10:** {total}/50 — ضيق {lvl}", reply_markup=TESTS_KB); return TESTS_MENU
        if s.id=="tipi":
            vals=s.ans[:]
            for idx in s.reverse: vals[idx] = 8 - vals[idx]
            extr=(vals[0]+vals[5])/2; agre=(vals[1]+vals[6])/2; cons=(vals[2]+vals[7])/2; emot=(vals[3]+vals[8])/2; open_=(vals[4]+vals[9])/2
            lab=lambda x: "عالٍ" if x>=5.5 else ("منخفض" if x<=2.5 else "متوسط")
            msg=(f"**TIPI (1–7):**\n"
                 f"• الانبساط: {extr:.1f} ({lab(extr)})\n• التوافق: {agre:.1f} ({lab(agre)})\n"
                 f"• الانضباط: {cons:.1f} ({lab(cons)})\n• الاستقرار الانفعالي: {emot:.1f} ({lab(emot)})\n"
                 f"• الانفتاح: {open_:.1f} ({lab(open_)})")
            await update.message.reply_text(msg, reply_markup=PERSONALITY_KB); return PERS_MENU

        await update.message.reply_text("تم الحساب.", reply_markup=TESTS_KB); return TESTS_MENU

    context.user_data["s_i"] = i
    await update.message.reply_text(survey_prompt(s, i)); return SURVEY

# ========= سقوط عام =========
async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اختر من الأزرار أو اكتب /start.", reply_markup=TOP_KB); return MENU

# ========= الربط والتشغيل =========
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            MENU: [
                CallbackQueryHandler(ai_start_cb,  pattern="^start_ai$"),
                CallbackQueryHandler(dsm_start_cb, pattern="^start_dsm$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, top_router),
            ],

            AI_CHAT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat_flow)],

            CBT_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cbt_free_text),
                MessageHandler(filters.TEXT & ~filters.COMMAND, cbt_router),
            ],

            TH_SITU:[MessageHandler(filters.TEXT & ~filters.COMMAND, tr_situ)],
            TH_EMO:[MessageHandler(filters.TEXT & ~filters.COMMAND, tr_emo)],
            TH_AUTO:[MessageHandler(filters.TEXT & ~filters.COMMAND, tr_auto)],
            TH_FOR:[MessageHandler(filters.TEXT & ~filters.COMMAND, tr_for)],
            TH_AGAINST:[MessageHandler(filters.TEXT & ~filters.COMMAND, tr_against)],
            TH_ALT:[MessageHandler(filters.TEXT & ~filters.COMMAND, tr_alt)],
            TH_RERATE:[MessageHandler(filters.TEXT & ~filters.COMMAND, tr_rerate)],

            EXPO_WAIT:[MessageHandler(filters.TEXT & ~filters.COMMAND, expo_wait)],
            EXPO_FLOW:[
                CallbackQueryHandler(expo_cb, pattern="^expo_(suggest|help)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, expo_flow),
                CallbackQueryHandler(expo_actions, pattern="^expo_(start|rate)$"),
            ],

            TESTS_MENU:[MessageHandler(filters.TEXT & ~filters.COMMAND, tests_router)],
            PTSD_Q:[MessageHandler(filters.TEXT & ~filters.COMMAND, ptsd_flow)],
            SURVEY:[MessageHandler(filters.TEXT & ~filters.COMMAND, survey_flow)],

            PERS_MENU:[MessageHandler(filters.TEXT & ~filters.COMMAND, pers_router)],
            BIN_YN:[MessageHandler(filters.TEXT & ~filters.COMMAND, bin_flow)],
        },
        fallbacks=[MessageHandler(filters.ALL, fallback)],
        allow_reentry=True
    )

    app.add_handler(CommandHandler("version", cmd_version))
    app.add_handler(CommandHandler("ai_diag", cmd_ai_diag))
    app.add_handler(conv)

    if PUBLIC_URL:
        # يتطلب python-telegram-bot[webhooks] لو أردت Webhook
        app.run_webhook(
            listen="0.0.0.0", port=PORT,
            url_path=f"{BOT_TOKEN}",
            webhook_url=f"{(PUBLIC_URL or '').rstrip('/')}/{BOT_TOKEN}",
            drop_pending_updates=True
        )
    else:
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
