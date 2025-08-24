# -*- coding: utf-8 -*-
# app.py — ArabiPsycho (Flask webhook + python-telegram-bot v21 + OpenRouter AI)

import os, asyncio, logging, threading
from typing import Optional, List, Dict

import httpx
from flask import Flask, request, abort

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# ========== Logging ==========
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("arabi_psycho")

# ========== ENV ==========
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("متغير TELEGRAM_BOT_TOKEN مفقود (Render > Environment).")

PUBLIC_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBHOOK_SECRET = "secret"  # endpoint: /webhook/secret

AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
AI_API_KEY  = os.getenv("AI_API_KEY", "")
AI_MODEL    = os.getenv("AI_MODEL", "openrouter/auto")

CONTACT_THERAPIST_URL    = os.getenv("CONTACT_THERAPIST_URL", "https://t.me/your_therapist")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "https://t.me/your_psychiatrist")

# ========== Flask + PTB ==========
app = Flask(__name__)
tg_app: Application = Application.builder().token(BOT_TOKEN).build()

# سنشغّل PTB داخل لوب asyncio بخيط خلفي
tg_loop: Optional[asyncio.AbstractEventLoop] = None
def _ptb_thread():
    global tg_loop
    tg_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(tg_loop)

    async def _init():
        await tg_app.initialize()
        await tg_app.start()
        if PUBLIC_URL:
            try:
                url = f"{PUBLIC_URL}/webhook/{WEBHOOK_SECRET}"
                await tg_app.bot.set_webhook(url=url, allowed_updates=["message", "callback_query"])
                info = await tg_app.bot.get_webhook_info()
                LOG.info("Webhook set: %s | pending: %s", info.url, info.pending_update_count)
            except Exception as e:
                LOG.exception("set_webhook failed: %s", e)
        LOG.info("PTB initialized & started")

    tg_loop.run_until_complete(_init())
    tg_loop.run_forever()

threading.Thread(target=_ptb_thread, daemon=True).start()

# ========== Keyboards ==========
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧠 العلاج السلوكي (CBT)", callback_data="cbt"),
         InlineKeyboardButton("🧪 الاختبارات النفسية", callback_data="tests")],
        [InlineKeyboardButton("🧩 اضطرابات الشخصية", callback_data="personality"),
         InlineKeyboardButton("🤖 تشخيص DSM (ذكاء اصطناعي)", callback_data="ai_dsm")],
        [InlineKeyboardButton("👩‍⚕️ الأخصائي النفسي", url=CONTACT_THERAPIST_URL),
         InlineKeyboardButton("👨‍⚕️ الطبيب النفسي", url=CONTACT_PSYCHIATRIST_URL)],
    ])

def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع للقائمة", callback_data="back_home")]])

def cbt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 سجل المزاج", callback_data="cbt_mood"),
         InlineKeyboardButton("💭 سجل الأفكار", callback_data="cbt_thought")],
        [InlineKeyboardButton("🚶‍♂️ تعرّض تدريجي", callback_data="cbt_exposure"),
         InlineKeyboardButton("🧰 أدوات سريعة", callback_data="cbt_tools")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")],
    ])

def tests_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("PHQ-9 (اكتئاب)", callback_data="test_phq9")],
        [InlineKeyboardButton("GAD-7 (قلق)", callback_data="test_gad7")],
        [InlineKeyboardButton("PC-PTSD-5 (صدمة)", callback_data="test_pcptsd5")],
        [InlineKeyboardButton("فحص نوبات الهلع", callback_data="test_panic")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")],
    ])

def personality_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("حدّية", callback_data="pd_bpd"),
         InlineKeyboardButton("انعزالية", callback_data="pd_schizoid")],
        [InlineKeyboardButton("نرجسية", callback_data="pd_npd"),
         InlineKeyboardButton("وسواسية قهرية", callback_data="pd_ocpd")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")],
    ])

# ========== AI (DSM assist) ==========
AI_FLAG = "ai_mode"
async def ai_dsm_reply(prompt: str) -> Optional[str]:
    if not AI_API_KEY:
        return None
    system = (
        "أنت مساعد نفسي يعتمد DSM-5-TR. لا تقدّم تشخيصًا نهائيًا ولا أدوية. "
        "اطرح أسئلة فرز مختصرة ثم لخّص احتمالات تشخيصية أولية وتحذير بضرورة التقييم السريري."
    )
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {AI_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": PUBLIC_URL or "https://render.com",
                    "X-Title": "Arabi Psycho",
                },
                json={
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 800,
                },
            )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        LOG.exception("AI error: %s", e)
        return None

# ========== Tests state ==========
SURVEY = "survey"       # context.user_data[SURVEY] = {"id", "title", "items", "min", "max", "scale", "i", "ans":[]}
PANIC = "panic"         # context.user_data[PANIC] = {"i":0, "a":[]}
PTSD  = "ptsd"          # context.user_data[PTSD]  = {"i":0, "yes":0}

GAD7 = [
    "الشعور بالتوتر أو القلق أو العصبية",
    "عدم القدرة على التوقف عن القلق أو التحكم فيه",
    "القلق الزائد حيال أمور مختلفة",
    "صعوبة الاسترخاء",
    "التململ أو صعوبة البقاء هادئًا",
    "الانزعاج بسهولة أو العصبية",
    "الخوف من أن شيئًا فظيعًا قد يحدث"
]
PHQ9 = [
    "قلة الاهتمام أو المتعة بالقيام بأي شيء",
    "الشعور بالإحباط أو الاكتئاب أو اليأس",
    "صعوبة النوم أو النوم الزائد",
    "الشعور بالتعب أو قلة الطاقة",
    "ضعف الشهية أو الإفراط في الأكل",
    "الشعور بأنك سيّئ عن نفسك أو فاشل",
    "صعوبة التركيز على الأشياء",
    "الحركة/الكلام ببطء شديد أو توتر زائد",
    "أفكار بإيذاء النفس أو أن الموت قد يكون أفضل"
]
PCPTSD5 = [
    "آخر شهر: كوابيس/ذكريات مزعجة عن حدث صادم؟ (نعم/لا)",
    "تجنّبت التفكير بالحدث أو أماكن تُذكّرك به؟ (نعم/لا)",
    "كنتَ سريع الفزع/على أعصابك؟ (نعم/لا)",
    "شعرتَ بالخدر/الانفصال عن الناس/الأنشطة؟ (نعم/لا)",
    "شعرتَ بالذنب/اللوم بسبب الحدث؟ (نعم/لا)",
]

def start_scale_test(ctx: ContextTypes.DEFAULT_TYPE, tid: str):
    if tid == "gad7":
        ctx.user_data[SURVEY] = {"id": tid, "title": "GAD-7 — القلق",
                                 "items": GAD7, "min":0, "max":3,
                                 "scale":"0=أبدًا، 1=عدة أيام، 2=أكثر من نصف الأيام، 3=تقريبًا كل يوم",
                                 "i":0, "ans":[]}
    elif tid == "phq9":
        ctx.user_data[SURVEY] = {"id": tid, "title": "PHQ-9 — الاكتئاب",
                                 "items": PHQ9, "min":0, "max":3,
                                 "scale":"0=أبدًا، 1=عدة أيام، 2=أكثر من نصف الأيام، 3=تقريبًا كل يوم",
                                 "i":0, "ans":[]}

def summarize_scale(d: Dict) -> str:
    total = sum(d["ans"])
    if d["id"] == "gad7":
        level = "خفيف جدًا/طبيعي" if total <= 4 else "قلق خفيف" if total <= 9 else "قلق متوسط" if total <= 14 else "قلق شديد"
        msg = f"**نتيجة GAD-7:** {total}/21 — {level}."
        if total >= 10: msg += "\n💡 يُوصى بالتقييم المهني."
        return msg
    if d["id"] == "phq9":
        if total <= 4: level = "لا اكتئاب/خفيف جدًا"
        elif total <= 9: level = "اكتئاب خفيف"
        elif total <= 14: level = "اكتئاب متوسط"
        elif total <= 19: level = "متوسط-شديد"
        else: level = "شديد"
        msg = f"**نتيجة PHQ-9:** {total}/27 — {level}."
        if d["ans"][8] > 0:
            msg += "\n⚠️ بند الأفكار المؤذية > 0 — اطلب مساعدة فورية عند أي خطورة."
        return msg
    return "تم."

# ========== Commands ==========
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop(AI_FLAG, None)
    context.user_data.pop(SURVEY, None)
    context.user_data.pop(PANIC, None)
    context.user_data.pop(PTSD, None)
    await update.effective_message.reply_text(
        "أنا شغّال ✅ اختر خدمة:",
        reply_markup=main_menu_kb(),
        parse_mode=ParseMode.HTML,
    )

async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("القائمة:", reply_markup=main_menu_kb())

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("/start /menu /help")

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_action(ChatAction.TYPING)
    await update.effective_message.reply_text("pong ✅")

# ========== Callback router ==========
async def cb_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q: return
    await q.answer()
    d = q.data

    if d == "back_home":
        context.user_data.clear()
        await q.edit_message_text("القائمة الرئيسية:", reply_markup=main_menu_kb()); return

    if d == "cbt":
        msg = ("العلاج السلوكي المعرفي (CBT):\n"
               "اختر أداة لبدء خطوة عملية الآن.")
        await q.edit_message_text(msg, reply_markup=cbt_kb()); return
    if d == "cbt_mood":
        await q.edit_message_text("📝 قيّم مزاجك 0–10، واذكر الحدث والفكرة والسلوك، وما ستجرّبه لتحسين 1 نقطة.",
                                  reply_markup=cbt_kb()); return
    if d == "cbt_thought":
        await q.edit_message_text("💭 سجل الأفكار: الموقف → الفكرة التلقائية → الدليل مع/ضد → صياغة متوازنة → شدة قبل/بعد.",
                                  reply_markup=cbt_kb()); return
    if d == "cbt_exposure":
        await q.edit_message_text("🚶‍♂️ تعرّض تدريجي: سلّم 0–10، ابدأ 3–4 وكرّر حتى يهبط القلق 50% ثم اصعد درجة.",
                                  reply_markup=cbt_kb()); return
    if d == "cbt_tools":
        await q.edit_message_text("🧰 أدوات: تنفس 4-4-6 / تمارين 5-4-3-2-1 / نشاط ممتع 10 دقائق.",
                                  reply_markup=cbt_kb()); return

    if d == "tests":
        await q.edit_message_text("اختر اختباراً:", reply_markup=tests_kb()); return
    if d == "test_gad7":
        start_scale_test(context, "gad7")
        s = context.user_data[SURVEY]; i = s["i"]
        await q.edit_message_text(f"بدء {s['title']}\n({i+1}/{len(s['items'])}) {s['items'][i]}\n{s['scale']}",
                                  reply_markup=back_kb()); return
    if d == "test_phq9":
        start_scale_test(context, "phq9")
        s = context.user_data[SURVEY]; i = s["i"]
        await q.edit_message_text(f"بدء {s['title']}\n({i+1}/{len(s['items'])}) {s['items'][i]}\n{s['scale']}",
                                  reply_markup=back_kb()); return
    if d == "test_pcptsd5":
        context.user_data[PTSD] = {"i":0, "yes":0}
        await q.edit_message_text(PCPTSD5[0], reply_markup=back_kb()); return
    if d == "test_panic":
        context.user_data[PANIC] = {"i":0, "a":[]}
        await q.edit_message_text("آخر 4 أسابيع: هل حدثت نوبات هلع مفاجئة؟ (نعم/لا)", reply_markup=back_kb()); return

    if d == "personality":
        await q.edit_message_text("اختر اضطراباً للاطلاع على ملخص توصيفي:", reply_markup=personality_kb()); return
    pd_map = {
        "pd_bpd": "الحدّية: تقلب وجداني، اندفاعية، حساسية للهجر، علاقات متقلبة.",
        "pd_schizoid": "الانعزالية: انطواء، فتور عاطفي، قلة اهتمام بالعلاقات.",
        "pd_npd": "النرجسية: شعور بالعظمة، حاجة لإعجاب، حساسية للنقد، تعاطف منخفض.",
        "pd_ocpd": "الوسواسية القهرية للشخصية: كمالية وتصلّب وانشغال بالقواعد.",
    }
    if d in pd_map:
        await q.edit_message_text(
            f"🧩 {pd_map[d]}\n\nللاستشارة المتخصصة:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👩‍⚕️ الأخصائي النفسي", url=CONTACT_THERAPIST_URL)],
                [InlineKeyboardButton("👨‍⚕️ الطبيب النفسي", url=CONTACT_PSYCHIATRIST_URL)],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")],
            ])
        )
        return

    if d == "ai_dsm":
        context.user_data[AI_FLAG] = True
        await q.edit_message_text(
            "✅ وضع تشخيص DSM (ذكاء اصطناعي) مفعّل.\nاكتب أعراضك بإيجاز.\nللخروج: «رجوع».",
            reply_markup=back_kb(), parse_mode=ParseMode.MARKDOWN
        )
        return

# ========== Text router ==========
def _to_int(s: str) -> Optional[int]:
    trans = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    try: return int((s or "").strip().translate(trans))
    except: return None

def _yn(s: str) -> Optional[bool]:
    t = (s or "").strip().lower()
    if t in ("نعم","ايه","ايوه","yes","y"): return True
    if t in ("لا","no","n"): return False
    return None

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.effective_message.text or "").strip()

    # AI mode
    if context.user_data.get(AI_FLAG):
        await update.effective_chat.send_action(ChatAction.TYPING)
        ai_text = await ai_dsm_reply(text)
        if ai_text:
            await update.effective_message.reply_text(
                ai_text + "\n\n⚠️ هذه نتيجة أولية وليست تشخيصًا. يُنصح بالتقييم السريري.",
                parse_mode=ParseMode.HTML, reply_markup=back_kb()
            )
        else:
            await update.effective_message.reply_text(
                "تعذّر استخدام الذكاء الاصطناعي حاليًا.", reply_markup=back_kb()
            )
        return

    # Numeric surveys
    if SURVEY in context.user_data:
        s = context.user_data[SURVEY]
        n = _to_int(text)
        if n is None or not (s["min"] <= n <= s["max"]):
            await update.effective_message.reply_text(f"أدخل رقمًا بين {s['min']} و{s['max']}.", reply_markup=back_kb()); return
        s["ans"].append(n); s["i"] += 1
        if s["i"] >= len(s["items"]):
            msg = summarize_scale(s)
            context.user_data.pop(SURVEY, None)
            await update.effective_message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=tests_kb())
            return
        i = s["i"]
        await update.effective_message.reply_text(
            f"({i+1}/{len(s['items'])}) {s['items'][i]}\n{s['scale']}", reply_markup=back_kb()
        )
        return

    # Panic yes/no
    if PANIC in context.user_data:
        st = context.user_data[PANIC]
        ans = _yn(text)
        if ans is None:
            await update.effective_message.reply_text("أجب بـ نعم/لا.", reply_markup=back_kb()); return
        st["a"].append(ans); st["i"] += 1
        if st["i"] == 1:
            await update.effective_message.reply_text("هل تخاف من حدوث نوبة أخرى أو تتجنب أماكن لذلك؟ (نعم/لا)",
                                                      reply_markup=back_kb()); return
        a1, a2 = st["a"]
        context.user_data.pop(PANIC, None)
        result = "سلبي." if not (a1 and a2) else "إيجابي — مؤشر لهلع/قلق متوقع."
        await update.effective_message.reply_text(f"**نتيجة فحص الهلع:** {result}", parse_mode=ParseMode.MARKDOWN,
                                                  reply_markup=tests_kb()); return

    # PTSD yes/no
    if PTSD in context.user_data:
        st = context.user_data[PTSD]
        ans = _yn(text)
        if ans is None:
            await update.effective_message.reply_text("أجب بـ نعم/لا.", reply_markup=back_kb()); return
        if ans: st["yes"] += 1
        st["i"] += 1
        if st["i"] < len(PCPTSD5):
            await update.effective_message.reply_text(PCPTSD5[st["i"]], reply_markup=back_kb()); return
        yes = st["yes"]; context.user_data.pop(PTSD, None)
        res = "إيجابي (≥3 نعم) — يُوصى بالتقييم." if yes >= 3 else "سلبي — أقل من حد الإشارة."
        await update.effective_message.reply_text(f"**نتيجة PC-PTSD-5:** {yes}/5 — {res}",
                                                  parse_mode=ParseMode.MARKDOWN, reply_markup=tests_kb()); return

    # Default
    await update.effective_message.reply_text("استلمت ✅ اختر من القائمة:", reply_markup=main_menu_kb())

# ========== Register handlers ==========
def register_handlers():
    tg_app.add_handler(CommandHandler("start", cmd_start))
    tg_app.add_handler(CommandHandler("menu",  cmd_menu))
    tg_app.add_handler(CommandHandler("help",  cmd_help))
    tg_app.add_handler(CommandHandler("ping",  cmd_ping))
    tg_app.add_handler(CallbackQueryHandler(cb_router))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    LOG.info("Handlers registered")

register_handlers()

# ========== Flask routes ==========
@app.get("/")
def alive(): return "OK", 200

@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook() -> tuple[str, int]:
    # قبول header مثل: application/json; charset=utf-8
    ctype = (request.headers.get("content-type") or "").lower()
    if not ctype.startswith("application/json"):
        LOG.warning("Blocked content-type=%s", ctype); abort(403)
    try:
        data = request.get_json(force=True, silent=False)
        # لوق تشخيصي
        try:
            prev = data.get("message", {}).get("text") or data.get("callback_query", {}).get("data")
        except Exception:
            prev = None
        LOG.info("INCOMING update: %s", prev)

        update = Update.de_json(data, tg_app.bot)
        if tg_loop and tg_loop.is_running():
            asyncio.run_coroutine_threadsafe(tg_app.process_update(update), tg_loop)
            return "OK", 200
        else:
            LOG.error("PTB loop not running"); return "ERR", 503
    except Exception as e:
        LOG.exception("webhook error: %s", e)
        return "ERR", 200

# ===== Run on Render with gunicorn =====
# Start Command:
# gunicorn -w 1 -k gthread -b 0.0.0.0:$PORT app:app
