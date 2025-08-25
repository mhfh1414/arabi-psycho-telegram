# app.py — عربي سايكو: AI + DSM5 إرشادي + CBT موسّع + اختبارات نفسية وشخصية + تحويل طبي
# Python 3.10+ | python-telegram-bot v21.6

import os, re, json, time, asyncio, logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict

import requests
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ConversationHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ========= إعداد عام =========
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho")
VERSION = "2025-08-26.1"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("يرجى ضبط TELEGRAM_BOT_TOKEN أو BOT_TOKEN")

# ذكاء اصطناعي (OpenAI أو OpenRouter)
AI_BASE_URL = (os.getenv("AI_BASE_URL") or "").strip()         # مثل: https://api.openai.com/v1
AI_API_KEY  = (os.getenv("AI_API_KEY") or "").strip()
AI_MODEL    = os.getenv("AI_MODEL", "gpt-4o-mini").strip()

# التحويل الطبي (اختياري)
CONTACT_THERAPIST_URL    = os.getenv("CONTACT_THERAPIST_URL", "")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "")

# Webhook لو متوفر، وإلا Polling
PUBLIC_URL = os.getenv("PUBLIC_URL") or os.getenv("WEBHOOK_URL") or os.getenv("RENDER_EXTERNAL_URL")
PORT = int(os.getenv("PORT", "10000"))

# ========= أدوات مساعدة =========
AR_DIGITS = "٠١٢٣٤٥٦٧٨٩"
EN_DIGITS = "0123456789"
TRANS = str.maketrans(AR_DIGITS, EN_DIGITS)

def normalize_num(s: str) -> str:
    return (s or "").strip().translate(TRANS)

def to_int(s: str) -> Optional[int]:
    try:
        return int(normalize_num(s))
    except Exception:
        return None

def has(word: str, t: str) -> bool:
    return word in (t or "")

async def send_long(chat, text: str, kb=None):
    chunk = 3500
    for i in range(0, len(text), chunk):
        await chat.send_message(text[i:i+chunk], reply_markup=kb if i+chunk>=len(text) else None)

# ========= مفاتيح =========
TOP_KB = ReplyKeyboardMarkup(
    [
        ["🧠 عربي سايكو"],
        ["💊 العلاج السلوكي المعرفي (CBT)", "📝 الاختبارات النفسية"],
        ["🧩 اختبارات الشخصية", "🧑‍⚕️ التحويل الطبي"]
    ],
    resize_keyboard=True
)

CBT_KB = ReplyKeyboardMarkup(
    [
        ["ما هو CBT؟", "أخطاء التفكير"],
        ["سجلّ الأفكار (تمرين)", "سجلّ المزاج (يومي)"],
        ["التنشيط السلوكي", "التعرّض التدريجي"],
        ["طرق علاج القلق", "طرق علاج الاكتئاب"],
        ["إدارة الغضب", "التخلّص من الخوف"],
        ["الاسترخاء والتنفس", "اليقظة الذهنية"],
        ["حل المشكلات", "بروتوكول النوم"],
        ["◀️ رجوع"]
    ],
    resize_keyboard=True
)

TESTS_KB = ReplyKeyboardMarkup(
    [
        ["PHQ-9 اكتئاب", "GAD-7 قلق"],
        ["PCL-5 (صدمة)", "Mini-SPIN رهاب اجتماعي"],
        ["WHO-5 رفاه", "ISI-7 أرق"],
        ["PSS-10 ضغوط", "K10 ضيق نفسي"],
        ["TIPI الخمسة الكبار", "◀️ رجوع"]
    ],
    resize_keyboard=True
)

PERSO_KB = ReplyKeyboardMarkup(
    [
        ["SAPAS اضطراب شخصية", "MSI-BPD حدّية"],
        ["نبذة اضطرابات الشخصية", "◀️ رجوع"]
    ],
    resize_keyboard=True
)

AI_CHAT_KB = ReplyKeyboardMarkup([["◀️ إنهاء جلسة عربي سايكو"]], resize_keyboard=True)

# ========= حالات =========
MENU, CBT_MENU, TESTS_MENU, PERSO_MENU, AI_CHAT = range(5)
# سجلّ الأفكار
TH_SITU, TH_EMO, TH_AUTO, TH_FOR, TH_AGAINST, TH_ALT, TH_RERATE = range(10,17)
# التعرّض
EXPO_WAIT, EXPO_FLOW = range(20,22)
# سجلّ المزاج
MOOD_RATE, MOOD_DESC, MOOD_THOUGHT, MOOD_BEHAV, MOOD_PLAN = range(30,35)
# اختبارات
PANIC_Q, PTSD_Q, SURVEY = range(40,43)

# ========= أمان (كلمات أزمة) =========
CRISIS_WORDS = ["انتحار","سأؤذي نفسي","اذي نفسي","قتل نفسي","ما ابغى اعيش","اريد اموت","ابي اموت","فقدت الامل"]
def is_crisis(txt: str) -> bool:
    low = (txt or "").replace("أ","ا").replace("إ","ا").replace("آ","ا").lower()
    return any(w in low for w in CRISIS_WORDS)

# ========= ذكاء اصطناعي =========
AI_SYSTEM_GENERAL = (
    "أنت «عربي سايكو» معالج نفسي افتراضي يعتمد مبادئ CBT. "
    "قدّم تعليمات عملية قصيرة، أسئلة استكشافية، واقتراحات تدريبات منزلية. "
    "أكّد دائمًا أنك لست بديلاً للطوارئ أو التشخيص الطبي."
)
AI_SYSTEM_DSM = (
    "أنت «عربي سايكو» في وضع استرشادي مستلهم من DSM-5. "
    "اطلب تفاصيل: المدة، الشدة، التأثير على الوظيفة. "
    "قدّم احتمالات/محاور تقييم غير نهائية + تحذيرات أمان + توصية بمختص. "
    "أدرج تمارين CBT مناسبة للأعراض."
)

def ai_call(user_content: str, history: List[Dict[str,str]], dsm_mode: bool) -> str:
    if not (AI_BASE_URL and AI_API_KEY and AI_MODEL):
        return "تعذّر استخدام الذكاء الاصطناعي حاليًا (تأكّد من المفاتيح/النموذج)."
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    system = AI_SYSTEM_DSM if dsm_mode else AI_SYSTEM_GENERAL
    payload = {
        "model": AI_MODEL,
        "messages": [{"role":"system","content":system}] + history + [{"role":"user","content":user_content}],
        "temperature": 0.4,
        "max_tokens": 700,
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
        return ("⚠️ سلامتك أهم. إن كان هناك خطر فوري فاتصل بطوارئ بلدك الآن. "
                "جرّب تنفّس 4-7-8 عشر مرات واطلب دعم شخص تثق به وحدّد موعدًا عاجلًا مع مختص.")
    hist: List[Dict[str,str]] = context.user_data.get("ai_hist", [])[-20:]
    dsm_mode = bool(context.user_data.get("ai_mode") == "dsm")
    reply = await asyncio.to_thread(ai_call, text, hist, dsm_mode)
    hist += [{"role":"user","content":text},{"role":"assistant","content":reply}]
    context.user_data["ai_hist"] = hist[-20:]
    return reply

# ========= نصوص CBT =========
CBT_TXT = {
    "about": (
        "🔹 **ما هو CBT؟**\n"
        "يربط بين **الفكر ↔ الشعور ↔ السلوك**. نلتقط الفكرة التلقائية غير المفيدة، "
        "نراجع الدليل معها/ضدها، ونقترح سلوكًا صغيرًا مفيدًا؛ مع التكرار يتحسّن المزاج.\n\n"
        "الخطوات: 1) سمِّ المشاعر 0–10. 2) الموقف والفكرة. 3) دليل معها/ضدها. "
        "4) فكرة بديلة متوازنة. 5) جرّب خطوة صغيرة الآن (10–20د) ثم قيّم التغيّر."
    ),
    "dist": (
        "🧠 **أخطاء التفكير الشائعة**: التهويل، التعميم، قراءة الأفكار، التنبؤ السلبي، الأبيض/الأسود، يجب/لازم.\n"
        "أسئلة مضادة: ما الدليل؟ ما البديل؟ ماذا أنصح صديقي لو كان مكاني؟"
    ),
    "relax": "🌬️ **تنفّس 4-7-8**: شهيق 4 ث، حبس 7 ث، زفير 8 ث ×4. ومعه شدّ/إرخاء عضلي 5/10 ث من القدم للرأس.",
    "mind": "🧘 **يقظة ذهنية 5-4-3-2-1**: 5 أشياء تراها، 4 تلمسها، 3 تسمعها، 2 تشمها، 1 تتذوقها. ارجع للحاضر بلا حكم.",
    "prob": "🧩 **حل المشكلات**: عرّف المشكلة بدقة → بدائل بلا نقد → مزايا/عيوب → خطة (متى/أين/كيف) → جرّب → قيّم.",
    "sleep":"🛌 **بروتوكول النوم**: استيقاظ ثابت، السرير للنوم فقط، أوقف الشاشات قبل النوم بساعة، لا تبقَ بالسرير يقظًا >20د."
}

# محتوى علاجي موسّع
CBT_TXT.update({
    "anxiety": (
        "😟 **طرق علاج القلق (مختصر+عملي)**\n"
        "• تعرّض تدريجي مع منع الطمأنة/الهروب.\n"
        "• تمرين التنفّس 4-7-8 + إرخاء عضلي.\n"
        "• تحدّي الأفكار المقلقة بالحقائق: الأسوأ/الأرجح/الأفضل.\n"
        "• أنشطة صغيرة يومية 10–20د + تقليل الكافيين.\n"
        "• نوم منتظم + حركة خفيفة (مشي 15–20د)."
    ),
    "depr": (
        "🌥️ **طرق علاج الاكتئاب**\n"
        "• تنشيط سلوكي: ثلاثة أنشطة صغيرة يوميًا (عناية ذاتية/منزل/تواصل/خروج قصير).\n"
        "• سجل أفكار → بدائل متوازنة.\n"
        "• تواصل اجتماعي قصير + تعرّض لضوء الصباح.\n"
        "• حركة يومية 15–20د.\n"
        "• ضبط مواعيد النوم والاستيقاظ."
    ),
    "anger": (
        "🔥 **إدارة الغضب**\n"
        "• وقفة 10 ثوانٍ + زفير طويل.\n"
        "• نموذج ABC: موقف→فكرة→انفعال (بدّل الفكرة).\n"
        "• جمل «أنا أشعر… حين… وأحتاج…» بدل الهجوم.\n"
        "• خروج قصير من الموقف ثم عودة بخطة.\n"
        "• راقب المحفّزات وسجّلها."
    ),
    "fear": (
        "😨 **التخلّص من الخوف**\n"
        "• اصنع سلّم تعرّض من 2/10 إلى 7/10.\n"
        "• ابقَ في الموقف حتى يهبط القلق ≥ النصف دون طمأنة.\n"
        "• كرّر 3–5 مرات بأيام متتالية وسجّل التقدّم."
    ),
})

# ========= تمارين/حالات =========
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

@dataclass
class MoodLog:
    rate: Optional[int] = None
    desc: str = ""
    thought: str = ""
    beh: str = ""
    plan: str = ""

# ========= محرك الاستبيانات =========
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

# بنوك الأسئلة
PHQ9 = Survey("phq9","PHQ-9 — الاكتئاب",
    ["قلة الاهتمام/المتعة","الإحباط/اليأس","مشاكل النوم","التعب/قلة الطاقة","تغيّر الشهية",
     "الشعور بالسوء عن النفس","صعوبة التركيز","بطء/توتر ملحوظ","أفكار بإيذاء النفس"],
    "0=أبدًا،1=عدة أيام،2=أكثر من نصف الأيام،3=تقريبًا كل يوم",0,3)

GAD7 = Survey("gad7","GAD-7 — القلق",
    ["توتر/قلق/عصبية","عدم القدرة على إيقاف القلق","الانشغال بالهموم","صعوبة الاسترخاء",
     "تململ/صعوبة الهدوء","العصبية/الانزعاج بسهولة","الخوف من حدوث أمر سيئ"],
    "0=أبدًا،1=عدة أيام،2=أكثر من نصف الأيام،3=تقريبًا كل يوم",0,3)

MINISPIN = Survey("minispin","Mini-SPIN — الرهاب الاجتماعي",
    ["أتجنب مواقف اجتماعية خوف الإحراج","أقلق أن يلاحظ الآخرون ارتباكي","أخاف التحدث أمام الآخرين"],
    "0=أبدًا،1=قليلًا،2=إلى حد ما،3=كثيرًا،4=جداً",0,4)

TIPI = Survey("tipi","TIPI — الخمسة الكبار (10)",
    ["منفتح/اجتماعي","ناقد قليل المودة (عكسي)","منظم/موثوق","يتوتر بسهولة",
     "منفتح على الخبرة","انطوائي/خجول (عكسي)","ودود/متعاون","مهمل/عشوائي (عكسي)",
     "هادئ وثابت (عكسي)","تقليدي/غير خيالي (عكسي)"],
    "قيّم 1–7 (1=لا تنطبق…7=تنطبق تمامًا)",1,7,reverse=[1,5,7,8,9])

# PCL-5 (20 بندًا) — آخر شهر
PCL5_ITEMS = [
 "إزعاج بسبب ذكريات/صور/أفكار متعلقة بالحدث الصادم؟","أحلام مزعجة حول الحدث؟","تصرّفت/شعرت كأن الحدث يحدث مجددًا؟",
 "انزعاج شديد من شيء يذكّرك بالحدث؟","تجنّبت الأفكار/المشاعر المتعلقة بالحدث؟","تجنّبت المواقف/الأماكن المذكرة؟",
 "صعوبة تذكّر جوانب مهمة من الحدث؟","مشاعر سلبية قوية (خوف/غضب/ذنب/خزي)؟","انخفاض الاهتمام بالأنشطة؟",
 "شعور بالانعزال عن الآخرين؟","صعوبة في المشاعر الإيجابية؟","تهيّج/نوبات غضب؟",
 "سلوك متهوّر/مدمّر؟","يقظة مفرطة/حذر زائد؟","ارتباك أو صعوبة في التركيز؟",
 "فرط انتباه/تنبّه؟","تململ عند المفاجآت/الفزع؟","مشاكل في النوم؟",
 "شعور دائم بالذنب/اللوم؟","تشاؤم/توقع الأسوأ حول الذات/العالم؟"
]
PCL5 = Survey("pcl5","PCL-5 — أعراض ما بعد الصدمة (آخر شهر)", PCL5_ITEMS,
              "0=لا شيء،1=قليلًا،2=متوسط،3=شديد،4=شديد جدًا",0,4)

ISI7 = Survey("isi7","ISI-7 — شدة الأرق",
    ["صعوبة بدء النوم","صعوبة استمرار النوم","الاستيقاظ المبكر","الرضا عن النوم",
     "تأثير الأرق على الأداء نهارًا","ملاحظة الآخرين للمشكلة","القلق/الانزعاج من نومك"],
    "0=لا،1=خفيف،2=متوسط،3=شديد،4=شديد جدًا",0,4)

PSS10 = Survey("pss10","PSS-10 — الضغوط المُدركة",
    ["كم شعرت بأن الأمور خرجت عن سيطرتك؟","انزعجت من أمر غير متوقع؟","شعرت بالتوتر؟",
     "تحكمت بالأمور؟ (عكسي)","ثقتك في التعامل مع مشكلاتك؟ (عكسي)","سارت الأمور كما ترغب؟ (عكسي)",
     "لم تستطع التأقلم مع كل ما عليك؟","سيطرت على الانفعالات؟ (عكسي)","شعرت بأن المشاكل تتراكم؟","وجدت وقتًا للأشياء المهمة؟ (عكسي)"],
    "0=أبدًا،1=نادرًا،2=أحيانًا،3=كثيرًا،4=دائمًا",0,4,reverse=[3,4,5,7,9])

WHO5 = Survey("who5","WHO-5 — الرفاه",
    ["شعرتُ بأنني مبتهج وفي مزاج جيد","شعرتُ بالهدوء والسكينة","شعرتُ بالنشاط والحيوية",
     "كنتُ أستيقظ مرتاحًا","كان يومي مليئًا بما يهمّني"],
    "0=لم يحصل مطلقًا…5=طوال الوقت",0,5)

K10 = Survey("k10","K10 — الضيق النفسي (آخر 4 أسابيع)",
    ["شعرت بالتعب من غير سبب؟","عصبي/متوتر؟","ميؤوس؟","قلق شديد؟","كل شيء جهد عليك؟",
     "لا تستطيع الهدوء؟","حزين بشدة؟","لا شيء يفرحك؟","لا تحتمل التأخير؟","شعور بلا قيمة؟"],
    "1=أبدًا،2=قليلًا،3=أحيانًا،4=غالبًا،5=دائمًا",1,5)

SAPAS_QS = [
  "هل علاقاتك القريبة غير مستقرة أو قصيرة؟ (نعم/لا)","هل تتصرف اندفاعيًا دون تفكير؟ (نعم/لا)",
  "خلافات متكررة؟ (نعم/لا)","يراكا لناس «غريب الأطوار»؟ (نعم/لا)","تشُكّ بالناس ويصعب الثقة؟ (نعم/لا)",
  "تتجنب الاختلاط خوف الإحراج/الرفض؟ (نعم/لا)","تقلق كثيرًا على أشياء صغيرة؟ (نعم/لا)","كمالية/صرامة تؤثر على حياتك؟ (نعم/لا)"
]
MSI_QS = [
 "علاقاتك شديدة التقلب؟ (نعم/لا)","صورتك الذاتية تتبدل جدًا؟ (نعم/لا)","اندفاعية مؤذية أحيانًا؟ (نعم/لا)",
 "محاولات/تهديدات إيذاء نفسك؟ (نعم/لا)","مشاعرك تتقلب بسرعة؟ (نعم/لا)","فراغ داخلي دائم؟ (نعم/لا)",
 "غضب شديد يصعب تهدئته؟ (نعم/لا)","خوف قوي من الهجر؟ (نعم/لا)","توتر شديد/أفكار غريبة تحت الضغط؟ (نعم/لا)","اختبارات/تجنّب خوف الهجر؟ (نعم/لا)"
]

PD_TEXT = (
    "🧩 **اضطرابات الشخصية — DSM-5 (عناقيد A/B/C)**\n\n"
    "A (غريبة/شاذة): الزورية، الفُصامية، الفُصامية الشكل.\n"
    "B (درامية/اندفاعية): المعادية للمجتمع، الحدّية، الهستيرية، النرجسية.\n"
    "C (قلِقة/خائفة): التجنبية، الاتكالية، الوسواسية القهرية للشخصية.\n\n"
    "الفكرة: نمط ثابت مبكر يؤثر على الإدراك والانفعال والعلاقات والتحكّم.\n"
    "🔸 لا يُعد هذا تشخيصًا. للاستدلال استخدم SAPAS وMSI-BPD ثم راجع مختصًا."
)

# ========= لوحات التحويل الطبي =========
def referral_keyboard():
    rows = []
    if CONTACT_THERAPIST_URL:
        rows.append([InlineKeyboardButton("تحويل إلى أخصائي نفسي", url=CONTACT_THERAPIST_URL)])
    if CONTACT_PSYCHIATRIST_URL:
        rows.append([InlineKeyboardButton("تحويل إلى طبيب نفسي", url=CONTACT_PSYCHIATRIST_URL)])
    if not rows:
        rows.append([InlineKeyboardButton("أرسل وسيلة تواصل مناسبة لك", url="https://t.me/")])
    return InlineKeyboardMarkup(rows)

# ========= أوامر =========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = ("مرحبًا! معك **عربي سايكو** — معالج نفسي افتراضي بالذكاء الاصطناعي "
           "تحت إشراف أخصائي نفسي (ليس بديلاً للطوارئ/التشخيص الطبي).")
    await update.effective_chat.send_message(txt, reply_markup=TOP_KB)
    return MENU

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/start — القائمة الرئيسية\n/help — المساعدة\n/ai_diag — تشخيص الربط مع الذكاء الاصطناعي\n/version — رقم الإصدار")

async def cmd_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"عربي سايكو — النسخة: {VERSION}")

async def cmd_ai_diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"AI_BASE_URL set={bool(AI_BASE_URL)} | KEY set={bool(AI_API_KEY)} | MODEL={AI_MODEL}")

# ========= المستوى الأعلى =========
async def top_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if has("عربي سايكو", t) or t.strip() == "🧠 عربي سايكو":
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("ابدأ جلسة عربي سايكو 🤖", callback_data="start_ai")],
            [InlineKeyboardButton("DSM-5 تشخيص استرشادي", callback_data="start_dsm")]
        ])
        msg = ("معك **عربي سايكو** — معالج نفسي افتراضي بالذكاء الاصطناعي (ليس بديلاً للطوارئ/التشخيص الطبي).\n"
               "اختر:")
        await update.message.reply_text(msg, reply_markup=kb)
        return MENU

    if has("العلاج السلوكي", t):
        await update.message.reply_text("اختر وحدة من CBT:", reply_markup=CBT_KB)
        return CBT_MENU

    if has("الاختبارات النفسية", t):
        await update.message.reply_text("اختر اختبارًا:", reply_markup=TESTS_KB)
        return TESTS_MENU

    if has("اختبارات الشخصية", t):
        await update.message.reply_text("اختبارات الشخصية:", reply_markup=PERSO_KB)
        return PERSO_MENU

    if has("التحويل الطبي", t):
        await update.message.reply_text("خيارات التحويل:", reply_markup=referral_keyboard())
        return MENU

    await update.message.reply_text("اختر من الأزرار أو اكتب /help.", reply_markup=TOP_KB)
    return MENU

# ========= جلسة AI =========
async def ai_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["ai_hist"] = []
    context.user_data["ai_mode"] = "free"
    await q.message.chat.send_message(
        "بدأت جلسة **عربي سايكو**. اكتب ما يضايقك الآن وسأساعدك بخطوات عملية.\n"
        "لإنهاء الجلسة: «◀️ إنهاء جلسة عربي سايكو».",
        reply_markup=AI_CHAT_KB
    )
    return AI_CHAT

async def dsm_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["ai_hist"] = []
    context.user_data["ai_mode"] = "dsm"
    await q.message.chat.send_message(
        "✅ دخلت وضع **DSM-5 الاسترشادي** (غير تشخيصي). صف الأعراض بالمدة/الشدة/الأثر وسأقترح محاور تقييم وتمارين مناسبة.",
        reply_markup=AI_CHAT_KB
    )
    return AI_CHAT

async def ai_chat_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    if txt in ("◀️ إنهاء جلسة عربي سايكو","/خروج","خروج"):
        await update.message.reply_text("انتهت الجلسة. رجعناك للقائمة.", reply_markup=TOP_KB)
        return MENU
    await update.effective_chat.send_action(ChatAction.TYPING)
    reply = await ai_respond(txt, context)
    await update.message.reply_text(reply, reply_markup=AI_CHAT_KB)
    return AI_CHAT

# ========= CBT Router =========
async def cbt_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if t == "◀️ رجوع":
        await update.message.reply_text("رجعناك للقائمة.", reply_markup=TOP_KB);  return MENU

    # نصوص مباشرة
    if has("ما هو CBT", t):      await send_long(update.effective_chat, CBT_TXT["about"], CBT_KB);  return CBT_MENU
    if has("أخطاء التفكير", t):  await send_long(update.effective_chat, CBT_TXT["dist"], CBT_KB);   return CBT_MENU
    if has("الاسترخاء", t):      await update.message.reply_text(CBT_TXT["relax"], reply_markup=CBT_KB);  return CBT_MENU
    if has("اليقظة", t):         await update.message.reply_text(CBT_TXT["mind"], reply_markup=CBT_KB);   return CBT_MENU
    if has("حل المشكلات", t):    await update.message.reply_text(CBT_TXT["prob"], reply_markup=CBT_KB);   return CBT_MENU
    if has("بروتوكول النوم", t): await update.message.reply_text(CBT_TXT["sleep"], reply_markup=CBT_KB);  return CBT_MENU
    if has("طرق علاج القلق", t): await send_long(update.effective_chat, CBT_TXT["anxiety"], CBT_KB);      return CBT_MENU
    if has("طرق علاج الاكتئاب", t): await send_long(update.effective_chat, CBT_TXT["depr"], CBT_KB);      return CBT_MENU
    if has("إدارة الغضب", t):    await send_long(update.effective_chat, CBT_TXT["anger"], CBT_KB);        return CBT_MENU
    if has("التخلّص من الخوف", t): await send_long(update.effective_chat, CBT_TXT["fear"], CBT_KB);       return CBT_MENU

    # التنشيط السلوكي
    if has("التنشيط السلوكي", t):
        context.user_data["ba_wait"] = True
        await update.message.reply_text("أرسل 3 أنشطة صغيرة اليوم (10–20د) مفصولة بأسطر/فواصل (مثال: مشي قصير، ترتيب درج، اتصال قصير).",
                                       reply_markup=ReplyKeyboardRemove())
        return CBT_MENU

    # سجلّ الأفكار
    if has("سجلّ الأفكار", t):
        context.user_data["tr"] = ThoughtRecord()
        await update.message.reply_text("📝 اكتب **الموقف** باختصار (متى/أين/مع من؟).", reply_markup=ReplyKeyboardRemove())
        return TH_SITU

    # التعرّض
    if has("التعرّض التدريجي", t):
        context.user_data["expo"] = ExposureState()
        await update.message.reply_text("أرسل درجة القلق الحالية 0–10.", reply_markup=ReplyKeyboardRemove())
        return EXPO_WAIT

    # سجلّ المزاج اليومي
    if has("سجلّ المزاج", t):
        context.user_data["mood"] = MoodLog()
        await update.message.reply_text("قيّم مزاجك الآن من 0 إلى 10:", reply_markup=ReplyKeyboardRemove())
        return MOOD_RATE

    # لو جاء نص أثناء انتظار باكج التنشيط
    if context.user_data.get("ba_wait"):
        context.user_data["ba_wait"] = False
        parts = [s.strip() for s in re.split(r"[,\n،]+", update.message.text or "") if s.strip()]
        plan = "خطة اليوم:\n• " + "\n• ".join(parts[:3] or ["نشاط بسيط 10–20 دقيقة الآن."])
        plan += "\nقيّم مزاجك قبل/بعد 0–10."
        await update.message.reply_text(plan)
        await update.message.reply_text("رجوع لقائمة CBT:", reply_markup=CBT_KB)
        return CBT_MENU

    await update.message.reply_text("اختر وحدة من القائمة:", reply_markup=CBT_KB)
    return CBT_MENU

# ===== سجلّ الأفكار (تدفق) =====
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
        f"• التقييم بعد: {tr.end if tr.end is not None else '—'}\n"
        "استمر بالتدريب يوميًا."
    )
    await send_long(update.effective_chat, txt)
    await update.message.reply_text("اختر من قائمة CBT:", reply_markup=CBT_KB)
    return CBT_MENU

# ===== تعرّض تدريجي =====
async def expo_wait(update: Update, context: ContextTypes.DEFAULT_TYPE):
    n = to_int(update.message.text)
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
        await q.edit_message_text("أمثلة: ركوب مصعد لطابقين، انتظار صف قصير، الجلوس بمقهى 10 دقائق قرب المخرج.\nاكتب موقفك.")
    else:
        await q.edit_message_text("القاعدة: تعرّض آمن + منع الطمأنة + البقاء حتى يهبط القلق للنصف ثم كرّر في أيام متتالية.")
    return EXPO_FLOW

async def expo_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st: ExposureState = context.user_data["expo"]; st.plan = (update.message.text or "").strip()
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ابدأ الآن", callback_data="expo_start")],
        [InlineKeyboardButton("تم — قيّم الدرجة", callback_data="expo_rate")]
    ])
    await update.message.reply_text(f"خطة التعرض:\n• {st.plan}\nابدأ والبقاء حتى يهبط القلق ≥ النصف.", reply_markup=kb)
    return EXPO_FLOW

async def expo_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "expo_start": await q.edit_message_text("بالتوفيق! عند الانتهاء أرسل الدرجة الجديدة 0–10.");  return EXPO_WAIT
    if q.data == "expo_rate":  await q.edit_message_text("أرسل الدرجة الجديدة 0–10.");  return EXPO_WAIT
    return EXPO_FLOW

# ===== سجلّ المزاج اليومي =====
async def mood_rate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    n = to_int(update.message.text)
    if n is None or not (0 <= n <= 10):
        await update.message.reply_text("أدخل رقم 0–10.");  return MOOD_RATE
    m: MoodLog = context.user_data["mood"]; m.rate = n
    await update.message.reply_text("اذكر حدثًا/موقفًا اليوم ومن كان معك:");  return MOOD_DESC

async def mood_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m: MoodLog = context.user_data["mood"]; m.desc = update.message.text.strip()
    await update.message.reply_text("ما الفكرة السائدة لديك؟");  return MOOD_THOUGHT

async def mood_thought(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m: MoodLog = context.user_data["mood"]; m.thought = update.message.text.strip()
    await update.message.reply_text("ما السلوك الذي فعلته/ستفعله لتحسين نقطة واحدة؟ (10–20د)");  return MOOD_BEHAV

async def mood_beh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m: MoodLog = context.user_data["mood"]; m.beh = update.message.text.strip()
    await update.message.reply_text("اكتب خطة قصيرة للساعات القادمة (متى/أين/كيف):");  return MOOD_PLAN

async def mood_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    m: MoodLog = context.user_data["mood"]; m.plan = update.message.text.strip()
    txt = (f"🗒️ **سجلّ المزاج**\n• التقييم: {m.rate}/10\n• الحدث: {m.desc}\n• الفكرة: {m.thought}\n"
           f"• السلوك: {m.beh}\n• الخطة: {m.plan}\n— جرّب الخطة وقيّم التغيّر لاحقًا.")
    await send_long(update.effective_chat, txt)
    await update.message.reply_text("رجوع لقائمة CBT:", reply_markup=CBT_KB)
    return CBT_MENU

# ========= Router الاختبارات =========
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
        "PHQ-9 اكتئاب":"phq9","GAD-7 قلق":"gad7","PCL-5 (صدمة)":"pcl5",
        "Mini-SPIN رهاب اجتماعي":"minispin","TIPI الخمسة الكبار":"tipi",
        "WHO-5 رفاه":"who5","ISI-7 أرق":"isi7","PSS-10 ضغوط":"pss10","K10 ضيق نفسي":"k10"
    }.get(t)

    if key is None:
        await update.message.reply_text("اختر اختبارًا:", reply_markup=TESTS_KB);  return TESTS_MENU

    s_map = {"phq9":PHQ9,"gad7":GAD7,"pcl5":PCL5,"minispin":MINISPIN,"tipi":TIPI,"who5":WHO5,"isi7":ISI7,"pss10":PSS10,"k10":K10}
    s0 = s_map[key]
    s = Survey(s0.id, s0.title, list(s0.items), s0.scale, s0.min_v, s0.max_v, list(s0.reverse))
    context.user_data["s"] = s; context.user_data["s_i"] = 0
    await update.message.reply_text(f"بدء **{s.title}**.\n{survey_prompt(s,0)}", reply_markup=ReplyKeyboardRemove())
    return SURVEY

async def survey_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    s: Survey = context.user_data["s"]; i = context.user_data["s_i"]
    n = to_int(update.message.text)
    if n is None or not (s.min_v <= n <= s.max_v):
        await update.message.reply_text(f"أدخل رقمًا بين {s.min_v} و{s.max_v}.");  return SURVEY
    s.ans.append(n); i += 1
    if i >= len(s.items):
        # تفسير موجز
        if s.id=="gad7":
            total=sum(s.ans); lvl = "طبيعي/خفيف جدًا" if total<=4 else "قلق خفيف" if total<=9 else "قلق متوسط" if total<=14 else "قلق شديد"
            await update.message.reply_text(f"**GAD-7:** {total}/21 — {lvl}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="phq9":
            total=sum(s.ans)
            if   total<=4: lvl="لا/خفيف جدًا"
            elif total<=9: lvl="خفيف"
            elif total<=14: lvl="متوسط"
            elif total<=19: lvl="متوسط-شديد"
            else: lvl="شديد"
            warn = "\n⚠️ بند أفكار الإيذاء >0 — اطلب مساعدة فورية." if s.ans[8]>0 else ""
            await update.message.reply_text(f"**PHQ-9:** {total}/27 — {lvl}{warn}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="pcl5":
            total=sum(s.ans); cut=33
            note = "يشير إلى احتمال اضطراب ما بعد الصدمة (يُستحسن تقييم سريري)." if total>=cut else "أقل من حد الإشارة."
            await update.message.reply_text(f"**PCL-5:** {total}/80 — {note}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="minispin":
            total=sum(s.ans); msg="مؤشر رهاب اجتماعي محتمل" if total>=6 else "أقل من حد الإشارة"
            await update.message.reply_text(f"**Mini-SPIN:** {total}/12 — {msg}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="tipi":
            vals = s.ans[:]
            for idx in s.reverse: vals[idx] = 8 - vals[idx]
            extr=(vals[0]+vals[5])/2; agre=(vals[1]+vals[6])/2; cons=(vals[2]+vals[7])/2; emot=(vals[3]+vals[8])/2; open_=(vals[4]+vals[9])/2
            def lab(x): return "عالٍ" if x>=5.5 else ("منخفض" if x<=2.5 else "متوسط")
            msg=(f"**TIPI (1–7):**\n"
                 f"• الانبساط: {extr:.1f} ({lab(extr)})\n• التوافق: {agre:.1f} ({lab(agre)})\n"
                 f"• الانضباط: {cons:.1f} ({lab(cons)})\n• الاستقرار الانفعالي: {emot:.1f} ({lab(emot)})\n"
                 f"• الانفتاح: {open_:.1f} ({lab(open_)})")
            await update.message.reply_text(msg, reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="isi7":
            total=sum(s.ans)
            lvl = "أرق ضئيل" if total<=7 else "أرق خفيف" if total<=14 else "أرق متوسط" if total<=21 else "أرق شديد"
            await update.message.reply_text(f"**ISI-7:** {total}/28 — {lvl}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="pss10":
            vals=s.ans[:]
            for idx in s.reverse: vals[idx] = s.max_v - vals[idx]
            total=sum(vals); lvl = "منخفض" if total<=13 else "متوسط" if total<=26 else "عالٍ"
            await update.message.reply_text(f"**PSS-10:** {total}/40 — ضغط {lvl}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="who5":
            total=sum(s.ans)*4; note="منخفض (≤50) — يُستحسن تحسين الروتين والتواصل/التقييم." if total<=50 else "جيد."
            await update.message.reply_text(f"**WHO-5:** {total}/100 — {note}", reply_markup=TESTS_KB);  return TESTS_MENU
        if s.id=="k10":
            total=sum(s.ans)
            lvl = "خفيف" if total<=19 else "متوسط" if total<=24 else "شديد" if total<=29 else "شديد جدًا"
            await update.message.reply_text(f"**K10:** {total}/50 — ضيق {lvl}", reply_markup=TESTS_KB);  return TESTS_MENU

        await update.message.reply_text("تم الحساب.", reply_markup=TESTS_KB);  return TESTS_MENU

    context.user_data["s_i"] = i
    await update.message.reply_text(survey_prompt(s, i));  return SURVEY

# ========= اختبارات الشخصية Router =========
async def perso_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if t == "◀️ رجوع":
        await update.message.reply_text("رجعناك للقائمة.", reply_markup=TOP_KB);  return MENU

    if t == "نبذة اضطرابات الشخصية":
        await send_long(update.effective_chat, PD_TEXT, PERSO_KB);  return PERSO_MENU

    if t == "SAPAS اضطراب شخصية":
        context.user_data["bin"] = BinState(i=0, yes=0, qs=SAPAS_QS)
        await update.message.reply_text(SAPAS_QS[0], reply_markup=ReplyKeyboardRemove());  return SURVEY

    if t == "MSI-BPD حدّية":
        context.user_data["bin"] = BinState(i=0, yes=0, qs=MSI_QS)
        await update.message.reply_text(MSI_QS[0], reply_markup=ReplyKeyboardRemove());  return SURVEY

    await update.message.reply_text("اختر من القائمة:", reply_markup=PERSO_KB);  return PERSO_MENU

# مكمّل لثنائي (SAPAS/MSI)
async def survey_binary_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "bin" not in context.user_data:
        await update.message.reply_text("اختر اختبارًا:", reply_markup=PERSO_KB);  return PERSO_MENU
    st: BinState = context.user_data["bin"]
    ans = (update.message.text or "").strip().lower()
    ans_bool = True if ans in ("نعم","ايه","ايوه","yes","y") else False if ans in ("لا","no","n") else None
    if ans_bool is None:
        await update.message.reply_text("أجب بـ نعم/لا.");  return SURVEY
    st.yes += 1 if ans_bool else 0; st.i += 1
    if st.i < len(st.qs):
        await update.message.reply_text(st.qs[st.i]);  return SURVEY
    # النتيجة
    if len(st.qs)==8:
        cut=3; msg = f"**SAPAS:** {st.yes}/8 — " + ("إيجابي (≥3) يُستحسن تقييم سريري." if st.yes>=cut else "سلبي.")
    else:
        cut=7; msg = f"**MSI-BPD:** {st.yes}/10 — " + ("إيجابي (≥7) يُستحسن تقييم سريري." if st.yes>=cut else "سلبي.")
    context.user_data.pop("bin", None)
    await update.message.reply_text(msg, reply_markup=PERSO_KB)
    return PERSO_MENU

# ========= سقوط عام =========
async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اختر من الأزرار أو اكتب /help.", reply_markup=TOP_KB)
    return MENU

# ========= ربط وتشغيل =========
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, top_router)],

            CBT_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, cbt_router)],
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

            MOOD_RATE:[MessageHandler(filters.TEXT & ~filters.COMMAND, mood_rate)],
            MOOD_DESC:[MessageHandler(filters.TEXT & ~filters.COMMAND, mood_desc)],
            MOOD_THOUGHT:[MessageHandler(filters.TEXT & ~filters.COMMAND, mood_thought)],
            MOOD_BEHAV:[MessageHandler(filters.TEXT & ~filters.COMMAND, mood_beh)],
            MOOD_PLAN:[MessageHandler(filters.TEXT & ~filters.COMMAND, mood_plan)],

            TESTS_MENU:[MessageHandler(filters.TEXT & ~filters.COMMAND, tests_router)],
            SURVEY:[MessageHandler(filters.TEXT & ~filters.COMMAND, survey_flow)],

            PERSO_MENU:[MessageHandler(filters.TEXT & ~filters.COMMAND, perso_router)],
            # ثنائي (SAPAS/MSI)
            PANIC_Q:[MessageHandler(filters.TEXT & ~filters.COMMAND, survey_binary_flow)],  # نستخدمه كحاوية
            PTSD_Q:[MessageHandler(filters.TEXT & ~filters.COMMAND, survey_binary_flow)],   # كذلك

            AI_CHAT:[MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat_flow)],
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
            listen="0.0.0.0", port=PORT, url_path=f"{BOT_TOKEN}",
            webhook_url=f"{PUBLIC_URL.rstrip('/')}/{BOT_TOKEN}",
            drop_pending_updates=True
        )
    else:
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
