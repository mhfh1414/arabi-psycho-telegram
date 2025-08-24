# -*- coding: utf-8 -*-
# app.py — ArabiPsycho Telegram bot on Render (Flask webhook + PTB v21, thread-safe)

import os
import json
import asyncio
import logging
import threading
from typing import Optional

import httpx
from flask import Flask, request, abort

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ---------------- Logging ----------------
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("arabi_psycho")

# ---------------- Env ----------------
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("متغير TELEGRAM_BOT_TOKEN غير موجود في الإعدادات (Render > Environment).")

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBHOOK_SECRET = "secret"  # رابط الويب هوك: /webhook/secret

AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
AI_API_KEY = os.getenv("AI_API_KEY")  # ضع مفتاح OpenRouter أو OpenAI هنا
AI_MODEL = os.getenv("AI_MODEL", "openrouter/auto")

CONTACT_THERAPIST_URL = os.getenv("CONTACT_THERAPIST_URL", "https://t.me/your_therapist")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "https://t.me/your_psychiatrist")

# ---------------- Flask & PTB ----------------
app = Flask(__name__)
tg_app: Application = Application.builder().token(TELEGRAM_TOKEN).build()

# نشغّل PTB في لوب/ثريد مستقل
_PTB_STARTED = False
_PTB_LOOP: Optional[asyncio.AbstractEventLoop] = None


def _ptb_thread_runner(loop: asyncio.AbstractEventLoop):
    asyncio.set_event_loop(loop)
    loop.run_until_complete(tg_app.initialize())
    loop.run_until_complete(tg_app.start())
    if RENDER_URL:
        loop.run_until_complete(
            tg_app.bot.set_webhook(
                url=f"{RENDER_URL}/webhook/{WEBHOOK_SECRET}",
                max_connections=40,
                allowed_updates=["message", "callback_query"],
            )
        )
        info = loop.run_until_complete(tg_app.bot.get_webhook_info())
        LOG.info("Webhook set: %s | pending: %s", info.url, info.pending_update_count)
    LOG.info("PTB background loop is running")
    loop.run_forever()


def ensure_ptb_started():
    global _PTB_STARTED, _PTB_LOOP
    if _PTB_STARTED:
        return
    _PTB_STARTED = True
    _PTB_LOOP = asyncio.new_event_loop()
    t = threading.Thread(target=_ptb_thread_runner, args=(_PTB_LOOP,), daemon=True)
    t.start()

# حالة المستخدم لوضع الذكاء الاصطناعي
AI_MODE_FLAG = "ai_dsm_mode"

# نصوص الأزرار (لتطابق الرسائل مع الكيبورد السفلي)
BTN_CBT = "🧠 العلاج السلوكي (CBT)"
BTN_TESTS = "🧪 اختبارات نفسية"
BTN_PD = "🧩 اضطرابات الشخصية"
BTN_AI = "🤖 تشخيص DSM (ذكاء اصطناعي)"
BTN_THERAPIST = "👩‍⚕️ الأخصائي النفسي"
BTN_PSYCHIATRIST = "👨‍⚕️ الطبيب النفسي"

# --------------- Keyboards ---------------
def main_menu_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(BTN_CBT, callback_data="cbt"),
         InlineKeyboardButton(BTN_TESTS, callback_data="tests")],
        [InlineKeyboardButton(BTN_PD, callback_data="personality"),
         InlineKeyboardButton(BTN_AI, callback_data="ai_dsm")],
        [InlineKeyboardButton(BTN_THERAPIST, url=CONTACT_THERAPIST_URL),
         InlineKeyboardButton(BTN_PSYCHIATRIST, url=CONTACT_PSYCHIATRIST_URL)],
    ])

def main_menu_reply() -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(BTN_CBT), KeyboardButton(BTN_TESTS)],
        [KeyboardButton(BTN_PD), KeyboardButton(BTN_AI)],
        [KeyboardButton(BTN_THERAPIST), KeyboardButton(BTN_PSYCHIATRIST)],
    ]
    return ReplyKeyboardMarkup(rows, resize_keyboard=True)

def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع للقائمة", callback_data="back_home")]])

def cbt_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 سجّل المزاج", callback_data="cbt_mood"),
         InlineKeyboardButton("💭 سجل الأفكار", callback_data="cbt_thought")],
        [InlineKeyboardButton("🚶‍♂️ تعرّض تدريجي", callback_data="cbt_exposure"),
         InlineKeyboardButton("🧰 أدوات سريعة", callback_data="cbt_tools")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")],
    ])

def tests_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("PHQ-9 (اكتئاب)", callback_data="test_phq9")],
        [InlineKeyboardButton("GAD-7 (قلق)", callback_data="test_gad7")],
        [InlineKeyboardButton("PCL-5 (صدمة)", callback_data="test_pcl5")],
        [InlineKeyboardButton("اضطرابات الشخصية (مختصر)", callback_data="test_pd")],
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

# --------------- AI helper ---------------
async def ai_dsm_reply(prompt: str) -> Optional[str]:
    if not AI_API_KEY:
        return None
    system = (
        "أنت مساعد طبّي نفسي افتراضي. لا تقدّم تشخيصاً نهائياً ولا علاجاً دوائياً. "
        "اعتمد DSM-5-TR كمراجع وصفية، اطرح أسئلة فرز مختصرة، ثم لخّص احتمالات أولية "
        "مع تنبيه واضح بضرورة التقييم السريري."
    )
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {AI_API_KEY}",
                    "Content-Type": "application/json",
                    # هذه تساعد بعض المزودين (مثل OpenRouter) على قبول الطلب
                    "HTTP-Referer": RENDER_URL or "https://arabi-psycho-telegram.onrender.com",
                    "X-Title": "ArabiPsycho",
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
        if resp.status_code >= 400:
            LOG.error("AI HTTP %s: %s", resp.status_code, resp.text[:500])
            return None
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        LOG.exception("AI error: %s", e)
        return None

# --------------- Handlers ---------------
async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_action(ChatAction.TYPING)
    await update.effective_message.reply_text("pong ✅")

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop(AI_MODE_FLAG, None)
    await update.effective_message.reply_text(
        "أنا شغّال ✅\nاختر خدمة من القائمة:",
        reply_markup=main_menu_reply(),   # ← كيبورد سفلي دائم
        parse_mode=ParseMode.HTML,
    )
    # ونرسل أيضاً نفس القائمة كرسالة بأزرار Inline (اختياري)
    await update.effective_message.reply_text("القائمة الرئيسية:", reply_markup=main_menu_inline())

async def cb_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()
    data = q.data

    if data == "back_home":
        context.user_data.pop(AI_MODE_FLAG, None)
        await q.edit_message_text("القائمة الرئيسية:", reply_markup=main_menu_inline())
        return

    if data == "cbt":
        msg = (
            "العلاج السلوكي المعرفي (CBT): اختر أداة لبدء خطوة عملية.\n"
            "يمكنك تسجيل المزاج، سجل الأفكار، أو التعرّض التدريجي."
        )
        await q.edit_message_text(msg, reply_markup=cbt_kb())
        return

    if data == "cbt_mood":
        txt = (
            "📝 **سجل المزاج (يومي)**\n"
            "- قيّم مزاجك من 0 إلى 10 الآن.\n"
            "- اذكر حدث اليوم ومن حولك.\n"
            "- الفكرة السائدة والسلوك.\n"
            "- ما التجربة القادمة لرفع نقطة واحدة؟"
        )
        await q.edit_message_text(txt, reply_markup=cbt_kb(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "cbt_thought":
        txt = (
            "💭 **سجل الأفكار**\n"
            "1) الموقف  2) الفكرة التلقائية  3) الدليل مع/ضد\n"
            "4) إعادة الصياغة المتوازنة  5) شدة الشعور قبل/بعد"
        )
        await q.edit_message_text(txt, reply_markup=cbt_kb(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "cbt_exposure":
        txt = (
            "🚶‍♂️ **التعرّض التدريجي**\n"
            "- اصنع سلّم 0–10 من الأسهل للأصعب.\n"
            "- ابدأ من 3–4 وكرر حتى ينخفض القلق 50% ثم تقدّم."
        )
        await q.edit_message_text(txt, reply_markup=cbt_kb(), parse_mode=ParseMode.MARKDOWN)
        return

    if data == "cbt_tools":
        txt = "🧰 أدوات سريعة:\n- تنفس 4-4-6\n- تفعيل الحواس 5-4-3-2-1\n- نشاط ممتع/مفيد 10 دقائق"
        await q.edit_message_text(txt, reply_markup=cbt_kb())
        return

    if data == "tests":
        await q.edit_message_text("اختر اختباراً:", reply_markup=tests_kb())
        return

    for tcode, tname in [
        ("test_phq9", "PHQ-9 (الاكتئاب)"),
        ("test_gad7", "GAD-7 (القلق)"),
        ("test_pcl5", "PCL-5 (الصدمة)"),
        ("test_pd", "مختصر اضطرابات الشخصية"),
    ]:
        if data == tcode:
            await q.edit_message_text(
                f"📋 {tname}\n"
                "سأرسل لك الأسئلة إذا كتبت: *ابدأ الاختبار*.\n"
                "النتائج للفحص الأولي وليست تشخيصاً نهائياً.",
                reply_markup=back_kb(),
                parse_mode=ParseMode.MARKDOWN,
            )
            return

    if data == "personality":
        await q.edit_message_text("اختر اضطراباً للاطلاع على ملخص توصيفي:", reply_markup=personality_kb())
        return

    pd_map = {
        "pd_bpd": "الحدّية: تقلب وجداني، اندفاعية، حساسية للهجر، علاقات متقلبة.",
        "pd_schizoid": "الانعزالية: انطواء وفتور عاطفي وقلة اهتمام بالعلاقات.",
        "pd_npd": "النرجسية: شعور بالعظمة، حاجة لإعجاب، تعاطف منخفض.",
        "pd_ocpd": "الوسواسية القهرية (شخصية): كمالية وتصلّب وانشغال بالقواعد.",
    }
    if data in pd_map:
        await q.edit_message_text(
            f"🧩 {pd_map[data]}\n\nللاستشارة المتخصصة:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(BTN_THERAPIST, url=CONTACT_THERAPIST_URL)],
                [InlineKeyboardButton(BTN_PSYCHIATRIST, url=CONTACT_PSYCHIATRIST_URL)],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")],
            ]),
        )
        return

    if data == "ai_dsm":
        context.user_data[AI_MODE_FLAG] = True
        await q.edit_message_text(
            "✅ دخلت وضع *تشخيص DSM (ذكاء اصطناعي)*.\n"
            "اكتب الأعراض بإيجاز وسأعطيك أسئلة فرز ثم ملخص احتمالات أولية.\n"
            "للخروج اضغط «رجوع».",
            reply_markup=back_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

# توجيه نصوص الكيبورد السفلي
async def route_main_menu_texts(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    if text == BTN_CBT:
        await update.effective_message.reply_text(
            "العلاج السلوكي المعرفي (CBT): اختر أداة:",
            reply_markup=cbt_kb(),
        )
        return True
    if text == BTN_TESTS:
        await update.effective_message.reply_text("اختر اختباراً:", reply_markup=tests_kb())
        return True
    if text == BTN_PD:
        await update.effective_message.reply_text("اختر اضطراباً للاطلاع على ملخص:", reply_markup=personality_kb())
        return True
    if text == BTN_AI:
        context.user_data[AI_MODE_FLAG] = True
        await update.effective_message.reply_text(
            "✅ دخلت وضع *تشخيص DSM (ذكاء اصطناعي)*.\n"
            "اكتب الأعراض بإيجاز…",
            reply_markup=back_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return True
    if text == BTN_THERAPIST or text == BTN_PSYCHIATRIST:
        await update.effective_message.reply_text(
            "للتواصل:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(BTN_THERAPIST, url=CONTACT_THERAPIST_URL)],
                [InlineKeyboardButton(BTN_PSYCHIATRIST, url=CONTACT_PSYCHIATRIST_URL)],
            ]),
        )
        return True
    return False

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.effective_message.text or "").strip()

    # لو ضغط زر من الكيبورد السفلي
    if await route_main_menu_texts(update, context, text):
        return

    # وضع الذكاء الاصطناعي
    if context.user_data.get(AI_MODE_FLAG):
        await update.effective_chat.send_action(ChatAction.TYPING)
        ai_text = await ai_dsm_reply(text)
        if ai_text:
            await update.effective_message.reply_text(
                ai_text + "\n\n⚠️ هذه نتيجة أولية ولا تُعد تشخيصاً. يُنصح بالتقييم السريري.",
                parse_mode=ParseMode.HTML,
            )
        else:
            await update.effective_message.reply_text(
                "تعذّر استخدام الذكاء الاصطناعي حالياً. أعد المحاولة لاحقاً أو تواصل مع مختص."
            )
        return

    if text == "ابدأ الاختبار":
        await update.effective_message.reply_text(
            "أرسل اسم الاختبار (PHQ-9 / GAD-7 / PCL-5) وسأعطيك الأسئلة خطوة بخطوة.",
            reply_markup=back_kb(),
        )
        return

    await update.effective_message.reply_text("استلمت ✅", reply_markup=main_menu_reply())

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        "الأوامر:\n/start — القائمة الرئيسية\n/ping — اختبار سريع\n/help — المساعدة"
    )

# --------------- Register handlers ---------------
def register_handlers() -> None:
    tg_app.add_handler(CommandHandler("start", cmd_start))
    tg_app.add_handler(CommandHandler("help", cmd_help))
    tg_app.add_handler(CommandHandler("ping", cmd_ping))
    tg_app.add_handler(CallbackQueryHandler(cb_router))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    LOG.info("Handlers registered")

register_handlers()

# --------------- Flask routes (webhook) ---------------
@app.get("/")
def root_alive():
    ensure_ptb_started()
    return "OK", 200

@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook() -> tuple[str, int]:
    ensure_ptb_started()
    try:
        data = request.get_json(force=True, silent=False)
    except Exception as e:
        LOG.exception("bad json: %s", e)
        abort(400)

    try:
        update = Update.de_json(data, tg_app.bot)
        asyncio.run_coroutine_threadsafe(tg_app.process_update(update), _PTB_LOOP)
        LOG.info("INCOMING update: %s", "callback_query" if update.callback_query else "message")
        return "OK", 200
    except Exception as e:
        LOG.exception("webhook error: %s", e)
        return "ERR", 200
