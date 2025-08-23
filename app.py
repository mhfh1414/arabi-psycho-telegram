# -*- coding: utf-8 -*-
# app.py — ArabiPsycho Telegram bot (Webhook عبر Flask + PTB في خيط خلفي)

import os
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
WEBHOOK_SECRET = "secret"  # endpoint سيكون /webhook/secret

AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
AI_API_KEY = os.getenv("AI_API_KEY")  # إن لم يتوفر سيعمل البوت بدون ذكاء اصطناعي
AI_MODEL = os.getenv("AI_MODEL", "openrouter/auto")

CONTACT_THERAPIST_URL = os.getenv("CONTACT_THERAPIST_URL", "https://t.me/your_therapist")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "https://t.me/your_psychiatrist")

# ---------------- Flask & PTB ----------------
app = Flask(__name__)
tg_app: Application = Application.builder().token(TELEGRAM_TOKEN).build()

# حالة المستخدم لوضع الذكاء الاصطناعي
AI_MODE_FLAG = "ai_dsm_mode"

# --------------- Keyboards ---------------
def main_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🧠 العلاج السلوكي (CBT)", callback_data="cbt"),
            InlineKeyboardButton("🧪 اختبارات نفسية", callback_data="tests"),
        ],
        [
            InlineKeyboardButton("🧩 اضطرابات الشخصية", callback_data="personality"),
            InlineKeyboardButton("🤖 تشخيص DSM (ذكاء اصطناعي)", callback_data="ai_dsm"),
        ],
        [
            InlineKeyboardButton("👩‍⚕️ الأخصائي النفسي", url=CONTACT_THERAPIST_URL),
            InlineKeyboardButton("👨‍⚕️ الطبيب النفسي", url=CONTACT_PSYCHIATRIST_URL),
        ],
    ]
    return InlineKeyboardMarkup(rows)

def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع للقائمة", callback_data="back_home")]])

def cbt_kb() -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("📝 سجّل المزاج", callback_data="cbt_mood"),
            InlineKeyboardButton("💭 سجل الأفكار", callback_data="cbt_thought"),
        ],
        [
            InlineKeyboardButton("🚶‍♂️ تعرّض تدريجي", callback_data="cbt_exposure"),
            InlineKeyboardButton("🧰 أدوات سريعة", callback_data="cbt_tools"),
        ],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")],
    ]
    return InlineKeyboardMarkup(rows)

def tests_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("PHQ-9 (اكتئاب)", callback_data="test_phq9")],
        [InlineKeyboardButton("GAD-7 (قلق)", callback_data="test_gad7")],
        [InlineKeyboardButton("PCL-5 (صدمة)", callback_data="test_pcl5")],
        [InlineKeyboardButton("اضطرابات الشخصية (مختصر)", callback_data="test_pd")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")],
    ]
    return InlineKeyboardMarkup(rows)

def personality_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("حدّية", callback_data="pd_bpd"),
         InlineKeyboardButton("انعزالية", callback_data="pd_schizoid")],
        [InlineKeyboardButton("نرجسية", callback_data="pd_npd"),
         InlineKeyboardButton("وسواسية قهرية", callback_data="pd_ocpd")],
        [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")],
    ]
    return InlineKeyboardMarkup(rows)

# --------------- AI helper ---------------
async def ai_dsm_reply(prompt: str) -> Optional[str]:
    """يرجع استجابة أولية وفق DSM-5-TR (ليست تشخيصاً نهائياً)."""
    if not AI_API_KEY:
        return None

    system = (
        "أنت مساعد طبّي نفسي افتراضي. لا تقدّم تشخيصاً نهائياً أو وصفة دوائية. "
        "اعتمد DSM-5-TR لتوليد أسئلة فرز قصيرة ثم احتمالات أولية مع تنبيه بضرورة التقييم السريري."
    )
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json"},
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
        resp.raise_for_status()
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
    text = "أنا شغّال ✅\nاختر خدمة من القائمة:"
    await update.effective_message.reply_text(text, reply_markup=main_menu_kb(), parse_mode=ParseMode.HTML)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("الأوامر:\n/start — القائمة الرئيسية\n/ping — اختبار سريع\n/help — المساعدة")

async def cb_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()
    data = q.data

    # رجوع
    if data == "back_home":
        context.user_data.pop(AI_MODE_FLAG, None)
        await q.edit_message_text("القائمة الرئيسية:", reply_markup=main_menu_kb())
        return

    # CBT
    if data == "cbt":
        msg = (
            "العلاج السلوكي المعرفي (CBT): اختر أداة عملية.\n"
            "سجل المزاج/الأفكار، التعرّض التدريجي، أو أدوات سريعة."
        )
        await q.edit_message_text(msg, reply_markup=cbt_kb()); return

    if data == "cbt_mood":
        txt = (
            "📝 **سجل المزاج (يومي)**\n"
            "- قيّم مزاجك 0–10\n- الحدث ومن حولك\n- الفكرة السائدة والسلوك\n- خطوة صغيرة للتحسّن"
        )
        await q.edit_message_text(txt, reply_markup=cbt_kb(), parse_mode=ParseMode.MARKDOWN); return

    if data == "cbt_thought":
        txt = "💭 **سجل الأفكار**\n1) الموقف\n2) الفكرة\n3) الدليل مع/ضد\n4) إعادة الصياغة\n5) الشدة قبل/بعد"
        await q.edit_message_text(txt, reply_markup=cbt_kb(), parse_mode=ParseMode.MARKDOWN); return

    if data == "cbt_exposure":
        txt = (
            "🚶‍♂️ **التعرّض التدريجي**\n"
            "- اصنع سلّماً من 0 إلى 10\n- ابدأ من 3–4 وكرّر حتى ينخفض القلق 50%\n- تقدّم درجة درجة"
        )
        await q.edit_message_text(txt, reply_markup=cbt_kb(), parse_mode=ParseMode.MARKDOWN); return

    if data == "cbt_tools":
        txt = "🧰 أدوات سريعة:\n- تنفّس 4-4-6\n- تفعيل الحواس 5-4-3-2-1\n- نشاط ممتع/مفيد 10 دقائق"
        await q.edit_message_text(txt, reply_markup=cbt_kb()); return

    # اختبارات
    if data == "tests":
        await q.edit_message_text("اختر اختباراً:", reply_markup=tests_kb()); return

    for tcode, tname in [
        ("test_phq9", "PHQ-9 (الاكتئاب)"),
        ("test_gad7", "GAD-7 (القلق)"),
        ("test_pcl5", "PCL-5 (الصدمة)"),
        ("test_pd", "مختصر اضطرابات الشخصية"),
    ]:
        if data == tcode:
            await q.edit_message_text(
                f"📋 {tname}\nاكتب: *ابدأ الاختبار* وسأرسل الأسئلة خطوة بخطوة.\nالنتيجة أولية وليست تشخيصاً.",
                reply_markup=back_kb(),
                parse_mode=ParseMode.MARKDOWN,
            )
            return

    # اضطرابات الشخصية
    if data == "personality":
        await q.edit_message_text("اختر اضطراباً للاطلاع على ملخص DSM-5-TR:", reply_markup=personality_kb()); return

    pd_map = {
        "pd_bpd": "الحدّية: تقلب وجداني، اندفاعية، حساسية للهجر، علاقات متقلبة.",
        "pd_schizoid": "الانعزالية: انطواء وفتور عاطفي وقلة اهتمام بالعلاقات.",
        "pd_npd": "النرجسية: شعور بالعظمة، حاجة لإعجاب، حساسية للنقد، تعاطف منخفض.",
        "pd_ocpd": "الوسواسية القهرية (شخصية): كمالية وتصلّب وانشغال بالقواعد.",
    }
    if data in pd_map:
        await q.edit_message_text(
            f"🧩 {pd_map[data]}\n\nللاستشارة اضغط الزر بالأسفل.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👩‍⚕️ الأخصائي النفسي", url=CONTACT_THERAPIST_URL)],
                [InlineKeyboardButton("👨‍⚕️ الطبيب النفسي", url=CONTACT_PSYCHIATRIST_URL)],
                [InlineKeyboardButton("⬅️ رجوع", callback_data="back_home")],
            ]),
        )
        return

    # وضع الذكاء الاصطناعي
    if data == "ai_dsm":
        context.user_data[AI_MODE_FLAG] = True
        await q.edit_message_text(
            "✅ دخلت وضع *تشخيص DSM (ذكاء اصطناعي)*.\nاكتب أعراضك بإيجاز.\nللخروج: «رجوع».",
            reply_markup=back_kb(),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.effective_message.text or "").strip()

    # إذا المستخدم فعّل وضع الذكاء الاصطناعي
    if context.user_data.get(AI_MODE_FLAG):
        await update.effective_chat.send_action(ChatAction.TYPING)
        ai_text = await ai_dsm_reply(text)
        if ai_text:
            suffix = "\n\n⚠️ نتيجة أولية وليست تشخيصاً. يُنصح بالتقييم السريري."
            await update.effective_message.reply_text(ai_text + suffix, parse_mode=ParseMode.HTML)
        else:
            await update.effective_message.reply_text("تعذر استخدام الذكاء الاصطناعي حالياً. حاول لاحقاً أو تواصل مع مختص.")
        return

    # نصوص عامة
    if text == "ابدأ الاختبار":
        await update.effective_message.reply_text("أرسل اسم الاختبار (مثلاً: PHQ-9 أو GAD-7).", reply_markup=back_kb())
        return

    # الرد الافتراضي مع القائمة
    await update.effective_message.reply_text("استلمت ✅", reply_markup=main_menu_kb())

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
    return "OK", 200

@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook() -> tuple[str, int]:
    if request.headers.get("content-type") != "application/json":
        abort(403)
    try:
        data = request.get_json(force=True, silent=False)
        update = Update.de_json(data, tg_app.bot)
        tg_app.update_queue.put_nowait(update)  # لا نستخدم asyncio هنا
        return "OK", 200
    except Exception as e:
        LOG.exception("webhook error: %s", e)
        return "ERR", 200

# --------------- تشغيل PTB في خيط خلفي + ضبط Webhook ---------------
async def _ensure_webhook():
    if not RENDER_URL:
        LOG.warning("RENDER_EXTERNAL_URL غير محدد؛ لن أضبط webhook تلقائياً.")
        return
    url = f"{RENDER_URL}/webhook/{WEBHOOK_SECRET}"
    try:
        await tg_app.bot.set_webhook(url=url, max_connections=40, allowed_updates=["message", "callback_query"])
        info = await tg_app.bot.get_webhook_info()
        LOG.info("Webhook set: %s | pending: %s", info.url, info.pending_update_count)
    except Exception as e:
        LOG.exception("set_webhook failed: %s", e)

def _ptb_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(tg_app.initialize())
    loop.run_until_complete(tg_app.start())
    loop.create_task(_ensure_webhook())
    LOG.info("PTB loop is running.")
    loop.run_forever()

_ptb_thread_started = False

# Flask 3.x: ما عاد فيه before_first_request -> نستخدم before_request مع فلاغ
@app.before_request
def _startup_once():
    global _ptb_thread_started
    if not _ptb_thread_started:
        threading.Thread(target=_ptb_loop, daemon=True, name="ptb-loop").start()
        _ptb_thread_started = True
        LOG.info("Started PTB background loop thread.")

# ملاحظة: أمر التشغيل في Render يجب أن يكون:
# gunicorn -w 1 -k gthread -b 0.0.0.0:$PORT app:app
