# -*- coding: utf-8 -*-
import os
import json
import asyncio
import logging
from typing import Dict, Any, Optional

from flask import Flask, request, abort

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

import httpx

# ----------------------- إعدادات عامة -----------------------
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("app")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("ضع TELEGRAM_BOT_TOKEN في متغيرات البيئة (Render → Environment).")

RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
WEBHOOK_PATH = "/webhook/secret"
WEBHOOK_URL = f"{RENDER_URL}{WEBHOOK_PATH}" if RENDER_URL else None

AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1")
AI_API_KEY = os.getenv("AI_API_KEY")  # اختياري
AI_MODEL = os.getenv("AI_MODEL", "openrouter/auto")

CONTACT_THERAPIST_URL = os.getenv("CONTACT_THERAPIST_URL", "https://t.me/your_therapist")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "https://t.me/your_psychiatrist")

# مفاتيح حالة المستخدم للاختبارات والـ DSM
STATE_KEY = "state"         # None | "phq9" | "gad7" | "await_dsm"
STATE_STEP = "step"         # رقم السؤال الحالي
STATE_SCORES = "scores"     # لائحة الدرجات


# ----------------------- أدوات مساعدة -----------------------
def main_menu_markup() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🧠 العلاج السلوكي المعرفي (CBT)", callback_data="menu:cbt"),
        ],
        [
            InlineKeyboardButton("🧪 اختبارات نفسية", callback_data="menu:tests"),
            InlineKeyboardButton("🧩 اضطرابات الشخصية", callback_data="menu:personality"),
        ],
        [
            InlineKeyboardButton("🤖 عربي سايكو | DSM-AI", callback_data="menu:dsm"),
        ],
        [
            InlineKeyboardButton("🧑‍⚕️ أخصائي نفسي", url=CONTACT_THERAPIST_URL),
            InlineKeyboardButton("👨‍⚕️ طبيب نفسي", url=CONTACT_PSYCHIATRIST_URL),
        ],
    ]
    return InlineKeyboardMarkup(rows)


def tests_menu_markup() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("PHQ-9 (الاكتئاب)", callback_data="tests:phq9")],
        [InlineKeyboardButton("GAD-7 (القلق)", callback_data="tests:gad7")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="nav:home")],
    ]
    return InlineKeyboardMarkup(rows)


def cbt_menu_text() -> str:
    return (
        "العلاج السلوكي المعرفي (CBT):\n"
        "• ABC: الموقف → الأفكار → المشاعر/السلوك.\n"
        "• تحدّي الأفكار: دَعّم/فَنّد الدليل، وصِغ بدائل متوازنة.\n"
        "• تفعيل سلوكي: خطوات صغيرة يومية ممتعة/مفيدة.\n"
        "• تمارين تنفّس 4-7-8 والاسترخاء العضلي.\n\n"
        "ابدأ بخطوة بسيطة اليوم ✨"
    )


def personality_text() -> str:
    return (
        "اضطرابات الشخصية (ملخص):\n"
        "• عنقودية A: بارانويد/انفصامي/انفصامِي شكلي.\n"
        "• عنقودية B: حدّي/نرجسي/هيستيري/معادي للمجتمع.\n"
        "• عنقودية C: تجنّبي/اعتمادي/وسواسي قهري (شخصية).\n"
        "التشخيص النهائي سريري بواسطة مختص؛ هذه معلومات تثقيفية فقط."
    )


PHQ9_QUESTIONS = [
    "قلة الاهتمام أو المتعة بالقيام بالأشياء.",
    "الشعور بالاكتئاب أو الإحباط أو اليأس.",
    "صعوبة في النوم أو النوم الزائد.",
    "الإرهاق أو قلة الطاقة.",
    "ضعف الشهية أو الإفراط في الأكل.",
    "الشعور بسوء تجاه نفسك أو أنك فاشل.",
    "صعوبة التركيز على الأشياء.",
    "الحركة أو الكلام ببطء شديد أو توتر زائد ملحوظ.",
    "أفكار بأنك ستكون أفضل حالاً لو متّ أو إيذاء النفس.",
]

GAD7_QUESTIONS = [
    "الشعور بالعصبية أو القلق أو على الحافة.",
    "عدم القدرة على إيقاف القلق أو السيطرة عليه.",
    "القلق المفرط حول أشياء مختلفة.",
    "صعوبة في الاسترخاء.",
    "عدم القدرة على الهدوء بسبب التململ.",
    "سهولة الانزعاج أو الضيق.",
    "الخوف من حدوث شيء فظيع.",
]

SCALE_NOTE = "أجب لكل بند برقم: 0=أبداً، 1=عدة أيام، 2=أكثر من النصف، 3=تقريبًا يوميًا."


def score_interpretation_phq9(score: int) -> str:
    if score <= 4: lvl = "حد أدنى"
    elif score <= 9: lvl = "خفيف"
    elif score <= 14: lvl = "متوسط"
    elif score <= 19: lvl = "شديد نوعًا ما"
    else: lvl = "شديد"
    return f"الدرجة الكلية PHQ-9 = {score} → شدة الاكتئاب: {lvl}."


def score_interpretation_gad7(score: int) -> str:
    if score <= 4: lvl = "حد أدنى"
    elif score <= 9: lvl = "خفيف"
    elif score <= 14: lvl = "متوسط"
    else: lvl = "شديد"
    return f"الدرجة الكلية GAD-7 = {score} → شدة القلق: {lvl}."


async def send_typing(ctx: ContextTypes.DEFAULT_TYPE, chat_id: int):
    await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)


# ----------------------- Handlers أساسية -----------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إظهار القائمة الرئيسية."""
    chat_id = update.effective_chat.id
    await send_typing(context, chat_id)
    context.user_data.clear()
    await update.effective_message.reply_text(
        "مرحبًا! أنا عربي سايكو 🤝\nاختر من القائمة:",
        reply_markup=main_menu_markup(),
    )


async def on_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("pong ✅")


# ----------------------- أزرار القائمة -----------------------
async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data or ""

    # رجوع للقائمة
    if data == "nav:home":
        await query.edit_message_text("القائمة الرئيسية:", reply_markup=main_menu_markup())
        return

    # CBT
    if data == "menu:cbt":
        await query.edit_message_text(cbt_menu_text(), reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ رجوع", callback_data="nav:home")]]
        ))
        return

    # اضطرابات الشخصية
    if data == "menu:personality":
        await query.edit_message_text(personality_text(), reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("⬅️ رجوع", callback_data="nav:home")]]
        ))
        return

    # اختبارات
    if data == "menu:tests":
        await query.edit_message_text("اختر اختبارًا:", reply_markup=tests_menu_markup())
        return

    if data == "tests:phq9":
        context.user_data[STATE_KEY] = "phq9"
        context.user_data[STATE_STEP] = 0
        context.user_data[STATE_SCORES] = []
        await query.edit_message_text(
            f"بدء PHQ-9:\n{SCALE_NOTE}\n\nالسؤال 1/9:\n{PHQ9_QUESTIONS[0]}"
        )
        return

    if data == "tests:gad7":
        context.user_data[STATE_KEY] = "gad7"
        context.user_data[STATE_STEP] = 0
        context.user_data[STATE_SCORES] = []
        await query.edit_message_text(
            f"بدء GAD-7:\n{SCALE_NOTE}\n\nالسؤال 1/7:\n{GAD7_QUESTIONS[0]}"
        )
        return

    # عربي سايكو DSM-AI
    if data == "menu:dsm":
        context.user_data[STATE_KEY] = "await_dsm"
        context.user_data.pop(STATE_STEP, None)
        context.user_data.pop(STATE_SCORES, None)
        await query.edit_message_text(
            "أرسل وصفًا موجزًا لأعراضك (المدة/الشدة/التأثير اليومي). "
            "سأعطيك تلخيصًا استرشاديًا وفق DSM-5-TR (ليس تشخيصًا نهائيًا)."
        )
        return


# ----------------------- منطق الرسائل (اختبارات/DSM) -----------------------
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    text = (msg.text or "").strip()

    # بلا حالة → رد افتراضي
    state = context.user_data.get(STATE_KEY)

    # ---- اختبار PHQ-9 ----
    if state == "phq9":
        try:
            score = int(text)
            if score < 0 or score > 3:
                raise ValueError
        except ValueError:
            await msg.reply_text("أدخل رقمًا من 0 إلى 3 لكل سؤال. حاول مجددًا.")
            return

        step = context.user_data.get(STATE_STEP, 0)
        scores = context.user_data.get(STATE_SCORES, [])
        scores.append(score)
        step += 1
        context.user_data[STATE_STEP] = step
        context.user_data[STATE_SCORES] = scores

        if step < len(PHQ9_QUESTIONS):
            await msg.reply_text(
                f"السؤال {step+1}/{len(PHQ9_QUESTIONS)}:\n{PHQ9_QUESTIONS[step]}"
            )
        else:
            total = sum(scores)
            context.user_data.clear()
            await msg.reply_text(
                score_interpretation_phq9(total)
                + "\n\nهذه أداة فحص وليست تشخيصًا نهائيًا. إذا كانت الدرجة متوسطة أو أعلى، "
                  "فكر باستشارة مختص.",
                reply_markup=main_menu_markup(),
            )
        return

    # ---- اختبار GAD-7 ----
    if state == "gad7":
        try:
            score = int(text)
            if score < 0 or score > 3:
                raise ValueError
        except ValueError:
            await msg.reply_text("أدخل رقمًا من 0 إلى 3 لكل سؤال. حاول مجددًا.")
            return

        step = context.user_data.get(STATE_STEP, 0)
        scores = context.user_data.get(STATE_SCORES, [])
        scores.append(score)
        step += 1
        context.user_data[STATE_STEP] = step
        context.user_data[STATE_SCORES] = scores

        if step < len(GAD7_QUESTIONS):
            await msg.reply_text(
                f"السؤال {step+1}/{len(GAD7_QUESTIONS)}:\n{GAD7_QUESTIONS[step]}"
            )
        else:
            total = sum(scores)
            context.user_data.clear()
            await msg.reply_text(
                score_interpretation_gad7(total)
                + "\n\nهذه أداة فحص وليست تشخيصًا نهائيًا. إذا كانت الدرجة متوسطة أو أعلى، "
                  "فكر باستشارة مختص.",
                reply_markup=main_menu_markup(),
            )
        return

    # ---- عربي سايكو DSM-AI ----
    if state == "await_dsm":
        # لو ما فيه مفتاح API نرد برد بديل
        if not AI_API_KEY:
            await msg.reply_text(
                "وصف ممتاز! (ميزة التحليل الذكي غير مفعلة لعدم وجود AI_API_KEY)\n"
                "خلاصة استرشادية: راقب نمط الأعراض ومدتها وتأثيرها على الوظائف اليومية. "
                "للتشخيص السريري النهائي يلزم مقابلة مختص.",
                reply_markup=main_menu_markup(),
            )
            context.user_data.clear()
            return

        await send_typing(context, msg.chat_id)
        prompt = (
            "أنت مساعد مختص نفسي يطبّق DSM-5-TR بشكل استرشادي (ليس تشخيصًا طبيًا). "
            "لخّص الأعراض، واقترح احتمالات تشخيصية DSM مع درجة ثقة منخفضة/متوسطة/عالية، "
            "واذكر معايير يجب التحقق منها، ومتى ينصح بالإحالة لطبيب نفسي.\n\n"
            f"وصف المستخدم:\n{text}"
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    f"{AI_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {AI_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": AI_MODEL,
                        "messages": [
                            {"role": "system", "content": "أجب بالعربية الفصحى المبسطة."},
                            {"role": "user", "content": prompt},
                        ],
                    },
                )
                r.raise_for_status()
                data = r.json()
                # OpenRouter/OpenAI متوافق: choices[0].message.content
                content = (
                    data.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "تعذر الحصول على رد.")
                )
        except Exception as e:
            LOG.exception("AI error: %s", e)
            content = (
                "تعذر تشغيل التحليل الذكي حاليًا. حاول لاحقًا.\n"
                "تذكير: هذه الخدمة تثقيفية وليست بديلاً للتشخيص السريري."
            )

        context.user_data.clear()
        await msg.reply_text(content, reply_markup=main_menu_markup())
        return

    # ---- بدون حالة: رد افتراضي أو /start ----
    if text.lower() == "ping":
        await msg.reply_text("pong ✅")
        return

    await msg.reply_text(
        "استلمت رسالتك ✅\nاكتب /start لإظهار القائمة.",
        reply_markup=main_menu_markup(),
    )


# ----------------------- إنشاء التطبيق & الويبهوك -----------------------
app = Flask(__name__)

application = Application.builder().token(TELEGRAM_TOKEN).build()

# تسجيل الهاندلرز
application.add_handler(CommandHandler("start", cmd_start))
application.add_handler(CallbackQueryHandler(on_callback))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
application.add_handler(MessageHandler(filters.Regex(r"(?i)^ping$"), on_ping))


@app.get("/")
def health():
    return "OK", 200


@app.post(WEBHOOK_PATH)
def receive_update():
    if request.headers.get("content-type") == "application/json":
        update = Update.de_json(request.get_json(force=True), application.bot)
        try:
            # دفع التحديث لمعالجة Async داخل حلقة التطبيق
            asyncio.get_event_loop().create_task(application.process_update(update))
        except RuntimeError:
            # في حال إعادة تشغيل العامل: استخدم حلقة جديدة مؤقتًا
            loop = asyncio.new_event_loop()
            loop.create_task(application.process_update(update))
            loop.call_soon(loop.stop)
        return "OK", 200
    abort(403)


async def ensure_webhook():
    """تعيين الويبهوك عند الإقلاع إذا كان RENDER_EXTERNAL_URL موجود."""
    if WEBHOOK_URL:
        try:
            await application.bot.set_webhook(url=WEBHOOK_URL, allowed_updates=["message", "callback_query"])
            LOG.info("Webhook set: %s", WEBHOOK_URL)
        except Exception as e:
            LOG.exception("Failed to set webhook: %s", e)


def run_server():
    # تشغيل التطبيق التيليجرامي
    application.job_queue.scheduler  # يضمن تهيئة الـ loop
    # جدولة ضبط الويبهوك بعد الإقلاع
    application.create_task(ensure_webhook())
    # Flask سيُدار بواسطة gunicorn على Render
    return app


# نقطة الدخول لـ Render (gunicorn سيبحث عن: app:run_server())
server = run_server()
