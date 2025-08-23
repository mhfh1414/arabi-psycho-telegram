# -*- coding: utf-8 -*-
# app.py — نسخة تعمل مع Flask + python-telegram-bot، وتعرض أزرار عربية

import os
import json
import logging
import asyncio
from typing import Optional

import httpx
from flask import Flask, request, abort

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# ===== تسجيل =====
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("app")

# ===== متغيرات البيئة =====
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
AI_BASE_URL   = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1")
AI_API_KEY    = os.getenv("AI_API_KEY", "")
AI_MODEL      = os.getenv("AI_MODEL", "openrouter/auto")

CONTACT_THERAPIST_URL   = os.getenv("CONTACT_THERAPIST_URL", "https://t.me/your_therapist")
CONTACT_PSYCHIATRIST_URL= os.getenv("CONTACT_PSYCHIATRIST_URL","https://t.me/your_psychiatrist")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN غير موجود في بيئة التشغيل")

# ===== تطبيق تيليجرام =====
app_tg = Application.builder().token(TELEGRAM_TOKEN).build()

def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("العلاج السلوكي المعرفي (CBT)", callback_data="cbt")],
        [InlineKeyboardButton("اختبارات نفسية", callback_data="tests")],
        [InlineKeyboardButton("اضطرابات الشخصية (DSM-5)", callback_data="pd")],
        [InlineKeyboardButton("تشخيص آلي مبدئي (DSM)", callback_data="ai")],
        [
            InlineKeyboardButton("أخصائي نفسي", url=CONTACT_THERAPIST_URL),
            InlineKeyboardButton("طبيب نفسي",   url=CONTACT_PSYCHIATRIST_URL),
        ],
    ])

def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع للقائمة", callback_data="back")]])

TXT_WELCOME = (
    "مرحبًا بك في *ArabiPsycho Bot* 👋\n\n"
    "اختر من القائمة أدناه:"
)
TXT_CBT = (
    "العلاج السلوكي المعرفي (CBT):\n"
    "- إعادة البناء المعرفي.\n- التعرّض المتدرّج.\n- تفعيل السلوكيات الإيجابية.\n\n"
    "تمرين سريع: اكتب فكرة مزعجة واحدة وفكرة بديلة أكثر توازنًا."
)
TXT_TESTS = (
    "اختبارات مبدئية (إرشادية فقط): PHQ9 / GAD7 / PCL5 / PERSONALITY\n"
    "اكتب اسم الاختبار لبدئه."
)
TXT_PD = (
    "اضطرابات الشخصية (DSM-5) — معلومات توعوية مختصرة.\n"
    "التشخيص الدقيق يحتاج مقابلة إكلينيكية."
)
TXT_AI_INFO = (
    "أرسل وصفًا لأعراضك وسأعطي تحليلًا مبدئيًا وفق DSM-5 (تثقيفيًا).\n"
    "لتفعيل الذكاء الاصطناعي ضع AI_API_KEY في المتغيرات."
)
TXT_FALLBACK = "استلمت رسالتك ✅\nاكتب /start لعرض القائمة."

async def ai_diagnose(prompt: str) -> str:
    if not AI_API_KEY:
        return "ميزة الذكاء الاصطناعي غير مفعّلة حاليًا (AI_API_KEY مفقود)."
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {AI_API_KEY}"},
                json={
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content":
                         "أنت مساعد نفسي عربي؛ قدّم تحليلًا مبدئيًا فقط وفق DSM-5 مع تنبيه أنه ليس تشخيصًا نهائيًا."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                },
            )
        data = r.json()
        if "choices" in data and data["choices"]:
            return data["choices"][0]["message"]["content"].strip()
        return f"تعذّر التوليد: {json.dumps(data)[:400]}..."
    except Exception as e:
        LOG.exception("AI error")
        return f"خطأ بالاتصال بمحرك الذكاء الاصطناعي: {e}"

# ===== Handlers =====
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    await update.effective_chat.send_message(
        TXT_WELCOME, reply_markup=main_menu_kb(), parse_mode="Markdown"
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_chat.send_message("اكتب /start لعرض القائمة.")

async def on_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not q:
        return
    await q.answer()
    if q.data == "cbt":
        await q.edit_message_text(TXT_CBT, reply_markup=back_kb())
    elif q.data == "tests":
        await q.edit_message_text(TXT_TESTS, reply_markup=back_kb())
    elif q.data == "pd":
        await q.edit_message_text(TXT_PD, reply_markup=back_kb())
    elif q.data == "ai":
        await q.edit_message_text(TXT_AI_INFO, reply_markup=back_kb())
    elif q.data == "back":
        await q.edit_message_text(TXT_WELCOME, reply_markup=main_menu_kb(), parse_mode="Markdown")

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    key = txt.upper().replace("-", "")
    if key in {"PHQ9", "GAD7", "PCL5", "PERSONALITY"}:
        await update.message.reply_text("سيتم إضافة نماذج مبسطة للاختبارات قريبًا. للقائمة: /start")
        return
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    reply = await ai_diagnose(txt)
    await update.message.reply_text(reply if reply else TXT_FALLBACK)

app_tg.add_handler(CommandHandler("start", cmd_start))
app_tg.add_handler(CommandHandler("help",  cmd_help))
app_tg.add_handler(CallbackQueryHandler(on_menu_callback))
app_tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

# ===== تشغيل تطبيق PTB مرة واحدة عند الإقلاع =====
def _start_ptb_once():
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(app_tg.initialize())
    loop.run_until_complete(app_tg.start())
    LOG.info("telegram ext Application started")

_start_ptb_once()

# ===== Flask + Webhook =====
server = Flask(__name__)

@server.get("/")
def health():
    return "OK"

@server.post("/webhook/secret")
def webhook():
    if request.method != "POST":
        abort(405)
    data = request.get_json(force=True, silent=True) or {}
    if not data:
        return "no-data", 200
    update = Update.de_json(data, app_tg.bot)
    asyncio.get_event_loop().create_task(app_tg.process_update(update))
    return "ok", 200

# نقطة دخول gunicorn
server: Flask = server
