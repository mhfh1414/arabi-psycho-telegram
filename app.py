# app.py — عربي سايكو (Render + Telegram Webhook + OpenRouter)
# Python 3.11 | python-telegram-bot v21.x
# Proc command on Render:
# gunicorn -w 1 -k gthread -b 0.0.0.0:$PORT app:app

import os
import asyncio
import logging
import threading
from typing import List, Dict

import httpx
from flask import Flask, request

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, ContextTypes, filters
)

# ---------------- Logs ----------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("arabi-psycho")

# ---------------- ENV ----------------
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
PUBLIC_URL = (os.getenv("RENDER_EXTERNAL_URL") or "").rstrip("/")
WEBHOOK_PATH = "/webhook/secret"

AI_BASE_URL = (os.getenv("AI_BASE_URL") or "https://openrouter.ai/api/v1").rstrip("/")
AI_API_KEY  = os.getenv("AI_API_KEY", "")
AI_MODEL    = os.getenv("AI_MODEL", "google/gemini-flash-1.5")

if not BOT_TOKEN:
    raise RuntimeError("✖ TELEGRAM_BOT_TOKEN مفقود في Environment.")

# ---------------- Flask (for gunicorn) ----------------
app = Flask(__name__)

@app.get("/")
def health():
    return "Arabi Psycho OK"

# ---------------- Telegram Application ----------------
tg_app: Application = Application.builder().token(BOT_TOKEN).build()
_event_loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()

AI_SYSTEM_PROMPT = (
    "أنت «عربي سايكو»، مساعد نفسي عربي يعتمد مبادئ CBT.\n"
    "- تحدث بلطف وبالعربية المبسطة.\n"
    "- ساعد في تنظيم الأفكار وتمارين قصيرة.\n"
    "- لا تقدم تشخيصًا طبيًا أو أدوية. عند خطر فوري وجّه لطلب مساعدة عاجلة.\n"
    "- اختم بتلخيص قصير وخطوة عملية واحدة."
)

async def ai_complete(messages: List[Dict[str, str]]) -> str:
    """OpenRouter /chat/completions"""
    if not AI_API_KEY:
        return "(الذكاء الاصطناعي غير مفعّل: AI_API_KEY مفقود)"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": PUBLIC_URL or "https://render.com",
        "X-Title": "Arabi Psycho",
    }
    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 600,
    }
    url = f"{AI_BASE_URL}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        log.exception("AI error")
        return f"(تعذّر توليد الرد: {e})"

async def ai_respond(user_text: str, context: ContextTypes.DEFAULT_TYPE) -> str:
    hist = context.user_data.get("ai_history", [])
    hist = hist[-20:]
    convo = [{"role": "system", "content": AI_SYSTEM_PROMPT}] + hist + [
        {"role": "user", "content": user_text}
    ]
    reply = await ai_complete(convo)
    hist += [{"role": "user", "content": user_text}, {"role": "assistant", "content": reply}]
    context.user_data["ai_history"] = hist[-20:]
    return reply

# ---------------- Commands ----------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "مرحبًا! أنا **عربي سايكو**.\n"
        "• اكتب: عربي سايكو — لبدء جلسة الذكاء الاصطناعي.\n"
        "• اكتب: إنهاء — لإنهاء الجلسة.\n"
        "• اكتب: ping — لاختبار البوت."
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("استخدم /start ثم جرّب كلمة: عربي سايكو")

async def cmd_ai_diag(update: Update, context: ContextTypes.DEFAULT_TYPE):
    base_ok = "True" if AI_BASE_URL else "False"
    key_ok  = "True" if AI_API_KEY else "False"
    model   = AI_MODEL or "-"
    await update.message.reply_text(f"AI_BASE_URL set={base_ok} | KEY set={key_ok} | MODEL={model}")

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong ✅")

# ---------------- Messages Router ----------------
async def text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    # بدء/إنهاء جلسة AI
    if text.startswith("عربي سايكو"):
        context.user_data["ai_mode"] = True
        context.user_data["ai_history"] = []
        await update.message.reply_text(
            "بدأت جلسة **عربي سايكو**.\nاكتب شكواك الآن.\n(أرسل: إنهاء) للخروج."
        )
        return

    if text in ("إنهاء", "انهاء", "خروج", "◀️ إنهاء جلسة عربي سايكو"):
        context.user_data["ai_mode"] = False
        await update.message.reply_text("انتهت الجلسة. اكتب: عربي سايكو لبدء جلسة جديدة.")
        return

    # كلمة اختبار سريعة
    if text.lower() == "ping":
        await update.message.reply_text("pong ✅")
        return

    # لو الجلسة مفعّلة — رد بالذكاء الاصطناعي
    if context.user_data.get("ai_mode"):
        try:
            await update.effective_chat.send_action(ChatAction.TYPING)
        except Exception:
            pass
        reply = await ai_respond(text, context)
        await update.message.reply_text(reply)
        return

    # افتراضي
    await update.message.reply_text("اكتب /start ثم اكتب: عربي سايكو")

# ---------------- Register Handlers ----------------
def _register_handlers():
    tg_app.add_handler(CommandHandler("start", cmd_start))
    tg_app.add_handler(CommandHandler("help", cmd_help))
    tg_app.add_handler(CommandHandler("ai_diag", cmd_ai_diag))
    tg_app.add_handler(CommandHandler("ping", cmd_ping))
    tg_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_router))

_register_handlers()

# ---------------- Webhook Boot Thread ----------------
def _bot_loop():
    asyncio.set_event_loop(_event_loop)

    async def _startup():
        await tg_app.initialize()
        await tg_app.start()
        if PUBLIC_URL:
            hook_url = f"{PUBLIC_URL}{WEBHOOK_PATH}"
            await tg_app.bot.set_webhook(url=hook_url, drop_pending_updates=True)
            log.info(f"✓ Webhook set: {hook_url}")
        else:
            log.warning("RENDER_EXTERNAL_URL غير محدد؛ لن يتم تعيين Webhook.")

    _event_loop.run_until_complete(_startup())
    _event_loop.run_forever()

threading.Thread(target=_bot_loop, daemon=True).start()

# ---------------- Webhook endpoint ----------------
@app.post(WEBHOOK_PATH)
def webhook():
    """Receive Telegram updates and pass to PTB inside background loop."""
    try:
        data = request.get_json(force=True)
        update = Update.de_json(data, tg_app.bot)
        asyncio.run_coroutine_threadsafe(tg_app.process_update(update), _event_loop)
    except Exception as e:
        log.exception("webhook error: %s", e)
        return "error", 500
    return "ok"
