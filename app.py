# app.py — عربي سايكو (Render + Telegram Webhook + OpenRouter)
# Start command on Render:
#   gunicorn -w 1 -k gthread -b 0.0.0.0:$PORT app:app

import os, re, json, asyncio, logging, threading
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

import httpx
from flask import Flask, request

from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

# ========= Logs =========
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("arabi-psycho")

# ========= ENV =========
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
PUBLIC_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
WEBHOOK_PATH = "/webhook/secret"

AI_BASE_URL = (os.getenv("AI_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
AI_API_KEY  = os.getenv("AI_API_KEY", "")
AI_MODEL    = os.getenv("AI_MODEL", "openrouter/auto")

CONTACT_THERAPIST_URL    = os.getenv("CONTACT_THERAPIST_URL", "https://t.me/your_therapist")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL","https://t.me/your_psychiatrist")

if not BOT_TOKEN:
    raise RuntimeError("✖ TELEGRAM_BOT_TOKEN مفقود في Environment")

# ========= Flask (لـ gunicorn) =========
app = Flask(__name__)

@app.get("/")
def health():
    return "Arabi Psycho OK"

# ========= Telegram Application =========
tg_app: Application = Application.builder().token(BOT_TOKEN).build()
_event_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()

# ========= أدوات مساعدة =========
AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
EN_DIGITS = "0123456789"
TRANS = str.maketrans(AR_DIGITS, EN_DIGITS)

def nrm_num(s: str) -> str:
    return s.strip().translate(TRANS)

def to_int(s: str) -> Optional[int]:
    try:
        return int(nrm_num(s))
    except Exception:
        return None

def yn(s: str) -> Optional[bool]:
    t = s.strip().lower()
    m = {"نعم": True,"ايه": True,"ايوه": True,"yes": True,"y": True,
         "لا": False,"no": False,"n": False}
    return m.get(t)

async def send_long(chat, text, kb=None):
    chunk = 3500
    for i in range(0, len(text), chunk):
        await chat.send_message(text[i:i+chunk], reply_markup=kb if i+chunk>=len(text) else None)

# ========= لوحات =========
TOP_KB = ReplyKeyboardMarkup(
    [
        ["عربي سايكو 🧠"],
        ["العلاج السلوكي المعرفي (CBT) 💊", "الاختبارات النفسية 📝"],
        ["اضطرابات الشخصية 🧩", "التحويل الطبي 🩺"],
    ], resize_keyboard=True
)
CBT_KB = ReplyKeyboardMarkup(
    [
        ["ما هو CBT؟", "أخطاء التفكير"],
        ["سجل الأفكار (تمرين)", "التعرّض التدريجي (قلق/هلع)"],
        ["التنشيط السلوكي (مزاج)", "الاسترخاء والتنفس"],
        ["اليقظة الذهنية", "حل المشكلات"],
        ["بروتوكول النوم", "◀️ رجوع"],
    ], resize_keyboard=True
)
TESTS_KB = ReplyKeyboardMarkup(
    [
        ["GAD-7 قلق", "PHQ-9 اكتئاب"],
        ["Mini-SPIN رهاب اجتماعي", "فحص نوبات الهلع"],
        ["PC-PTSD-5 ما بعد الصدمة", "اختبار الشخصية (TIPI)"],
        ["◀️ رجوع"],
    ], resize_keyboard=True
)
AI_CHAT_KB = ReplyKeyboardMarkup([["◀️ إنهاء جلسة عربي سايكو"]], resize_keyboard=True)

# ========= حالات =========
MENU, CBT_MENU, TESTS_MENU = range(3)
THOUGHT_SITU, THOUGHT_EMO, THOUGHT_AUTO, THOUGHT_FOR, THOUGHT_AGAINST, THOUGHT_ALTERN, THOUGHT_RERATE = range(10,17)
EXPO_WAIT_RATING, EXPO_FLOW = range(20,22)
SURVEY_ACTIVE = 30
PANIC_Q = 40
PTSD_Q = 50
AI_CHAT = 60

# ========= نصوص CBT =========
CBT_TXT = {
    "about": (
        "🔹 **ما هو CBT؟**\n"
        "يربط بين **الفكر ↔️ الشعور ↔️ السلوك**.\n"
        "نعدّل الأفكار غير المفيدة، ونجرب سلوكيات بنّاءة، فتتحسن المشاعر تدريجيًا.\n"
        "النجاح يحتاج **خطوات صغيرة + تكرار + قياس** (قبل/بعد 0–10)."
    ),
    "distortions": (
        "🧠 **أخطاء التفكير الشائعة**\n"
        "• التعميم المفرط — «دائمًا أفشل»\n"
        "• التهويل/تقليل الإيجابي — «كارثة!»\n"
        "• قراءة الأفكار — «يظنونني…»\n"
        "• التنبؤ السلبي — «أكيد بيصير أسوأ»\n"
        "• الأبيض/الأسود — «يا كامل يا صفر»\n"
        "• يجب/لازم — «لازم ما أغلط»\n"
        "👉 اسأل: *ما الدليل؟ ما البديل المتوازن؟ ماذا أنصح صديقًا في موقفي؟*"
    ),
    "relax": "🌬️ **التنفس 4-7-8**: شهيق 4، حبس 7، زفير 8 ×4. 🪢 شد/إرخِ كل عضلة 5/10 ثوانٍ.",
    "mind":  "🧘 **اليقظة** 5-4-3-2-1: 5 ترى، 4 تلمس، 3 تسمع، 2 تشمّ، 1 تتذوق.",
    "problem":"🧩 **حلّ المشكلات**: 1 تعريف — 2 بدائل — 3 مزايا/عيوب — 4 خطة — 5 تجربة وتقويم.",
    "sleep": "🛌 **بروتوكول النوم**: استيقاظ ثابت، السرير للنوم فقط، لا تبقَ >20 دقيقة مستيقظًا، خفّف منبّهات، أوقف الشاشات قبل ساعة.",
}

# ========= تمارين =========
@dataclass
class ThoughtRecord:
    situation: str = ""
    emotion: str = ""
    auto: str = ""
    evidence_for: str = ""
    evidence_against: str = ""
    alternative: str = ""
    start_rating: Optional[int] = None
    end_rating: Optional[int] = None

@dataclass
class ExposureState:
    suds: Optional[int] = None
    plan: Optional[str] = None

# ========= استبيانات =========
@dataclass
class Survey:
    id: str
    title: str
    items: List[str]
    scale_text: str
    min_val: int
    max_val: int
    reverse: List[int] = field(default_factory=list)
    answers: List[int] = field(default_factory=list)

GAD7_ITEMS = [
    "الشعور بالتوتر أو القلق أو العصبية",
    "عدم القدرة على التوقف عن القلق أو التحكم فيه",
    "القلق الزائد حيال أمور مختلفة",
    "صعوبة الاسترخاء",
    "التململ أو صعوبة البقاء هادئًا",
    "الانزعاج بسهولة أو العصبية",
    "الخوف من أن شيئًا فظيعًا قد يحدث"
]
PHQ9_ITEMS = [
    "قلة الاهتمام أو المتعة بالقيام بأي شيء",
    "الشعور بالإحباط أو الاكتئاب أو اليأس",
    "صعوبة النوم أو النوم الزائد",
    "الشعور بالتعب أو قلة الطاقة",
    "ضعف الشهية أو الإفراط في الأكل",
    "الشعور بأنك سيئ عن نفسك أو فاشل",
    "صعوبة التركيز على الأشياء",
    "الحركة/الكلام ببطء شديد أو توتر زائد",
    "أفكار بإيذاء النفس أو أن الموت قد يكون أفضل"
]
MINISPIN_ITEMS = [
    "أتجنب المواقف الاجتماعية خوفًا من الإحراج",
    "أقلق من أن يلاحظ الآخرون ارتباكي",
    "أخاف من التحدث أمام الآخرين"
]
TIPI_ITEMS = [
    "أنا منفتح/اجتماعي",
    "أنا ناقد وقلّما أُظهر المودة (عكسي)",
    "أنا منظم وموثوق",
    "أنا أتوتر بسهولة",
    "أنا منفتح على تجارب جديدة",
    "أنا انطوائي/خجول (عكسي)",
    "أنا ودود ومتعاطف",
    "أنا مهمل/عشوائي (عكسي)",
    "أنا هادئ وثابت انفعاليًا (عكسي)",
    "أنا تقليدي/غير خيالي (عكسي)"
]
TIPI_REVERSE = [1,5,7,8,9]
PC_PTSD5_ITEMS = [
    "خلال الشهر الماضي: هل راودتك كوابيس أو ذكريات مزعجة لحدث صادم؟ (نعم/لا)",
    "هل تجنّبت التفكير بالحدث أو أماكن تُذكّرك به؟ (نعم/لا)",
    "هل كنت دائم اليقظة أو سريع الفزع أو على أعصابك؟ (نعم/لا)",
    "هل شعرت بالخدر/الانفصال عن الناس أو الأنشطة؟ (نعم/لا)",
    "هل شعرت بالذنب أو اللوم بسبب الحدث؟ (نعم/لا)"
]

TEST_BANK: Dict[str, Dict[str, Any]] = {
    "gad7": {"title": "GAD-7 — القلق",
             "survey": Survey("gad7", "GAD-7 — القلق", GAD7_ITEMS,
                              "0=أبدًا، 1=عدة أيام، 2=أكثر من نصف الأيام، 3=تقريبًا كل يوم", 0, 3)},
    "phq9": {"title": "PHQ-9 — الاكتئاب",
             "survey": Survey("phq9", "PHQ-9 — الاكتئاب", PHQ9_ITEMS,
                              "0=أبدًا، 1=عدة أيام، 2=أكثر من نصف الأيام، 3=تقريبًا كل يوم", 0, 3)},
    "minispin": {"title": "Mini-SPIN — الرهاب الاجتماعي",
                 "survey": Survey("minispin", "Mini-SPIN — الرهاب الاجتماعي", MINISPIN_ITEMS,
                                  "0=أبدًا، 1=قليلًا، 2=إلى حد ما، 3=كثيرًا، 4=جداً", 0, 4)},
    "tipi": {"title": "TIPI — الخمسة الكبار (10 بنود)",
             "survey": Survey("tipi", "TIPI — الشخصية", TIPI_ITEMS,
                              "قيّم 1–7 (1=لا تنطبق…7=تنطبق تمامًا)", 1, 7, reverse=TIPI_REVERSE)},
}

# ========= اضطرابات الشخصية + التحويل =========
PD_TEXT = (
    "🧩 **اضطرابات الشخصية — DSM-5 (العناقيد)**\n"
    "**A (غريبة/شاذة):** الزورية، الفُصامية/الانعزالية، الفُصامية الشكل.\n"
    "**B (درامية/اندفاعية):** المعادية للمجتمع، الحدّية، الهستيرية، النرجسية.\n"
    "**C (قلِقة/خائفة):** التجنبية، الاتكالية، الوسواسية القهرية للشخصية.\n\n"
    "ℹ️ للتثقيف فقط — ليس تشخيصًا. اطلب تقييمًا مهنيًا عند تأثير واضح على الحياة."
)

# ========= ذكاء اصطناعي عبر OpenRouter =========
AI_SYSTEM_PROMPT = (
    "أنت «عربي سايكو»، مساعد نفسي عربي يعتمد مبادئ CBT.\n"
    "- تحدث بلطف وبالعربية المبسطة.\n"
    "- ساعد في تنظيم الأفكار وتمارين قصيرة وتطبيع المشاعر.\n"
    "- لا تقدم تشخيصًا طبيًا أو أدوية. عند خطر فوري وجّه لطلب مساعدة عاجلة.\n"
    "- اختم بتلخيص قصير وخطوة عملية واحدة."
)

async def ai_complete(messages: List[Dict[str, str]]) -> str:
    if not AI_API_KEY:
        return "(الذكاء الاصطناعي غير مفعّل: AI_API_KEY مفقود)"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": PUBLIC_URL or "https://render.com",
        "X-Title": "Arabi Psycho",
    }
    payload = {"model": AI_MODEL, "messages": messages, "temperature": 0.4, "max_tokens": 600}
    url = f"{AI_BASE_URL}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.exception("AI error")
        return f"(تعذّر توليد الرد: {e})"

async def ai_respond(user_text: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    hist: List[Dict[str, str]] = context.user_data.get("ai_history", [])
    hist = hist[-20:]
    convo = [{"role": "system", "content": AI_SYSTEM_PROMPT}] + hist + [{"role":"user","content":user_text}]
    reply = await ai_complete(convo)
    hist += [{"role":"user","content":user_text},{"role":"assistant","content":reply}]
    context.user_data["ai_history"] = hist[-20:]
    return reply

# ========= أوامر عامة =========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        "مرحبًا! أنا **عربي سايكو**. ابدأ جلسة الذكاء الاصطناعي أو ادخل على CBT والاختبارات.",
        reply_markup=TOP_KB
    )
    return MENU

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "القائمة: عربي سايكو 🧠 | CBT | الاختبارات النفسية 📝 | اضطرابات الشخصية 🧩 | التحويل الطبي 🩺",
        reply_markup=TOP_KB
    )
    return MENU

async def cmd_ai_diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    base_ok = "True" if AI_BASE_URL else "False"
    key_ok  = "True" if AI_API_KEY else "False"
    model   = AI_MODEL or "-"
    await update.message.reply_text(f"AI_BASE_URL set={base_ok} | KEY set={key_ok} | MODEL={model}")

# ========= مستوى علوي =========
async def top_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()

    if t.startswith("عربي سايكو"):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("ابدأ جلسة عربي سايكو 🤖", callback_data="start_ai")],
            [InlineKeyboardButton("تشخيص استرشادي DSM-5",    callback_data="ai_dsm")],
        ])
        await update.message.reply_text(
            "أنا مساعد نفسي مدعوم بالذكاء الاصطناعي تحت إشراف أخصائي نفسي.\n"
            "ملاحظة: الردود دعم تعليمي/سلوكي وليست تشخيصًا طبيًا.",
            reply_markup=kb
        )
        return MENU

    if t.startswith("العلاج السلوكي"):
        await update.message.reply_text("اختر وحدة CBT:", reply_markup=CBT_KB);  return CBT_MENU

    if t.startswith("الاختبارات"):
        await update.message.reply_text("اختر اختبارًا:", reply_markup=TESTS_KB);  return TESTS_MENU

    if t.startswith("اضطرابات الشخصية"):
        await send_long(update.effective_chat, PD_TEXT)
        await update.message.reply_text("للدعم العملي اختر CBT أو ابدأ جلسة عربي سايكو.", reply_markup=TOP_KB)
        return MENU

    if t.startswith("التحويل الطبي"):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("تحويل إلى أخصائي نفسي 🎓", url=CONTACT_THERAPIST_URL)],
            [InlineKeyboardButton("تحويل إلى طبيب نفسي 🩺",   url=CONTACT_PSYCHIATRIST_URL)],
        ])
        await update.message.reply_text("اختر نوع التحويل: (روابط خارجية)", reply_markup=kb)
        return MENU

    await update.message.reply_text("اختر من الأزرار أو اكتب /start.", reply_markup=TOP_KB)
    return MENU

# ========= جلسة AI =========
async def start_ai_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "ai_dsm":
        await q.message.reply_text("اكتب شكواك وسأقيّمها استرشاديًا وفق DSM-5 (غير طبي).")
    context.user_data["ai_history"] = []
    await q.message.reply_text(
        "بدأت جلسة **عربي سايكو**. اكتب شكواك الآن.\nلإنهاء الجلسة: «◀️ إنهاء جلسة عربي سايكو».",
        reply_markup=AI_CHAT_KB
    )
    return AI_CHAT

async def ai_chat_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text in ("◀️ إنهاء جلسة عربي سايكو", "/خروج", "خروج"):
        await update.message.reply_text("انتهت الجلسة. رجوع للقائمة.", reply_markup=TOP_KB)
        return MENU
    try:
        await update.effective_chat.send_action(ChatAction.TYPING)
    except Exception:
        pass
    reply = await ai_respond(text, context)
    await update.message.reply_text(reply, reply_markup=AI_CHAT_KB)
    return AI_CHAT

# ========= CBT Router =========
async def cbt_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if t == "◀️ رجوع":
        await update.message.reply_text("رجعناك للقائمة.", reply_markup=TOP_KB);  return MENU
    if t == "ما هو CBT؟":
        await send_long(update.effective_chat, CBT_TXT["about"], kb=CBT_KB);  return CBT_MENU
    if t == "أخطاء التفكير":
        await send_long(update.effective_chat, CBT_TXT["distortions"], kb=CBT_KB);  return CBT_MENU
    if t == "الاسترخاء والتنفس":
        await update.message.reply_text(CBT_TXT["relax"], reply_markup=CBT_KB);  return CBT_MENU
    if t == "اليقظة الذهنية":
        await update.message.reply_text(CBT_TXT["mind"], reply_markup=CBT_KB);  return CBT_MENU
    if t == "حل المشكلات":
        await update.message.reply_text(CBT_TXT["problem"], reply_markup=CBT_KB);  return CBT_MENU
    if t == "بروتوكول النوم":
        await update.message.reply_text(CBT_TXT["sleep"], reply_markup=CBT_KB);  return CBT_MENU

    if t == "سجل الأفكار (تمرين)":
        context.user_data["tr"] = ThoughtRecord()
        await update.message.reply_text("📝 اكتب **الموقف** باختصار (متى/أين/مع من؟).", reply_markup=ReplyKeyboardRemove())
        return THOUGHT_SITU

    if t == "التعرّض التدريجي (قلق/هلع)":
        context.user_data["expo"] = ExposureState()
        await update.message.reply_text("أرسل درجة قلقك الحالية 0–10.", reply_markup=ReplyKeyboardRemove())
        return EXPO_WAIT_RATING

    if t == "التنشيط السلوكي (مزاج)":
        context.user_data["ba_wait"] = True
        await update.message.reply_text(
            "اختر 3 أنشطة صغيرة اليوم (10–20 د): حركة خفيفة/تواصل/رعاية ذاتية.\nأرسلها مفصولة بفواصل/أسطر.",
            reply_markup=ReplyKeyboardRemove()
        )
        return CBT_MENU

    await update.message.reply_text("اختر وحدة من القائمة.", reply_markup=CBT_KB)
    return CBT_MENU

async def cbt_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("ba_wait"):
        context.user_data["ba_wait"] = False
        parts = [s.strip() for s in re.split(r"[,\n،]+", update.message.text) if s.strip()]
        plan = "خطة اليوم:\n• " + "\n• ".join(parts[:3] or [update.message.text.strip()])
        await update.message.reply_text(plan + "\nقيّم مزاجك قبل/بعد 0–10.")
        await update.message.reply_text("عد لقائمة CBT:", reply_markup=CBT_KB)
        return CBT_MENU
    return CBT_MENU

# ===== سجل الأفكار =====
async def tr_situ(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tr: ThoughtRecord = context.user_data["tr"]; tr.situation = update.message.text.strip()
    await update.message.reply_text("ما الشعور الأساسي الآن؟ وقيّمه 0–10 (مثال: قلق 7/10).");  return THOUGHT_EMO

async def tr_emo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tr: ThoughtRecord = context.user_data["tr"]; tr.emotion = update.message.text.strip()
    m = re.search(r"(\d+)", nrm_num(tr.emotion)); tr.start_rating = int(m.group(1)) if m else None
    await update.message.reply_text("ما **الفكرة التلقائية**؟");  return THOUGHT_AUTO

async def tr_auto(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tr"].auto = update.message.text.strip()
    await update.message.reply_text("اكتب **أدلة تؤيد** الفكرة.");  return THOUGHT_FOR

async def tr_for(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tr"].evidence_for = update.message.text.strip()
    await update.message.reply_text("اكتب **أدلة تنفي** الفكرة.");  return THOUGHT_AGAINST

async def tr_against(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tr"].evidence_against = update.message.text.strip()
    await update.message.reply_text("اكتب **فكرة بديلة متوازنة**.");  return THOUGHT_ALTERN

async def tr_altern(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["tr"].alternative = update.message.text.strip()
    await update.message.reply_text("أعد تقييم الشعور الآن 0–10.");  return THOUGHT_RERATE

async def tr_rerate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tr: ThoughtRecord = context.user_data["tr"]; n = to_int(update.message.text); tr.end_rating = n
    text = (
        "✅ **ملخص سجل الأفكار**\n"
        f"• الموقف: {tr.situation}\n"
        f"• الشعور/قبل: {tr.emotion}\n"
        f"• الفكرة: {tr.auto}\n"
        f"• أدلة تؤيد: {tr.evidence_for}\n"
        f"• أدلة تنفي: {tr.evidence_against}\n"
        f"• بديل: {tr.alternative}\n"
        f"• بعد: {tr.end_rating if tr.end_rating is not None else '—'}"
    )
    await send_long(update.effective_chat, text)
    await update.message.reply_text("اختر من قائمة CBT:", reply_markup=CBT_KB)
    return CBT_MENU

# ===== التعرض =====
async def expo_receive_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    n = to_int(update.message.text)
    if n is None or not (0 <= n <= 10):
        await update.message.reply_text("أرسل رقمًا من 0 إلى 10.");  return EXPO_WAIT_RATING
    st: ExposureState = context.user_data["expo"]; st.suds = n
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("اقتراح مواقف 3–4/10", callback_data="expo_suggest")],
        [InlineKeyboardButton("شرح سريع",          callback_data="expo_help")],
    ])
    txt = f"درجتك الحالية = {n}/10.\nاكتب موقفًا مناسبًا لدرجة 3–4/10 أو استخدم الأزرار."
    await update.message.reply_text(txt, reply_markup=kb);  return EXPO_FLOW

async def expo_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query;  await q.answer()
    if q.data == "expo_suggest":
        await q.edit_message_text("أمثلة: ركوب المصعد طابقين/انتظار صف قصير/الجلوس قرب المخرج 10 د.\nاكتب موقفك.")
    if q.data == "expo_help":
        await q.edit_message_text("القاعدة: تعرّض آمن + منع الطمأنة + البقاء حتى يهبط القلق للنصف ثم كرر.")
    return EXPO_FLOW

async def expo_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st: ExposureState = context.user_data["expo"]; st.plan = update.message.text.strip()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ابدأ الآن",      callback_data="expo_start")],
        [InlineKeyboardButton("تم — قيّم الدرجة", callback_data="expo_rate")]
    ])
    await update.message.reply_text(f"خطة التعرض:\n• {st.plan}\nابدأ وابقَ حتى تهبط الدرجة ≥ النصف.", reply_markup=kb)
    return EXPO_FLOW

async def expo_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query;  await q.answer()
    if q.data in ("expo_start", "expo_rate"):
        await q.edit_message_text("أرسل الدرجة الجديدة (0–10).");  return EXPO_WAIT_RATING
    return EXPO_FLOW

# ========= الاختبارات =========
@dataclass
class PanicState:
    i: int = 0
    ans: List[bool] = field(default_factory=list)

def survey_prompt(s: Survey, idx: int) -> str:
    return f"({idx+1}/{len(s.items)}) {s.items[idx]}\n{s.scale_text}"

async def tests_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text.strip()
    if t == "◀️ رجوع":
        await update.message.reply_text("رجعناك للقائمة.", reply_markup=TOP_KB);  return MENU

    key_map = {
        "GAD-7 قلق": "gad7",
        "PHQ-9 اكتئاب": "phq9",
        "Mini-SPIN رهاب اجتماعي": "minispin",
        "اختبار الشخصية (TIPI)": "tipi",
        "فحص نوبات الهلع": "panic",
        "PC-PTSD-5 ما بعد الصدمة": "pcptsd5",
    }
    if t not in key_map:
        await update.message.reply_text("اختر اختبارًا من الأزرار:", reply_markup=TESTS_KB);  return TESTS_MENU

    kid = key_map[t]
    if kid == "panic":
        context.user_data["panic"] = PanicState()
        await update.message.reply_text(
            "خلال آخر 4 أسابيع: هل حدثت لديك **نوبات هلع مفاجئة**؟ (نعم/لا)",
            reply_markup=ReplyKeyboardRemove()
        );  return PANIC_Q

    if kid == "pcptsd5":
        context.user_data["ptsd_i"] = 0
        context.user_data["ptsd_yes"] = 0
        context.user_data["ptsd_qs"] = PC_PTSD5_ITEMS
        await update.message.reply_text(PC_PTSD5_ITEMS[0], reply_markup=ReplyKeyboardRemove());  return PTSD_Q

    base = TEST_BANK[kid]["survey"]
    s = Survey(base.id, base.title, list(base.items), base.scale_text, base.min_val, base.max_val, list(base.reverse))
    context.user_data["survey"] = s; context.user_data["survey_idx"] = 0
    await update.message.reply_text(f"بدء **{s.title}**.\n{survey_prompt(s,0)}", reply_markup=ReplyKeyboardRemove())
    return SURVEY_ACTIVE

async def panic_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st: PanicState = context.user_data["panic"]; ans = yn(update.message.text)
    if ans is None:
        await update.message.reply_text("أجب بـ نعم/لا.");  return PANIC_Q
    st.ans.append(ans); st.i += 1
    if st.i == 1:
        await update.message.reply_text("هل تخاف من حدوث نوبة أخرى أو تتجنب أماكن لذلك؟ (نعم/لا)");  return PANIC_Q
    a1, a2 = st.ans
    result = "سلبي." if not (a1 and a2) else "إيجابي — مؤشر لهلع/قلق متوقع."
    await update.message.reply_text(f"**نتيجة فحص الهلع:** {result}", reply_markup=TESTS_KB);  return TESTS_MENU

async def ptsd_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ans = yn(update.message.text)
    if ans is None:
        await update.message.reply_text("أجب بـ نعم/لا.");  return PTSD_Q
    if ans: context.user_data["ptsd_yes"] += 1
    context.user_data["ptsd_i"] += 1; i = context.user_data["ptsd_i"]; qs = context.user_data["ptsd_qs"]
    if i < len(qs):
        await update.message.reply_text(qs[i]);  return PTSD_Q
    yes = context.user_data["ptsd_yes"]
    result = "إيجابي (≥3 نعم) — يُوصى بالتقييم." if yes >= 3 else "سلبي — أقل من حد الإشارة."
    await update.message.reply_text(f"**نتيجة PC-PTSD-5:** {yes}/5 — {result}", reply_markup=TESTS_KB);  return TESTS_MENU

async def survey_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s: Survey = context.user_data["survey"]; idx = context.user_data["survey_idx"]
    n = to_int(update.message.text)
    if n is None or not (s.min_val <= n <= s.max_val):
        await update.message.reply_text(f"أدخل رقمًا بين {s.min_val} و{s.max_val}.");  return SURVEY_ACTIVE
    s.answers.append(n); idx += 1
    if idx >= len(s.items):
        if s.id == "gad7":
            total = sum(s.answers)
            level = "خفيف جدًا/طبيعي" if total <= 4 else "قلق خفيف" if total <= 9 else "قلق متوسط" if total <= 14 else "قلق شديد"
            msg = f"**نتيجة GAD-7:** {total}/21 — {level}."
            if total >= 10: msg += "\n💡 يُوصى بالتقييم المهني."
            await update.message.reply_text(msg, reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id == "phq9":
            total = sum(s.answers)
            if total <= 4: level = "لا اكتئاب/خفيف جدًا"
            elif total <= 9: level = "اكتئاب خفيف"
            elif total <= 14: level = "اكتئاب متوسط"
            elif total <= 19: level = "متوسط-شديد"
            else: level = "شديد"
            msg = f"**نتيجة PHQ-9:** {total}/27 — {level}."
            if s.answers[8] and s.answers[8] > 0:
                msg += "\n⚠️ بند الأفكار المؤذية > 0 — اطلب مساعدة فورية عند أي خطورة."
            await update.message.reply_text(msg, reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id == "minispin":
            total = sum(s.answers)
            msg = f"**نتيجة Mini-SPIN:** {total}/12."
            msg += " (مؤشر رهاب اجتماعي محتمل)" if total >= 6 else " (أقل من حدّ الإشارة)"
            await update.message.reply_text(msg, reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id == "tipi":
            vals = s.answers[:]
            for i in s.reverse: vals[i] = 8 - vals[i]
            extr = (vals[0] + vals[5]) / 2
            agre = (vals[1] + vals[6]) / 2
            cons = (vals[2] + vals[7]) / 2
            emot = (vals[3] + vals[8]) / 2
            open_ = (vals[4] + vals[9]) / 2
            def label(x): return "عالٍ" if x >= 5.5 else ("منخفض" if x <= 2.5 else "متوسط")
            msg = (
                "**نتيجة TIPI (1–7):**\n"
                f"• الانبساط: {extr:.1f} ({label(extr)})\n"
                f"• التوافق/الود: {agre:.1f} ({label(agre)})\n"
                f"• الضمير/الانضباط: {cons:.1f} ({label(cons)})\n"
                f"• الاستقرار الانفعالي: {emot:.1f} ({label(emot)})\n"
                f"• الانفتاح على الخبرة: {open_:.1f} ({label(open_)})"
            )
            await update.message.reply_text(msg, reply_markup=TESTS_KB);  return TESTS_MENU

        await update.message.reply_text("تم الحساب.", reply_markup=TESTS_KB);  return TESTS_MENU

    context.user_data["survey_idx"] = idx
    await update.message.reply_text(survey_prompt(s, idx));  return SURVEY_ACTIVE

# ========= Fallback =========
async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اختر من الأزرار أو اكتب /start.", reply_markup=TOP_KB)
    return MENU

# ========= ربط Handlers =========
def _register_handlers():
    conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", cmd_start),
            CommandHandler("help",  cmd_help),
            CommandHandler("ai_diag", cmd_ai_diag),
        ],
        states={
            MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, top_router)],

            CBT_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cbt_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, cbt_free_text),
            ],
            THOUGHT_SITU:    [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_situ)],
            THOUGHT_EMO:     [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_emo)],
            THOUGHT_AUTO:    [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_auto)],
            THOUGHT_FOR:     [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_for)],
            THOUGHT_AGAINST: [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_against)],
            THOUGHT_ALTERN:  [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_altern)],
            THOUGHT_RERATE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, tr_rerate)],

            EXPO_WAIT_RATING: [MessageHandler(filters.TEXT & ~filters.COMMAND, expo_receive_rating)],
            EXPO_FLOW: [
                CallbackQueryHandler(expo_cb,     pattern=r"^expo_(suggest|help)$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, expo_free_text),
                CallbackQueryHandler(expo_actions, pattern=r"^expo_(start|rate)$"),
            ],

            TESTS_MENU:    [MessageHandler(filters.TEXT & ~filters.COMMAND, tests_router)],
            SURVEY_ACTIVE: [MessageHandler(filters.TEXT & ~filters.COMMAND, survey_flow)],
            PANIC_Q:       [MessageHandler(filters.TEXT & ~filters.COMMAND, panic_flow)],
            PTSD_Q:        [MessageHandler(filters.TEXT & ~filters.COMMAND, ptsd_flow)],

            AI_CHAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat_flow)],
        },
        fallbacks=[MessageHandler(filters.ALL, fallback)],
        allow_reentry=True,
    )

    tg_app.add_handler(conv)
    tg_app.add_handler(CallbackQueryHandler(start_ai_cb, pattern=r"^(start_ai|ai_dsm)$"))

_register_handlers()

# ========= Webhook / Thread =========
def _bot_loop():
    asyncio.set_event_loop(_event_loop)
    async def _startup():
        await tg_app.initialize()
        await tg_app.start()
        if PUBLIC_URL:
            hook = f"{PUBLIC_URL}{WEBHOOK_PATH}"
            await tg_app.bot.set_webhook(url=hook, drop_pending_updates=True)
            log.info(f"✓ Webhook set: {hook}")
        else:
            log.warning("RENDER_EXTERNAL_URL غير محدد؛ لن يتم تعيين Webhook.")
    _event_loop.run_until_complete(_startup())
    _event_loop.run_forever()

threading.Thread(target=_bot_loop, daemon=True).start()

@app.post(WEBHOOK_PATH)
def webhook():
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, tg_app.bot)
        asyncio.run_coroutine_threadsafe(tg_app.process_update(update), _event_loop)
    except Exception as e:
        log.exception("webhook error: %s", e)
        return "error", 500
    return "ok"
