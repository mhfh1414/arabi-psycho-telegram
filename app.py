# app.py — عربي سايكو: AI + CBT + اختبارات + اضطرابات الشخصية
# Python 3.10+ | python-telegram-bot v21

import os, re, asyncio, json, time, logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

import requests
from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho")

# ========= مفاتيح البيئة (متوافقة مع إعداداتك القديمة) =========
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
AI_BASE_URL = os.getenv("AI_BASE_URL", "").strip()
AI_API_KEY  = os.getenv("AI_API_KEY", "").strip()
AI_MODEL    = os.getenv("AI_MODEL", "openrouter/anthropic/claude-3.5-sonnet")

if not BOT_TOKEN:
    raise RuntimeError("ضبط TELEGRAM_BOT_TOKEN مطلوب")

# ========= أدوات مساعدة =========
AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
EN_DIGITS = "0123456789"
TRANS = str.maketrans(AR_DIGITS, EN_DIGITS)

def normalize_num(s: str) -> str:
    return s.strip().translate(TRANS)

def to_int(s: str) -> Optional[int]:
    try:
        return int(normalize_num(s))
    except Exception:
        return None

def yn(s: str) -> Optional[bool]:
    t = s.strip().lower()
    return {"نعم":True,"ايه":True,"ايوه":True,"yes":True,"y":True,
            "لا":False,"no":False,"n":False}.get(t)

async def send_long(chat, text, kb=None):
    chunk = 3500
    for i in range(0, len(text), chunk):
        await chat.send_message(text[i:i+chunk], reply_markup=kb if i+chunk>=len(text) else None)

def has(word: str, t: str) -> bool:
    """مطابقة مرنة بدون اعتماد على الإيموجي."""
    return word in (t or "")

# ========= تسعيرة =========
CURRENCY = "SAR"
PRICES: Dict[str, Dict[str, int]] = {
    "PHQ-9 — الاكتئاب": {"test": 25, "assessment": 80},
    "GAD-7 — القلق": {"test": 25, "assessment": 80},
    "Mini-SPIN — الرهاب الاجتماعي": {"test": 25, "assessment": 80},
    "فحص نوبات الهلع (2)": {"test": 20, "assessment": 70},
    "PC-PTSD-5 — ما بعد الصدمة": {"test": 30, "assessment": 90},
    "TIPI — الشخصية (10)": {"test": 25, "assessment": 70},
    "SAPAS — فحص اضطراب شخصية": {"test": 25, "assessment": 80},
    "MSI-BPD — فحص الحدّية": {"test": 25, "assessment": 80},
}

# ========= لوحات =========
TOP_KB = ReplyKeyboardMarkup(
    [
        ["عربي سايكو 🧠"],
        ["العلاج السلوكي المعرفي (CBT) 💊", "الاختبارات النفسية 📝"],
        ["اضطرابات الشخصية 🧩", "التسعيرة 💳"]
    ],
    resize_keyboard=True
)

CBT_KB = ReplyKeyboardMarkup(
    [
        ["نبذة عن CBT", "أخطاء التفكير"],
        ["سجلّ الأفكار (تمرين)", "التعرّض التدريجي (قلق/هلع)"],
        ["التنشيط السلوكي (المزاج)", "الاسترخاء والتنفس"],
        ["اليقظة الذهنية", "حل المشكلات"],
        ["بروتوكول النوم", "◀️ رجوع"]
    ],
    resize_keyboard=True
)

TESTS_KB = ReplyKeyboardMarkup(
    [
        ["GAD-7 قلق", "PHQ-9 اكتئاب"],
        ["Mini-SPIN رهاب اجتماعي", "فحص نوبات الهلع"],
        ["PC-PTSD-5 ما بعد الصدمة", "اختبار الشخصية (TIPI)"],
        ["SAPAS اضطراب شخصية", "MSI-BPD حدّية"],
        ["◀️ رجوع"]
    ],
    resize_keyboard=True
)

AI_CHAT_KB = ReplyKeyboardMarkup([["◀️ إنهاء جلسة عربي سايكو"]], resize_keyboard=True)

# ========= حالات =========
MENU, CBT_MENU, TESTS_MENU, AI_CHAT, EXPO_WAIT, EXPO_FLOW, \
TH_SITU, TH_EMO, TH_AUTO, TH_FOR, TH_AGAINST, TH_ALT, TH_RERATE, \
PANIC_Q, PTSD_Q, SURVEY = range(16)

# ========= نصوص CBT =========
CBT_ABOUT = (
    "🔹 **ما هو CBT؟**\n"
    "يربط بين **الفكر ↔️ الشعور ↔️ السلوك**. بتعديل أفكار غير مفيدة وتجربة سلوكيات بنّاءة، تتحسن المشاعر تدريجيًا.\n"
    "النجاح يحتاج **خطوات صغيرة + تكرار + قياس** (قبل/بعد 0–10).\n"
    "أمثلة مفيدة: سجلّ الأفكار، التعرّض التدريجي، التنشيط السلوكي، اليقظة الذهنية."
)
CBT_DIST = (
    "🧠 **أخطاء التفكير**\n"
    "• التعميم المفرط • التهويل • قراءة الأفكار • التنبؤ السلبي • الأبيض/الأسود • يجب/لازم.\n"
    "اسأل: *ما الدليل؟ ما البديل المتوازن؟ ماذا أنصح صديقًا في موقفي؟*"
)
CBT_RELAX = "🌬️ **تنفس 4-7-8**: شهيق 4، حبس 7، زفير 8 (×4). وشد/إرخاء العضلات 5 ثوانٍ ثم 10."
CBT_MINDF = "🧘 **اليقظة الذهنية 5-4-3-2-1**: 5 ترى، 4 تلمس، 3 تسمع، 2 تشم، 1 تتذوق."
CBT_PROB = "🧩 **حلّ المشكلات**: تعريف دقيق → بدائل بلا حكم → مزايا/عيوب → خطة متى/أين/كيف → جرّب ثم قيّم."
CBT_SLEEP= "🛌 **النوم**: استيقاظ ثابت، السرير للنوم، لا تبقَ >20 دقيقة مستيقظًا، خفّف منبّهات، أوقف الشاشات ساعة قبل النوم."

# ========= كيانات تمارين =========
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

# ========= محرك الاستبيانات =========
@dataclass
class SurveyObj:
    id: str
    title: str
    items: List[str]
    scale: str
    min_v: int
    max_v: int
    reverse: List[int] = field(default_factory=list)
    ans: List[int] = field(default_factory=list)

def survey_prompt(s: SurveyObj, i: int) -> str:
    return f"({i+1}/{len(s.items)}) {s.items[i]}\n{ s.scale }"

GAD7 = SurveyObj("gad7","GAD-7 — القلق",
    ["الشعور بالتوتر أو القلق", "عدم القدرة على إيقاف القلق", "القلق الزائد حيال أمور مختلفة",
     "صعوبة الاسترخاء", "التململ أو صعوبة البقاء هادئًا", "الانزعاج بسهولة", "الخوف من أن شيئًا فظيعًا قد يحدث"],
    "0=أبدًا، 1=عدة أيام، 2=أكثر من نصف الأيام، 3=تقريبًا كل يوم", 0, 3)

PHQ9 = SurveyObj("phq9","PHQ-9 — الاكتئاب",
    ["قلة الاهتمام أو المتعة", "الشعور بالإحباط/اليأس", "مشاكل النوم", "التعب أو قلة الطاقة",
     "تغيّر الشهية", "الشعور بالسوء عن النفس", "صعوبة التركيز", "بطء/توتر في الحركة أو الكلام",
     "أفكار بإيذاء النفس"],
    "0=أبدًا، 1=عدة أيام، 2=أكثر من نصف الأيام، 3=تقريبًا كل يوم", 0, 3)

MINISPIN = SurveyObj("minispin","Mini-SPIN — الرهاب الاجتماعي",
    ["أتجنب المواقف الاجتماعية خوفًا من الإحراج", "أقلق أن يلاحظ الآخرون ارتباكي", "أخاف التحدث أمام الآخرين"],
    "0=أبدًا،1=قليلًا،2=إلى حد ما،3=كثيرًا،4=جداً", 0, 4)

TIPI = SurveyObj("tipi","TIPI — الشخصية (10 بنود)",
    ["أنا منفتح/اجتماعي", "أنا ناقد وقلّما أُظهر المودة (عكسي)", "أنا منظم وموثوق", "أنا أتوتر بسهولة",
     "أنا منفتح على خبرات جديدة", "أنا انطوائي/خجول (عكسي)", "أنا ودود ومتعاون", "أنا مهمل/عشوائي (عكسي)",
     "أنا هادئ وثابت (عكسي)", "أنا تقليدي/غير خيالي (عكسي)"],
    "قيّم 1–7 (1=لا تنطبق…7=تنطبق تمامًا)", 1, 7, reverse=[1,5,7,8,9])

PC_PTSD5 = [
  "خلال الشهر الماضي: هل راودتك كوابيس أو ذكريات مزعجة لحدث صادم؟ (نعم/لا)",
  "هل تجنبت التفكير بالحدث أو أماكن تذكّرك به؟ (نعم/لا)",
  "هل كنت دائم اليقظة أو سريع الفزع؟ (نعم/لا)",
  "هل شعرت بالخدر/الانفصال عن الناس أو الأنشطة؟ (نعم/لا)",
  "هل شعرت بالذنب أو اللوم بسبب الحدث؟ (نعم/لا)"
]

SAPAS = [
  "هل تصف نفسك عادةً بأنك شخص مندفع أو تتصرف دون تفكير كافٍ؟ (نعم/لا)",
  "هل لديك علاقات غير مستقرة أو صراعات متكررة مع الآخرين؟ (نعم/لا)",
  "هل تجد صعوبة في الثبات على نشاط أو عمل لفترة طويلة؟ (نعم/لا)",
  "هل تتصرف أحيانًا بطرق غريبة أو غير مألوفة للآخرين؟ (نعم/لا)",
  "هل تميل للقلق الشديد بشأن ما يعتقده الناس عنك؟ (نعم/لا)",
  "هل تشك كثيرًا في نوايا الآخرين؟ (نعم/لا)",
  "هل تواجه صعوبة في السيطرة على غضبك؟ (نعم/لا)",
  "هل تتجنب الاقتراب من الناس خوفًا من الرفض أو النقد؟ (نعم/لا)"
]

MSI_BPD = [
  "هل تتبدل مشاعرك بسرعة وبشدة خلال اليوم؟ (نعم/لا)",
  "هل شعرت بهوية غير واضحة عن نفسك؟ (نعم/لا)",
  "هل لديك علاقات عاطفية شديدة التقلب؟ (نعم/لا)",
  "هل تتصرف باندفاعية (صرف، أكل، قيادة…)؟ (نعم/لا)",
  "هل تخاف من الهجر بدرجة كبيرة؟ (نعم/لا)",
  "هل لديك محاولات/أفكار لإيذاء النفس؟ (نعم/لا)",
  "هل تغضب بشدة ويصعب تهدئتك؟ (نعم/لا)",
  "هل تشعر بالفراغ المزمن؟ (نعم/لا)",
  "هل تعاني من شعور بالارتياب أو تبدلات شديدة تحت الضغط؟ (نعم/لا)",
  "هل تتأرجح صورتك عن الآخرين بين المثالية والازدراء؟ (نعم/لا)",
]

# ========= اضطرابات الشخصية (نص تثقيفي مختصر) =========
PD_TEXT = (
    "🧩 **اضطرابات الشخصية — DSM-5 (عناقيد A/B/C)**\n"
    "**A (غريبة/شاذة):** الزورية، الانعزالية، الفُصامية الشكل.\n"
    "**B (درامية/اندفاعية):** المعادية للمجتمع، الحدّية، الهستيرية، النرجسية.\n"
    "**C (قلِقة/خائفة):** التجنبية، الاتكالية، الوسواسية للشخصية.\n\n"
    "هذه المعلومات للتثقيف فقط. للاسترشاد يمكن استخدام **SAPAS** و **MSI-BPD** من «الاختبارات النفسية»،\n"
    "وليست تشخيصًا طبيًا."
)

# ========= ذكاء اصطناعي =========
AI_SYSTEM = (
    "أنت «عربي سايكو»، مساعد نفسي عربي يعتمد مبادئ CBT. لا تقدّم تشخيصات رسمية أو أدوية.\n"
    "سلّط الضوء على خطوات عملية قصيرة، واطرح أسئلة استكشافية، وأنهِ برد مختصر ونقاط قابلة للتطبيق."
)

def ai_call(user_content: str, history: List[Dict[str,str]]) -> str:
    if not (AI_BASE_URL and AI_API_KEY and AI_MODEL):
        return "تعذّر الاتصال بالذكاء الاصطناعي (مفاتيح البيئة غير مضبوطة)."
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_MODEL,
        "messages": [{"role":"system","content":AI_SYSTEM}] + history + [{"role":"user","content":user_content}],
        "max_tokens": 500,
        "temperature": 0.4,
    }
    try:
        r = requests.post(f"{AI_BASE_URL.rstrip('/')}/chat/completions", headers=headers, data=json.dumps(payload), timeout=30)
        r.raise_for_status()
        j = r.json()
        return j["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"تعذّر الاتصال بالذكاء الاصطناعي: {e}"

async def ai_respond(text: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    hist: List[Dict[str,str]] = context.user_data.get("ai_hist", [])
    hist = hist[-20:]
    reply = await asyncio.to_thread(ai_call, text, hist)
    hist += [{"role":"user","content":text},{"role":"assistant","content":reply}]
    context.user_data["ai_hist"] = hist[-20:]
    return reply

# ========= /start =========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        "مرحبًا! أنا **عربي سايكو**.\n"
        "للمحادثة الذكية اختر «عربي سايكو 🧠». وللـCBT والاختبارات استخدم الأزرار.",
        reply_markup=TOP_KB
    )
    return MENU

# ========= مستوى علوي =========
async def top_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if has("عربي سايكو", t):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("ابدأ جلسة عربي سايكو 🤖", callback_data="start_ai")],
            [InlineKeyboardButton("تواصل/الدعم", url="https://t.me/your_contact")]
        ])
        await update.message.reply_text(
            "أنا مساعد نفسي مدعوم بالذكاء الاصطناعي تحت إشراف أخصائي نفسي مرخّص.\n"
            "اكتب ما يزعجك الآن وسأساعدك بخطوات CBT عملية. تفضّل وابدأ شكواك 👇",
            reply_markup=kb
        )
        return MENU

    if has("العلاج السلوكي", t) or t == "/cbt":
        await update.message.reply_text("اختر وحدة من CBT:", reply_markup=CBT_KB)
        return CBT_MENU

    if has("الاختبارات النفسية", t):
        await update.message.reply_text("اختر اختبارًا:", reply_markup=TESTS_KB)
        return TESTS_MENU

    if has("اضطرابات الشخصية", t):
        await send_long(update.effective_chat, PD_TEXT, TOP_KB);  return MENU

    if has("التسعيرة", t):
        lines = ["💳 **التسعيرة**:"]
        for name, p in PRICES.items():
            lines.append(f"• {name}: اختبار {p['test']} {CURRENCY} / فحص {p['assessment']} {CURRENCY}")
        await update.message.reply_text("\n".join(lines), reply_markup=TOP_KB)
        return MENU

    await update.message.reply_text("اختر من الأزرار أو اكتب /start.", reply_markup=TOP_KB)
    return MENU

# ========= جلسة AI =========
async def start_ai_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["ai_hist"] = []
    await q.message.chat.send_message(
        "بدأت جلسة **عربي سايكو**. أكتب ما يزعجك الآن…\n"
        "لإنهاء الجلسة اضغط «◀️ إنهاء جلسة عربي سايكو».",
        reply_markup=AI_CHAT_KB
    )
    return AI_CHAT

async def ai_chat_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text in ("◀️ إنهاء جلسة عربي سايكو", "خروج", "/خروج"):
        await update.message.reply_text("انتهت الجلسة. رجعناك للقائمة.", reply_markup=TOP_KB)
        return MENU
    await update.effective_chat.send_chat_action("typing")
    reply = await ai_respond(text, context)
    await update.message.reply_text(reply, reply_markup=AI_CHAT_KB)
    return AI_CHAT

# ========= CBT Router =========
async def cbt_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if t == "◀️ رجوع":
        await update.message.reply_text("رجعناك للقائمة.", reply_markup=TOP_KB);  return MENU
    if has("نبذة", t):
        await send_long(update.effective_chat, CBT_ABOUT, CBT_KB);  return CBT_MENU
    if has("أخطاء التفكير", t):
        await send_long(update.effective_chat, CBT_DIST, CBT_KB);  return CBT_MENU
    if has("الاسترخاء", t):
        await update.message.reply_text(CBT_RELAX, reply_markup=CBT_KB);  return CBT_MENU
    if has("اليقظة", t):
        await update.message.reply_text(CBT_MINDF, reply_markup=CBT_KB);  return CBT_MENU
    if has("حل المشكلات", t):
        await update.message.reply_text(CBT_PROB, reply_markup=CBT_KB);  return CBT_MENU
    if has("بروتوكول النوم", t):
        await update.message.reply_text(CBT_SLEEP, reply_markup=CBT_KB);  return CBT_MENU
    if has("التنشيط السلوكي", t):
        context.user_data["ba_wait"] = True
        await update.message.reply_text(
            "أرسل 3 أنشطة صغيرة لليوم (10–20 دقيقة) مفصولة بفواصل/أسطر.",
            reply_markup=ReplyKeyboardRemove()
        )
        return CBT_MENU
    if has("سجلّ الأفكار", t):
        context.user_data["tr"] = ThoughtRecord()
        await update.message.reply_text("📝 اكتب **الموقف** باختصار (متى/أين/مع من؟).", reply_markup=ReplyKeyboardRemove())
        return TH_SITU
    if has("التعرّض التدريجي", t):
        context.user_data["expo"] = ExposureState()
        await update.message.reply_text("أرسل درجة قلقك الحالية 0–10.", reply_markup=ReplyKeyboardRemove())
        return EXPO_WAIT
    await update.message.reply_text("اختر وحدة من القائمة:", reply_markup=CBT_KB);  return CBT_MENU

async def cbt_free_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("ba_wait"):
        context.user_data["ba_wait"] = False
        parts = [s.strip() for s in re.split(r"[,\n،]+", update.message.text or "") if s.strip()]
        plan = "خطة اليوم:\n• " + "\n• ".join(parts[:3] or ["نشاط بسيط الآن لمدة 10–20 دقيقة."])
        await update.message.reply_text(plan + "\nقيّم مزاجك قبل/بعد 0–10.")
        await update.message.reply_text("رجوع لقائمة CBT:", reply_markup=CBT_KB)
    return CBT_MENU

# ===== سجل الأفكار =====
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
        "✅ **ملخص سجلّ الأفكار**\n"
        f"• الموقف: {tr.situation}\n• الشعور قبل: {tr.emotion}\n• الفكرة: {tr.auto}\n"
        f"• أدلة تؤيد: {tr.ev_for}\n• أدلة تنفي: {tr.ev_against}\n• البديل: {tr.alternative}\n"
        f"• التقييم بعد: {tr.end if tr.end is not None else '—'}"
    )
    await send_long(update.effective_chat, txt);  await update.message.reply_text("اختر من قائمة CBT:", reply_markup=CBT_KB)
    return CBT_MENU

# ===== التعرض =====
async def expo_wait(update: Update, context: ContextTypes.DEFAULT_TYPE):
    n = to_int(update.message.text or "")
    if n is None or not (0 <= n <= 10):
        await update.message.reply_text("أرسل رقمًا من 0 إلى 10.");  return EXPO_WAIT
    st: ExposureState = context.user_data["expo"]; st.suds = n
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("أمثلة 3–4/10", callback_data="expo_suggest")],
        [InlineKeyboardButton("شرح سريع", callback_data="expo_help")]
    ])
    await update.message.reply_text(f"درجتك = {n}/10. اكتب موقفًا مناسبًا 3–4/10 أو استخدم الأزرار.", reply_markup=kb)
    return EXPO_FLOW

async def expo_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "expo_suggest":
        await q.edit_message_text("أمثلة: ركوب المصعد لطابقين، انتظار صف قصير، الجلوس بمقهى 10 دقائق قرب المخرج.\nاكتب موقفك.")
    else:
        await q.edit_message_text("القاعدة: تعرّض آمن + منع الطمأنة + البقاء حتى يهبط القلق للنصف ثم كرّر.")
    return EXPO_FLOW

async def expo_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st: ExposureState = context.user_data["expo"]; st.plan = (update.message.text or "").strip()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ابدأ الآن", callback_data="expo_start")],
        [InlineKeyboardButton("تم — قيّم الدرجة", callback_data="expo_rate")]
    ])
    await update.message.reply_text(f"خطة التعرض:\n• {st.plan}\nابدأ والبقاء حتى يهبط القلق للنصف.", reply_markup=kb)
    return EXPO_FLOW

async def expo_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "expo_start": await q.edit_message_text("بالتوفيق! عند الانتهاء أرسل الدرجة الجديدة 0–10.");  return EXPO_WAIT
    if q.data == "expo_rate":  await q.edit_message_text("أرسل الدرجة الجديدة 0–10.");  return EXPO_WAIT
    return EXPO_FLOW

# ========= اختبارات =========
@dataclass
class BinState:
    i: int = 0
    yes: int = 0
    qs: List[str] = field(default_factory=list)

async def tests_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if t == "◀️ رجوع":
        await update.message.reply_text("رجعناك للقائمة.", reply_markup=TOP_KB);  return MENU

    key = {
        "GAD-7 قلق":"gad7","PHQ-9 اكتئاب":"phq9","Mini-SPIN رهاب اجتماعي":"minispin",
        "اختبار الشخصية (TIPI)":"tipi","فحص نوبات الهلع":"panic","PC-PTSD-5 ما بعد الصدمة":"pcptsd5",
        "SAPAS اضطراب شخصية":"sapas","MSI-BPD حدّية":"msi"
    }.get(t)

    if key is None:
        await update.message.reply_text("اختر اختبارًا:", reply_markup=TESTS_KB);  return TESTS_MENU

    if key == "panic":
        context.user_data["panic"] = BinState(i=0, yes=0, qs=["هل حدثت لديك نوبات هلع مفاجئة خلال 4 أسابيع؟ (نعم/لا)","هل تخاف من حدوث نوبة أخرى أو تتجنب أماكن خوفًا من ذلك؟ (نعم/لا)"])
        await update.message.reply_text(context.user_data["panic"].qs[0], reply_markup=ReplyKeyboardRemove());  return PANIC_Q

    if key == "pcptsd5":
        context.user_data["pc"] = BinState(i=0, yes=0, qs=PC_PTSD5)
        await update.message.reply_text(PC_PTSD5[0], reply_markup=ReplyKeyboardRemove());  return PTSD_Q

    if key in ("sapas","msi"):
        context.user_data["bin"] = BinState(i=0, yes=0, qs= SAPAS if key=="sapas" else MSI_BPD)
        await update.message.reply_text(context.user_data["bin"].qs[0], reply_markup=ReplyKeyboardRemove());  return SURVEY

    s_map = {"gad7":GAD7, "phq9":PHQ9, "minispin":MINISPIN, "tipi":TIPI}
    s0 = s_map[key]
    s = SurveyObj(s0.id, s0.title, list(s0.items), s0.scale, s0.min_v, s0.max_v, list(s0.reverse))
    context.user_data["s"] = s; context.user_data["s_i"] = 0
    await update.message.reply_text(f"بدء **{s.title}**.\n{survey_prompt(s,0)}", reply_markup=ReplyKeyboardRemove())
    return SURVEY

async def panic_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st: BinState = context.user_data["panic"]; ans = yn(update.message.text or "")
    if ans is None: await update.message.reply_text("أجب بـ نعم/لا.");  return PANIC_Q
    st.yes += 1 if ans else 0; st.i += 1
    if st.i < 2: await update.message.reply_text(st.qs[1]);  return PANIC_Q
    msg = "إيجابي — قد تكون هناك نوبات هلع" if st.yes==2 else "سلبي — لا مؤشر قوي حاليًا"
    await update.message.reply_text(f"**نتيجة فحص الهلع:** {msg}", reply_markup=TESTS_KB);  return TESTS_MENU

async def ptsd_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st: BinState = context.user_data["pc"]; ans = yn(update.message.text or "")
    if ans is None: await update.message.reply_text("أجب بـ نعم/لا.");  return PTSD_Q
    st.yes += 1 if ans else 0; st.i += 1
    if st.i < len(st.qs): await update.message.reply_text(st.qs[st.i]);  return PTSD_Q
    result = "إيجابي (≥3 «نعم») — يُوصى بالتقييم." if st.yes>=3 else "سلبي — أقل من حد الإشارة."
    await update.message.reply_text(f"**PC-PTSD-5:** {st.yes}/5 — {result}", reply_markup=TESTS_KB);  return TESTS_MENU

async def survey_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ثنائية (SAPAS/MSI)
    if "bin" in context.user_data:
        st: BinState = context.user_data["bin"]; ans = yn(update.message.text or "")
        if ans is None: await update.message.reply_text("أجب بـ نعم/لا.");  return SURVEY
        st.yes += 1 if ans else 0; st.i += 1
        if st.i < len(st.qs): await update.message.reply_text(st.qs[st.i]);  return SURVEY
        if len(st.qs)==8:
            cut = 3; msg = f"**SAPAS:** {st.yes}/8 — " + ("إيجابي (≥3) يُستحسن التقييم." if st.yes>=cut else "سلبي.")
        else:
            cut = 7; msg = f"**MSI-BPD:** {st.yes}/10 — " + ("إيجابي (≥7) يُستحسن التقييم." if st.yes>=cut else "سلبي.")
        await update.message.reply_text(msg, reply_markup=TESTS_KB);  context.user_data.pop("bin");  return TESTS_MENU

    # درجات (GAD/PHQ/Mini/TIPI)
    s: SurveyObj = context.user_data["s"]; i = context.user_data["s_i"]
    n = to_int(update.message.text or "")
    if n is None or not (s.min_v <= n <= s.max_v):
        await update.message.reply_text(f"أدخل رقمًا بين {s.min_v} و{s.max_v}.");  return SURVEY
    s.ans.append(n); i += 1
    if i >= len(s.items):
        if s.id=="gad7":
            total = sum(s.ans); level = "طبيعي/خفيف" if total<=4 else "قلق خفيف" if total<=9 else "قلق متوسط" if total<=14 else "قلق شديد"
            await update.message.reply_text(f"**GAD-7:** {total}/21 — {level}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="phq9":
            total = sum(s.ans)
            level = "0-4 طبيعي/خفيف جدًا" if total<=4 else "5-9 خفيف" if total<=9 else "10-14 متوسط" if total<=14 else "15-19 متوسط-شديد" if total<=19 else "20-27 شديد"
            warn = "\n⚠️ بند الأفكار المؤذية >0 — اطلب مساعدة فورية عند أي خطورة." if s.ans[8]>0 else ""
            await update.message.reply_text(f"**PHQ-9:** {total}/27 — {level}{warn}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="minispin":
            total = sum(s.ans); msg = "مؤشر رهاب اجتماعي محتمل" if total>=6 else "أقل من حدّ الإشارة"
            await update.message.reply_text(f"**Mini-SPIN:** {total}/12 — {msg}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="tipi":
            vals = s.ans[:]
            for idx in s.reverse: vals[idx] = 8 - vals[idx]
            extr=(vals[0]+vals[5])/2; agre=(vals[1]+vals[6])/2; cons=(vals[2]+vals[7])/2; emot=(vals[3]+vals[8])/2; open_=(vals[4]+vals[9])/2
            def lab(x): return "عالٍ" if x>=5.5 else ("منخفض" if x<=2.5 else "متوسط")
            msg = (f"**TIPI (1–7):**\n"
                   f"• الانبساط: {extr:.1f} ({lab(extr)})\n• التوافق: {agre:.1f} ({lab(agre)})\n"
                   f"• الانضباط: {cons:.1f} ({lab(cons)})\n• الاستقرار الانفعالي: {emot:.1f} ({lab(emot)})\n"
                   f"• الانفتاح: {open_:.1f} ({lab(open_)})")
            await update.message.reply_text(msg, reply_markup=TESTS_KB);  return TESTS_MENU
        await update.message.reply_text("تم الحساب.", reply_markup=TESTS_KB);  return TESTS_MENU
    context.user_data["s_i"] = i
    await update.message.reply_text(survey_prompt(s, i));  return SURVEY

# ========= تشخيص/إصلاحي بسيط =========
async def version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"نسخة عربي سايكو: {int(time.time())}\n"
        f"أزرار القائمة: عربي سايكو / CBT / اختبارات / اضطرابات / تسعيرة"
    )

async def ai_diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"AI_BASE_URL set={bool(AI_BASE_URL)} | KEY set={bool(AI_API_KEY)} | MODEL={AI_MODEL}"
    )

# ========= ربط كل شيء =========
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, top_router)],
            CBT_MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, cbt_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, cbt_free_text),
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
            PANIC_Q:[MessageHandler(filters.TEXT & ~filters.COMMAND, panic_flow)],
            PTSD_Q:[MessageHandler(filters.TEXT & ~filters.COMMAND, ptsd_flow)],
            SURVEY:[MessageHandler(filters.TEXT & ~filters.COMMAND, survey_flow)],
            AI_CHAT:[MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat_flow)],
        },
        fallbacks=[MessageHandler(filters.ALL, start)],
        allow_reentry=True
    )

    app.add_handler(CallbackQueryHandler(start_ai_cb, pattern="^start_ai$"))
    app.add_handler(CommandHandler("version", version))
    app.add_handler(CommandHandler("ai_diag", ai_diag))
    app.add_handler(conv)
    app.run_polling()

if __name__ == "__main__":
    main()
