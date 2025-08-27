# app.py — عربي سايكو: ذكاء اصطناعي + DSM5 استرشادي + CBT موسّع + اختبارات + شخصية + تحويل طبي
# Python 3.10+ | python-telegram-bot v21.6

import os, re, asyncio, json, logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict

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

# ========== إعداد عام ==========
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho")

VERSION = "2025-08-27.1"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("يرجى ضبط TELEGRAM_BOT_TOKEN")

# ذكاء اصطناعي
AI_BASE_URL = (os.getenv("AI_BASE_URL") or "").strip()
AI_API_KEY  = (os.getenv("AI_API_KEY") or "").strip()
AI_MODEL    = (os.getenv("AI_MODEL") or "gpt-4o-mini").strip()

# روابط تحويل طبي (اختياري)
# تم ضبط رابط الأخصائي على حساب تيليجرام الذي زوّدتني به
CONTACT_THERAPIST_URL    = os.getenv("CONTACT_THERAPIST_URL", "https://t.me/Mhfh1414")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "")

# Webhook أو Polling
PUBLIC_URL = os.getenv("PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL") or os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", "10000"))

# ========== أدوات مساعدة ==========
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

def has(substr: str, txt: str) -> bool:
    return substr in (txt or "")

async def send_long(chat, text: str, kb=None):
    chunk = 3500
    for i in range(0, len(text), chunk):
        await chat.send_message(text[i:i+chunk], reply_markup=kb if i+chunk>=len(text) else None)

# ========== أزرار القوائم ==========
TOP_KB = ReplyKeyboardMarkup(
    [
        ["عربي سايكو 🧠"],
        ["العلاج السلوكي المعرفي (CBT) 💊", "الاختبارات النفسية 📝"],
        ["اختبارات الشخصية 🧩", "اضطرابات الشخصية 📚"],
        ["الأخصائي النفسي 👨‍⚕️", "التحويل الطبي 🧑‍⚕️"]
    ],
    resize_keyboard=True
)

CBT_KB = ReplyKeyboardMarkup(
    [
        ["خطة CBT شاملة (مقترحة)"],
        ["ما هو CBT؟", "أخطاء التفكير"],
        ["طرق علاج القلق", "طرق علاج الاكتئاب"],
        ["إدارة الغضب", "التخلّص من الخوف"],
        ["سجلّ الأفكار (تمرين)", "التعرّض التدريجي (قلق/هلع)"],
        ["التنشيط السلوكي (تحسين المزاج)", "الاسترخاء والتنفس"],
        ["اليقظة الذهنية (Mindfulness)", "حل المشكلات"],
        ["بروتوكول النوم", "◀️ رجوع"]
    ],
    resize_keyboard=True
)

AI_CHAT_KB = ReplyKeyboardMarkup([["◀️ إنهاء جلسة عربي سايكو"]], resize_keyboard=True)

# ========== حالات المحادثة ==========
MENU, CBT_MENU, TESTS_MENU, PERS_MENU, AI_CHAT = range(5)
TH_SITU, TH_EMO, TH_AUTO, TH_FOR, TH_AGAINST, TH_ALT, TH_RERATE = range(10,17)
EXPO_WAIT, EXPO_FLOW = range(20,22)
PANIC_Q, PTSD_Q, SURVEY = range(30,33)

# ========== أمان (كلمات أزمة) ==========
CRISIS_WORDS = ["انتحار","سأؤذي نفسي","اذي نفسي","قتل نفسي","ما ابغى اعيش","فقدت الامل","اريد اموت","ابي اموت"]
def is_crisis(txt: str) -> bool:
    low = (txt or "").replace("أ","ا").replace("إ","ا").replace("آ","ا").lower()
    return any(w in low for w in CRISIS_WORDS)

# ========== ذكاء اصطناعي ==========
AI_SYSTEM_GENERAL = (
    "أنت «عربي سايكو»، مساعد نفسي عربي يعتمد مبادئ CBT.\n"
    "- لست بديلاً عن الطوارئ أو التشخيص الطبي أو وصف الأدوية.\n"
    "- قدّم خطوات عملية قصيرة، تعليمات واضحة، وأسئلة استكشافية.\n"
    "- اختتم الرد بنقاط عملية موجزة."
)
AI_SYSTEM_DSM = (
    "أنت «عربي سايكو»، مساعد نفسي عربي بمقاربة DSM-5 استرشادية (غير تشخيصية).\n"
    "- لا تقدّم تشخيصًا نهائيًا. ساعد المستخدم على تنظيم الأعراض (المدة/الشدة/الأثر).\n"
    "- اقترح محاور تقييم وتمارين CBT مناسبة وتنبيهات أمان عند اللزوم."
)

def ai_call(user_content: str, history: List[Dict[str,str]], dsm_mode: bool) -> str:
    if not (AI_BASE_URL and AI_API_KEY and AI_MODEL):
        return "تعذّر استخدام الذكاء الاصطناعي حاليًا (تأكد من المفاتيح/النموذج)."
    headers = {"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"}
    sys = AI_SYSTEM_DSM if dsm_mode else AI_SYSTEM_GENERAL
    payload = {
        "model": AI_MODEL,
        "messages": [{"role":"system","content":sys}] + history + [{"role":"user","content":user_content}],
        "temperature": 0.4,
        "max_tokens": 700,
    }
    try:
        r = requests.post(f"{AI_BASE_URL.rstrip('/')}/chat/completions", headers=headers, data=json.dumps(payload), timeout=45)
        r.raise_for_status()
        j = r.json()
        return j["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"تعذّر الاتصال بالذكاء الاصطناعي: {e}"

async def ai_respond(text: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    if is_crisis(text):
        return ("⚠️ سلامتك أولاً. إن كان لديك خطر فوري على نفسك/غيرك فاتصل بالطوارئ فورًا.\n"
                "جرّب تنفّس 4-7-8 عشر مرات وابقَ مع شخص تثق به وحدّد موعدًا عاجلاً مع مختص.")
    hist: List[Dict[str,str]] = context.user_data.get("ai_hist", [])
    hist = hist[-20:]
    dsm_mode = (context.user_data.get("ai_mode") == "dsm")
    reply = await asyncio.to_thread(ai_call, text, hist, dsm_mode)
    hist += [{"role":"user","content":text},{"role":"assistant","content":reply}]
    context.user_data["ai_hist"] = hist[-20:]
    return reply

# ========== CBT نصوص ==========
CBT_TXT = {
    "plan": (
        "🧭 **خطة CBT شاملة (4 أسابيع مقترحة)**\n"
        "الأسبوع 1: تتبّع مزاج 0–10 + سجلّ أفكار مرة يوميًا + تنفّس 4-7-8 ×4 مرتين يوميًا.\n"
        "الأسبوع 2: تنشيط سلوكي: 3 مهام قصيرة يوميًا (عناية ذاتية/علاقة/إنجاز بسيط).\n"
        "الأسبوع 3: تعرّض تدريجي لموقف 3–4/10 يوميًا حتى يهبط القلق للنصف (بدون طمأنة).\n"
        "الأسبوع 4: حل مشكلات/يقظة ذهنية 10–15د يوميًا + بروتوكول نوم ثابت.\n\n"
        "🎯 قواعد عامة: صغير ومتكرر أفضل من كبير ونادر — قياس قبل/بعد — مراجعة أسبوعية."
    ),
    "about": (
        "🔹 **ما هو CBT؟**\n"
        "يربط بين **الفكر ↔ الشعور ↔ السلوك**. نلتقط الفكرة غير المفيدة، نراجع الدليل، "
        "ونجرّب سلوكًا صغيرًا مفيدًا؛ مع التكرار يتحسّن المزاج.\n\n"
        "الخطوات:\n"
        "1) سمِّ مشاعرك 0–10.\n2) اكتب الموقف والفكرة التلقائية.\n3) الدليل معها/ضدها.\n"
        "4) فكرة بديلة متوازنة.\n5) خطوة سلوكية صغيرة الآن (5–15د) ثم قياس التغيّر."
    ),
    "dist": (
        "🧠 **أخطاء التفكير الشائعة**: التعميم، التهويل، قراءة الأفكار، التنبؤ السلبي، الأبيض/الأسود، يجب/لازم.\n"
        "اسأل نفسك: ما الدليل؟ ما البديل؟ ماذا أنصح صديقًا مكاني؟"
    ),
    "anx": (
        "⚓ **طرق علاج القلق (مختصر عملي)**\n"
        "• تعرّض تدريجي: قائمة مواقف من الأسهل للأصعب (3–4/10 أولًا) والبقاء حتى يهبط القلق ≥ النصف.\n"
        "• منع الطمأنة والهروب.\n"
        "• تنظيم التنفّس (4-7-8) وتمارين يقظة 5-4-3-2-1.\n"
        "• نشاط يومي خفيف 10–20د (مشي/تواصل/شمس).\n"
        "• قلّل الكافيين قبل 6–8 ساعات من النوم."
    ),
    "dep": (
        "🌤️ **طرق علاج الاكتئاب (تنشيط سلوكي)**\n"
        "• جدول مصغّر: ثلاث مهام قصيرة يوميًا (عناية ذاتية/علاقة/إنجاز بسيط).\n"
        "• قاعدة 5 دقائق: ابدأ ولو بخمس دقائق لكسر الجمود.\n"
        "• تتبّع المزاج والنوم، وخفّض العزلة تدريجيًا.\n"
        "• فكّر متوازن: راجع الفكرة السوداوية بدليل وبديل عملي."
    ),
    "anger": (
        "🔥 **إدارة الغضب**\n"
        "إشارة مبكرة → تنفّس بطيء 4-7-8 ×4 → اسمِ مشاعرك بدقة → مهلة قصيرة/انسحاب آمن → "
        "ارجع بخطة حلّ مشكلة (متى/أين/كيف). دوّن المحفّزات المتكررة."
    ),
    "fear": (
        "🧭 **التخلص من الخوف (تعرض)**\n"
        "عرّف الموقف المخيف 3–4/10، ابقَ فيه بلا طمأنة حتى يهبط القلق، كرّر 3–4 مرات يوميًا ثم انتقل للأصعب."
    ),
    "relax": "🌬️ **الاسترخاء والتنفس**: شهيق4، حبس7، زفير8 (×4). وشد/إرخاء تدريجي من القدم للرأس.",
    "mind": "🧘 **يقظة ذهنية** 5-4-3-2-1: 5 ترى، 4 تلمس، 3 تسمع، 2 تشم، 1 تتذوق. ارجع للحاضر دون حكم.",
    "prob": "🧩 **حل المشكلات**: حدد المشكلة بدقة → بدائل بلا حكم → مزايا/عيوب → خطة متى/أين/كيف → جرّب → قيِّم.",
    "sleep":"🛌 **بروتوكول النوم**: استيقاظ ثابت، السرير للنوم فقط، أوقف الشاشات ساعة قبل النوم، تجنّب القيلولة الطويلة.",
}

# ========== تمارين/حالات ==========
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

# ========== بنوك أسئلة ==========
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

ISI7 = Survey("isi7","ISI-7 — شدّة الأرق",
    ["صعوبة بدء النوم","صعوبة الاستمرار بالنوم","الاستيقاظ المبكر","الرضا عن النوم",
     "تأثير الأرق على الأداء بالنهار","ملاحظة الآخرين لمشكلتك","القلق/الانزعاج من نومك"],
    "0=لا،1=خفيف،2=متوسط،3=شديد،4=شديد جدًا",0,4)

PSS10 = Survey("pss10","PSS-10 — الضغوط المُدركة",
    ["كم شعرت بأن الأمور خرجت عن سيطرتك؟","كم انزعجت من أمر غير متوقع؟","كم شعرت بالتوتر؟",
     "كم شعرت بأنك تتحكم بالأمور؟ (عكسي)","كم شعرت بالثقة في التعامل مع مشكلاتك؟ (عكسي)",
     "كم شعرت أن الأمور تسير كما ترغب؟ (عكسي)","كم لم تستطع التأقلم مع كل ما عليك؟",
     "كم سيطرت على الانفعالات؟ (عكسي)","كم شعرت بأن المشاكل تتراكم؟","كم وجدت وقتًا للأشياء المهمة؟ (عكسي)"],
    "0=أبدًا،1=نادرًا،2=أحيانًا،3=كثيرًا،4=دائمًا",0,4,reverse=[3,4,5,7,9])

WHO5 = Survey("who5","WHO-5 — الرفاه",
    ["شعرتُ بأنني مبتهج وفي مزاج جيد","شعرتُ بالهدوء والسكينة","شعرتُ بالنشاط والحيوية",
     "كنتُ أستيقظ مرتاحًا","كان يومي مليئًا بما يهمّني"],
    "0=لم يحصل مطلقًا…5=طوال الوقت",0,5)

K10 = Survey("k10","K10 — الضيق النفسي (4 أسابيع)",
    ["كم مرة شعرت بالتعب بلا سبب؟","عصبي/متوتر؟","ميؤوس؟","قلق شديد؟","كل شيء جهد عليك؟",
     "لا تستطيع الهدوء؟","حزين بشدة؟","لا شيء يفرحك؟","لا تحتمل أي تأخير؟","شعور بلا قيمة؟"],
    "1=أبدًا،2=قليلًا،3=أحيانًا،4=غالبًا،5=دائمًا",1,5)

PC_PTSD5 = [
  "آخر شهر: كوابيس/ذكريات مزعجة لحدث صادم؟ (نعم/لا)",
  "تجنّبت التفكير/الأماكن المرتبطة بالحدث؟ (نعم/لا)",
  "كنت على أعصابك/سريع الفزع؟ (نعم/لا)",
  "شعرت بالخدر/الانفصال عن الناس/الأنشطة؟ (نعم/لا)",
  "شعرت بالذنب/اللوم بسبب الحدث؟ (نعم/لا)"
]

SAPAS = [
  "هل علاقاتك القريبة غير مستقرة أو قصيرة؟ (نعم/لا)",
  "هل تتصرف اندفاعيًا دون تفكير كافٍ؟ (نعم/لا)",
  "هل تدخل في خلافات متكررة؟ (نعم/لا)",
  "هل يراك الناس «غريب الأطوار»؟ (نعم/لا)",
  "هل تشكّ بالناس ويصعب الثقة؟ (نعم/لا)",
  "هل تتجنب الاختلاط خوف الإحراج/الرفض؟ (نعم/لا)",
  "هل تقلق كثيرًا على أشياء صغيرة؟ (نعم/لا)",
  "هل لديك كمالية/صرامة تؤثر على حياتك؟ (نعم/لا)",
]

MSI_BPD = [
  "علاقاتك شديدة التقلب؟ (نعم/لا)","صورتك عن نفسك تتبدل جدًا؟ (نعم/لا)",
  "سلوك اندفاعي مؤذٍ أحيانًا؟ (نعم/لا)","محاولات/تهديدات إيذاء نفسك؟ (نعم/لا)",
  "مشاعرك تتقلب بسرعة وبشدة؟ (نعم/لا)","فراغ داخلي دائم؟ (نعم/لا)",
  "غضب شديد يصعب تهدئته؟ (نعم/لا)","خوف قوي من الهجر؟ (نعم/لا)",
  "توتر شديد/أفكار غريبة تحت الضغط؟ (نعم/لا)","تجنّب/اختبارات للآخرين خوف الهجر؟ (نعم/لا)"
]

# ========== اضطرابات الشخصية ==========
PD_TEXT = (
    "🧩 **اضطرابات الشخصية — DSM-5 (عناقيد A/B/C)**\n\n"
    "A (غريبة/شاذة): الزورية، الفُصامية/الانعزالية، الفُصامية الشكل.\n"
    "B (درامية/اندفاعية): المعادية للمجتمع، الحدّية، الهستيرية، النرجسية.\n"
    "C (قلِقة/خائفة): التجنبية، الاتكالية، الوسواسية القهرية للشخصية.\n\n"
    "الفكرة: نمط مستمر مبكر نسبياً يؤثر على الإدراك والانفعالات والعلاقات والسلوك.\n"
    "الاسترشاد: استخدم **SAPAS** (شاشة عامة) و **MSI-BPD** (مؤشرات الحدّية). النتيجة ليست تشخيصًا.\n"
    "اطلب تقييمًا مختصًا عند الضيق الشديد، إيذاء الذات، أو تدهور العلاقات والعمل."
)

# ========== التحويل الطبي ==========
def referral_keyboard():
    rows = []
    if CONTACT_THERAPIST_URL:
        rows.append([InlineKeyboardButton("تحويل إلى أخصائي نفسي", url=CONTACT_THERAPIST_URL)])
    if CONTACT_PSYCHIATRIST_URL:
        rows.append([InlineKeyboardButton("تحويل إلى طبيب نفسي", url=CONTACT_PSYCHIATRIST_URL)])
    if not rows:
        rows.append([InlineKeyboardButton("راسلنا على تيليجرام", url="https://t.me/")])
    return InlineKeyboardMarkup(rows)

# ========== رسائل موحّدة مع أزرار ==========
def tests_psych_inline():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("PHQ-9 (اكتئاب)", callback_data="test:phq9"),
         InlineKeyboardButton("GAD-7 (قلق)", callback_data="test:gad7")],
        [InlineKeyboardButton("Mini-SPIN (رهاب اجتماعي)", callback_data="test:minispin"),
         InlineKeyboardButton("ISI-7 (أرق)", callback_data="test:isi7")],
        [InlineKeyboardButton("PSS-10 (ضغوط)", callback_data="test:pss10"),
         InlineKeyboardButton("WHO-5 (رفاه)", callback_data="test:who5")],
        [InlineKeyboardButton("K10 (ضيق نفسي)", callback_data="test:k10")],
        [InlineKeyboardButton("PC-PTSD-5 (صدمة)", callback_data="test:pcptsd5"),
         InlineKeyboardButton("فحص نوبات الهلع", callback_data="test:panic")],
    ])

def tests_personality_inline():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("TIPI (الخمسة الكبار)", callback_data="test:tipi")],
        [InlineKeyboardButton("SAPAS (شاشة عامة)", callback_data="test:sapas"),
         InlineKeyboardButton("MSI-BPD (حدّية)", callback_data="test:msi")],
    ])

def pd_inline():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("ابدأ SAPAS", callback_data="test:sapas"),
         InlineKeyboardButton("ابدأ MSI-BPD", callback_data="test:msi")],
        [InlineKeyboardButton("TIPI الخمسة الكبار", callback_data="test:tipi")],
    ])

# ========== أوامر عامة ==========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        "مرحبًا! أنا **عربي سايكو** — مساعد نفسي افتراضي بالذكاء الاصطناعي (ليس بديلاً للطوارئ/التشخيص الطبي).",
        reply_markup=TOP_KB
    )
    return MENU

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("/start — القائمة\n/help — المساعدة\n/ping — اختبار سريع")

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong ✅")

async def cmd_version(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"نسخة عربي سايكو: {VERSION}")

async def cmd_ai_diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"AI_BASE_URL set={bool(AI_BASE_URL)} | KEY set={bool(AI_API_KEY)} | MODEL={AI_MODEL}"
    )

# ========== المستوى الأعلى ==========
async def top_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""

    if has("عربي سايكو", t):
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("ابدأ جلسة عربي سايكو 🤖", callback_data="start_ai")],
            [InlineKeyboardButton("جلسة عربي سايكو + DSM", callback_data="start_ai_dsm")],
            [InlineKeyboardButton("DSM-5 تشخيص استرشادي فقط", callback_data="start_dsm")],
        ])
        await update.message.reply_text(
            "معك **عربي سايكو** — معالج نفسي افتراضي بالذكاء الاصطناعي (ليس بديلاً للطوارئ/التشخيص الطبي).\nاختر:",
            reply_markup=kb
        )
        return MENU

    if has("العلاج السلوكي", t):
        await update.message.reply_text(
            "اختر وحدة من CBT (يمكنك البدء بـ **خطة CBT شاملة (مقترحة)**):",
            reply_markup=CBT_KB
        )
        return CBT_MENU

    if has("الاختبارات النفسية", t):
        text = ("📝 **الاختبارات النفسية (زر موحّد)**\n"
                "اختر اختبارًا: اكتئاب، قلق، رهاب اجتماعي، أرق، ضغوط، رفاه، ضيق نفسي، PTSD، فحص هلع.")
        await update.message.reply_text(text, reply_markup=tests_psych_inline())
        return MENU

    if has("اختبارات الشخصية", t):
        text = ("🧩 **اختبارات الشخصية (زر موحّد)**\n"
                "• TIPI (الخمسة الكبار)\n• SAPAS (شاشة عامة)\n• MSI-BPD (مؤشرات الحدّية)")
        await update.message.reply_text(text, reply_markup=tests_personality_inline())
        return MENU

    if has("اضطرابات الشخصية", t):
        await send_long(update.effective_chat, PD_TEXT, pd_inline())
        return MENU

    if has("الأخصائي النفسي", t) or has("الاخصائي النفسي", t):
        await update.message.reply_text(
            "👨‍⚕️ **الأخصائي النفسي**\nللحجز أو الاستفسار اختر:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("حجز جلسة على تيليجرام", url=CONTACT_THERAPIST_URL)],
                [InlineKeyboardButton("إرسال سؤال الآن", url=CONTACT_THERAPIST_URL)],
            ])
        )
        return MENU

    if has("التحويل الطبي", t):
        await update.message.reply_text("اختر نوع التحويل:", reply_markup=referral_keyboard())
        return MENU

    await update.message.reply_text("اختر من الأزرار أو اكتب /help.", reply_markup=TOP_KB)
    return MENU

# ========== بدء/إدارة جلسة AI ==========
async def ai_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["ai_hist"] = []
    context.user_data["ai_mode"] = "free"
    await q.message.chat.send_message(
        "بدأت جلسة **عربي سايكو**. اكتب ما يضايقك الآن وسأساعدك بخطوات عملية.\n"
        "لإنهاء الجلسة: «◀️ إنهاء جلسة عربي سايكو».", reply_markup=AI_CHAT_KB
    )
    return AI_CHAT

async def ai_start_dsm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["ai_hist"] = []
    context.user_data["ai_mode"] = "dsm"
    await q.message.chat.send_message(
        "✅ دخلت جلسة **عربي سايكو + DSM** (استرشادي غير تشخيصي).\n"
        "صف الأعراض بالمدة/الشدة/الأثر وسأقترح محاور تقييم وتمارين CBT مناسبة.",
        reply_markup=AI_CHAT_KB
    )
    return AI_CHAT

async def dsm_start_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    context.user_data["ai_hist"] = []
    context.user_data["ai_mode"] = "dsm"
    await q.message.chat.send_message(
        "✅ دخلت وضع **DSM-5 الاسترشادي** (غير تشخيصي).",
        reply_markup=AI_CHAT_KB
    )
    return AI_CHAT

async def ai_chat_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    if text in ("◀️ إنهاء جلسة عربي سايكو","/خروج","خروج","رجوع","◀️ رجوع"):
        await update.message.reply_text("انتهت الجلسة. رجعناك للقائمة.", reply_markup=TOP_KB)
        return MENU
    await update.effective_chat.send_action(ChatAction.TYPING)
    reply = await ai_respond(text, context)
    await update.message.reply_text(reply, reply_markup=AI_CHAT_KB)
    return AI_CHAT

# ======= بدء اختبار عبر زر =======
async def start_test_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    code = q.data.split(":",1)[1]  # مثل: test:phq9
    mapping = {
        "phq9":"PHQ-9 اكتئاب","gad7":"GAD-7 قلق","minispin":"Mini-SPIN رهاب اجتماعي","isi7":"ISI-7 أرق",
        "pss10":"PSS-10 ضغوط","who5":"WHO-5 رفاه","k10":"K10 ضيق نفسي","pcptsd5":"PC-PTSD-5 صدمة","panic":"فحص نوبات الهلع",
        "tipi":"TIPI الخمسة الكبار","sapas":"SAPAS اضطراب شخصية","msi":"MSI-BPD حدّية"
    }
    text = mapping.get(code)
    if not text:
        return MENU

    # رسالة صناعية بسيطة متوافقة مع الراوترات
    class SimpleMessage:
        def __init__(self, chat, txt): self.chat = chat; self.text = txt
        async def reply_text(self, *a, **k): return await self.chat.send_message(*a, **k)

    class SimpleUpdate:
        def __init__(self, chat, txt): self.message = SimpleMessage(chat, txt)

    u2 = SimpleUpdate(q.message.chat, text)
    if code in ("tipi","sapas","msi"):
        return await pers_router(u2, context)
    else:
        return await tests_router(u2, context)

# ========== CBT Router ==========
async def cbt_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""

    if t == "◀️ رجوع":
        await update.message.reply_text("رجعناك للقائمة.", reply_markup=TOP_KB);  return MENU

    if has("خطة CBT شاملة", t):
        await send_long(update.effective_chat, CBT_TXT["plan"], CBT_KB);  return CBT_MENU

    if has("ما هو CBT", t):  await send_long(update.effective_chat, CBT_TXT["about"], CBT_KB);  return CBT_MENU
    if has("أخطاء التفكير", t):  await send_long(update.effective_chat, CBT_TXT["dist"], CBT_KB);  return CBT_MENU
    if has("طرق علاج القلق", t):  await send_long(update.effective_chat, CBT_TXT["anx"], CBT_KB);  return CBT_MENU
    if has("طرق علاج الاكتئاب", t):  await send_long(update.effective_chat, CBT_TXT["dep"], CBT_KB);  return CBT_MENU
    if has("إدارة الغضب", t):  await send_long(update.effective_chat, CBT_TXT["anger"], CBT_KB);  return CBT_MENU
    if has("التخلّص من الخوف", t):  await send_long(update.effective_chat, CBT_TXT["fear"], CBT_KB);  return CBT_MENU
    if has("الاسترخاء", t):  await update.message.reply_text(CBT_TXT["relax"], reply_markup=CBT_KB);  return CBT_MENU
    if has("اليقظة", t):  await update.message.reply_text(CBT_TXT["mind"], reply_markup=CBT_KB);  return CBT_MENU
    if has("حل المشكلات", t):  await update.message.reply_text(CBT_TXT["prob"], reply_markup=CBT_KB);  return CBT_MENU
    if has("بروتوكول النوم", t):  await update.message.reply_text(CBT_TXT["sleep"], reply_markup=CBT_KB);  return CBT_MENU

    if has("التنشيط السلوكي", t):
        context.user_data["ba_wait"] = True
        await update.message.reply_text("أرسل 3 أنشطة صغيرة اليوم (10–20د) مفصولة بفواصل/أسطر.", reply_markup=ReplyKeyboardRemove())
        return CBT_MENU

    if has("سجلّ الأفكار", t):
        context.user_data["tr"] = ThoughtRecord()
        await update.message.reply_text("📝 اكتب **الموقف** باختصار (متى/أين/مع من؟).", reply_markup=ReplyKeyboardRemove())
        return TH_SITU

    if has("التعرّض التدريجي", t):
        context.user_data["expo"] = ExposureState()
        await update.message.reply_text("أرسل درجة قلقك الحالية 0–10.", reply_markup=ReplyKeyboardRemove())
        return EXPO_WAIT

    # إدخال أنشطة BA
    if context.user_data.get("ba_wait"):
        context.user_data["ba_wait"] = False
        parts = [s.strip() for s in re.split(r"[,\n،]+", t) if s.strip()]
        plan = "خطة اليوم:\n• " + "\n• ".join(parts[:3] or ["نشاط بسيط 10–20 دقيقة الآن."])
        await update.message.reply_text(plan + "\nقيّم مزاجك قبل/بعد 0–10.", reply_markup=CBT_KB)
        return CBT_MENU

    await update.message.reply_text("اختر وحدة من القائمة:", reply_markup=CBT_KB)
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
        "✅ **ملخص سجلّ الأفكار**\n"
        f"• الموقف: {tr.situation}\n• الشعور قبل: {tr.emotion}\n• الفكرة: {tr.auto}\n"
        f"• أدلة تؤيد: {tr.ev_for}\n• أدلة تنفي: {tr.ev_against}\n• البديل: {tr.alternative}\n"
        f"• التقييم بعد: {tr.end if tr.end is not None else '—'}\n"
        "استمر بالتدريب يوميًا."
    )
    await send_long(update.effective_chat, txt)
    await update.message.reply_text("اختر من قائمة CBT:", reply_markup=CBT_KB)
    return CBT_MENU

# التعرّض
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
        await q.edit_message_text("أمثلة: ركوب المصعد لطابقين، الانتظار في صف قصير، الجلوس بمقهى 10 دقائق.\nاكتب موقفك.")
    else:
        await q.edit_message_text("القاعدة: تعرّض آمن + منع الطمأنة + البقاء حتى يهبط القلق للنصف ثم كرّر.")
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
    if q.data == "expo_start":
        await q.edit_message_text("بالتوفيق! عند الانتهاء أرسل الدرجة الجديدة 0–10.")
        return EXPO_WAIT
    if q.data == "expo_rate":
        await q.edit_message_text("أرسل الدرجة الجديدة 0–10.")
        return EXPO_WAIT
    return EXPO_FLOW

# ========== اختبارات ثنائية نعم/لا ==========
@dataclass
class BinState:
    i: int = 0
    yes: int = 0
    qs: List[str] = field(default_factory=list)

# ========== Router الاختبارات ==========
async def tests_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if t == "◀️ رجوع":
        await update.message.reply_text("رجعناك للقائمة.", reply_markup=TOP_KB);  return MENU

    key = {
        "PHQ-9 اكتئاب":"phq9","GAD-7 قلق":"gad7","Mini-SPIN رهاب اجتماعي":"minispin",
        "TIPI الخمسة الكبار":"tipi","ISI-7 أرق":"isi7","PSS-10 ضغوط":"pss10","WHO-5 رفاه":"who5","K10 ضيق نفسي":"k10",
        "PC-PTSD-5 صدمة":"pcptsd5","فحص نوبات الهلع":"panic"
    }.get(t)

    if key is None:
        await update.message.reply_text("اختر اختبارًا:", reply_markup=tests_psych_inline());  return MENU

    if key == "panic":
        context.user_data["panic"] = BinState(i=0, yes=0, qs=[
            "خلال 4 أسابيع: هل حدثت لديك نوبات هلع مفاجئة؟ (نعم/لا)",
            "هل تخاف من حدوث نوبة أخرى أو تتجنب أماكن بسببها؟ (نعم/لا)"
        ])
        await update.message.reply_text(context.user_data["panic"].qs[0], reply_markup=ReplyKeyboardRemove());  return PANIC_Q

    if key == "pcptsd5":
        context.user_data["pc"] = BinState(i=0, yes=0, qs=PC_PTSD5)
        await update.message.reply_text(PC_PTSD5[0], reply_markup=ReplyKeyboardRemove());  return PTSD_Q

    # الاستبيانات الرقمية
    s_map = {"phq9":PHQ9,"gad7":GAD7,"minispin":MINISPIN,"tipi":TIPI,"isi7":ISI7,"pss10":PSS10,"who5":WHO5,"k10":K10}
    s0 = s_map[key]
    s = Survey(s0.id, s0.title, list(s0.items), s0.scale, s0.min_v, s0.max_v, list(s0.reverse))
    context.user_data["s"] = s; context.user_data["s_i"] = 0
    await update.message.reply_text(f"بدء **{s.title}**.\n{survey_prompt(s,0)}", reply_markup=ReplyKeyboardRemove())
    return SURVEY

# اختبارات الشخصية (TIPI/SAPAS/MSI)
async def pers_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text or ""
    if t == "◀️ رجوع":
        await update.message.reply_text("رجعناك للقائمة.", reply_markup=TOP_KB);  return MENU

    if t in ("SAPAS اضطراب شخصية","MSI-BPD حدّية","TIPI الخمسة الكبار"):
        if t == "SAPAS اضطراب شخصية":
            context.user_data["bin"] = BinState(i=0, yes=0, qs=SAPAS)
            await update.message.reply_text(SAPAS[0], reply_markup=ReplyKeyboardRemove());  return SURVEY
        if t == "MSI-BPD حدّية":
            context.user_data["bin"] = BinState(i=0, yes=0, qs=MSI_BPD)
            await update.message.reply_text(MSI_BPD[0], reply_markup=ReplyKeyboardRemove());  return SURVEY
        if t == "TIPI الخمسة الكبار":
            s = Survey(TIPI.id, TIPI.title, list(TIPI.items), TIPI.scale, TIPI.min_v, TIPI.max_v, list(TIPI.reverse))
            context.user_data["s"] = s; context.user_data["s_i"] = 0
            await update.message.reply_text(f"بدء **{s.title}**.\n{survey_prompt(s,0)}", reply_markup=ReplyKeyboardRemove())
            return SURVEY

    await update.message.reply_text("اختر اختبار شخصية:", reply_markup=tests_personality_inline())
    return MENU

# تدفق الهلع
async def panic_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st: BinState = context.user_data["panic"]; ans = (update.message.text or "").strip().lower()
    if ans not in ("نعم","لا","yes","no"):
        await update.message.reply_text("أجب بـ نعم/لا.");  return PANIC_Q
    st.yes += 1 if ans in ("نعم","yes") else 0; st.i += 1
    if st.i < len(st.qs):
        await update.message.reply_text(st.qs[st.i]);  return PANIC_Q
    msg = "إيجابي — قد تكون هناك نوبات هلع" if st.yes==2 else "سلبي — لا مؤشر قوي حاليًا"
    context.user_data.pop("panic", None)  # تنظيف الحالة
    await update.message.reply_text(f"**نتيجة فحص الهلع:** {msg}", reply_markup=TOP_KB);  return MENU

# تدفق PTSD
async def ptsd_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    st: BinState = context.user_data["pc"]; ans = (update.message.text or "").strip().lower()
    if ans not in ("نعم","لا","yes","no"):
        await update.message.reply_text("أجب بـ نعم/لا.");  return PTSD_Q
    st.yes += 1 if ans in ("نعم","yes") else 0; st.i += 1
    if st.i < len(st.qs):
        await update.message.reply_text(st.qs[st.i]);  return PTSD_Q
    result = "إيجابي (≥3 «نعم») — يُوصى بالتقييم." if st.yes>=3 else "سلبي — أقل من حد الإشارة."
    context.user_data.pop("pc", None)  # تنظيف الحالة
    await update.message.reply_text(f"**PC-PTSD-5:** {st.yes}/5 — {result}", reply_markup=TOP_KB);  return MENU

# تدفق الاستبيانات (ثنائية أو درجات)
async def survey_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ثنائي (SAPAS / MSI)
    if "bin" in context.user_data:
        st: BinState = context.user_data["bin"]; ans = (update.message.text or "").strip().lower()
        if ans not in ("نعم","لا","yes","no"):
            await update.message.reply_text("أجب بـ نعم/لا.");  return SURVEY
        st.yes += 1 if ans in ("نعم","yes") else 0; st.i += 1
        if st.i < len(st.qs):
            await update.message.reply_text(st.qs[st.i]);  return SURVEY
        if len(st.qs)==8:
            cut=3; msg = f"**SAPAS:** {st.yes}/8 — " + ("إيجابي (≥3) يُستحسن التقييم." if st.yes>=cut else "سلبي.")
        else:
            cut=7; msg = f"**MSI-BPD:** {st.yes}/10 — " + ("إيجابي (≥7) يُستحسن التقييم." if st.yes>=cut else "سلبي.")
        context.user_data.pop("bin", None)  # تنظيف
        await update.message.reply_text(msg, reply_markup=TOP_KB)
        return MENU

    # درجات
    s: Survey = context.user_data.get("s")
    i = context.user_data.get("s_i", 0)
    if not s:
        await update.message.reply_text("لا توجد جلسة اختبار قيد التشغيل. اختر اختبارًا من القائمة.", reply_markup=TOP_KB)
        return MENU

    n = to_int(update.message.text)
    if n is None or not (s.min_v <= n <= s.max_v):
        await update.message.reply_text(f"أدخل رقمًا بين {s.min_v} و{s.max_v}.");  return SURVEY
    s.ans.append(n); i += 1
    if i >= len(s.items):
        # حساب النتائج النهائية
        if s.id=="gad7":
            total=sum(s.ans); lvl = "طبيعي/خفيف جدًا" if total<=4 else "قلق خفيف" if total<=9 else "قلق متوسط" if total<=14 else "قلق شديد"
            context.user_data.pop("s", None); context.user_data.pop("s_i", None)
            await update.message.reply_text(f"**GAD-7:** {total}/21 — {lvl}", reply_markup=TOP_KB);  return MENU
        if s.id=="phq9":
            total=sum(s.ans)
            if   total<=4: lvl="لا/خفيف جدًا"
            elif total<=9: lvl="خفيف"
            elif total<=14: lvl="متوسط"
            elif total<=19: lvl="متوسط-شديد"
            else: lvl="شديد"
            warn = "\n⚠️ بند أفكار الإيذاء >0 — اطلب مساعدة فورية." if s.ans[8]>0 else ""
            context.user_data.pop("s", None); context.user_data.pop("s_i", None)
            await update.message.reply_text(f"**PHQ-9:** {total}/27 — {lvl}{warn}", reply_markup=TOP_KB);  return MENU
        if s.id=="minispin":
            total=sum(s.ans); msg="مؤشر رهاب اجتماعي محتمل" if total>=6 else "أقل من حد الإشارة"
            context.user_data.pop("s", None); context.user_data.pop("s_i", None)
            await update.message.reply_text(f"**Mini-SPIN:** {total}/12 — {msg}", reply_markup=TOP_KB);  return MENU
        if s.id=="tipi":
            vals = s.ans[:]
            for idx in s.reverse: vals[idx] = 8 - vals[idx]
            extr=(vals[0]+vals[5])/2; agre=(vals[1]+vals[6])/2; cons=(vals[2]+vals[7])/2; emot=(vals[3]+vals[8])/2; open_=(vals[4]+vals[9])/2
            def lab(x): return "عالٍ" if x>=5.5 else ("منخفض" if x<=2.5 else "متوسط")
            msg=(f"**TIPI (1–7):**\n"
                 f"• الانبساط: {extr:.1f} ({lab(extr)})\n• التوافق: {agre:.1f} ({lab(agre)})\n"
                 f"• الانضباط: {cons:.1f} ({lab(cons)})\n• الاستقرار الانفعالي: {emot:.1f} ({lab(emot)})\n"
                 f"• الانفتاح: {open_:.1f} ({lab(open_)})")
            context.user_data.pop("s", None); context.user_data.pop("s_i", None)
            await update.message.reply_text(msg, reply_markup=TOP_KB);  return MENU
        if s.id=="isi7":
            total=sum(s.ans)
            if   total<=7: lvl="أرق ضئيل"
            elif total<=14: lvl="أرق خفيف"
            elif total<=21: lvl="أرق متوسط"
            else: lvl="أرق شديد"
            context.user_data.pop("s", None); context.user_data.pop("s_i", None)
            await update.message.reply_text(f"**ISI-7:** {total}/28 — {lvl}", reply_markup=TOP_KB);  return MENU
        if s.id=="pss10":
            vals=s.ans[:]
            for idx in s.reverse: vals[idx] = s.max_v - vals[idx]
            total=sum(vals)
            lvl = "منخفض" if total<=13 else "متوسط" if total<=26 else "عالٍ"
            context.user_data.pop("s", None); context.user_data.pop("s_i", None)
            await update.message.reply_text(f"**PSS-10:** {total}/40 — ضغط {lvl}", reply_markup=TOP_KB);  return MENU
        if s.id=="who5":
            total=sum(s.ans)*4
            note="منخفض (≤50) — يُستحسن تحسين الروتين والتواصل/التقييم." if total<=50 else "جيد."
            context.user_data.pop("s", None); context.user_data.pop("s_i", None)
            await update.message.reply_text(f"**WHO-5:** {total}/100 — {note}", reply_markup=TOP_KB);  return MENU
        if s.id=="k10":
            total=sum(s.ans)
            if   total<=19: lvl="خفيف"
            elif total<=24: lvl="متوسط"
            elif total<=29: lvl="شديد"
            else: lvl="شديد جدًا"
            context.user_data.pop("s", None); context.user_data.pop("s_i", None)
            await update.message.reply_text(f"**K10:** {total}/50 — ضيق {lvl}", reply_markup=TOP_KB);  return MENU

        await update.message.reply_text("تم الحساب.", reply_markup=TOP_KB);  return MENU

    context.user_data["s_i"] = i
    await update.message.reply_text(survey_prompt(s, i));  return SURVEY

# ========== سقوط عام ==========
async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اختر من الأزرار أو اكتب /help.", reply_markup=TOP_KB)
    return MENU

# ========== ربط وتشغيل ==========
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            MENU: [
                CallbackQueryHandler(ai_start_cb, pattern="^start_ai$"),
                CallbackQueryHandler(ai_start_dsm_cb, pattern="^start_ai_dsm$"),
                CallbackQueryHandler(dsm_start_cb, pattern="^start_dsm$"),
                CallbackQueryHandler(start_test_cb, pattern=r"^test:[\w\-]+$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, top_router),
            ],

            CBT_MENU: [
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
                CallbackQueryHandler(expo_cb, pattern=r"^expo_(suggest|help)$"),  # ← نُقل من MENU إلى هنا
                MessageHandler(filters.TEXT & ~filters.COMMAND, expo_flow),
                CallbackQueryHandler(expo_actions, pattern=r"^expo_(start|rate)$"),
            ],

            TESTS_MENU:[MessageHandler(filters.TEXT & ~filters.COMMAND, tests_router)],
            PERS_MENU:[MessageHandler(filters.TEXT & ~filters.COMMAND, pers_router)],
            PANIC_Q:[MessageHandler(filters.TEXT & ~filters.COMMAND, panic_flow)],
            PTSD_Q:[MessageHandler(filters.TEXT & ~filters.COMMAND, ptsd_flow)],
            SURVEY:[MessageHandler(filters.TEXT & ~filters.COMMAND, survey_flow)],

            AI_CHAT:[MessageHandler(filters.TEXT & ~filters.COMMAND, ai_chat_flow)],
        },
        fallbacks=[MessageHandler(filters.ALL, fallback)],
        allow_reentry=True
    )

    # سجّل الأوامر فقط خارج المحادثة
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("ping", cmd_ping))
    app.add_handler(CommandHandler("version", cmd_version))
    app.add_handler(CommandHandler("ai_diag", cmd_ai_diag))
    app.add_handler(conv)

    if PUBLIC_URL:
        try:
            app.run_webhook(
                listen="0.0.0.0",
                port=PORT,
                url_path=f"{BOT_TOKEN}",
                webhook_url=f"{PUBLIC_URL.rstrip('/')}/{BOT_TOKEN}",
                drop_pending_updates=True
            )
        except Exception as e:
            log.error("Webhook فشل (%s) — التحويل إلى polling.", e)
            app.run_polling(drop_pending_updates=True)
    else:
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
