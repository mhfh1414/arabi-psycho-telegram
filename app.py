# app.py — عربي سايكو: AI + DSM5 إرشادي + CBT + اختبارات + اختبارات شخصية + تحويل طبي
# Python 3.11 | python-telegram-bot v21.6

import os, re, asyncio, json, logging, requests
from dataclasses import dataclass, field
from typing import Optional, List, Dict

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

# ===== إعداد عام =====
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("arabi-psycho")
VERSION = "2025-08-24-personality-menu"

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("يرجى ضبط TELEGRAM_BOT_TOKEN")

AI_BASE_URL = (os.getenv("AI_BASE_URL") or "").strip()  # مثال: https://api.openai.com/v1
AI_API_KEY  = (os.getenv("AI_API_KEY") or "").strip()
AI_MODEL    = os.getenv("AI_MODEL", "gpt-4o-mini").strip()

PUBLIC_URL = os.getenv("PUBLIC_URL") or os.getenv("RENDER_EXTERNAL_URL") or os.getenv("WEBHOOK_URL")
PORT = int(os.getenv("PORT", "10000"))

CONTACT_THERAPIST_URL    = os.getenv("CONTACT_THERAPIST_URL", "")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "")

# ===== أدوات مساعدة =====
AR_DIGITS="٠١٢٣٤٥٦٧٨٩"; EN_DIGITS="0123456789"; TRANS=str.maketrans(AR_DIGITS, EN_DIGITS)
def normalize_num(s:str)->str: return (s or "").strip().translate(TRANS)
def to_int(s:str)->Optional[int]:
    try: return int(normalize_num(s))
    except: return None
def has(word:str, t:str)->bool: return word in (t or "")
async def send_long(chat, text, kb=None):
    chunk=3500
    for i in range(0,len(text),chunk):
        await chat.send_message(text[i:i+chunk], reply_markup=kb if i+chunk>=len(text) else None)

# ===== أمان (كلمات أزمة) =====
CRISIS_WORDS = ["انتحار","سأؤذي نفسي","اذي نفسي","قتل نفسي","ما ابغى اعيش","اريد اموت","ابي اموت","فقدت الامل"]
def is_crisis(txt:str)->bool:
    low=(txt or "").replace("أ","ا").replace("إ","ا").replace("آ","ا").lower()
    return any(w in low for w in CRISIS_WORDS)

# ===== ذكاء اصطناعي =====
AI_SYSTEM_GENERAL=(
  "أنت «عربي سايكو»، مساعد CBT عربي. لست بديلاً عن الطوارئ أو وصف الدواء. "
  "اعمل بخطوات عملية، تعليم واضح، وأسئلة استكشافية. اختم بنقاط عملية."
)
AI_SYSTEM_DSM=(
  "أنت «عربي سايكو» في وضع DSM-5 الاسترشادي (غير تشخيصي). "
  "رتّب الأعراض حسب المدة/الشدة/الأثر، واقترح مسارات تقييم وتمارين CBT مناسبة وتنبيهات أمان."
)

def ai_call(user_content:str, history:List[Dict[str,str]], dsm_mode:bool)->str:
    if not (AI_BASE_URL and AI_API_KEY and AI_MODEL):
        return "تعذّر استخدام الذكاء الاصطناعي (تحقق من المفتاح/الموديل/الرابط)."
    headers={"Authorization":f"Bearer {AI_API_KEY}","Content-Type":"application/json"}
    sys=AI_SYSTEM_DSM if dsm_mode else AI_SYSTEM_GENERAL
    payload={"model":AI_MODEL,"messages":[{"role":"system","content":sys}]+history+[{"role":"user","content":user_content}],
             "temperature":0.4,"max_tokens":700}
    r=requests.post(f"{AI_BASE_URL.rstrip('/')}/chat/completions", headers=headers, data=json.dumps(payload), timeout=30)
    if r.status_code>=400:
        try:
            err=r.json()
            return f"تعذّر الاتصال بالذكاء الاصطناعي: {err.get('error',{}).get('message','تحقق من الإعدادات')}"
        except: return f"تعذّر الاتصال بالذكاء الاصطناعي: HTTP {r.status_code}"
    return r.json()["choices"][0]["message"]["content"].strip()

async def ai_respond(text:str, context:ContextTypes.DEFAULT_TYPE)->str:
    if is_crisis(text):
        return ("سلامتك أولاً. لو لديك خطر فوري فاتصل بطوارئ بلدك فورًا. "
                "جرّب تنفس 4-7-8 عشر مرات وحدّد موعدًا عاجلاً مع مختص.")
    hist=context.user_data.get("ai_hist", [])[-20:]
    dsm_mode=context.user_data.get("ai_mode")=="dsm"
    reply=await asyncio.to_thread(ai_call, text, hist, dsm_mode)
    hist+=[{"role":"user","content":text},{"role":"assistant","content":reply}]
    context.user_data["ai_hist"]=hist[-20:]
    return reply

# ===== لوحات الأزرار =====
TOP_KB = ReplyKeyboardMarkup(
    [
        ["عربي سايكو 🧠"],
        ["العلاج السلوكي المعرفي (CBT) 💊", "الاختبارات النفسية 📝"],
        ["اختبارات الشخصية 🔍", "التحويل الطبي 🩺"],
        ["القائمة ◀️"]
    ], resize_keyboard=True
)

CBT_KB = ReplyKeyboardMarkup(
    [
        ["ما هو CBT؟ (مبسّط)", "أخطاء التفكير الشائعة"],
        ["سجلّ الأفكار (تمرين)", "التعرّض التدريجي (قلق/هلع)"],
        ["التنشيط السلوكي (تحسين المزاج)", "الاسترخاء والتنفس"],
        ["اليقظة الذهنية", "حل المشكلات"],
        ["بروتوكول النوم (مختصر)", "دفتر الامتنان",],
        ["خطة 3×3 لليوم", "◀️ رجوع"]
    ], resize_keyboard=True
)

TESTS_KB = ReplyKeyboardMarkup(
    [
        ["PHQ-9 اكتئاب", "GAD-7 قلق"],
        ["Mini-SPIN رهاب اجتماعي", "PC-PTSD-5 صدمة"],
        ["فحص نوبات الهلع", "ISI-7 أرق"],
        ["PSS-10 ضغوط", "WHO-5 رفاه"],
        ["K10 ضيق نفسي", "◀️ رجوع"]
    ], resize_keyboard=True
)

PERSONALITY_KB = ReplyKeyboardMarkup(
    [
        ["TIPI الخمسة الكبار (10 بنود)"],
        ["SAPAS اضطراب شخصية (غربلة)"],
        ["MSI-BPD حدّية (غربلة)"],
        ["◀️ رجوع"]
    ], resize_keyboard=True
)

AI_CHAT_KB = ReplyKeyboardMarkup([["◀️ إنهاء جلسة عربي سايكو"]], resize_keyboard=True)

# ===== حالات المحادثة =====
MENU, CBT_MENU, TESTS_MENU, PERS_MENU, AI_CHAT = range(5)
TH_SITU, TH_EMO, TH_AUTO, TH_FOR, TH_AGAINST, TH_ALT, TH_RERATE = range(10,17)
EXPO_WAIT, EXPO_FLOW = range(20,22)
PANIC_Q, PTSD_Q, SURVEY = range(30,33)

# ===== نصوص CBT =====
CBT_TXT = {
  "about": "🔹 ما هو CBT؟ يربط بين الفكر↔الشعور↔السلوك… (مختصر عملي).",
  "dist": "🧠 أخطاء التفكير: تعميم/تهويل/قراءة أفكار/تنبؤ سلبي/أبيض-أسود/«لازم». اسأل: ما الدليل؟ البدائل؟",
  "relax":"🌬️ تنفّس 4-7-8 ×4. شد/إرخاء العضلات 5 ثوانٍ ثم 10 من القدم للرأس.",
  "mind":"🧘 تمرين 5-4-3-2-1 للعودة للحاضر بلا حكم.",
  "prob":"🧩 حل المشكلات: عرّف بدقة → بدائل بلا حكم → مزايا/عيوب → متى/أين/كيف → جرّب → قيّم.",
  "sleep":"🛌 ثبّت الاستيقاظ، أوقف الشاشات قبل ساعة، لا تبقَ بالسرير يقظًا >20 دقيقة.",
  "grat":"🙏 دفتر الامتنان: كل مساء اكتب 3 أشياء ممتنًا لها + سبب قصير لكل واحدة (لمدة 2 أسبوع).",
  "plan33":"🗂️ خطة 3×3: 3 مهام صغيرة للعمل + 3 للحياة + 3 للصحة (كل مهمة ≤20د)."
}

# ===== تمارين CBT التفاعلية =====
@dataclass
class ThoughtRecord:
    situation:str=""; emotion:str=""; auto:str=""; ev_for:str=""; ev_against:str=""; alternative:str=""
    start:Optional[int]=None; end:Optional[int]=None

@dataclass
class ExposureState:
    suds:Optional[int]=None; plan:Optional[str]=None

# ===== محرك الاستبيانات =====
@dataclass
class Survey:
    id:str; title:str; items:List[str]; scale:str; min_v:int; max_v:int; reverse:List[int]=field(default_factory=list)
    ans:List[int]=field(default_factory=list)

def survey_prompt(s:Survey, i:int)->str:
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
 "توتر شديد/أفكار غريبة تحت الضغط؟ (نعم/لا)","اختبارات/تجنّب للآخرين خوف الهجر؟ (نعم/لا)"
]

ISI7 = Survey("isi7","ISI-7 — الأرق",
 ["صعوبة بدء النوم","صعوبة الاستمرار بالنوم","الاستيقاظ المبكر","الرضا عن النوم",
  "تأثير الأرق على الأداء بالنهار","ملاحظة الآخرين للمشكلة","القلق من نومك"],
 "0=لا،1=خفيف،2=متوسط،3=شديد،4=شديد جدًا",0,4)

PSS10 = Survey("pss10","PSS-10 — الضغوط المُدركة",
 ["خرجت الأمور عن السيطرة؟","انزعجت من أمر غير متوقع؟","شعرت بالتوتر؟",
  "تتحكم بالأمور؟ (عكسي)","واثق بالتعامل مع مشكلاتك؟ (عكسي)","الأمور تسير كما ترغب؟ (عكسي)",
  "لم تستطع التأقلم مع كل ما عليك؟","سيطرت على الانفعالات؟ (عكسي)","المشكلات تتراكم؟","وجدت وقتًا للأشياء المهمة؟ (عكسي)"],
 "0=أبدًا،1=نادرًا،2=أحيانًا،3=كثيرًا،4=دائمًا",0,4,reverse=[3,4,5,7,9])

WHO5 = Survey("who5","WHO-5 — الرفاه",
 ["مزاج مبتهج","هدوء وسكينة","نشاط وحيوية","أستيقظ مرتاحًا","يومي مليء بما يهمّني"],
 "0=لم يحصل…5=طوال الوقت",0,5)

K10 = Survey("k10","K10 — الضيق النفسي",
 ["تعب بلا سبب؟","عصبي/متوتر؟","ميؤوس؟","قلق شديد؟","كل شيء جهد؟",
  "لا تستطيع الهدوء؟","حزين بشدة؟","لا شيء يفرحك؟","لا تحتمل التأخير؟","شعور بلا قيمة؟"],
 "1=أبدًا…5=دائمًا",1,5)

# ===== مفاتيح لوحات التحويل الطبي =====
def referral_keyboard():
    rows=[]
    if CONTACT_THERAPIST_URL:
        rows.append([InlineKeyboardButton("تحويل إلى أخصائي نفسي", url=CONTACT_THERAPIST_URL)])
    if CONTACT_PSYCHIATRIST_URL:
        rows.append([InlineKeyboardButton("تحويل إلى طبيب نفسي", url=CONTACT_PSYCHIATRIST_URL)])
    if not rows: rows.append([InlineKeyboardButton("أرسل رقم/رابط التواصل الخاص بك", url="https://t.me/")])
    return InlineKeyboardMarkup(rows)

# ===== أوامر عامة =====
async def cmd_start(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message(
        "مرحبًا! أنا **عربي سايكو**.\nاختر من الأزرار أو اكتب مشكلتك لبدء جلسة.",
        reply_markup=TOP_KB
    ); return MENU

async def cmd_help(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "الأوامر: /start /help /version /ai_diag\n"
        "القوائم: عربي سايكو / CBT / الاختبارات / اختبارات الشخصية / التحويل الطبي",
        reply_markup=TOP_KB
    )

async def cmd_version(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"عربي سايكو — نسخة {VERSION}", reply_markup=TOP_KB)

async def cmd_ai_diag(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"AI_BASE_URL set={bool(AI_BASE_URL)} | KEY set={bool(AI_API_KEY)} | MODEL={AI_MODEL}"
    )

# ===== مستوى علوي =====
async def top_router(update:Update, context:ContextTypes.DEFAULT_TYPE):
    t=update.message.text or ""
    if t in ("القائمة ◀️","القائمة","رجوع","◀️"):
        await update.message.reply_text("القائمة:", reply_markup=TOP_KB); return MENU
    if has("عربي سايكو", t):
        kb=InlineKeyboardMarkup([
            [InlineKeyboardButton("ابدأ جلسة عربي سايكو 🤖", callback_data="start_ai")],
            [InlineKeyboardButton("تشخيص استرشادي DSM-5", callback_data="start_dsm")],
        ])
        await update.message.reply_text(
            "أنا مساعد نفسي مدعوم بالذكاء الاصطناعي (دعم/تعليم، ليس تشخيصًا).", reply_markup=kb
        ); return MENU
    if has("العلاج السلوكي", t):
        await update.message.reply_text("اختر وحدة CBT:", reply_markup=CBT_KB); return CBT_MENU
    if has("الاختبارات النفسية", t):
        await update.message.reply_text("اختر اختبارًا:", reply_markup=TESTS_KB); return TESTS_MENU
    if has("اختبارات الشخصية", t):
        await update.message.reply_text("اختبارات الشخصية:", reply_markup=PERSONALITY_KB); return PERS_MENU
    if has("التحويل الطبي", t):
        await update.message.reply_text("اختر نوع التحويل:", reply_markup=referral_keyboard()); return MENU
    await update.message.reply_text("اختر من الأزرار أو اكتب /start.", reply_markup=TOP_KB); return MENU

# ===== بدء جلسة AI =====
async def ai_start_cb(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    context.user_data["ai_hist"]=[]; context.user_data["ai_mode"]="free"
    await q.message.chat.send_message("بدأت جلسة **عربي سايكو**. اكتب شكواك الآن.", reply_markup=AI_CHAT_KB)
    return AI_CHAT

async def dsm_start_cb(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    context.user_data["ai_hist"]=[]; context.user_data["ai_mode"]="dsm"
    await q.message.chat.send_message("وضع **DSM-5 الاسترشادي**. صف الأعراض بالمدة/الشدة/الأثر.", reply_markup=AI_CHAT_KB)
    return AI_CHAT

async def ai_chat_flow(update:Update, context:ContextTypes.DEFAULT_TYPE):
    text=(update.message.text or "").strip()
    if text in ("◀️ إنهاء جلسة عربي سايكو","خروج","/خروج"):
        await update.message.reply_text("انتهت الجلسة. رجعناك للقائمة.", reply_markup=TOP_KB); return MENU
    await update.effective_chat.send_action(ChatAction.TYPING)
    reply=await ai_respond(text, context)
    await update.message.reply_text(reply, reply_markup=AI_CHAT_KB); return AI_CHAT

# ===== CBT Router =====
async def cbt_router(update:Update, context:ContextTypes.DEFAULT_TYPE):
    t=update.message.text or ""
    if t=="◀️ رجوع": await update.message.reply_text("القائمة:", reply_markup=TOP_KB); return MENU
    if has("ما هو CBT", t): await send_long(update.effective_chat, CBT_TXT["about"], CBT_KB); return CBT_MENU
    if has("أخطاء التفكير", t): await send_long(update.effective_chat, CBT_TXT["dist"], CBT_KB); return CBT_MENU
    if has("الاسترخاء", t): await update.message.reply_text(CBT_TXT["relax"], reply_markup=CBT_KB); return CBT_MENU
    if has("اليقظة", t): await update.message.reply_text(CBT_TXT["mind"], reply_markup=CBT_KB); return CBT_MENU
    if has("حل المشكلات", t): await update.message.reply_text(CBT_TXT["prob"], reply_markup=CBT_KB); return CBT_MENU
    if has("بروتوكول النوم", t): await update.message.reply_text(CBT_TXT["sleep"], reply_markup=CBT_KB); return CBT_MENU
    if has("دفتر الامتنان", t): await update.message.reply_text(CBT_TXT["grat"], reply_markup=CBT_KB); return CBT_MENU
    if has("خطة 3×3", t): await update.message.reply_text(CBT_TXT["plan33"], reply_markup=CBT_KB); return CBT_MENU

    if has("التنشيط السلوكي", t):
        context.user_data["ba_wait"]=True
        await update.message.reply_text("أرسل 3 أنشطة صغيرة اليوم (10–20د) مفصولة بفواصل/أسطر.", reply_markup=ReplyKeyboardRemove())
        return CBT_MENU

    if has("سجلّ الأفكار", t):
        context.user_data["tr"]=ThoughtRecord()
        await update.message.reply_text("📝 اكتب **الموقف** باختصار (متى/أين/مع من؟).", reply_markup=ReplyKeyboardRemove())
        return TH_SITU

    if has("التعرّض التدريجي", t):
        context.user_data["expo"]=ExposureState()
        await update.message.reply_text("أرسل درجة قلقك الحالية 0–10.", reply_markup=ReplyKeyboardRemove())
        return EXPO_WAIT

    await update.message.reply_text("اختر وحدة من القائمة:", reply_markup=CBT_KB); return CBT_MENU

async def cbt_free_text(update:Update, context:ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("ba_wait"):
        context.user_data["ba_wait"]=False
        parts=[s.strip() for s in re.split(r"[,\n،]+", update.message.text or "") if s.strip()]
        plan="خطة اليوم:\n• "+"\n• ".join(parts[:3] or ["نشاط بسيط 10–20 دقيقة الآن."])
        await update.message.reply_text(plan+"\nقيّم مزاجك قبل/بعد 0–10.")
        await update.message.reply_text("رجوع لقائمة CBT:", reply_markup=CBT_KB)
    return CBT_MENU

# ===== سجل الأفكار =====
async def tr_situ(update:Update, context:ContextTypes.DEFAULT_TYPE):
    tr:ThoughtRecord=context.user_data["tr"]; tr.situation=update.message.text.strip()
    await update.message.reply_text("ما الشعور الآن؟ اكتب الاسم وقيمته (مثال: قلق 7/10)."); return TH_EMO
async def tr_emo(update:Update, context:ContextTypes.DEFAULT_TYPE):
    tr:ThoughtRecord=context.user_data["tr"]; tr.emotion=update.message.text.strip()
    m=re.search(r"(\d+)", normalize_num(tr.emotion)); tr.start=int(m.group(1)) if m else None
    await update.message.reply_text("ما **الفكرة التلقائية**؟"); return TH_AUTO
async def tr_auto(update:Update, context:ContextTypes.DEFAULT_TYPE):
    tr:ThoughtRecord=context.user_data["tr"]; tr.auto=update.message.text.strip()
    await update.message.reply_text("اكتب **أدلة تؤيد** الفكرة."); return TH_FOR
async def tr_for(update:Update, context:ContextTypes.DEFAULT_TYPE):
    tr:ThoughtRecord=context.user_data["tr"]; tr.ev_for=update.message.text.strip()
    await update.message.reply_text("اكتب **أدلة تنفي** الفكرة."); return TH_AGAINST
async def tr_against(update:Update, context:ContextTypes.DEFAULT_TYPE):
    tr:ThoughtRecord=context.user_data["tr"]; tr.ev_against=update.message.text.strip()
    await update.message.reply_text("اكتب **فكرة بديلة متوازنة**."); return TH_ALT
async def tr_alt(update:Update, context:ContextTypes.DEFAULT_TYPE):
    tr:ThoughtRecord=context.user_data["tr"]; tr.alternative=update.message.text.strip()
    await update.message.reply_text("أعد تقييم الشعور 0–10."); return TH_RERATE
async def tr_rerate(update:Update, context:ContextTypes.DEFAULT_TYPE):
    tr:ThoughtRecord=context.user_data["tr"]; tr.end=to_int(update.message.text)
    txt=(f"✅ ملخص سجلّ الأفكار\n• الموقف: {tr.situation}\n• الشعور قبل: {tr.emotion}\n• الفكرة: {tr.auto}\n"
         f"• أدلة تؤيد: {tr.ev_for}\n• أدلة تنفي: {tr.ev_against}\n• البديل: {tr.alternative}\n"
         f"• التقييم بعد: {tr.end if tr.end is not None else '—'}\nاستمر بالتدريب يوميًا.")
    await send_long(update.effective_chat, txt); await update.message.reply_text("اختر من قائمة CBT:", reply_markup=CBT_KB); return CBT_MENU

# ===== التعرض =====
async def expo_wait(update:Update, context:ContextTypes.DEFAULT_TYPE):
    n=to_int(update.message.text or "")
    if n is None or not (0<=n<=10):
        await update.message.reply_text("أرسل رقمًا من 0 إلى 10."); return EXPO_WAIT
    st:ExposureState=context.user_data["expo"]; st.suds=n
    kb=InlineKeyboardMarkup([
        [InlineKeyboardButton("أمثلة 3–4/10", callback_data="expo_suggest")],
        [InlineKeyboardButton("شرح سريع", callback_data="expo_help")]
    ])
    await update.message.reply_text(f"درجتك = {n}/10. اكتب موقفًا 3–4/10 أو استخدم الأزرار.", reply_markup=kb)
    return EXPO_FLOW

async def expo_cb(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if q.data=="expo_suggest":
        await q.edit_message_text("أمثلة: مصعد لطابقين، انتظار صف قصير، الجلوس بمقهى 10 دقائق قرب المخرج.\nاكتب موقفك.")
    else:
        await q.edit_message_text("القاعدة: تعرّض آمن + منع الطمأنة + البقاء حتى يهبط القلق للنصف ثم كرّر.")
    return EXPO_FLOW

async def expo_flow(update:Update, context:ContextTypes.DEFAULT_TYPE):
    st:ExposureState=context.user_data["expo"]; st.plan=(update.message.text or "").strip()
    kb=InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ ابدأ الآن", callback_data="expo_start")],
        [InlineKeyboardButton("تم — قيّم الدرجة", callback_data="expo_rate")]
    ])
    await update.message.reply_text(f"خطة التعرض:\n• {st.plan}\nابدأ والبقاء حتى يهبط القلق ≥ النصف.", reply_markup=kb)
    return EXPO_FLOW

async def expo_actions(update:Update, context:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if q.data=="expo_start": await q.edit_message_text("بالتوفيق! عند الانتهاء أرسل الدرجة الجديدة 0–10."); return EXPO_WAIT
    if q.data=="expo_rate":  await q.edit_message_text("أرسل الدرجة الجديدة 0–10."); return EXPO_WAIT
    return EXPO_FLOW

# ===== حالات ثنائية نعم/لا =====
@dataclass
class BinState: i:int=0; yes:int=0; qs:List[str]=field(default_factory=list)

# ===== Router الاختبارات =====
async def tests_router(update:Update, context:ContextTypes.DEFAULT_TYPE):
    t=update.message.text or ""
    if t=="◀️ رجوع": await update.message.reply_text("القائمة:", reply_markup=TOP_KB); return MENU

    key={
      "PHQ-9 اكتئاب":"phq9","GAD-7 قلق":"gad7","Mini-SPIN رهاب اجتماعي":"minispin",
      "PC-PTSD-5 صدمة":"pcptsd5","فحص نوبات الهلع":"panic",
      "TIPI الخمسة الكبار (10 بنود)":"tipi","SAPAS اضطراب شخصية (غربلة)":"sapas","MSI-BPD حدّية (غربلة)":"msi",
      "ISI-7 أرق":"isi7","PSS-10 ضغوط":"pss10","WHO-5 رفاه":"who5","K10 ضيق نفسي":"k10"
    }.get(t)

    if key is None:
        await update.message.reply_text("اختر اختبارًا:", reply_markup=TESTS_KB); return TESTS_MENU

    if key=="panic":
        context.user_data["panic"]=BinState(i=0,yes=0,qs=[
            "خلال 4 أسابيع: هل حدثت لديك نوبات هلع مفاجئة؟ (نعم/لا)",
            "هل تخاف من حدوث نوبة أخرى أو تتجنب أماكن بسببها؟ (نعم/لا)"
        ])
        await update.message.reply_text(context.user_data["panic"].qs[0], reply_markup=ReplyKeyboardRemove()); return PANIC_Q

    if key=="pcptsd5":
        context.user_data["pc"]=BinState(i=0,yes=0,qs=PC_PTSD5)
        await update.message.reply_text(PC_PTSD5[0], reply_markup=ReplyKeyboardRemove()); return PTSD_Q

    if key in ("sapas","msi"):
        qs=SAPAS if key=="sapas" else MSI_BPD
        context.user_data["bin"]=BinState(i=0,yes=0,qs=qs)
        await update.message.reply_text(qs[0], reply_markup=ReplyKeyboardRemove()); return SURVEY

    s_map={"phq9":PHQ9,"gad7":GAD7,"minispin":MINISPIN,"tipi":TIPI,"isi7":ISI7,"pss10":PSS10,"who5":WHO5,"k10":K10}
    s0=s_map[key]; s=Survey(s0.id,s0.title,list(s0.items),s0.scale,s0.min_v,s0.max_v,list(s0.reverse))
    context.user_data["s"]=s; context.user_data["s_i"]=0
    await update.message.reply_text(f"بدء **{s.title}**.\n{survey_prompt(s,0)}", reply_markup=ReplyKeyboardRemove()); return SURVEY

# ثنائي: هلع / PTSD / SAPAS / MSI
async def panic_flow(update:Update, context:ContextTypes.DEFAULT_TYPE):
    st:BinState=context.user_data["panic"]; ans=(update.message.text or "").strip().lower()
    if ans not in ("نعم","لا","yes","no","y","n"):
        await update.message.reply_text("أجب بـ نعم/لا."); return PANIC_Q
    st.yes += 1 if ans in ("نعم","yes","y") else 0; st.i+=1
    if st.i < len(st.qs): await update.message.reply_text(st.qs[st.i]); return PANIC_Q
    msg="إيجابي — قد تكون هناك نوبات هلع" if st.yes==2 else "سلبي — لا مؤشر قوي حاليًا"
    await update.message.reply_text(f"**نتيجة فحص الهلع:** {msg}", reply_markup=TESTS_KB); return TESTS_MENU

async def ptsd_flow(update:Update, context:ContextTypes.DEFAULT_TYPE):
    st:BinState=context.user_data["pc"]; ans=(update.message.text or "").strip().lower()
    if ans not in ("نعم","لا","yes","no","y","n"):
        await update.message.reply_text("أجب بـ نعم/لا."); return PTSD_Q
    st.yes += 1 if ans in ("نعم","yes","y") else 0; st.i+=1
    if st.i < len(st.qs): await update.message.reply_text(st.qs[st.i]); return PTSD_Q
    result="إيجابي (≥3 «نعم») — يُوصى بالتقييم." if st.yes>=3 else "سلبي — أقل من حد الإشارة."
    await update.message.reply_text(f"**PC-PTSD-5:** {st.yes}/5 — {result}", reply_markup=TESTS_KB); return TESTS_MENU

async def survey_flow(update:Update, context:ContextTypes.DEFAULT_TYPE):
    # ثنائي SAPAS / MSI
    if "bin" in context.user_data:
        st:BinState=context.user_data["bin"]; ans=(update.message.text or "").strip().lower()
        if ans not in ("نعم","لا","yes","no","y","n"):
            await update.message.reply_text("أجب بـ نعم/لا."); return SURVEY
        st.yes += 1 if ans in ("نعم","yes","y") else 0; st.i+=1
        if st.i < len(st.qs): await update.message.reply_text(st.qs[st.i]); return SURVEY
        msg = (f"**SAPAS:** {st.yes}/8 — "+("إيجابي (≥3) يُستحسن التقييم." if len(st.qs)==8 and st.yes>=3 else "سلبي.")) \
              if len(st.qs)==8 else \
              (f"**MSI-BPD:** {st.yes}/10 — "+("إيجابي (≥7) يُستحسن التقييم." if st.yes>=7 else "سلبي."))
        await update.message.reply_text(msg, reply_markup=PERSONALITY_KB); context.user_data.pop("bin",None); return PERS_MENU

    # درجات
    s:Survey=context.user_data["s"]; i=context.user_data["s_i"]; n=to_int(update.message.text)
    if n is None or not (s.min_v<=n<=s.max_v):
        await update.message.reply_text(f"أدخل رقمًا بين {s.min_v} و{s.max_v}."); return SURVEY
    s.ans.append(n); i+=1
    if i >= len(s.items):
        if s.id=="gad7":
            total=sum(s.ans); lvl="طبيعي/خفيف جدًا" if total<=4 else "خفيف" if total<=9 else "متوسط" if total<=14 else "شديد"
            await update.message.reply_text(f"**GAD-7:** {total}/21 — قلق {lvl}", reply_markup=TESTS_KB); return TESTS_MENU
        if s.id=="phq9":
            total=sum(s.ans)
            lvl="لا/خفيف جدًا" if total<=4 else "خفيف" if total<=9 else "متوسط" if total<=14 else "متوسط-شديد" if total<=19 else "شديد"
            warn="\n⚠️ بند أفكار الإيذاء >0 — اطلب مساعدة فورية." if s.ans[8]>0 else ""
            await update.message.reply_text(f"**PHQ-9:** {total}/27 — {lvl}{warn}", reply_markup=TESTS_KB); return TESTS_MENU
        if s.id=="minispin":
            total=sum(s.ans); msg="مؤشر رهاب اجتماعي محتمل" if total>=6 else "أقل من حد الإشارة"
            await update.message.reply_text(f"**Mini-SPIN:** {total}/12 — {msg}", reply_markup=TESTS_KB); return TESTS_MENU
        if s.id=="tipi":
            vals=s.ans[:]
            for idx in s.reverse: vals[idx]=8-vals[idx]
            extr=(vals[0]+vals[5])/2; agre=(vals[1]+vals[6])/2; cons=(vals[2]+vals[7])/2; emot=(vals[3]+vals[8])/2; open_=(vals[4]+vals[9])/2
            lab=lambda x: "عالٍ" if x>=5.5 else "منخفض" if x<=2.5 else "متوسط"
            msg=(f"**TIPI (1–7):**\n• الانبساط: {extr:.1f} ({lab(extr)})\n• التوافق: {agre:.1f} ({lab(agre)})\n"
                 f"• الانضباط: {cons:.1f} ({lab(cons)})\n• الاستقرار الانفعالي: {emot:.1f} ({lab(emot)})\n"
                 f"• الانفتاح: {open_:.1f} ({lab(open_)})")
            await update.message.reply_text(msg, reply_markup=PERSONALITY_KB); return PERS_MENU
        if s.id=="isi7":
            total=sum(s.ans); lvl="ضئيل" if total<=7 else "خفيف" if total<=14 else "متوسط" if total<=21 else "شديد"
            await update.message.reply_text(f"**ISI-7:** {total}/28 — أرق {lvl}", reply_markup=TESTS_KB); return TESTS_MENU
        if s.id=="pss10":
            vals=s.ans[:]
            for idx in s.reverse: vals[idx]=s.max_v-vals[idx]
            total=sum(vals); lvl="منخفض" if total<=13 else "متوسط" if total<=26 else "عالٍ"
            await update.message.reply_text(f"**PSS-10:** {total}/40 — ضغط {lvl}", reply_markup=TESTS_KB); return TESTS_MENU
        if s.id=="who5":
            total=sum(s.ans)*4; note="منخفض (≤50) — حسّن الروتين وتواصل/قيّم." if total<=50 else "جيد."
            await update.message.reply_text(f"**WHO-5:** {total}/100 — {note}", reply_markup=TESTS_KB); return TESTS_MENU
        if s.id=="k10":
            total=sum(s.ans); lvl="خفيف" if total<=19 else "متوسط" if total<=24 else "شديد" if total<=29 else "شديد جدًا"
            await update.message.reply_text(f"**K10:** {total}/50 — ضيق {lvl}", reply_markup=TESTS_KB); return TESTS_MENU
        await update.message.reply_text("تم الحساب.", reply_markup=TESTS_KB); return TESTS_MENU

    context.user_data["s_i"]=i
    await update.message.reply_text(survey_prompt(s,i)); return SURVEY

# ===== قائمة اختبارات الشخصية (توجيه بسيط) =====
async def personality_router(update:Update, context:ContextTypes.DEFAULT_TYPE):
    t=update.message.text or ""
    if t=="◀️ رجوع": await update.message.reply_text("القائمة:", reply_markup=TOP_KB); return MENU
    # مجرد إعادة استخدام tests_router بنفس النص
    return await tests_router(update, context)

# ===== سقوط عام =====
async def fallback(update:Update, context:ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("اختر من الأزرار أو اكتب /start.", reply_markup=TOP_KB); return MENU

# ===== Main =====
def main():
    app=Application.builder().token(BOT_TOKEN).build()

    conv=ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            MENU:[MessageHandler(filters.TEXT & ~filters.COMMAND, top_router)],

            CBT_MENU:[
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
            PERS_MENU:[MessageHandler(filters.TEXT & ~filters.COMMAND, personality_router)],

            PANIC_Q:[MessageHandler(filters.TEXT & ~filters.COMMAND, panic_flow)],
            PTSD_Q:[MessageHandler(filters.TEXT & ~filters.COMMAND, ptsd_flow)],
            SURVEY:[MessageHandler(filters.TEXT & ~filters.COMMAND, survey_flow)],

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
        app.run_webhook(listen="0.0.0.0", port=PORT, url_path=f"{BOT_TOKEN}",
                        webhook_url=f"{(PUBLIC_URL or '').rstrip('/')}/{BOT_TOKEN}",
                        drop_pending_updates=True)
    else:
        app.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()
