# -*- coding: utf-8 -*-
import os, json, asyncio, logging
from flask import Flask, request, abort

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters, ContextTypes
)

logging.basicConfig(level=logging.INFO)
LOG = logging.getLogger("app")

# ====== الإعدادات من المتغيرات ======
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN مفقود في Environment")

# ====== بوت تيليجرام ======
app_tg = Application.builder().token(TELEGRAM_TOKEN).concurrent_updates(True).build()

# ---- أوامر تجريبية أساسية ----
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "أنا شغّال ✅\n"
        "جرّب /ping\n"
        "أو اكتب أي رسالة وسيتم الرد عليها."
    )

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("pong ✅")

# نصوص عادية (نردّ فورًا – بدون ذكاء اصطناعي مؤقتًا لضمان التشغيل)
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.effective_chat.send_action(ChatAction.TYPING)
    except Exception:
        pass
    await update.message.reply_text(f"استلمت: {update.message.text}")

# تسجيل الهاندلرز
def register_handlers() -> None:
    app_tg.add_handler(CommandHandler("start", cmd_start))
    app_tg.add_handler(CommandHandler("ping",  cmd_ping))
    app_tg.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))

# نهيّئ ونشغّل التطبيق (مرّة واحدة عند الإقلاع)
register_handlers()
asyncio.run(app_tg.initialize())
asyncio.run(app_tg.start())

# ====== خادم Flask للويبهوك ======
server = Flask(__name__)

@server.get("/")
def health():
    return "Arabi Psycho OK"

@server.post("/webhook/secret")
def webhook():
    try:
        data = request.get_json(force=True, silent=True) or {}
        print(">>> incoming update:", json.dumps(data, ensure_ascii=False))
        update = Update.de_json(data, app_tg.bot)
        # نعالج التحديث بشكل متزامن
        asyncio.run(app_tg.process_update(update))
    except Exception as e:
        LOG.exception("webhook error")
        abort(500)
    return "OK"
