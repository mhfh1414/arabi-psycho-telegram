# -*- coding: utf-8 -*-
# app.py — نسخة نظيفة مع أزرار وقوائم، وتعمل Webhook على Render

import os
import json
import logging
import asyncio
from typing import Optional

import httpx
from flask import Flask, request, abort

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
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

# ====== تسجيل ======
logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("app")

# ====== متغيرات البيئة ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
EXTERNAL_URL = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_MODEL = os.getenv("AI_MODEL", "openrouter/auto")

CONTACT_THERAPIST_URL = os.getenv("CONTACT_THERAPIST_URL", "https://t.me/your_therapist")
CONTACT_PSYCHIATRIST_URL = os.getenv("CONTACT_PSYCHIATRIST_URL", "https://t.me/your_psychiatrist")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN غير موجود في بيئة التشغيل")

# ====== تطبيق التيليجرام ======
app_tg = Application.builder().token(TELEGRAM_TOKEN).build()

# ====== لوحات الأزرار ======
def main_menu_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("العلاج السلوكي المعرفي (CBT)", callback_data="cbt")],
        [InlineKeyboardButton("اختبارات نفسية", callback_data="tests")],
        [InlineKeyboardButton("اضطرابات الشخصية (DSM-5)", callback_data="pd")],
        [InlineKeyboardButton("تشخيص آلي مبدئي (DSM)", callback_data="ai")],
        [
            InlineKeyboardButton("أخصائي نفسي", url=CONTACT_THERAPIST_URL),
            InlineKeyboardButton("طبيب نفسي", url=CONTACT_PSYCHIATRIST_URL),
        ],
    ]
    return InlineKeyboardMarkup(rows)

def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ رجوع للقائمة", callback_data="back")]])

# ====== نصوص ثابتة (كلها داخل سلاسل نصية) ======
TXT_WELCOME = (
    "مرحبًا بك في *ArabiPsycho Bot* 👋\n\n"
    "اختر من القائمة أدناه:"
)

TXT_CBT = (
    "العلاج السلوكي المعرفي (CBT):\n"
    "- إعادة البناء المعرفي (تحديد الأفكار المشوهة واستبدالها).\n"
    "- تدرّج التعرّض للمواقف المثيرة للقلق.\n"
    "- تفعيل السلوكيات الإيجابية والمتوازنة.\n\n"
    "ابدأ بخطوة بسيطة اليوم: سجّل فكرة مزعجة واحدة، ثم اسأل نفسك:\n"
    "1) ما الدليل مع/ضد هذه الفكرة؟\n"
    "2) ما الفكرة البديلة المتوازنة؟"
)

TXT_TESTS = (
    "اختبارات نفسية مبدئية (للاسترشاد فقط وليست تشخيصًا نهائيًا):\n"
    "• PHQ-9: مؤشرات الاكتئاب.\n"
    "• GAD-7: مؤشرات القلق.\n"
    "• PCL-5: مؤشرات اضطراب ما بعد الصدمة.\n"
    "• نمط الشخصية (مؤشرات عامة).\n\n"
    "اكتب: PHQ9 أو GAD7 أو PCL5 أو PERSONALITY لبدء أسئلة قصيرة."
)

TXT_PD = (
    "اضطرابات الشخصية (DSM-5) — معلومات توعوية مختصرة:\n"
    "• الشخصية الحدّية، النرجسية، التجنبية، المعادية للمجتمع… إلخ.\n"
    "التشخيص الدقيق يحتاج مقابلة إكلينيكية. هذا البوت للتثقيف ومؤشرات أولية فقط."
)

TXT_AI_INFO = (
    "التشخيص الآلي المبدئي (DSM):\n"
    "أرسل وصفًا للأعراض (المدة، الشدة، المواقف)، وسأقدّم تحليلًا أوليًا "
    "مبنيًا على معايير DSM-5 *بغرض التثقيف فقط*.\n"
    "— إذا ظهر رد بسيط فقط، فعّل مفتاح API للخدمة الذكية في المتغيرات (AI_API_KEY)."
)

TXT_FALLBACK = (
    "استلمت رسالتك ✅\n"
    "للقائمة الرئيسية: /start\n"
    "ولتحليل آلي مبدئي، فعّل AI_API_KEY أو أرسل اختبارات: PHQ9 / GAD7 / PCL5."
)

# ====== ذكاء اصطناعي (اختياري) ======
async def ai_diagnose(prompt: str) -> str:
    if not AI_API_KEY:
        return "ميزة الذكاء الاصطناعي غير مفعّلة حاليًا (لا يوجد AI_API_KEY)."

    system = (
        "أنت مساعد نفسي عربي. قدّم تحليلًا مبدئيًا فقط وفق DSM-5 مع تنبيه واضح "
        "أنه ليس تشخيصًا نهائيًا. اطلب استشارة مختص عند الحاجة."
    )
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{AI_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {AI_API_KEY}"},
                json={
                    "model": AI_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                },
            )
        data = resp.json()
        if "choices" in data and data["choices"]:
            return data["choices"][0]["message"]["content"].strip()
        return f"تعذّر توليد رد ذكي. الاستجابة: {json.dumps(data)[:400]}..."
    except Exception as e:
        LOG.exception("AI error")
        return f"تعذّر الاتصال بمحرك الذكاء الاصطناعي: {e}"

# ====== Handlers ======
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await context.bot.send_chat_action(update.effective_chat.id, ChatAction.TYPING)
    await update.effective_chat.send_message(
        TXT_WELCOME, reply_markup=main_menu_kb(), parse_mode="Markdown"
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_chat.send_message("اكتب /start لعرض القائمة.")

async def on_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q:
        return
    await q.answer()
    data = q.data

    if data == "cbt":
        await q.edit_message_text(TXT_CBT, reply_markup=back_kb())
    elif data == "tests":
        await q.edit_message_text(TXT_TESTS, reply_markup=back_kb())
    elif data == "pd":
        await q.edit_message_text(TXT_PD, reply_markup=back_kb())
    elif data == "ai":
        await q.edit_message_text(TXT_AI_INFO, reply_markup=back_kb())
    elif data == "back":
        await q.edit_message_text(TXT_WELCOME, reply_markup=main_menu_kb(), parse_mode="Markdown")

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.message.text or "").strip()
    chat_id = update.effective_chat.id

    # اختبارات مختصرة Placeholder
    key = text.upper().replace("-", "").replace("-", "")
    if key in {"PHQ9", "GAD7", "PCL5", "PERSONALITY"}:
        await update.message.reply_text(
            "تم تسجيل طلب الاختبار. (نموذج مبسّط سيُضاف لاحقًا). للقائمة: /start"
        )
        return

    # تحليل آلي مبدئي
    await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
    reply = await ai_diagnose(text)
    await update.message.reply_text(reply)

# ربط الهاندلرز
app_tg.add_handler(CommandHandler("start", cmd_start))
app_tg.add_handler(CommandHandler("help", cmd_help))
app_tg.add_handler(CallbackQueryHandler(on_menu_callback))
app_tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

# ====== Flask + Webhook ======
server = Flask(__name__)

@server.get("/")
def health() -> str:
    return "OK"

@server.post("/webhook/secret")
def receive_update():
    if request.method != "POST":
        abort(405)

    try:
        data = request.get_json(force=True, silent=True) or {}
    except Exception:
        data = {}

    if not data:
        return "no-data", 200

    update = Update.de_json(data, app_tg.bot)
    # عالج التحديث داخل لوب asyncio الخاص بالتطبيق
    asyncio.get_event_loop().create_task(app_tg.process_update(update))
    return "ok", 200

# نقطة تشغيل لـ gunicorn
server: Flask = server
